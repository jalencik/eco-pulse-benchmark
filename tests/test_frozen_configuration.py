"""The production model configuration is frozen, and selection never saw the test block.

WHY THIS FILE EXISTS
--------------------
The target transform (`log1p`) was chosen after the first corrected results were in hand. That
is exactly the situation in which a configuration can drift from "selected on validation" to
"selected because it won on test" without anyone intending it. These tests pin the properties
that make the choice defensible:

  * selection ran on the VALIDATION block only, and the selecting script never reads test;
  * the production scripts fit the transform that selection actually chose;
  * tuning and production optimise the SAME objective;
  * phase 5 and phase 6 apply it identically, so the two sections remain one model.

The validation evidence itself is banked in `t5_03_formulation_search_val.csv` and is part of
the audit trail, not a claim in prose.
"""

from __future__ import annotations

import ast
import pathlib

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEARCH = ROOT / "scripts" / "experiment_model_search.py"
PHASE5 = ROOT / "scripts" / "train_phase5.py"
PHASE6 = ROOT / "scripts" / "phase6_analysis.py"
VAL_TABLE = ROOT / "paper" / "tables" / "t5_03_formulation_search_val.csv"


def _code(path: pathlib.Path) -> str:
    """Source with comments and docstrings stripped, so prose cannot satisfy a check."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(
            node
        ):
            node.body = node.body[1:]
    return ast.unparse(tree)


def test_selection_script_never_reads_the_test_block():
    """The formulation search must be blind to test, or the winner is not pre-specified."""
    code = _code(SEARCH)
    for forbidden in ("te_lo", "te_hi", "t6_01_predictions", "test_start"):
        assert forbidden not in code, (
            f"experiment_model_search.py references `{forbidden}`; selection would have seen "
            "the test block and the frozen configuration would not be pre-specified"
        )
    assert "va_lo" in code and "va_hi" in code, "selection must score on the validation block"


def test_validation_evidence_is_banked():
    if not VAL_TABLE.exists():
        pytest.skip("formulation search not yet run")
    df = pd.read_csv(VAL_TABLE)
    assert {"model", "form", "fold", "rmse"} <= set(df.columns)
    forms = set(df.form.unique())
    assert {"raw", "log"} <= forms, f"the selected and previous forms must both be scored: {forms}"
    # The chosen configuration must actually be the validation winner among LightGBM forms.
    lgbm = df[df.model == "lgbm"]
    per_form = lgbm.groupby("form").apply(
        lambda g: g.groupby("fold").rmse.mean().mean(), include_groups=False
    )
    assert per_form.idxmin() == "log", (
        f"log is not the validation winner for LightGBM ({per_form.to_dict()}); the frozen "
        "production transform must be the one selection chose"
    )


def test_production_fits_the_selected_transform():
    for path in (PHASE5, PHASE6):
        code = _code(path)
        assert "log1p" in code, f"{path.name} does not fit the frozen log1p target"
        assert "expm1" in code, f"{path.name} does not invert the transform before scoring"


def test_tuning_and_production_share_one_objective():
    """Selecting hyperparameters under a different objective picks for the wrong problem."""
    tree = ast.parse(PHASE5.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "tune")
    body = ast.unparse(fn)
    assert "log1p" in body, "tune() does not optimise the log objective the model is fitted on"


def test_predictions_are_physically_valid():
    """expm1 of a low prediction can undershoot; concentrations may not be negative."""
    f = ROOT / "paper" / "tables" / "t6_01_predictions_task_n.csv"
    if not f.exists():
        pytest.skip("predictions not generated yet")
    pred = pd.read_csv(f)
    cols = [c for c in pred.columns if c.startswith("lgbm")]
    for c in cols:
        assert (pred[c] >= 0).all(), f"{c} contains negative PM2.5"
