"""Primary and sensitivity inference for "does the model beat debiased CAMS?".

THE PROBLEM THIS FILE EXISTS TO SOLVE
-------------------------------------
The published claim was *p* < 0.0001, from a Diebold-Mariano test treating 2,480 station-days
from 6 cities as independent observations. They are not independent in either dimension:

  * serially -- the loss differential has ACF +0.63 at lag 1, still +0.21 at lag 8;
  * cross-sectionally -- station-days cluster within cities, and cities contribute grossly
    unequal row counts, so the pooled statistic is dominated by whichever city has most rows.

Correcting either one moves the p-value by many orders of magnitude, and the two corrections
do not agree with each other. Choosing the more favourable one would be p-hacking, so this
script computes all of them, declares a primary analysis in advance on scientific grounds,
and reports the rest as sensitivity.

CHOOSING THE PRIMARY ANALYSIS
-----------------------------
Estimand: the expected reduction in squared error from using the learned model instead of
debiased CAMS **at a city with no local training labels**.

The unit of generalisation is therefore the CITY, not the station-day. The manuscript already
argues this in Section 5.4, and the whole protocol is leave-city-out. An inference that treats
station-days as exchangeable answers a different question -- "does the model do better on more
days?" -- which is not what a reader takes from "the model beats CAMS".

So the primary analysis aggregates to one number per city (6 observations) and tests those.

With only 6 clusters, cluster-robust asymptotics are unreliable: the CRVE standard error is
badly downward-biased below roughly 30-50 clusters (Cameron & Miller 2015). Two remedies are
appropriate at G = 6 and both are reported:

  * a paired t-test on the 6 city means with G-1 = 5 degrees of freedom, and
  * an **exact sign-flip permutation test** over all 2^6 = 64 sign assignments, which makes no
    distributional assumption at all. Its smallest attainable two-sided p-value is 2/64 =
    0.03125, and that floor is stated explicitly rather than hidden.

Neither is "the significant one". Both are reported with the same prominence.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TABLES = ROOT / "paper" / "tables"
OUT = TABLES / "t6_06_significance.csv"
RNG_SEED = 0
N_BOOT = 10_000


def _loss_differential(df: pd.DataFrame) -> pd.Series:
    """Squared-error differential, model minus CAMS. Negative favours the model."""
    return (df.pm25 - df.lgbm) ** 2 - (df.pm25 - df.pooled) ** 2


def _hac_se(d: np.ndarray, lag: int) -> float:
    """Newey-West long-run standard error of the mean, Bartlett kernel."""
    n = len(d)
    dc = d - d.mean()
    gamma0 = float(np.dot(dc, dc) / n)
    lrv = gamma0
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        gk = float(np.dot(dc[k:], dc[:-k]) / n)
        lrv += 2.0 * w * gk
    lrv = max(lrv, 1e-12)
    return float(np.sqrt(lrv / n))


def main() -> int:
    pred = pd.read_csv(TABLES / "t6_01_predictions_task_n.csv", dtype={"station_id": str})
    pred["d"] = _loss_differential(pred)
    rows: list[dict] = []

    # ---------- PRIMARY: city as the unit of generalisation ----------------------------
    city_means = pred.groupby("fold")["d"].mean()
    g = len(city_means)
    mean_d = float(city_means.mean())
    se = float(city_means.std(ddof=1) / np.sqrt(g))
    t_stat = mean_d / se
    p_t = float(2 * stats.t.sf(abs(t_stat), df=g - 1))
    crit = stats.t.ppf(0.975, df=g - 1)
    ci = (mean_d - crit * se, mean_d + crit * se)

    rows.append(
        {
            "analysis": "PRIMARY",
            "test": "paired t-test on city means",
            "unit": "city",
            "n": g,
            "statistic": t_stat,
            "p": p_t,
            "ci_lo": ci[0],
            "ci_hi": ci[1],
            "note": f"df = {g - 1}; cluster-robust asymptotics unreliable at G = {g}",
        }
    )

    # Exact sign-flip permutation over cities. Under the null of no difference, the sign of
    # each city's mean differential is exchangeable.
    obs = abs(mean_d)
    signs = list(itertools.product([-1, 1], repeat=g))
    perm = [abs(float(np.mean(np.array(s) * city_means.to_numpy()))) for s in signs]
    p_perm = float(np.mean([v >= obs - 1e-15 for v in perm]))
    rows.append(
        {
            "analysis": "PRIMARY",
            "test": "exact sign-flip permutation on city means",
            "unit": "city",
            "n": g,
            "statistic": mean_d,
            "p": p_perm,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "note": f"all 2^{g} = {len(signs)} sign assignments; "
            f"smallest attainable two-sided p = {2 / len(signs):.5f}",
        }
    )

    # ---------- SENSITIVITY: station-day with serial-correlation corrections -----------
    d_all = pred["d"].to_numpy()
    n = len(d_all)
    naive_se = float(d_all.std(ddof=1) / np.sqrt(n))
    t_naive = float(d_all.mean() / naive_se)
    rows.append(
        {
            "analysis": "SENSITIVITY",
            "test": "station-day, independence assumed (as originally published)",
            "unit": "station-day",
            "n": n,
            "statistic": t_naive,
            "p": float(2 * stats.norm.sf(abs(t_naive))),
            "ci_lo": d_all.mean() - 1.96 * naive_se,
            "ci_hi": d_all.mean() + 1.96 * naive_se,
            "note": "INVALID -- ignores serial and cross-sectional dependence; shown for "
            "comparison only",
        }
    )

    for lag in (8, 20, 60):
        se_h = _hac_se(d_all, lag)
        t_h = float(d_all.mean() / se_h)
        rows.append(
            {
                "analysis": "SENSITIVITY",
                "test": f"station-day, Newey-West HAC (Bartlett, lag {lag} d)",
                "unit": "station-day",
                "n": n,
                "statistic": t_h,
                "p": float(2 * stats.norm.sf(abs(t_h))),
                "ci_lo": d_all.mean() - 1.96 * se_h,
                "ci_hi": d_all.mean() + 1.96 * se_h,
                "note": "corrects serial dependence only; still treats cities as independent",
            }
        )

    # Cluster bootstrap over cities: resample whole cities with replacement. Honest about
    # cluster dependence, but coarse at G = 6 -- reported as sensitivity, not primary.
    rng = np.random.default_rng(RNG_SEED)
    cities = list(city_means.index)
    boot = []
    for _ in range(N_BOOT):
        draw = rng.choice(cities, size=g, replace=True)
        boot.append(float(np.mean([city_means[c] for c in draw])))
    boot_arr = np.array(boot)
    rows.append(
        {
            "analysis": "SENSITIVITY",
            "test": f"cluster bootstrap over cities ({N_BOOT:,} resamples)",
            "unit": "city",
            "n": g,
            "statistic": mean_d,
            "p": float(2 * min((boot_arr >= 0).mean(), (boot_arr <= 0).mean())),
            "ci_lo": float(np.percentile(boot_arr, 2.5)),
            "ci_hi": float(np.percentile(boot_arr, 97.5)),
            "note": f"percentile CI; only {g} distinct clusters to resample",
        }
    )

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    # ---------- per-fold results with a multiplicity correction ------------------------
    dm = pd.read_csv(TABLES / "t6_02_dm_lgbm_vs_cams.csv")
    folds = dm[dm.fold != "POOLED"].sort_values("p").reset_index(drop=True)
    m = len(folds)
    holm = []
    running = 0.0
    for i, r in folds.iterrows():
        adj = min(1.0, (m - i) * r.p)
        running = max(running, adj)  # Holm adjusted p-values are monotone
        holm.append(running)
    folds["p_holm"] = holm
    folds["sig_holm_05"] = folds.p_holm < 0.05
    folds[["fold", "n", "rmse_lgbm", "rmse_cams", "p", "p_holm", "sig_holm_05"]].to_csv(
        TABLES / "t6_07_per_fold_holm.csv", index=False
    )

    print(f"wrote {OUT} and t6_07_per_fold_holm.csv\n")
    print("PRIMARY (unit of generalisation = city, n = 6):")
    for r in rows:
        if r["analysis"] != "PRIMARY":
            continue
        print(f"  {r['test']:<44} p = {r['p']:.4f}")
    print("\nSENSITIVITY:")
    for r in rows:
        if r["analysis"] != "SENSITIVITY":
            continue
        print(f"  {r['test']:<62} p = {r['p']:.3g}")
    print(f"\nper-city mean loss differential (negative favours the model):")
    for c, v in city_means.items():
        print(f"  {c:<10} {v:+10.2f}")
    print(f"\nHolm-adjusted per-fold: {int(folds.sig_holm_05.sum())}/{m} significant at 0.05")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
