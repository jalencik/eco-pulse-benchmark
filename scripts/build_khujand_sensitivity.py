"""Leave-Khujand-out sensitivity for every pooled claim in the paper.

WHY THIS EXISTS
---------------
Khujand is the only two-station city in the benchmark, so it contributes far more rows to any
row-level statistic than any other city. It is also the one city the manuscript declares
*incomparable in kind*: both its instruments are Clarity low-cost optical sensors, every other
city is a US-embassy reference monitor, and it is the zero-label fold that carries part of the
paper's transfer argument.

Those two facts together are the sharpest objection available to a reviewer. The paper says
the fold is not comparable and then includes it, unqualified, in every pooled number it
reports. Until this script existed, nothing in the repository measured what the pooled
result would be without it, so the answer was unknown rather than reassuring.

WHAT IT COMPUTES
----------------
The same estimands as `build_significance.py`, on the same row-level predictions and with the
same squared-error loss differential, computed twice: over all six folds, and over the five
reference-grade folds with Khujand removed.

  * pooled RMSE for the model and for bias-corrected CAMS
  * the paired t-test on city means, which is the paper's primary analysis
  * the exact sign-flip permutation test over cities
  * each city's share of the pooled row count

Removing a city changes the permutation floor, and that is reported rather than hidden: with
six cities the smallest attainable two-sided p is 2/2^6 = 0.03125; with five it is
2/2^5 = 0.0625. A five-city permutation test therefore *cannot* return a significant result at
alpha = 0.05 no matter how large the effect. That is a property of the design, not a finding,
and a reader who is not told will misread the sensitivity as a collapse in evidence.

The verdict is classified mechanically so the prose cannot overstate it:

  ROBUST      both primary tests keep the same significance verdict, and the sign of the
              mean differential is unchanged
  WEAKENED    the verdict is unchanged but the effect moves materially (>50% of the
              full-sample mean differential)
  CHANGED     a primary test flips its significance verdict, or the sign reverses

Deterministic: no sampling, no randomness, exact enumeration over 2^G sign assignments.
"""

from __future__ import annotations

import itertools
import pathlib
import sys

import numpy as np
import pandas as pd
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLES = ROOT / "paper" / "tables"
OUT = TABLES / "t7_06_leave_khujand_out.csv"
EXCLUDED = "Khujand"
ALPHA = 0.05


def _loss_differential(df: pd.DataFrame) -> pd.Series:
    """Squared-error differential, model minus CAMS. Negative favours the model.

    Identical to build_significance.py by construction; if that definition changes, this
    sensitivity stops being comparable to the primary analysis it is a sensitivity for.
    """
    return (df.pm25 - df.lgbm) ** 2 - (df.pm25 - df.pooled) ** 2


def _rmse(obs: pd.Series, pred: pd.Series) -> float:
    return float(np.sqrt(((obs - pred) ** 2).mean()))


def _analyse(pred: pd.DataFrame, label: str) -> dict:
    city_means = pred.groupby("fold")["d"].mean()
    g = len(city_means)
    mean_d = float(city_means.mean())
    se = float(city_means.std(ddof=1) / np.sqrt(g))
    t_stat = mean_d / se
    p_t = float(2 * stats.t.sf(abs(t_stat), df=g - 1))

    # Exact sign-flip permutation over cities, all 2^g assignments.
    signs = list(itertools.product([-1, 1], repeat=g))
    obs = abs(mean_d)
    perm = [abs(float(np.mean(np.array(s) * city_means.to_numpy()))) for s in signs]
    p_perm = float(np.mean([v >= obs - 1e-12 for v in perm]))
    perm_floor = 2.0 / len(signs)

    return {
        "set": label,
        "n_cities": g,
        "n_rows": int(len(pred)),
        "rmse_model": _rmse(pred.pm25, pred.lgbm),
        "rmse_cams": _rmse(pred.pm25, pred.pooled),
        "mean_loss_differential": mean_d,
        "t_stat": t_stat,
        "p_paired_t": p_t,
        "p_permutation": p_perm,
        "permutation_floor": perm_floor,
        "sig_paired_t": bool(p_t < ALPHA),
        "sig_permutation": bool(p_perm < ALPHA),
    }


def main() -> int:
    pred = pd.read_csv(TABLES / "t6_01_predictions_task_n.csv", dtype={"station_id": str})
    pred["d"] = _loss_differential(pred)

    if EXCLUDED not in set(pred.fold):
        print(f"FAILED: fold {EXCLUDED!r} not present in t6_01", file=sys.stderr)
        return 1

    full = _analyse(pred, "all_cities")
    excl = _analyse(pred[pred.fold != EXCLUDED].copy(), f"excluding_{EXCLUDED}")

    # Verdict, decided by rule rather than by reading.
    flipped = (full["sig_paired_t"] != excl["sig_paired_t"]) or (
        full["sig_permutation"] != excl["sig_permutation"]
    )
    sign_reversed = np.sign(full["mean_loss_differential"]) != np.sign(
        excl["mean_loss_differential"]
    )
    moved = abs(excl["mean_loss_differential"] - full["mean_loss_differential"]) > 0.5 * abs(
        full["mean_loss_differential"]
    )
    verdict = "CHANGED" if (flipped or sign_reversed) else ("WEAKENED" if moved else "ROBUST")

    rows = [full, excl]
    for r in rows:
        r["verdict"] = verdict
    out = pd.DataFrame(rows)

    share = pred.groupby("fold").size() / len(pred)
    out["excluded_city_row_share"] = float(share[EXCLUDED])

    TABLES.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print(f"wrote {OUT}")
    print(f"\n  {EXCLUDED} contributes {100 * share[EXCLUDED]:.1f}% of the {len(pred)} pooled rows")
    print("\n  city row shares:")
    for c, v in share.sort_values(ascending=False).items():
        print(f"    {c:<10} {100 * v:5.1f}%")
    print()
    hdr = f"  {'':<22}{'all cities':>14}{'excl. ' + EXCLUDED:>18}"
    print(hdr)
    for key, fmt in [
        ("n_cities", "d"),
        ("n_rows", "d"),
        ("rmse_model", ".2f"),
        ("rmse_cams", ".2f"),
        ("mean_loss_differential", ".1f"),
        ("p_paired_t", ".4f"),
        ("p_permutation", ".4f"),
        ("permutation_floor", ".4f"),
    ]:
        a = format(full[key], fmt)
        b = format(excl[key], fmt)
        print(f"  {key:<22}{a:>14}{b:>18}")
    print(f"\n  VERDICT: {verdict}")
    if excl["permutation_floor"] > ALPHA:
        print(
            f"  Note: with {excl['n_cities']} cities the permutation floor is "
            f"{excl['permutation_floor']:.4f}, above alpha = {ALPHA}. That test cannot reach "
            "significance at any effect size, which is a property of the design."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
