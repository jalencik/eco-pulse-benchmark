"""Model-formulation search for Task N, scored ONLY on the validation block.

THE TEST BLOCK IS NEVER READ BY THIS SCRIPT.
-------------------------------------------
Selection uses leave-city-out over the TRAINING cities, scored on the validation block
(2023-01-11 .. 2023-12-21). The 2024 test block is not loaded, not scored and not referenced.
That is what makes any winner here a *pre-specified* choice when it is later evaluated once
on test, rather than a configuration chosen because it happened to win on test.

WHAT IS BEING TESTED, AND WHY
-----------------------------
The corrected daily ladder puts the tuned LightGBM *below plain inverse-distance weighting*:

    idw_k5_p2  29.44   <  ordinary_kriging 29.75  <  LightGBM 30.24

and the model's own highest-attribution feature is `nbr_idw`. That combination is the
signature of a specific, correctable failure: the model is being asked to learn the level of
PM2.5 in a city it has never seen, and is partly re-deriving an interpolation it was already
given as an input -- adding variance without adding signal.

Four formulations are compared, each with a stated scientific rationale, none chosen post hoc:

  A. `raw`          -- the current formulation. Predict daily PM2.5 directly.
  B. `log`          -- predict log1p(PM2.5). PM2.5 is right-skewed and heavy-tailed; squared
                       error on the raw scale is dominated by a few high days, so the fit is
                       driven by the tail rather than the bulk.
  C. `idw_residual` -- predict PM2.5 - nbr_idw, then add nbr_idw back. This is regression
                       kriging in its standard form: let the interpolator carry the spatial
                       level and let the learner model only the departure from it. It cannot
                       do worse than IDW by construction unless the residual is unlearnable.
  D. `log_residual` -- C on the log scale.

and three model families (LightGBM, ridge, random forest) to establish whether any weakness
is specific to gradient boosting rather than to the task.
"""

from __future__ import annotations

import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecopulse_ca.models.feature_table import build_feature_table, feature_columns
from ecopulse_ca.models.lag_features import SPATIAL_COLS, build_spatial_features

OUT = ROOT / "paper" / "tables" / "t5_03_formulation_search_val.csv"
SEEDS = [0, 1, 2]
TIER = "retrospective"


def rmse(y, p) -> float:
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def main() -> int:
    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
    B = {b["name"]: b for b in splits["temporal_blocks"]}
    tr_end = pd.Timestamp(B["train"]["end"]).tz_localize(None)
    va_lo = pd.Timestamp(B["val"]["start"]).tz_localize(None)
    va_hi = pd.Timestamp(B["val"]["end"]).tz_localize(None)

    coords = {s["station_id"]: (s["latitude"], s["longitude"]) for s in splits["stations"]}
    city_of = {s["station_id"]: s["city"] for s in splits["stations"]}
    df, _ = build_feature_table(splits)

    cities = sorted({s["city"] for s in splits["stations"]})
    rows = []

    for held in cities:
        sp = build_spatial_features(df, coords, exclude_city=held)
        feats = feature_columns(df, TIER) + SPATIAL_COLS
        tr = sp[(sp.city != held) & (sp.date <= tr_end) & sp.pm25.notna()]
        # SCORED ON VALIDATION. The test block is never touched in this script.
        va = sp[(sp.city == held) & (sp.date >= va_lo) & (sp.date <= va_hi) & sp.pm25.notna()]
        if len(tr) < 200 or len(va) < 30:
            print(f"  {held}: insufficient rows (train {len(tr)}, val {len(va)}) -- skipped")
            continue

        idw_tr = tr["nbr_idw"].to_numpy(dtype=float)
        idw_va = va["nbr_idw"].to_numpy(dtype=float)
        y_tr, y_va = tr.pm25.to_numpy(float), va.pm25.to_numpy(float)

        # Reference rungs, same rows, for context.
        rows.append({"fold": held, "n": len(va), "model": "idw_direct", "form": "-", "seed": 0,
                     "rmse": rmse(y_va, np.where(np.isfinite(idw_va), idw_va, np.nanmean(y_tr)))})
        rows.append({"fold": held, "n": len(va), "model": "train_global_mean", "form": "-",
                     "seed": 0, "rmse": rmse(y_va, np.full(len(y_va), y_tr.mean()))})

        for form in ("raw", "log", "idw_residual", "log_residual"):
            if form == "raw":
                tgt_tr, inv = y_tr, lambda p, i: p
            elif form == "log":
                tgt_tr, inv = np.log1p(y_tr), lambda p, i: np.expm1(p)
            elif form == "idw_residual":
                # nbr_idw is NaN on ~7% of rows (no neighbour reporting that day). Skipping
                # those rows would change the training set between formulations and make the
                # comparison unfair, so the interpolator falls back to the TRAINING mean --
                # a legal, training-only value -- and the residual is taken against that.
                base_tr = np.where(np.isfinite(idw_tr), idw_tr, y_tr.mean())
                base_va = np.where(np.isfinite(idw_va), idw_va, y_tr.mean())
                tgt_tr = y_tr - base_tr
                inv = lambda p, i, b=base_va: p + b
            else:
                base_tr = np.clip(np.where(np.isfinite(idw_tr), idw_tr, y_tr.mean()), 0, None)
                base_va = np.clip(np.where(np.isfinite(idw_va), idw_va, y_tr.mean()), 0, None)
                tgt_tr = np.log1p(y_tr) - np.log1p(base_tr)
                inv = lambda p, i, b=base_va: np.expm1(p + np.log1p(b))

            for name in ("lgbm", "ridge", "rf"):
                for seed in SEEDS:
                    if name == "lgbm":
                        m = lgb.LGBMRegressor(
                            n_estimators=800, learning_rate=0.03, num_leaves=31,
                            min_child_samples=20, colsample_bytree=0.7, subsample=0.8,
                            subsample_freq=1, random_state=seed, verbose=-1)
                    elif name == "ridge":
                        if seed:  # deterministic
                            continue
                        m = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
                    else:
                        m = RandomForestRegressor(
                            n_estimators=300, min_samples_leaf=5, n_jobs=-1,
                            random_state=seed)

                    X_tr = tr[feats].astype(float).fillna(tr[feats].astype(float).median())
                    X_va = va[feats].astype(float).fillna(tr[feats].astype(float).median())
                    m.fit(X_tr, tgt_tr)
                    pred = inv(np.asarray(m.predict(X_va), dtype=float), idw_va)
                    pred = np.where(np.isfinite(pred), pred, y_tr.mean())
                    pred = np.clip(pred, 0.0, None)  # negative PM2.5 is unphysical
                    rows.append({"fold": held, "n": len(va), "model": name, "form": form,
                                 "seed": seed, "rmse": rmse(y_va, pred)})
        print(f"  {held}: done ({len(va)} validation rows)", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f"\nwrote {OUT} ({len(out)} rows)\n")

    agg = (
        out.groupby(["model", "form"])
        .apply(lambda g: g.groupby("fold").rmse.mean().mean(), include_groups=False)
        .rename("val_fold_mean_rmse")
        .sort_values()
    )
    print("VALIDATION fold-mean RMSE (lower is better) -- selection basis:")
    for (mdl, form), v in agg.items():
        print(f"  {mdl:<18} {form:<14} {v:8.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
