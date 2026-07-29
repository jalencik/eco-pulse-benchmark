"""Phase 3: run the credential-free baseline ladder and emit the results tables.

Run:  python scripts/run_baselines.py

Seeds are executed, not assumed. Every model on this ladder is deterministic, so the five
seeds must produce bit-identical results -- and that is *verified* rather than skipped,
because "deterministic" is a claim about the code that can be wrong. Where it holds, the
tables say `(det.)` instead of `± 0.000`: a printed zero implies five independent runs
happened to agree, which would be a remarkable finding rather than an arithmetic certainty.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from ecopulse_ca.eval.diebold_mariano import (
    lag_sensitivity,
    nowcast_truncation_lag,
    pairwise_dm,
)
from ecopulse_ca.eval.metrics import WHO_2021_PM25_24H
from ecopulse_ca.eval.runner import (
    FORECASTERS,
    HORIZONS,
    NOWCASTERS,
    Blocks,
    blocks_from,
    forecast_batch,
    load_splits,
    run_task_f,
    run_task_n,
    window,
)
from ecopulse_ca.models.base import StationMeta

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "paper" / "tables"
PANEL = ROOT / "data" / "interim" / "benchmark_panel.parquet"
SEEDS = [0, 1, 2, 3, 4]


def load_context():
    splits = load_splits()
    panel = pd.read_parquet(PANEL)
    panel.columns = [str(c) for c in panel.columns]
    blocks = blocks_from(splits)
    census = pd.read_csv(
        ROOT / "data" / "interim" / "station_census.csv", keep_default_na=False, na_values=[""]
    )
    census["location_id"] = census["location_id"].astype(str)
    tz_raw = dict(zip(census.location_id, census.timezone, strict=False))
    city_tz = {
        "Bishkek": "Asia/Bishkek", "Ashgabat": "Asia/Ashgabat",
        "Almaty": "Asia/Almaty", "Tashkent": "Asia/Tashkent",
        "Dushanbe": "Asia/Dushanbe", "Khujand": "Asia/Dushanbe",
    }
    tz_of = {s["station_id"]: tz_raw.get(s["station_id"]) or city_tz.get(s["city"])
             for s in splits["stations"]}
    city_of = {s["station_id"]: s["city"] for s in splits["stations"]}
    return splits, panel, blocks, tz_of, city_of


def dm_task_f(panel, blocks: Blocks, city_of) -> pd.DataFrame:
    rows = []
    for sid in panel.columns:
        y = panel[sid]
        train = window(y, blocks.train)
        if train.notna().sum() < 24 * 30:
            continue
        for h in HORIZONS:
            obs = window(y, blocks.test)
            preds = {
                n: window(forecast_batch(y, n, h, train), blocks.test) for n in FORECASTERS
            }
            d = pairwise_dm(obs, preds, horizon_hours=h)
            d.insert(0, "horizon_h", h)
            d.insert(0, "city", city_of.get(sid, sid))
            d.insert(0, "station_id", sid)
            rows.append(d)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def dm_task_n(
    panel, splits, blocks: Blocks, sensitivity: list | None = None
) -> pd.DataFrame:
    import numpy as np

    sensitivity = [] if sensitivity is None else sensitivity

    meta = {
        s["station_id"]: StationMeta(s["station_id"], s["latitude"], s["longitude"],
                                     s["city"], True)
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

        fitted = {}
        for name, ctor in NOWCASTERS.items():
            m = ctor(0) if name == "idw_k5_p2" else ctor(seed=0)
            fitted[name] = m.fit(train_panel, meta)

        for held in held_ids:
            obs = window(panel[held], blocks.test)
            target = meta[held]
            preds = {}
            for name, m in fitted.items():
                preds[name] = pd.Series(
                    [m.predict(test_train.loc[ts], target) if ts in test_train.index else np.nan
                     for ts in obs.index],
                    index=obs.index, dtype=float,
                )
            n_obs = int(obs.notna().sum())
            d = pairwise_dm(
                obs, preds, truncation_lag=nowcast_truncation_lag(n_obs)
            )
            d.insert(0, "station_id", held)
            d.insert(0, "held_out_city", fold["held_out_city"])
            rows.append(d)

            # Robustness: a verdict that flips with the truncation lag is not a verdict.
            names = sorted(preds)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    s = lag_sensitivity(obs, preds[a], preds[b])
                    s.insert(0, "model_b", b)
                    s.insert(0, "model_a", a)
                    s.insert(0, "held_out_city", fold["held_out_city"])
                    sensitivity.append(s)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    splits, panel, blocks, tz_of, city_of = load_context()
    print(f"benchmark v{splits['benchmark_version']}  "
          f"test {blocks.test[0].date()} .. {blocks.test[1].date()}")
    print(f"stations {len(panel.columns)}  cities {len(set(city_of.values()))}\n")

    # ---- Task F -------------------------------------------------------------------
    print("Task F (forecasting) ...", flush=True)
    f_seeds = []
    for seed in SEEDS:
        df = run_task_f(panel, blocks, tz_of)
        df["seed"] = seed
        f_seeds.append(df)
    task_f = pd.concat(f_seeds, ignore_index=True)

    key = ["station_id", "horizon_h", "model"]
    spread = task_f.groupby(key)["rmse"].std(ddof=0).fillna(0.0)
    f_deterministic = bool((spread < 1e-12).all())
    print(f"  seed variance across {len(SEEDS)} seeds: "
          f"{'ZERO (deterministic, as declared)' if f_deterministic else 'NON-ZERO'}")

    task_f_agg = task_f[task_f.seed == 0].drop(columns="seed").copy()
    task_f_agg["city"] = task_f_agg.station_id.map(city_of)

    # ---- Task N -------------------------------------------------------------------
    print("Task N (leave-city-out nowcasting) ...", flush=True)
    n_seeds = [run_task_n(panel, splits, blocks, tz_of, seed=s) for s in SEEDS]
    task_n = pd.concat(n_seeds, ignore_index=True)
    nkey = ["fold", "station_id", "model"]
    nspread = task_n.groupby(nkey)["rmse"].std(ddof=0).fillna(0.0)
    n_deterministic = bool((nspread < 1e-12).all())
    print(f"  seed variance across {len(SEEDS)} seeds: "
          f"{'ZERO (deterministic, as declared)' if n_deterministic else 'NON-ZERO'}")
    task_n_agg = task_n[task_n.seed == 0].drop(columns="seed")

    # ---- DM tests -----------------------------------------------------------------
    print("Diebold-Mariano ...", flush=True)
    dm_f = dm_task_f(panel, blocks, city_of)
    sens: list = []
    dm_n = dm_task_n(panel, splits, blocks, sens)

    task_f_agg.to_csv(TABLES / "task_f_baselines.csv", index=False)
    task_n_agg.to_csv(TABLES / "task_n_baselines.csv", index=False)
    dm_f.to_csv(TABLES / "dm_task_f.csv", index=False)
    dm_n.to_csv(TABLES / "dm_task_n.csv", index=False)
    if sens:
        pd.concat(sens, ignore_index=True).to_csv(
            TABLES / "dm_lag_sensitivity.csv", index=False
        )

    # ---- Report -------------------------------------------------------------------
    det_f = "(det.)" if f_deterministic else "± see csv"
    det_n = "(det.)" if n_deterministic else "± see csv"

    print("\n" + "=" * 86)
    print(f"TASK F -- FORECASTING at monitored stations   [5 seeds, {det_f}]")
    print("=" * 86)
    pv = task_f_agg.pivot_table(index="model", columns="horizon_h",
                                values=["rmse", "mae", "f1_exceed"], aggfunc="mean")
    print(pv.round(3).to_string())

    print("\n" + "=" * 86)
    print(f"TASK N -- NOWCASTING, leave-city-out          [5 seeds, {det_n}]")
    print("=" * 86)
    pn = task_n_agg.groupby("model").agg(
        rmse=("rmse", "mean"), mae=("mae", "mean"), r2=("r2", "mean"),
        bias=("bias", "mean"), f1_exceed=("f1_exceed", "mean"), n=("n", "sum"),
    )
    print(pn.round(3).to_string())

    print("\nper held-out city (RMSE):")
    print(task_n_agg.pivot_table(index="held_out_city", columns="model",
                                 values="rmse", aggfunc="mean").round(2).to_string())

    if not dm_f.empty:
        sig = dm_f[dm_f.significant_at_05]
        print(f"\nDM Task F: {len(sig)}/{len(dm_f)} comparisons significant at p<0.05")
    if not dm_n.empty:
        sig = dm_n[dm_n.significant_at_05]
        print(f"DM Task N: {len(sig)}/{len(dm_n)} comparisons significant at p<0.05")

    print(f"\nWHO 2021 24h guideline used for exceedance: {WHO_2021_PM25_24H} ug/m3")
    print(f"tables -> {TABLES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
