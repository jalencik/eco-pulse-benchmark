"""Feature-by-feature audit table: source, availability, safety, missingness, variance.

Answers, per feature and from the data rather than from memory:
  * which family it belongs to (same grouping the SHAP tables use);
  * whether it is admissible in a DEPLOYABLE configuration (latency <= horizon);
  * how much of it is missing, overall and inside the test block;
  * whether it varies at all (a constant feature is dead weight);
  * whether it is near-duplicated by another feature (redundancy).

The leakage question -- "could this have been known at the prediction timestamp?" -- is
answered by the tier system rather than here: every predictor carries a measured acquisition
latency, and `deployable` excludes anything whose latency exceeds the forecast horizon. This
table reports which tier each feature falls in so that the answer is visible per feature.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecopulse_ca.models.feature_table import build_feature_table, feature_columns
from ecopulse_ca.models.lag_features import SPATIAL_COLS, build_spatial_features

OUT = ROOT / "paper" / "tables" / "t7_04_feature_audit.csv"


def family(f: str) -> str:
    if f in SPATIAL_COLS:
        return "spatial_neighbour"
    if "valid_px" in f:
        return "satellite_missingness"
    if any(k in f for k in ("aod", "aerosol", "no2", "so2", "co_col")):
        return "satellite"
    if "cams" in f:
        return "cams_forecast"
    if any(k in f for k in ("doy", "month", "dow", "heating")):
        return "calendar"
    return "static_geography"


def main() -> int:
    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
    B = {b["name"]: b for b in splits["temporal_blocks"]}
    te_lo = pd.Timestamp(B["test"]["start"]).tz_localize(None)
    te_hi = pd.Timestamp(B["test"]["end"]).tz_localize(None)
    coords = {s["station_id"]: (s["latitude"], s["longitude"]) for s in splits["stations"]}

    df, _ = build_feature_table(splits)
    sp = build_spatial_features(df, coords, exclude_city="Almaty")

    tiers = {t: set(feature_columns(df, t)) for t in ("static_only", "deployable", "retrospective")}
    all_feats = sorted(set(feature_columns(df, "retrospective")) | set(SPATIAL_COLS))

    test_mask = (sp.date >= te_lo) & (sp.date <= te_hi)
    rows = []
    for f in all_feats:
        if f not in sp.columns:
            continue
        col = pd.to_numeric(sp[f], errors="coerce")
        tier = (
            "static_only"
            if f in tiers["static_only"]
            else "deployable"
            if f in tiers["deployable"]
            else "retrospective"
            if f in tiers["retrospective"]
            else "spatial"
        )
        n_unique = int(col.nunique(dropna=True))
        rows.append(
            {
                "feature": f,
                "family": family(f),
                "lowest_tier": tier,
                "deployable": tier in ("static_only", "deployable", "spatial"),
                "missing_pct_all": float(col.isna().mean() * 100),
                "missing_pct_test": float(col[test_mask].isna().mean() * 100),
                "n_unique": n_unique,
                "std": float(col.std()),
                "constant": bool(n_unique <= 1),
                "corr_with_target": float(col.corr(sp.pm25)) if col.std() > 0 else np.nan,
            }
        )
    out = pd.DataFrame(rows)

    # redundancy: highest absolute correlation with any OTHER feature
    num = sp[[f for f in out.feature if f in sp.columns]].apply(pd.to_numeric, errors="coerce")
    cm = num.corr().abs()
    np.fill_diagonal(cm.values, 0.0)
    out["max_abs_corr_other"] = out.feature.map(cm.max()).astype(float)
    out["most_correlated_with"] = out.feature.map(cm.idxmax())
    out = out.sort_values(["family", "feature"])
    out.to_csv(OUT, index=False)

    print(f"wrote {OUT.name} ({len(out)} features)\n")
    print("=== FEATURE AUDIT ===")
    cols = [
        "feature",
        "family",
        "lowest_tier",
        "missing_pct_all",
        "missing_pct_test",
        "corr_with_target",
        "max_abs_corr_other",
    ]
    print(out[cols].round(3).to_string(index=False))

    print("\n=== FLAGS ===")
    const = out[out.constant]
    print(f"  constant features                : {len(const)} {list(const.feature)}")
    hi_miss = out[out.missing_pct_test > 50]
    print(f"  >50% missing in test block       : {len(hi_miss)} {list(hi_miss.feature)}")
    redundant = out[out.max_abs_corr_other > 0.95]
    print(f"  |r| > 0.95 with another feature  : {len(redundant)}")
    for _, r in redundant.iterrows():
        print(f"      {r.feature} ~ {r.most_correlated_with} ({r.max_abs_corr_other:.3f})")
    nondeploy = out[~out.deployable]
    print(f"  retrospective-only (not deployable): {len(nondeploy)} {list(nondeploy.feature)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
