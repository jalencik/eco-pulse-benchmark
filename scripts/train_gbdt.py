"""Phase 5: LightGBM under leave-one-city-out, against the debiased CAMS baseline.

Two protocol points that decide whether the numbers mean anything
-----------------------------------------------------------------
**Khujand is a pure zero-shot fold.** It has no training-block rows at all, so it never
contributes to any fold's training set. Its own fold is therefore strictly harder than the
others -- the model must transfer with no local history whatsoever -- and it is reported
separately rather than averaged in silently.

**The CAMS comparator must match the fold's legality.** Under leave-city-out the held-out
city has no labels, so its own bias cannot be estimated. Every fold is compared against
`debiased_pooled` (bias averaged over TRAINING stations only). Using `debiased_local` here
would leak the held-out city's labels into its own baseline.
"""
from __future__ import annotations
import json, pathlib, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import lightgbm as lgb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ecopulse_ca.models.feature_table import build_feature_table, feature_columns  # noqa: E402
from ecopulse_ca.models.cams_baseline import apply_pooled_debias, fit_bias  # noqa: E402
from ecopulse_ca.eval.metrics import regression_metrics  # noqa: E402

SEEDS = [0, 1, 2, 3, 4]
TIERS = ["static_only", "deployable", "retrospective"]

splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
blocks = {b["name"]: b for b in splits["temporal_blocks"]}
tr_end = pd.Timestamp(blocks["train"]["end"]).tz_localize(None)
te_lo = pd.Timestamp(blocks["test"]["start"]).tz_localize(None)
te_hi = pd.Timestamp(blocks["test"]["end"]).tz_localize(None)

df, cov = build_feature_table(splits)
print(f"feature table: {len(df):,} station-days, {df.station_id.nunique()} stations, "
      f"{df.city.nunique()} cities")
print(cov.report())
print(f"target coverage: {df.pm25.notna().sum():,} rows with PM2.5\n")

# CAMS pooled-debias comparator, fitted on the train block only.
panel = pd.read_parquet(ROOT / "data/interim/benchmark_panel.parquet")
panel.columns = [str(c) for c in panel.columns]
from ecopulse_ca.models.feature_table import CITY_TZ, daily_target  # noqa: E402
city_of = {s["station_id"]: s["city"] for s in splits["stations"]}
tgt = daily_target(panel, city_of)
daily_obs = {sid: g.set_index(g.date.dt.date).pm25 for sid, g in tgt.groupby("station_id")}
cams_raw = pd.read_parquet(ROOT / "data/interim/cams_pm25_forecast.parquet")
cams_raw["station_id"] = cams_raw.station_id.astype(str)
bias = fit_bias(cams_raw, daily_obs, tr_end)

rows = []
for tier in TIERS:
    feats = feature_columns(df, tier)
    for fold in splits["leave_city_out"]:
        held = fold["held_out_city"]
        tr = df[(df.city != held) & (df.date <= tr_end) & df.pm25.notna()]
        te = df[(df.city == held) & (df.date >= te_lo) & (df.date <= te_hi) & df.pm25.notna()]
        if len(tr) < 200 or len(te) < 30:
            print(f"  skip {tier}/{held}: train {len(tr)} test {len(te)}")
            continue
        for seed in SEEDS:
            m = lgb.LGBMRegressor(
                n_estimators=600, learning_rate=0.05, num_leaves=31,
                min_child_samples=30, subsample=0.8, subsample_freq=1,
                colsample_bytree=0.8, random_state=seed, verbose=-1,
            )
            m.fit(tr[feats], tr.pm25)
            pred = pd.Series(m.predict(te[feats]), index=te.index)
            reg = regression_metrics(te.pm25, pred)
            rows.append({"tier": tier, "held_out_city": held, "seed": seed,
                         "model": "lightgbm", "n_train": len(tr), "n_test": len(te),
                         "zero_shot": held == "Khujand", **reg.as_dict()})
        # CAMS comparator on the same rows
        held_ids = set(te.station_id.unique())
        sub = cams_raw[cams_raw.station_id.isin(held_ids)].copy()
        sub["date"] = pd.to_datetime(sub.time).dt.normalize()
        sub["pooled"] = apply_pooled_debias(sub, bias, held_out=held_ids)
        j = te.merge(sub[["station_id", "date", "pooled"]], on=["station_id", "date"],
                     how="left").dropna(subset=["pooled"])
        if len(j) >= 30:
            reg = regression_metrics(j.pm25, j.pooled)
            rows.append({"tier": tier, "held_out_city": held, "seed": 0,
                         "model": "cams_debiased_pooled", "n_train": 0, "n_test": len(j),
                         "zero_shot": held == "Khujand", **reg.as_dict()})

res = pd.DataFrame(rows)
res.to_csv(ROOT / "paper/tables/phase5_loco.csv", index=False)
print("\n" + "=" * 78)
print("LEAVE-ONE-CITY-OUT, test block 2024, daily mean PM2.5")
print("=" * 78)
piv = res[res.model == "lightgbm"].groupby(["tier"]).agg(
    rmse=("rmse", "mean"), mae=("mae", "mean"), r2=("r2", "mean"),
    rmse_sd=("rmse", "std"))
cam = res[res.model == "cams_debiased_pooled"].agg({"rmse": "mean", "mae": "mean", "r2": "mean"})
print(piv.round(2).to_string())
print(f"\ncams_debiased_pooled   rmse {cam.rmse:.2f}  mae {cam.mae:.2f}  r2 {cam.r2:.2f}")
print("\nper-city RMSE (lightgbm, mean over 5 seeds):")
print(res[res.model == "lightgbm"].pivot_table(index="held_out_city", columns="tier",
      values="rmse", aggfunc="mean").round(1).to_string())
print("\nseed spread (max sd across folds/tiers): "
      f"{res[res.model=='lightgbm'].groupby(['tier','held_out_city']).rmse.std().max():.3f}")
