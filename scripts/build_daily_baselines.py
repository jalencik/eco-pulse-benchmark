"""Task N baseline ladder scored at DAILY resolution, comparable to the models.

WHY THIS FILE EXISTS
--------------------
`t3_02_task_n_baselines_hourly.csv` scores the spatial baselines on **hourly** observations
(n = 8307, 6394, 7900 ... per station), while `t5_02_loco_tuned.csv` scores the learned
models on **daily** means (n = 345, 263, 334 ...). The manuscript then placed the two in one
ladder and reported the gap as the model's margin.

That comparison is invalid in the model's favour. Daily averaging removes within-day
variance, so an RMSE computed on hourly values is structurally larger than one computed on
daily means of the same data -- no model quality is involved. The giveaway is already in the
repository: `t3_02`'s own `n_days` column reproduces the models' `n` exactly.

This script re-scores every Task N baseline on the daily target, using:

  * the SAME target function the models use (`daily_target`, local calendar, >=18 hours), and
  * the SAME evaluation rows the models are scored on (the (station_id, date) pairs banked in
    `t6_01_predictions_task_n.csv`),

so the resulting ladder is directly comparable and the reported margin is real. The hourly
table is retained -- it is the honest way to describe hourly nowcasting -- but it is no longer
compared against daily model scores.

Constant predictors are added that the hourly table cannot express, and the LEGALITY of each
is recorded in a `legal` column. `train_global_mean` and `train_global_median` are fitted on
training cities over train+validation dates only. `oracle_city_constant` -- the held-out
city's own test-block mean -- is NOT legal: under leave-city-out that city contributes no
training label anywhere in the record, so no deployable method could compute it. It is kept
as a diagnostic floor (how much error is pure within-city day-to-day variance) and must never
be reported as a baseline the model loses to. An earlier version of this script did exactly
that, and the manuscript wrongly reported the model as beaten by a constant.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecopulse_ca.eval.metrics import regression_metrics
from ecopulse_ca.eval.runner import blocks_from, run_task_n
from ecopulse_ca.models.feature_table import CITY_TZ, daily_target

TABLES = ROOT / "paper" / "tables"
OUT = TABLES / "t3_06_task_n_baselines_daily.csv"


def main() -> int:
    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
    blocks = blocks_from(splits)
    city_of = {str(s["station_id"]): s["city"] for s in splits["stations"]}
    tz_of = {str(s["station_id"]): CITY_TZ[s["city"]] for s in splits["stations"]}

    panel = pd.read_parquet(ROOT / "data/interim/benchmark_panel.parquet")
    panel.columns = [str(c) for c in panel.columns]

    # The exact rows the models are scored on. Anchoring to these makes the comparison
    # row-for-row identical rather than merely "also daily".
    pred = pd.read_csv(TABLES / "t6_01_predictions_task_n.csv", dtype={"station_id": str})
    pred["date"] = pd.to_datetime(pred["date"])
    eval_rows = pred[["station_id", "date", "fold", "pm25"]].copy()

    # Hourly baseline predictions, then aggregated to the local-calendar daily mean.
    hourly = run_task_n(panel, splits, blocks, tz_of, seed=0, return_predictions=True)

    rows = []
    for (fold, station, model), g in hourly.groupby(["held_out_city", "station_id", "model"]):
        s = g.set_index("timestamp")["prediction"].dropna()
        if s.empty:
            continue
        local = s.tz_convert(CITY_TZ[city_of[str(station)]])
        ser = pd.Series(local.to_numpy(), index=local.index)
        grouped = ser.groupby(ser.index.date)
        # Same >=18-hour completeness rule as the target, so a day is not scored off 3 hours.
        agg = grouped.mean().where(grouped.count() >= 18).dropna()
        daily = pd.DataFrame(
            {
                "station_id": str(station),
                "date": pd.to_datetime(list(agg.index)),
                "pred": agg.to_numpy(),
            }
        )
        j = eval_rows.merge(daily, on=["station_id", "date"], how="inner").dropna()
        if len(j) < 30:
            continue
        m = regression_metrics(j.pm25, j.pred)
        rows.append(
            {
                "task": "N",
                "fold": fold,
                "held_out_city": fold,
                "station_id": str(station),
                "model": model,
                # Legal for NOWCASTING: these read concurrent observations from TRAINING
                # cities only, which is precisely the deployment case -- a monitoring network
                # exists elsewhere and a value is wanted where it does not.
                "legal": True,
                **m.as_dict(),
            }
        )

    # ---- constant predictors --------------------------------------------------------
    # Two of these are LEGAL and one is an ORACLE. The distinction is load-bearing and was
    # got wrong once: `oracle_city_constant` is the held-out city's own TEST-BLOCK mean, which
    # under leave-city-out cannot be known at prediction time, because the held-out city
    # contributes no training label anywhere in the record. It is retained as a DIAGNOSTIC --
    # the irreducible floor for any constant predictor, i.e. how much of the error is pure
    # within-city day-to-day variance -- and must never be presented as a baseline the model
    # "loses to". An earlier version of this script did exactly that, and the manuscript
    # reported the model as losing to a constant that no deployable method could compute.
    tg_all = daily_target(panel, city_of)
    tg_all["date"] = pd.to_datetime(tg_all["date"])
    train_end = pd.Timestamp(blocks.val[1]).tz_localize(None)

    for fold, g in eval_rows.groupby("fold"):
        # LEGAL: fitted only on training cities, only on train+validation dates.
        tr = tg_all[(tg_all.city != fold) & (tg_all.date <= train_end)]
        consts = {
            "train_global_mean": float(tr.pm25.mean()),
            "train_global_median": float(tr.pm25.median()),
            "oracle_city_constant": float(g.pm25.mean()),  # ORACLE -- diagnostic only
        }
        for name, const in consts.items():
            for station, gs in g.groupby("station_id"):
                m = regression_metrics(gs.pm25, pd.Series(const, index=gs.index))
                rows.append(
                    {
                        "task": "N",
                        "fold": fold,
                        "held_out_city": fold,
                        "station_id": str(station),
                        "model": name,
                        "legal": name != "oracle_city_constant",
                        **m.as_dict(),
                    }
                )

    out = pd.DataFrame(rows).sort_values(["fold", "model", "station_id"])
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(out)} rows)")

    print("\nfold-mean RMSE by model (daily, model-comparable rows):")
    fm = out.groupby("model").apply(
        lambda g: g.groupby("fold").rmse.mean().mean(), include_groups=False
    )
    for k, v in fm.sort_values().items():
        print(f"  {k:<24} {v:8.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
