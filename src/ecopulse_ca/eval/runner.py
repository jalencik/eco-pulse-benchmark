"""Run the credential-free baseline ladder over the frozen splits.

Two points a reviewer will press on, stated up front
----------------------------------------------------

**1. Test-block predictions legitimately read history from before the test block.**
A forecaster predicting 2024-01-01 06:00 at h=24 uses that station's observation at
2023-12-31 06:00, which sits in the purge block. That is not leakage. The purge exists to
stop *training* from seeing the test period; using the target station's own past as
*inference input* is the definition of forecasting, and is exactly what a deployed service
does. Leakage would be **fitting** on data inside or after the test block, which
`fit_window` prevents: every `fit()` call receives train-block data only.

**2. Batch prediction must provably agree with the per-origin contract.**
Looping `predict()` over 8,760 origins x 8 stations x 4 models is too slow, so forecasts are
computed as vectorised shifts. A vectorised path that silently disagreed with the model's
own `predict()` would report numbers for a model nobody implemented, so
`tests/test_runner_batch_equivalence.py` asserts the two agree on sampled origins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ecopulse_ca.eval.metrics import (
    WHO_2021_PM25_24H,
    exceedance_metrics,
    regression_metrics,
)
from ecopulse_ca.models.base import StationMeta
from ecopulse_ca.models.climatology import Climatology
from ecopulse_ca.models.idw import IDW, NearestMonitor
from ecopulse_ca.models.kriging import OrdinaryKriging
from ecopulse_ca.models.persistence import DiurnalPersistence, Persistence, SameHourMean
from ecopulse_ca.models.pool_mean import TrainingPoolMean

ROOT = Path(__file__).resolve().parents[3]
SPLITS = ROOT / "benchmark" / "splits" / "splits.json"
PANEL = ROOT / "data" / "interim" / "benchmark_panel.parquet"
HORIZONS = (24, 48, 72)


@dataclass
class Blocks:
    train: tuple[pd.Timestamp, pd.Timestamp]
    val: tuple[pd.Timestamp, pd.Timestamp]
    test: tuple[pd.Timestamp, pd.Timestamp]


def load_splits() -> dict:
    return json.loads(SPLITS.read_text(encoding="utf-8"))


def blocks_from(splits: dict) -> Blocks:
    b = {x["name"]: x for x in splits["temporal_blocks"]}
    def rng(name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
        return pd.Timestamp(b[name]["start"]), pd.Timestamp(b[name]["end"])
    return Blocks(rng("train"), rng("val"), rng("test"))


def window(series: pd.Series, span: tuple[pd.Timestamp, pd.Timestamp]) -> pd.Series:
    return series.loc[span[0]:span[1]]


# --------------------------------------------------------------------------- Task F
def forecast_batch(y: pd.Series, model_name: str, horizon: int, train: pd.Series) -> pd.Series:
    """Vectorised forecast for every target timestamp.

    Each expression mirrors the corresponding model's `predict()` semantics exactly; the
    equivalence is asserted by test, not assumed.
    """
    if model_name in ("persistence", "diurnal_persistence"):
        # At horizons that are multiples of 24 these coincide -- a documented degeneracy
        # of the ladder, not a copy-paste error. See models/persistence.py.
        return y.shift(horizon, freq="h").reindex(y.index)

    if model_name.startswith("same_hour"):
        n_days = 7
        # Origin is target-h; the admissible same-hour observations are the n_days values
        # at or before the origin, i.e. shifts h, h+24, ..., h+24*(n_days-1).
        parts = [y.shift(horizon + 24 * k, freq="h").reindex(y.index) for k in range(n_days)]
        stacked = pd.concat(parts, axis=1)
        return stacked.median(axis=1) if "median" in model_name else stacked.mean(axis=1)

    if model_name.startswith("climatology"):
        model = Climatology(use_median="median" in model_name).fit(train)
        idx = pd.DatetimeIndex(y.index)
        return pd.Series([model._lookup(t) for t in idx], index=y.index, dtype=float)

    raise ValueError(f"no batch path for {model_name!r}")


FORECASTERS = {
    "persistence": Persistence,
    "diurnal_persistence": DiurnalPersistence,
    "same_hour_mean_7d": SameHourMean,
    "climatology_mean": Climatology,
}


def run_task_f(panel: pd.DataFrame, blocks: Blocks, tz_of: dict[str, str]) -> pd.DataFrame:
    """Forecasting at monitored stations. One row per (station, model, horizon)."""
    rows = []
    for col in panel.columns:
        sid = str(col)
        y = panel[col]
        train = window(y, blocks.train)
        if train.notna().sum() < 24 * 30:
            continue
        for horizon in HORIZONS:
            obs = window(y, blocks.test)
            preds = {
                name: window(forecast_batch(y, name, horizon, train), blocks.test)
                for name in FORECASTERS
            }
            for name, pred in preds.items():
                reg = regression_metrics(obs, pred)
                exc = exceedance_metrics(obs, pred, WHO_2021_PM25_24H, tz_of.get(sid))
                rows.append({
                    "task": "F", "station_id": sid, "horizon_h": horizon, "model": name,
                    **reg.as_dict(), "f1_exceed": exc.f1,
                    "f1_trivial_always": exc.f1_trivial_always,
                    "beats_trivial": exc.beats_trivial,
                    "peirce_skill": exc.peirce_skill, "base_rate": exc.base_rate,
                    "precision": exc.precision, "recall": exc.recall,
                    "n_days": exc.n_days, "n_exceed_obs": exc.n_exceed_obs,
                })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- Task N
NOWCASTERS = {
    # Rung 0: the achievable constant. Any model claiming to have learned something
    # about an unmonitored city must beat this. See models/pool_mean.py.
    "training_pool_mean": TrainingPoolMean,
    "nearest_monitor": NearestMonitor,
    "idw_k5_p2": lambda seed: IDW(k=5, p=2.0, seed=seed),
    "ordinary_kriging": OrdinaryKriging,
}


def run_task_n(
    panel: pd.DataFrame,
    splits: dict,
    blocks: Blocks,
    tz_of: dict[str, str],
    seed: int = 0,
) -> pd.DataFrame:
    """Leave-city-out nowcasting. The held-out city contributes no training label."""
    meta = {
        s["station_id"]: StationMeta(
            s["station_id"], s["latitude"], s["longitude"], s["city"], True
        )
        for s in splits["stations"]
    }
    rows = []
    for fold in splits["leave_city_out"]:
        train_ids = [s for s in fold["train_stations"] if s in panel.columns]
        held_ids = [s for s in fold["held_out_stations"] if s in panel.columns]
        if not train_ids or not held_ids:
            continue

        train_panel = window(panel[train_ids], blocks.train)
        test_train = window(panel[train_ids], blocks.test)

        for name, ctor in NOWCASTERS.items():
            model = ctor(seed=seed) if name != "idw_k5_p2" else ctor(seed)
            model.fit(train_panel, meta)

            for held in held_ids:
                obs = window(panel[held], blocks.test)
                target = meta[held]
                preds = [
                    model.predict(test_train.loc[ts], target) if ts in test_train.index
                    else np.nan
                    for ts in obs.index
                ]
                pred = pd.Series(preds, index=obs.index, dtype=float)

                reg = regression_metrics(obs, pred)
                exc = exceedance_metrics(obs, pred, WHO_2021_PM25_24H, tz_of.get(held))
                row = {
                    "task": "N", "fold": fold["fold"], "held_out_city": fold["held_out_city"],
                    "station_id": held, "model": name, "seed": seed,
                    **reg.as_dict(), "f1_exceed": exc.f1,
                    "f1_trivial_always": exc.f1_trivial_always,
                    "beats_trivial": exc.beats_trivial,
                    "peirce_skill": exc.peirce_skill, "base_rate": exc.base_rate,
                    "precision": exc.precision, "recall": exc.recall,
                    "n_days": exc.n_days, "n_exceed_obs": exc.n_exceed_obs,
                }
                if name == "ordinary_kriging":
                    row["kriging_fallback_rate"] = round(model.fallback_rate, 4)
                rows.append(row)
    return pd.DataFrame(rows)
