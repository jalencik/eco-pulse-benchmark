"""The manuscript's figures must come from the banked CSVs, not from typing.

Every quoted statistic is a {{placeholder}} substituted at render time from numbers.json,
which is itself extracted from paper/tables/*.csv. This test enforces the chain end to end,
so a number cannot drift from its source and a stale figure cannot survive a re-run.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "paper" / "sections"
TABLES = ROOT / "paper" / "tables"
NUMBERS = ROOT / "paper" / "numbers.json"
PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

pytestmark = pytest.mark.skipif(not NUMBERS.exists(), reason="numbers.json not generated")


@pytest.fixture(scope="module")
def numbers() -> dict:
    return json.loads(NUMBERS.read_text(encoding="utf-8"))


class TestExtractionChain:
    def test_numbers_json_regenerates_identically(self, numbers):
        """Re-extracting from the CSVs must reproduce the same figures."""
        before = dict(numbers)
        subprocess.run([sys.executable, str(ROOT / "paper/scripts/extract_numbers.py")],
                       check=True, capture_output=True, cwd=ROOT)
        after = json.loads(NUMBERS.read_text(encoding="utf-8"))
        drift = {k for k in before if before[k] != after.get(k)}
        assert not drift, f"figures changed on re-extraction: {sorted(drift)[:10]}"

    def test_every_template_resolves(self):
        """An unresolved placeholder must fail the build, not print itself."""
        for tmpl in SEC.glob("*.md.tmpl"):
            keys = set(PLACEHOLDER.findall(tmpl.read_text(encoding="utf-8")))
            nums = json.loads(NUMBERS.read_text(encoding="utf-8"))
            missing = sorted(keys - set(nums))
            assert not missing, f"{tmpl.name} references unknown figures: {missing}"

    def test_rendered_output_has_no_placeholders_left(self):
        for md in SEC.glob("*.md"):
            left = PLACEHOLDER.findall(md.read_text(encoding="utf-8"))
            assert not left, f"{md.name} still contains placeholders: {left}"

    def test_every_template_has_a_rendered_counterpart(self):
        for tmpl in SEC.glob("*.md.tmpl"):
            assert (SEC / tmpl.name.replace(".md.tmpl", ".md")).exists(), (
                f"{tmpl.name} was never rendered"
            )


class TestFiguresMatchSourceTables:
    """Spot-check headline claims directly against the CSVs, bypassing numbers.json."""

    def test_dm_pooled_matches_table(self, numbers):
        dm = pd.read_csv(TABLES / "t6_02_dm_lgbm_vs_cams.csv")
        pooled = dm[dm.fold == "POOLED"].iloc[0]
        assert numbers["dm_pooled_stat"] == f"{pooled.dm:.2f}"
        assert numbers["rmse_lgbm_pooled"] == f"{pooled.rmse_lgbm:.2f}"

    def test_task_n_headline_matches_table(self, numbers):
        t5 = pd.read_csv(TABLES / "t5_02_loco_tuned.csv")
        g = t5[(t5.task == "N") & (t5.model == "lgbm_tuned") & (t5.tier == "retrospective")]
        assert numbers["taskn_retrospective_rmse"] == f"{g.rmse.mean():.2f}"
        assert numbers["taskn_retrospective_r2"] == f"{g.r2.mean():.2f}"

    def test_shap_shares_sum_to_100(self, numbers):
        shares = [float(v) for k, v in numbers.items() if k.startswith("shap_") and
                  k.endswith("_pct")]
        assert abs(sum(shares) - 100.0) < 0.5, f"SHAP families sum to {sum(shares)}"

    def test_benchmark_shape_matches_frozen_splits(self, numbers):
        sp = json.loads((ROOT / "benchmark/splits/splits.json").read_text(encoding="utf-8"))
        assert numbers["n_stations"] == str(len(sp["stations"]))
        assert numbers["n_cities"] == str(len({s["city"] for s in sp["stations"]}))
        assert numbers["purge_hours"] == str(sp["config"]["purge_hours"])


class TestClaimsAreHedgedWhereEvidenceIsPartial:
    """Guards specific overclaims this project has already had to walk back."""

    def test_intro_does_not_claim_state_of_the_art(self):
        txt = (SEC / "01_introduction.md").read_text(encoding="utf-8").lower()
        assert "state of the art" in txt, "the disclaimer section must remain"
        assert "we do not claim state of the art" in txt

    def test_intro_records_that_not_all_folds_are_significant(self, numbers):
        """3 of 6 folds are significant; the text must not imply all are."""
        assert int(numbers["dm_n_sig"]) < int(numbers["dm_n_folds"])

    def test_data_section_names_the_zero_shot_city(self):
        txt = (SEC / "02_data_pipeline.md").read_text(encoding="utf-8")
        assert "Khujand contributes no training rows" in txt
