"""Phase 5 with tuning: Task N (leave-city-out) and Task F (blocked-temporal), separately.

Hyperparameters are selected on the 2023 VALIDATION block and then frozen. The test block
is scored once per configuration -- the spec forbids tuning on test.
"""
from __future__ import annotations
import itertools, json, pathlib, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, lightgbm as lgb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ecopulse_ca.models.feature_table import build_feature_table, feature_columns, daily_target
from ecopulse_ca.models.lag_features import (LOCAL_LAG_COLS, SPATIAL_COLS,
                                             build_local_lags, build_spatial_features)
from ecopulse_ca.models.cams_baseline import apply_pooled_debias, fit_bias
from ecopulse_ca.eval.metrics import regression_metrics

SEEDS = [0, 1, 2, 3, 4]
TIERS = ["static_only", "deployable", "retrospective"]
GRID = list(itertools.product([0.03, 0.08], [31, 63], [20, 40], [0.7, 0.9]))

splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
B = {b["name"]: b for b in splits["temporal_blocks"]}
tr_end = pd.Timestamp(B["train"]["end"]).tz_localize(None)
va_lo, va_hi = (pd.Timestamp(B["val"]["start"]).tz_localize(None),
                pd.Timestamp(B["val"]["end"]).tz_localize(None))
te_lo, te_hi = (pd.Timestamp(B["test"]["start"]).tz_localize(None),
                pd.Timestamp(B["test"]["end"]).tz_localize(None))
coords = {s["station_id"]: (s["latitude"], s["longitude"]) for s in splits["stations"]}

df, cov = build_feature_table(splits)
print(cov.report(), flush=True)

def mk(seed, p):
    lr, leaves, mcs, ff = p
    return lgb.LGBMRegressor(n_estimators=800, learning_rate=lr, num_leaves=leaves,
                             min_child_samples=mcs, colsample_bytree=ff, subsample=0.8,
                             subsample_freq=1, random_state=seed, verbose=-1)

def tune(tr, va, feats):
    """Select on VALIDATION only. Test is never consulted here."""
    best, best_rmse = GRID[0], np.inf
    for p in GRID:
        m = mk(0, p).fit(tr[feats], tr.pm25)
        r = regression_metrics(va.pm25, pd.Series(m.predict(va[feats]), index=va.index))
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

rows = []
# ================= TASK N: leave-city-out, NO local lags =================
print("\n=== TASK N (leave-city-out) -- spatial features only, no local lags ===", flush=True)
for tier in TIERS:
    base = feature_columns(df, tier)
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
            m = mk(seed, p).fit(pd.concat([tr, va])[feats], pd.concat([tr, va]).pm25)
            r = regression_metrics(te.pm25, pd.Series(m.predict(te[feats]), index=te.index))
            rows.append({"task": "N", "tier": tier, "held_out_city": held, "seed": seed,
                         "model": "lgbm_tuned", "params": str(p), "val_rmse": vrmse,
                         "zero_shot": held == "Khujand", **r.as_dict()})
        ids = set(te.station_id.unique())
        s2 = cams[cams.station_id.isin(ids)].copy()
        s2["pooled"] = apply_pooled_debias(s2, bias, held_out=ids)
        j = te.merge(s2[["station_id","date","pooled"]], on=["station_id","date"]).dropna(subset=["pooled"])
        if len(j) >= 30:
            r = regression_metrics(j.pm25, j.pooled)
            rows.append({"task":"N","tier":tier,"held_out_city":held,"seed":0,
                         "model":"cams_debiased_pooled","params":"","val_rmse":np.nan,
                         "zero_shot":held=="Khujand", **r.as_dict()})
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
        m = mk(seed, p).fit(pd.concat([tr, va])[feats], pd.concat([tr, va]).pm25)
        r = regression_metrics(te.pm25, pd.Series(m.predict(te[feats]), index=te.index))
        rows.append({"task":"F","tier":tier,"held_out_city":"ALL","seed":seed,
                     "model":"lgbm_tuned_lags","params":str(p),"val_rmse":vrmse,
                     "zero_shot":False, **r.as_dict()})
    print(f"  {tier} done  params={p}", flush=True)

res = pd.DataFrame(rows)
res.to_csv(ROOT / "paper/tables/phase5_tuned.csv", index=False)
print("\n" + "="*76)
print("TASK N -- leave-city-out (spatial features only)")
print("="*76)
n = res[res.task=="N"]
print(n[n.model=="lgbm_tuned"].groupby("tier").agg(
    rmse=("rmse","mean"), mae=("mae","mean"), r2=("r2","mean"), sd=("rmse","std")).round(2).to_string())
c = n[n.model=="cams_debiased_pooled"].agg({"rmse":"mean","mae":"mean","r2":"mean"})
print(f"\ncams_debiased_pooled   rmse {c.rmse:.2f}  mae {c.mae:.2f}  r2 {c.r2:.2f}")
print("\nper-city RMSE:")
print(n[n.model=="lgbm_tuned"].pivot_table(index="held_out_city", columns="tier",
      values="rmse", aggfunc="mean").round(1).to_string())
print("\n" + "="*76)
print("TASK F -- blocked temporal, local lags (NOT comparable to Task N)")
print("="*76)
print(res[res.task=="F"].groupby("tier").agg(
    rmse=("rmse","mean"), mae=("mae","mean"), r2=("r2","mean"), sd=("rmse","std")).round(2).to_string())
