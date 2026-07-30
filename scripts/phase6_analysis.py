"""Phase 6: Diebold-Mariano significance, SHAP attribution, final tables.

DM on DAILY errors, so the truncation lag is re-derived
-------------------------------------------------------
Phase 3's `nowcast_truncation_lag` was calibrated for HOURLY loss differentials. These are
daily, so the autocorrelation timescale is different and the hourly rule would be wrong.
The lag is measured from the data here, and the verdict is reported across a lag sweep --
a conclusion that flips with the truncation choice is not a conclusion.
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
import shap

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
from ecopulse_ca.eval.diebold_mariano import diebold_mariano, lag_sensitivity, newey_west_bandwidth
from ecopulse_ca.eval.metrics import regression_metrics
from ecopulse_ca.models.cams_baseline import apply_pooled_debias, fit_bias
from ecopulse_ca.models.feature_table import build_feature_table, daily_target, feature_columns
from ecopulse_ca.models.lag_features import SPATIAL_COLS, build_spatial_features

SEEDS = [0, 1, 2, 3, 4]
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
city_of = {s["station_id"]: s["city"] for s in splits["stations"]}

df, cov = build_feature_table(splits)
tuned = pd.read_csv(ROOT / "paper/tables/phase5_tuned.csv")
best = {
    (r.tier, r.held_out_city): eval(r.params)
    for _, r in tuned[(tuned.task == "N") & (tuned.model == "lgbm_tuned")]
    .drop_duplicates(["tier", "held_out_city"])
    .iterrows()
}

panel = pd.read_parquet(ROOT / "data/interim/benchmark_panel.parquet")
panel.columns = [str(c) for c in panel.columns]
tg = daily_target(panel, city_of)
daily_obs = {sid: g.set_index(g.date.dt.date).pm25 for sid, g in tg.groupby("station_id")}
cams = pd.read_parquet(ROOT / "data/interim/cams_pm25_forecast.parquet")
cams["station_id"] = cams.station_id.astype(str)
cams["date"] = pd.to_datetime(cams.time).dt.normalize()
bias = fit_bias(cams, daily_obs, tr_end)

TIER = "retrospective"
preds, shap_rows = [], []
for fold in splits["leave_city_out"]:
    held = fold["held_out_city"]
    p = best.get((TIER, held))
    if p is None:
        continue
    sp = build_spatial_features(df, coords, exclude_city=held)
    feats = feature_columns(df, TIER) + SPATIAL_COLS
    tr = sp[(sp.city != held) & (sp.date <= va_hi) & sp.pm25.notna()]
    te = sp[(sp.city == held) & (sp.date >= te_lo) & (sp.date <= te_hi) & sp.pm25.notna()]
    if len(tr) < 200 or len(te) < 30:
        continue
    lr, leaves, mcs, ff = p
    ens = []
    for seed in SEEDS:
        m = lgb.LGBMRegressor(
            n_estimators=800,
            learning_rate=lr,
            num_leaves=leaves,
            min_child_samples=mcs,
            colsample_bytree=ff,
            subsample=0.8,
            subsample_freq=1,
            random_state=seed,
            verbose=-1,
        ).fit(tr[feats], tr.pm25)
        ens.append(m.predict(te[feats]))
        if seed == 0:
            sv = shap.TreeExplainer(m).shap_values(te[feats])
            imp = np.abs(sv).mean(axis=0)
            for f, v in zip(feats, imp, strict=True):
                shap_rows.append({"fold": held, "feature": f, "mean_abs_shap": float(v)})
    s2 = cams[cams.station_id.isin(set(te.station_id))].copy()
    s2["pooled"] = apply_pooled_debias(s2, bias, held_out=set(te.station_id))
    j = te[["station_id", "date", "pm25"]].copy()
    j["lgbm"] = np.mean(ens, axis=0)
    j = j.merge(s2[["station_id", "date", "pooled"]], on=["station_id", "date"]).dropna()
    j["fold"] = held
    preds.append(j)

P = pd.concat(preds, ignore_index=True)
P.to_csv(OUT / "phase6_predictions.csv", index=False)

print("=== DM: lgbm_retrospective vs cams_debiased_pooled (Task N, daily) ===")
d_all = ((P.lgbm - P.pm25) ** 2 - (P.pooled - P.pm25) ** 2).to_numpy()
d_c = d_all - d_all.mean()
print("  ACF of daily loss differential:")
for lag in (1, 2, 3, 7, 14, 30):
    print(f"    lag {lag:2d}d: {np.corrcoef(d_c[lag:], d_c[:-lag])[0, 1]:+.3f}")
nw = newey_west_bandwidth(len(P))
print(f"  Newey-West automatic bandwidth for n={len(P)}: {nw} days\n")

rows = []
for fold, g in P.groupby("fold"):
    r = diebold_mariano(g.pm25, g.lgbm, g.pooled, truncation_lag=nw)
    rows.append(
        {
            "fold": fold,
            "n": r.n,
            "rmse_lgbm": regression_metrics(g.pm25, g.lgbm).rmse,
            "rmse_cams": regression_metrics(g.pm25, g.pooled).rmse,
            "dm": r.statistic,
            "p": r.p_value,
            "better": r.better,
            "sig": r.significant_at_05,
        }
    )
r = diebold_mariano(P.pm25, P.lgbm, P.pooled, truncation_lag=nw)
rows.append(
    {
        "fold": "POOLED",
        "n": r.n,
        "rmse_lgbm": regression_metrics(P.pm25, P.lgbm).rmse,
        "rmse_cams": regression_metrics(P.pm25, P.pooled).rmse,
        "dm": r.statistic,
        "p": r.p_value,
        "better": r.better,
        "sig": r.significant_at_05,
    }
)
D = pd.DataFrame(rows)
D.to_csv(OUT / "phase6_dm_tests.csv", index=False)
print(D.round(4).to_string(index=False))

print("\n=== lag sensitivity (pooled) -- does the verdict survive the lag choice? ===")
LS = lag_sensitivity(P.pm25, P.lgbm, P.pooled, lags=(0, 5, 14, 30, 60))
LS.to_csv(OUT / "phase6_dm_lag_sensitivity.csv", index=False)
print(LS.round(4).to_string(index=False))

print("\n=== SHAP: mean |SHAP| by feature FAMILY ===")
S = pd.DataFrame(shap_rows)


def fam(f):
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


S["family"] = S.feature.map(fam)
S.to_csv(OUT / "phase6_shap_by_feature.csv", index=False)
famtab = S.groupby("family").mean_abs_shap.sum().sort_values(ascending=False)
tot = famtab.sum()
for k, v in famtab.items():
    print(f"  {k:24s} {v:8.3f}   {100 * v / tot:5.1f}%")
famtab.to_csv(OUT / "phase6_shap_by_family.csv")
print("\n  top 12 individual features:")
top = S.groupby("feature").mean_abs_shap.mean().sort_values(ascending=False).head(12)
for k, v in top.items():
    print(f"    {k:34s} {v:7.3f}")
print(f"\ntables -> {OUT}")
