"""Independently re-verify the reviewers' headline statistical claims.

This script is deliberately standalone: it reads only the banked CSVs that the paper
ships, and recomputes each contested quantity from scratch. It does not import the
project's own analysis code, because the point is to check that code's output.

Run:  .venv/Scripts/python.exe scripts/verify_review_claims.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "paper" / "tables" / "t6_01_predictions_task_n.csv"
LOCO = ROOT / "paper" / "tables" / "t5_02_loco_tuned.csv"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


df = pd.read_csv(PRED)
y, yhat, cams, fold = df["pm25"], df["lgbm"], df["pooled"], df["fold"]

# ---------------------------------------------------------------------------
# R2/F1 -- what does "R^2 = 0.07" actually measure?
# ---------------------------------------------------------------------------
rule("R2/F1  --  R-squared: per-fold mean vs pooled")


def r2(y_true: np.ndarray, y_pred: np.ndarray, baseline: float) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - baseline) ** 2))
    return 1.0 - ss_res / ss_tot


per_fold = {}
for city, g in df.groupby("fold"):
    # each fold scored against ITS OWN mean -- this is what the pipeline does
    per_fold[city] = r2(g["pm25"].to_numpy(), g["lgbm"].to_numpy(), g["pm25"].mean())

print("Per-fold R^2 (each vs its own city mean):")
for city, v in sorted(per_fold.items(), key=lambda kv: kv[1]):
    print(f"  {city:<10} n={len(df[df.fold == city]):>4}   R^2 = {v:+.4f}")

fold_mean = float(np.mean(list(per_fold.values())))
spread = (min(per_fold.values()), max(per_fold.values()))
pooled_global = r2(y.to_numpy(), yhat.to_numpy(), float(y.mean()))

print(f"\n  mean of per-fold R^2        = {fold_mean:+.4f}   <- the paper's '0.07'")
print(f"  per-fold spread             = {spread[0]:+.4f} to {spread[1]:+.4f}")
print(f"  POOLED R^2 (vs global mean) = {pooled_global:+.4f}   <- what a reader hears")

# ---------------------------------------------------------------------------
# R2/F2 -- does the pooled DM test survive clustering by city?
# ---------------------------------------------------------------------------
rule("R2/F2  --  Diebold-Mariano: pooled vs city-clustered")

# loss differential: squared error of lgbm minus squared error of CAMS.
# negative => lgbm better.
d = (y - yhat) ** 2 - (y - cams) ** 2

# (a) pooled, treating every station-day as independent (what the paper does)
t_pooled = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d))))
p_pooled = float(2 * stats.t.sf(abs(t_pooled), df=len(d) - 1))
print(f"pooled, n={len(d)} station-days treated as independent:")
print(f"  mean d = {d.mean():+.4f}   t = {t_pooled:+.4f}   p = {p_pooled:.3e}")

# (b) city as the unit of analysis -- 6 observations
city_d = d.groupby(fold).mean()
t_city = float(city_d.mean() / (city_d.std(ddof=1) / np.sqrt(len(city_d))))
p_city = float(2 * stats.t.sf(abs(t_city), df=len(city_d) - 1))
print(f"\ncity as unit of analysis, n={len(city_d)} cities:")
for city, v in city_d.items():
    print(f"  {city:<10} mean d = {v:+9.4f}")
print(f"  mean d = {city_d.mean():+.4f}   t = {t_city:+.4f}   p = {p_city:.4f}")

# (c) how dependent are the two Dushanbe stations, really?
rule("R2/F2  --  within-city dependence (the reason clustering matters)")
for city, g in df.groupby("fold"):
    ids = sorted(g["station_id"].unique())
    if len(ids) < 2:
        continue
    wide = g.pivot_table(index="date", columns="station_id", values="pm25")
    corr = wide.corr()
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            r = corr.loc[ids[i], ids[j]]
            n_ov = int(wide[[ids[i], ids[j]]].dropna().shape[0])
            print(f"  {city:<10} {ids[i]} vs {ids[j]}:  r = {r:.4f}  (n overlap = {n_ov})")

# ---------------------------------------------------------------------------
# R1/F1 -- Jensen bound: can the banked ensemble be the mean of the seeds?
# ---------------------------------------------------------------------------
rule("R1/F1  --  Jensen bound on the five-seed ensemble")

if LOCO.exists():
    loco = pd.read_csv(LOCO)
    rmse_col = "rmse"
    fold_col = "held_out_city"
    if rmse_col and fold_col:
        banked = df.groupby("fold").apply(
            lambda g: float(np.sqrt(np.mean((g["pm25"] - g["lgbm"]) ** 2))),
            include_groups=False,
        )
        print(f"{'fold':<10} {'QM bound':>10} {'banked':>10}   verdict")
        for city, g in loco.groupby(fold_col):
            seeds = g[rmse_col].to_numpy(dtype=float)
            qm = float(np.sqrt(np.mean(seeds**2)))
            got = banked.get(city, np.nan)
            bad = got > qm + 1e-9
            print(
                f"{city:<10} {qm:>10.4f} {got:>10.4f}   "
                f"{'*** VIOLATED by ' + format(got - qm, '.4f') if bad else 'ok'}"
            )
    else:
        print(f"  could not locate rmse/fold columns in {LOCO.name}: {list(loco.columns)}")
else:
    print(f"  {LOCO} missing")

print()
