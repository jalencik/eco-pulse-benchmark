"""Phase 5 with tuning: Task N (leave-city-out) and Task F (blocked-temporal), separately.

TARGET TRANSFORM -- frozen 2026-08-13, selected on VALIDATION ONLY
-----------------------------------------------------------------
The model fits `log1p(PM2.5)` and inverts with `expm1` before scoring. Metrics are computed
on the raw ug/m3 scale, so they stay comparable with every baseline.

Rationale, stated before the choice was made: daily PM2.5 in this record has skew 2.79 and
excess kurtosis 13.5 (median 29.9, p99 159.4, max 378.7). Squared error on the raw scale is
therefore dominated by a handful of extreme days, and the fit is driven by the tail rather
than the bulk. On log1p the same target has skew 0.20 and excess kurtosis -0.06.

Selected by `scripts/experiment_model_search.py`, which scores leave-city-out folds on the
**validation block only** and never reads the test block. Validation fold-mean RMSE:

    lgbm log            37.79   <- selected
    rf   log_residual   38.49
    rf   log            38.71
    lgbm log_residual   39.09
    lgbm raw            41.44   <- previous production configuration
    lgbm idw_residual   42.74
    ridge (any form)    45-49

The transform helps every model family tested, which is what distinguishes a real effect from
a lucky draw. Residual-against-IDW formulations were also tested, on the hypothesis that the
learner was re-deriving an interpolation it already had as a feature; they did not help
LightGBM, so that hypothesis is not supported and the simpler transform is kept.

Hyperparameters are selected on the 2023 VALIDATION block and then frozen. The test block
is scored once per configuration -- the spec forbids tuning on test.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ecopulse_ca.eval.metrics import regression_metrics
from ecopulse_ca.models.cams_baseline import apply_pooled_debias, fit_bias
from ecopulse_ca.models.feature_table import build_feature_table, daily_target, feature_columns
from ecopulse_ca.models.lag_features import (
    LOCAL_LAG_COLS,
    SPATIAL_COLS,
    build_local_lags,
    build_spatial_features,
)

SEEDS = [0, 1, 2, 3, 4]
TIERS = ["static_only", "deployable", "retrospective"]
GRID = list(itertools.product([0.03, 0.08], [31, 63], [20, 40], [0.7, 0.9]))

splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
B = {b["name"]: b for b in splits["temporal_blocks"]}
tr_end = pd.Timestamp(B["train"]["end"]).tz_localize(None)
va_lo, va_hi = (
    pd.Timestamp(B["val"]["start"]).tz_localize(None),
    pd.Timestamp(B["val"]["end"]).tz_localize(None),
)
te_lo, te_hi = (
    pd.Timestamp(B["test"]["start"]).tz_localize(None),
    pd.Timestamp(B["test"]["end"]).tz_localize(None),
)
coords = {s["station_id"]: (s["latitude"], s["longitude"]) for s in splits["stations"]}

df, cov = build_feature_table(splits)
print(cov.report(), flush=True)


def mk(seed, p):
    lr, leaves, mcs, ff = p
    return lgb.LGBMRegressor(
        n_estimators=800,
        learning_rate=lr,
        num_leaves=leaves,
        min_child_samples=mcs,
        colsample_bytree=ff,
        subsample=0.8,
        subsample_freq=1,
        random_state=seed,
        verbose=-1,
    )


def tune(tr, va, feats):
    """Select on VALIDATION only. Test is never consulted here.

    Fits the SAME log1p objective the production model uses. Selecting hyperparameters under
    one objective and then fitting under another would pick a configuration for a problem the
    model does not solve; the scoring is still RMSE on the raw ug/m3 scale, so the selection
    criterion is unchanged.
    """
    best, best_rmse = GRID[0], np.inf
    for p in GRID:
        m = mk(0, p).fit(tr[feats], np.log1p(tr.pm25))
        _pv = np.clip(np.expm1(m.predict(va[feats])), 0.0, None)
        r = regression_metrics(va.pm25, pd.Series(_pv, index=va.index))
        if np.isfinite(r.rmse) and r.rmse < best_rmse:
            best, best_rmse = p, r.rmse
    return best, best_rmse


# ---------- CAMS comparator (pooled debias, train-block bias) ----------
panel = pd.read_parquet(ROOT / "data/interim/benchmark_panel.parquet")
panel.columns = [str(c) for c in panel.columns]
city_of = {s["station_id"]: s["city"] for s in splits["stations"]}
tg = daily_target(panel, city_of)
daily_obs = {sid: g.set_index(g.date.dt.date).pm25 for sid, g in tg.groupby("station_id")}
cams = pd.read_parquet(ROOT / "data/interim/cams_pm25_forecast.parquet")
cams["station_id"] = cams.station_id.astype(str)
cams["date"] = pd.to_datetime(cams.time).dt.normalize()
bias = fit_bias(cams, daily_obs, tr_end)


# ---- Task N feature exclusion, frozen 2026-08-13 (second freeze) ---------------------
# Satellite retrieval-count features (`*_valid_px`) are EXCLUDED from Task N. Rationale,
# stated before the test block was scored under this configuration: retrieval success depends
# on local surface brightness, snow cover, cloud climatology and solar geometry, all of which
# are properties of a PARTICULAR CITY. Under leave-city-out the model sees missingness
# patterns from the training cities that do not describe the held-out one, so the family
# invites a city-specific artefact rather than a transferable signal.
#
# Selected by scripts/experiment_ablation_ensemble.py on the VALIDATION block only. Validation
# fold-mean RMSE 37.79 (all features) -> 36.03 (dropped), improving 4 of 6 folds
# (Bishkek -5.99, Almaty -2.97, Ashgabat -1.21, Khujand -0.91; Dushanbe +0.51,
# Tashkent +0.05). Ensembling with a random forest did NOT help (37.99 vs 37.74) and a
# training-fitted calibration offset helped only marginally (-0.37, inside fold noise across
# the ~31 configurations tried), so neither was adopted.
#
# They remain available for Task F, where the held-out entity is a time block rather than a
# city and the argument above does not apply.
MISSINGNESS_COLS = [c for c in df.columns if "valid_px" in str(c)]


def taskn_features(tier):
    """Tier columns minus the city-specific satellite-missingness family."""
    return [c for c in feature_columns(df, tier) if c not in MISSINGNESS_COLS]


rows = []
# ================= TASK N: leave-city-out, NO local lags =================
print("\n=== TASK N (leave-city-out) -- spatial features only, no local lags ===", flush=True)
for tier in TIERS:
    base = taskn_features(tier)
    for fold in splits["leave_city_out"]:
        held = fold["held_out_city"]
        sp = build_spatial_features(df, coords, exclude_city=held)
        feats = base + SPATIAL_COLS
        tr = sp[(sp.city != held) & (sp.date <= tr_end) & sp.pm25.notna()]
        va = sp[(sp.city != held) & (sp.date >= va_lo) & (sp.date <= va_hi) & sp.pm25.notna()]
        te = sp[(sp.city == held) & (sp.date >= te_lo) & (sp.date <= te_hi) & sp.pm25.notna()]
        if len(tr) < 200 or len(te) < 30 or len(va) < 50:
            continue
        p, vrmse = tune(tr, va, feats)
        for seed in SEEDS:
            _fit = pd.concat([tr, va])
            m = mk(seed, p).fit(_fit[feats], np.log1p(_fit.pm25))
            _p = np.clip(np.expm1(m.predict(te[feats])), 0.0, None)
            r = regression_metrics(te.pm25, pd.Series(_p, index=te.index))
            rows.append(
                {
                    "task": "N",
                    "tier": tier,
                    "held_out_city": held,
                    "seed": seed,
                    "model": "lgbm_tuned",
                    "params": str(p),
                    "val_rmse": vrmse,
                    "zero_shot": held == "Khujand",
                    **r.as_dict(),
                }
            )
        ids = set(te.station_id.unique())
        s2 = cams[cams.station_id.isin(ids)].copy()
        s2["pooled"] = apply_pooled_debias(s2, bias, held_out=ids)
        j = te.merge(s2[["station_id", "date", "pooled"]], on=["station_id", "date"]).dropna(
            subset=["pooled"]
        )
        if len(j) >= 30:
            r = regression_metrics(j.pm25, j.pooled)
            rows.append(
                {
                    "task": "N",
                    "tier": tier,
                    "held_out_city": held,
                    "seed": 0,
                    "model": "cams_debiased_pooled",
                    "params": "",
                    "val_rmse": np.nan,
                    "zero_shot": held == "Khujand",
                    **r.as_dict(),
                }
            )
    print(f"  {tier} done", flush=True)

# ================= TASK F: blocked temporal, local lags LEGAL =================
print("\n=== TASK F (blocked temporal, monitored stations) -- local lags legal ===", flush=True)
lagged = build_local_lags(df)
for tier in TIERS:
    feats = feature_columns(df, tier) + LOCAL_LAG_COLS
    tr = lagged[(lagged.date <= tr_end) & lagged.pm25.notna()]
    va = lagged[(lagged.date >= va_lo) & (lagged.date <= va_hi) & lagged.pm25.notna()]
    te = lagged[(lagged.date >= te_lo) & (lagged.date <= te_hi) & lagged.pm25.notna()]
    p, vrmse = tune(tr, va, feats)
    for seed in SEEDS:
        _fit = pd.concat([tr, va])
        m = mk(seed, p).fit(_fit[feats], np.log1p(_fit.pm25))
        _p = np.clip(np.expm1(m.predict(te[feats])), 0.0, None)
        r = regression_metrics(te.pm25, pd.Series(_p, index=te.index))
        rows.append(
            {
                "task": "F",
                "tier": tier,
                "held_out_city": "ALL",
                "seed": seed,
                "model": "lgbm_tuned_lags",
                "params": str(p),
                "val_rmse": vrmse,
                "zero_shot": False,
                **r.as_dict(),
            }
        )
    print(f"  {tier} done  params={p}", flush=True)

res = pd.DataFrame(rows)
# Writes the TRACKED filename directly. It previously wrote `phase5_tuned.csv`, which was
# renamed by hand to `t5_02_loco_tuned.csv` in 99b9a13 -- and that rename silently broke
# phase6_analysis.py, whose input then no longer existed on any clone. Producers now emit the
# name the paper cites, so there is no rename step left to lose.
res.to_csv(ROOT / "paper/tables/t5_02_loco_tuned.csv", index=False)
print("\n" + "=" * 76)
print("TASK N -- leave-city-out (spatial features only)")
print("=" * 76)
n = res[res.task == "N"]
print(
    n[n.model == "lgbm_tuned"]
    .groupby("tier")
    .agg(rmse=("rmse", "mean"), mae=("mae", "mean"), r2=("r2", "mean"), sd=("rmse", "std"))
    .round(2)
    .to_string()
)
c = n[n.model == "cams_debiased_pooled"].agg({"rmse": "mean", "mae": "mean", "r2": "mean"})
print(f"\ncams_debiased_pooled   rmse {c.rmse:.2f}  mae {c.mae:.2f}  r2 {c.r2:.2f}")
print("\nper-city RMSE:")
print(
    n[n.model == "lgbm_tuned"]
    .pivot_table(index="held_out_city", columns="tier", values="rmse", aggfunc="mean")
    .round(1)
    .to_string()
)
print("\n" + "=" * 76)
print("TASK F -- blocked temporal, local lags (NOT comparable to Task N)")
print("=" * 76)
print(
    res[res.task == "F"]
    .groupby("tier")
    .agg(rmse=("rmse", "mean"), mae=("mae", "mean"), r2=("r2", "mean"), sd=("rmse", "std"))
    .round(2)
    .to_string()
)
