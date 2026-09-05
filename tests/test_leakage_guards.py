"""Leakage assertions: no test-period information may reach training in any form.

These are deliberately written against the FROZEN SPLITS and the PRODUCER SOURCE, not against
a particular run's outputs, so they fail when someone changes the pipeline rather than only
when a specific artefact happens to be stale.

Leakage is the one defect class that cannot be detected by looking at results: a leaked model
simply looks good. So the guards have to be structural.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPLITS = ROOT / "benchmark" / "splits" / "splits.json"
TABLES = ROOT / "paper" / "tables"

pytestmark = pytest.mark.skipif(not SPLITS.exists(), reason="splits not frozen yet")


@pytest.fixture(scope="module")
def splits() -> dict:
    return json.loads(SPLITS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def blocks(splits) -> dict:
    return {b["name"]: b for b in splits["temporal_blocks"]}


def _ts(v: str) -> pd.Timestamp:
    return pd.Timestamp(v).tz_localize(None) if pd.Timestamp(v).tzinfo is None else pd.Timestamp(v)


# --------------------------------------------------------------------------- split integrity


def test_temporal_blocks_are_ordered_and_disjoint(blocks):
    order = ["train", "purge_train_val", "val", "purge_val_test", "test", "reserved_post_test"]
    prev_end = None
    for name in order:
        b = blocks[name]
        start, end = _ts(b["start"]), _ts(b["end"])
        assert start < end, f"{name}: start is not before end"
        if prev_end is not None:
            assert start > prev_end, f"{name} starts at {start}, overlapping the previous block"
        prev_end = end


def test_purge_gaps_separate_every_adjacent_pair(blocks):
    """A purge gap that is present but zero-width is not a purge gap."""
    for gap, before, after in [
        ("purge_train_val", "train", "val"),
        ("purge_val_test", "val", "test"),
    ]:
        assert _ts(blocks[gap]["start"]) > _ts(blocks[before]["end"])
        assert _ts(blocks[after]["start"]) > _ts(blocks[gap]["end"])
        width_h = (_ts(blocks[gap]["end"]) - _ts(blocks[gap]["start"])).total_seconds() / 3600
        assert width_h >= 24, f"{gap} is only {width_h} h wide"


def test_purge_gap_covers_the_declared_feature_lag(splits, blocks):
    """The gap must be at least as long as the longest feature reach.

    Otherwise a training row's own features overlap the test block even though its label
    does not -- leakage through the feature window rather than through the label.
    """
    purge_h = splits["config"]["purge_hours"]
    max_lag = splits["config"]["max_lag_hours"]
    max_hor = splits["config"]["max_horizon_hours"]
    assert purge_h >= max_lag + max_hor, (
        f"purge {purge_h} h is shorter than max_lag {max_lag} + max_horizon {max_hor}"
    )
    for gap in ("purge_train_val", "purge_val_test"):
        width_h = (_ts(blocks[gap]["end"]) - _ts(blocks[gap]["start"])).total_seconds() / 3600 + 1
        # Both quantities are in hours. An earlier version of this assertion compared hours
        # to purge_h / 24 and carried a second clause that could not fail.
        assert width_h >= purge_h, (
            f"{gap} width {width_h} h does not cover the declared purge {purge_h} h"
        )


# --------------------------------------------------------------------------- fold integrity


def test_leave_city_out_folds_never_train_on_the_held_out_city(splits):
    city_of = {str(s["station_id"]): s["city"] for s in splits["stations"]}
    for fold in splits["leave_city_out"]:
        held = fold["held_out_city"]
        train_cities = {city_of[str(s)] for s in fold["train_stations"]}
        assert held not in train_cities, (
            f"fold {fold['fold']}: held-out city {held} also appears in training"
        )
        held_ids = {str(s) for s in fold["held_out_stations"]}
        assert held_ids.isdisjoint({str(s) for s in fold["train_stations"]}), (
            f"fold {fold['fold']}: a station is in both train and held-out"
        )


def test_leave_station_out_folds_never_train_on_the_held_out_station(splits):
    for fold in splits["leave_station_out"]["folds"]:
        assert str(fold["held_out_station"]) not in {str(s) for s in fold["train_stations"]}


# ------------------------------------------------------------------ evaluation-set integrity


def test_predictions_fall_entirely_inside_the_test_block(blocks):
    f = TABLES / "t6_01_predictions_task_n.csv"
    if not f.exists():
        pytest.skip("predictions not generated yet")
    pred = pd.read_csv(f, parse_dates=["date"])
    lo, hi = (
        _ts(blocks["test"]["start"]).tz_localize(None),
        _ts(blocks["test"]["end"]).tz_localize(None),
    )
    assert pred.date.min() >= lo, f"prediction dated {pred.date.min()} precedes the test block"
    assert pred.date.max() <= hi, f"prediction dated {pred.date.max()} follows the test block"


def test_every_evaluated_station_is_a_benchmark_station(splits):
    f = TABLES / "t6_01_predictions_task_n.csv"
    if not f.exists():
        pytest.skip("predictions not generated yet")
    pred = pd.read_csv(f, dtype={"station_id": str})
    known = {str(s["station_id"]) for s in splits["stations"]}
    assert set(pred.station_id) <= known, f"unknown stations: {set(pred.station_id) - known}"


def test_each_fold_only_evaluates_its_own_held_out_city(splits):
    f = TABLES / "t6_01_predictions_task_n.csv"
    if not f.exists():
        pytest.skip("predictions not generated yet")
    pred = pd.read_csv(f, dtype={"station_id": str})
    city_of = {str(s["station_id"]): s["city"] for s in splits["stations"]}
    for fold, g in pred.groupby("fold"):
        cities = {city_of[s] for s in g.station_id}
        assert cities == {fold}, f"fold {fold} evaluates stations from {cities}"


# -------------------------------------------------------------------------- source-level guards


def test_tuning_never_consults_the_test_block():
    """Hyperparameters must be selected on validation only."""
    # Extract the function with ast rather than string slicing: `tune` is the last def in the
    # file, so splitting on the next "\ndef " swallowed the whole module-level training loop
    # and produced a false positive on the test-block bounds used there legitimately.
    import ast

    src = (ROOT / "scripts" / "train_phase5.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "tune"), None)
    assert fn is not None, "train_phase5.py no longer defines tune()"
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    for forbidden in ("te", "te_lo", "te_hi"):
        assert forbidden not in names, (
            f"tune() references `{forbidden}` -- hyperparameters must not see the test block"
        )
    # and it must actually consult the validation frame
    assert "va" in names, "tune() does not reference the validation frame"


def test_cams_bias_is_fitted_on_the_training_block_only():
    """The CAMS reference is what every model is measured against.

    A bias fitted over the full record would smuggle test-period information into the
    baseline itself, inflating the entire ladder without any model changing.
    """
    src = (ROOT / "src" / "ecopulse_ca" / "models" / "cams_baseline.py").read_text(encoding="utf-8")
    assert "joined[joined.index <= train_end.date()]" in src, (
        "fit_bias no longer restricts to the training block"
    )
    for caller in ("scripts/train_phase5.py", "scripts/phase6_analysis.py"):
        text = (ROOT / caller).read_text(encoding="utf-8")
        if "fit_bias(" in text:
            assert (
                "fit_bias(cams, daily_obs, tr_end)" in text
                or "fit_bias(cams, observed, tr_end)" in text
            ), f"{caller} calls fit_bias with something other than the train-block end"


def test_pooled_debias_excludes_the_held_out_city():
    """Task N's CAMS variant must not use labels from the city it is scoring."""
    src = (ROOT / "src" / "ecopulse_ca" / "models" / "cams_baseline.py").read_text(encoding="utf-8")
    body = src.split("def apply_pooled_debias(")[1]
    assert "if s not in held_out" in body, (
        "apply_pooled_debias no longer excludes held-out stations from the bias average"
    )
