"""Robustness of the ladder ranking: is "lowest RMSE" stable, or an artefact of six cities?

A fold-mean is a mean over {{n}} = 6 numbers. Reporting that the learned model has the lowest
one, without asking how that ordering behaves when a single city is removed, would overstate
what a six-city sample can support. This script asks the three questions a skeptical reviewer
asks first, and banks the answers whatever they are.

REPORTING, NOT SELECTION. Nothing here changes the frozen configuration.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = ROOT / "paper" / "tables"
OUT = T / "t7_05_ranking_robustness.csv"


def main() -> int:
    t5 = pd.read_csv(T / "t5_02_loco_tuned.csv")
    model = (
        t5[(t5.task == "N") & (t5.tier == "retrospective") & (t5.model == "lgbm_tuned")]
        .groupby("held_out_city")
        .rmse.mean()
    )
    seed_spread = (
        t5[(t5.task == "N") & (t5.tier == "retrospective") & (t5.model == "lgbm_tuned")]
        .groupby("seed")
        .apply(lambda g: g.groupby("held_out_city").rmse.mean().mean(), include_groups=False)
    )
    lad = pd.read_csv(T / "t3_06_task_n_baselines_daily.csv")
    legal = lad[lad.legal] if "legal" in lad.columns else lad
    rivals = {m: g.groupby("fold").rmse.mean() for m, g in legal.groupby("model")}

    rows = []
    for name, rival in rivals.items():
        common = model.index.intersection(rival.index)
        d = (model[common] - rival[common]).dropna()
        t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d))))
        p = float(2 * stats.t.sf(abs(t), len(d) - 1))
        # leave-one-city-out: does the model still lead without any single city?
        leads = sum(
            1 for c in common if model[common].drop(c).mean() < rival[common].drop(c).mean()
        )
        rows.append(
            {
                "rival": name,
                "model_rmse": float(model[common].mean()),
                "rival_rmse": float(rival[common].mean()),
                "margin": float(rival[common].mean() - model[common].mean()),
                "folds_model_better": int((d < 0).sum()),
                "n_folds": int(len(d)),
                "paired_t": t,
                "paired_p": p,
                "loco_subsets_model_leads": leads,
                "margin_over_seed_sd": float(
                    (rival[common].mean() - model[common].mean()) / seed_spread.std(ddof=1)
                ),
            }
        )
    out = pd.DataFrame(rows).sort_values("rival_rmse")
    out.to_csv(OUT, index=False)

    print(f"wrote {OUT.name}\n")
    print("=== RANKING ROBUSTNESS vs each LEGAL baseline ===")
    cols = ["rival", "model_rmse", "rival_rmse", "margin", "folds_model_better", "paired_p",
            "loco_subsets_model_leads", "margin_over_seed_sd"]
    print(out[cols].round(3).to_string(index=False))

    strongest = out.iloc[0]
    print(f"\nAgainst the strongest rival ({strongest.rival}):")
    print(f"  margin {strongest.margin:+.2f} ug/m3, paired p = {strongest.paired_p:.3f}, "
          f"leads in {int(strongest.loco_subsets_model_leads)}/{int(strongest.n_folds)} "
          f"leave-one-city-out subsets")
    print(f"  seed SD = {seed_spread.std(ddof=1):.3f}; margin is "
          f"{strongest.margin_over_seed_sd:.1f}x seed noise")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
