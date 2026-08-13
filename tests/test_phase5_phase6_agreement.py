"""Section 5 and Section 6 must describe ONE fitted model.

WHY THIS FILE EXISTS
--------------------
The abstract welds Section 5's RMSE to Section 6's Diebold-Mariano p-value in a single
sentence. That is only honest if the two sections report the same fit. They did not:

1. `phase6_analysis.py` trained on `date <= va_hi`, which swallowed the 10-day
   `purge_train_val` block that `train_phase5.py` deliberately withholds -- 9 extra days.
2. After fixing (1) the fits still differed, because phase 5 builds its training frame as
   `concat([train, val])` while phase 6 used a boolean mask. Same rows, different ORDER --
   and LightGBM's `subsample=0.8, subsample_freq=1` bags by row position, so row order
   changes the fitted model even at an identical seed.

A reviewer (R1) detected the symptom as a Jensen-bound violation and concluded the tables
were irreconcilable. They were reconcilable; the cause was fit divergence, not fabrication.

These tests pin both invariants so the sections cannot silently drift apart again.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLES = ROOT / "paper" / "tables"

TIER = "retrospective"  # the tier Section 6 analyses


@pytest.fixture(scope="module")
def preds() -> pd.DataFrame:
    return pd.read_csv(TABLES / "t6_01_predictions_task_n.csv")


@pytest.fixture(scope="module")
def loco() -> pd.DataFrame:
    t5 = pd.read_csv(TABLES / "t5_02_loco_tuned.csv")
    return t5[(t5.task == "N") & (t5.tier == TIER) & (t5.model == "lgbm_tuned")]


def _seed_cols(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.startswith("lgbm_seed"))


def _rmse(y: pd.Series, yhat: pd.Series) -> float:
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def test_per_seed_predictions_are_banked(preds):
    """Without per-seed columns the Jensen bound is only checkable across files.

    Checking it across two separately-fitted runs is exactly what produced a false positive.
    """
    cols = _seed_cols(preds)
    assert len(cols) == 5, f"expected 5 banked seed columns, found {cols}"


def test_jensen_bound_holds_within_a_single_run(preds):
    """RMSE(mean of members) <= quadratic mean of member RMSEs, by convexity.

    Unconditional for one model on one row set, so a violation means the aggregate and the
    members are not the same fit.
    """
    cols = _seed_cols(preds)
    for fold, g in preds.groupby("fold"):
        per_seed = np.array([_rmse(g.pm25, g[c]) for c in cols])
        bound = float(np.sqrt(np.mean(per_seed**2)))
        ensemble = _rmse(g.pm25, g.lgbm)
        assert ensemble <= bound + 1e-9, (
            f"{fold}: ensemble RMSE {ensemble:.4f} exceeds the quadratic-mean bound "
            f"{bound:.4f}. The banked ensemble is not the mean of the banked seeds."
        )


def test_ensemble_column_is_the_mean_of_the_seed_columns(preds):
    cols = _seed_cols(preds)
    recomputed = preds[cols].mean(axis=1)
    assert np.allclose(preds.lgbm, recomputed, atol=1e-9), (
        "the `lgbm` column is not the row-wise mean of the banked per-seed columns"
    )


def test_section5_and_section6_report_the_same_fit(preds, loco):
    """The load-bearing test: every fold-seed RMSE must agree to floating point.

    Section 5 evaluates the fit; Section 6 re-fits from the same hyperparameters. If the two
    disagree, the abstract is combining metrics from two different models.
    """
    cols = _seed_cols(preds)
    checked = 0
    for _, row in loco.iterrows():
        g = preds[preds.fold == row.held_out_city]
        assert not g.empty, f"no Section 6 predictions for fold {row.held_out_city}"
        col = f"lgbm_seed{int(row.seed)}"
        assert col in cols, f"{col} not banked"
        got = _rmse(g.pm25, g[col])
        assert got == pytest.approx(row.rmse, abs=1e-9), (
            f"{row.held_out_city} seed {int(row.seed)}: Section 5 reports RMSE {row.rmse:.6f}, "
            f"Section 6 produces {got:.6f}. The sections describe different fits."
        )
        checked += 1
    assert checked == 30, f"expected 30 fold-seed pairs, checked {checked}"


def test_evaluation_row_counts_match_between_sections(preds, loco):
    for _, row in loco.drop_duplicates("held_out_city").iterrows():
        n6 = int((preds.fold == row.held_out_city).sum())
        assert n6 == int(row.n), (
            f"{row.held_out_city}: Section 5 scored {int(row.n)} rows, Section 6 scored {n6}"
        )


def test_phase6_excludes_the_purge_block():
    """Guard the specific regression: `date <= va_hi` swallows purge_train_val."""
    src = (ROOT / "scripts" / "phase6_analysis.py").read_text(encoding="utf-8")
    code = "\n".join(line.split("#")[0] for line in src.splitlines())
    # Match the training frame specifically. A bare `sp.date <= va_hi` also appears in the
    # legitimate upper bound of the validation block, so the check must be narrower than that.
    assert "tr = sp[(sp.city != held) & (sp.date <= va_hi)" not in code, (
        "phase6 builds its training frame as `date <= va_hi`, which includes the 10-day "
        "purge_train_val block that phase 5 withholds -- the sections would describe "
        "different models"
    )
    assert "pd.concat([tr_block, va_block])" in code, (
        "phase6 must build its training frame as concat([train, val]) to match phase 5's row "
        "ORDER; LightGBM's row subsampling makes order affect the fit"
    )
