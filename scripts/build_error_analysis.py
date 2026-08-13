"""Error analysis, extreme-pollution performance and bias decomposition.

REPORTING, NOT SELECTION
------------------------
This script reads the FROZEN test-block predictions and describes how the final model
behaves. It chooses nothing: no threshold, feature, hyperparameter or model here feeds back
into the configuration, which was frozen before test was ever scored. That distinction is the
reason it is legitimate to look at test data at all -- describing a frozen model's errors is
reporting; changing the model in response would be tuning on test.

The exceedance thresholds are the WHO 2021 24-hour guideline (15 ug/m3) and its multiples,
fixed by an external standard rather than derived from the data.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = ROOT / "paper" / "tables"
WHO_24H = 15.0


def metrics(y: pd.Series, p: pd.Series) -> dict:
    e = p - y
    ss_res = float((e**2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "n": int(len(y)),
        "rmse": float(np.sqrt(np.mean(e**2))),
        "mae": float(np.mean(np.abs(e))),
        "bias": float(e.mean()),
        "median_bias": float(e.median()),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
    }


def main() -> int:
    pred = pd.read_csv(T / "t6_01_predictions_task_n.csv", dtype={"station_id": str},
                       parse_dates=["date"])
    census = pd.read_csv(ROOT / "data/interim/station_census.csv", dtype={"location_id": str},
                         keep_default_na=False, na_values=[""])
    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
    grade = {}
    low = set(census.loc[~census.is_monitor.astype(str).eq("True"), "location_id"])
    for s in splits["stations"]:
        grade[s["city"]] = grade.get(s["city"], "reference")
        if str(s["station_id"]) in low:
            grade[s["city"]] = "low-cost"

    # ---- per-fold -------------------------------------------------------------------
    rows = []
    for fold, g in pred.groupby("fold"):
        m = metrics(g.pm25, g.lgbm)
        mc = metrics(g.pm25, g.pooled)
        rows.append({"fold": fold, "instrument_grade": grade.get(fold, "?"), **m,
                     "cams_rmse": mc["rmse"], "beats_cams": m["rmse"] < mc["rmse"],
                     "obs_mean": float(g.pm25.mean()), "obs_sd": float(g.pm25.std()),
                     "exceed_rate": float((g.pm25 > WHO_24H).mean())})
    per_fold = pd.DataFrame(rows).sort_values("rmse")
    per_fold.to_csv(T / "t7_01_error_analysis_by_fold.csv", index=False)

    # ---- concentration regime (thresholds fixed by the WHO guideline) ----------------
    bands = [("clean (<= 1x WHO)", 0, WHO_24H), ("moderate (1-3x)", WHO_24H, 3 * WHO_24H),
             ("high (3-6x)", 3 * WHO_24H, 6 * WHO_24H), ("extreme (> 6x)", 6 * WHO_24H, np.inf)]
    rows = []
    for label, lo, hi in bands:
        sub = pred[(pred.pm25 > lo) & (pred.pm25 <= hi)]
        if len(sub) < 10:
            continue
        m = metrics(sub.pm25, sub.lgbm)
        mc = metrics(sub.pm25, sub.pooled)
        rows.append({"band": label, "lo": lo, "hi": hi if np.isfinite(hi) else "", **m,
                     "cams_rmse": mc["rmse"], "cams_bias": mc["bias"],
                     "share_of_rows": float(len(sub) / len(pred))})
    bands_df = pd.DataFrame(rows)
    bands_df.to_csv(T / "t7_02_error_by_concentration.csv", index=False)

    # ---- seasonal -------------------------------------------------------------------
    pred["season"] = pred.date.dt.month.map(
        {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
         6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"})
    rows = [{"season": s, **metrics(g.pm25, g.lgbm), "obs_mean": float(g.pm25.mean())}
            for s, g in pred.groupby("season")]
    pd.DataFrame(rows).to_csv(T / "t7_03_error_by_season.csv", index=False)

    print("=== PER-FOLD ERROR ANALYSIS (frozen test block) ===")
    cols = ["fold", "instrument_grade", "n", "rmse", "mae", "bias", "r2", "cams_rmse",
            "beats_cams", "obs_mean", "obs_sd"]
    print(per_fold[cols].round(3).to_string(index=False))

    print("\n=== BY CONCENTRATION REGIME (WHO 24 h guideline = 15 ug/m3) ===")
    print(bands_df[["band", "n", "share_of_rows", "rmse", "bias", "r2", "cams_rmse"]]
          .round(3).to_string(index=False))

    print("\n=== BY SEASON ===")
    print(pd.DataFrame(rows)[["season", "n", "rmse", "bias", "r2", "obs_mean"]]
          .round(3).to_string(index=False))

    # ---- what explains fold-level failure? ------------------------------------------
    print("\n=== WHAT PREDICTS A BAD FOLD? (Spearman, n = %d folds) ===" % len(per_fold))
    for col in ("obs_mean", "obs_sd", "exceed_rate", "n"):
        r = per_fold[["rmse", col]].corr(method="spearman").iloc[0, 1]
        print(f"  rmse vs {col:<12} rho = {r:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
