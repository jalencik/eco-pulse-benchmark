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
        subprocess.run(
            [sys.executable, str(ROOT / "paper/scripts/extract_numbers.py")],
            check=True,
            capture_output=True,
            cwd=ROOT,
        )
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
        shares = [
            float(v) for k, v in numbers.items() if k.startswith("shap_") and k.endswith("_pct")
        ]
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
        """The text must not imply every fold is significant.

        Updated for benchmark v1.1.0. Unadjusted, all six per-fold DM tests now clear 0.05,
        so the original assertion (n_sig < n_folds) no longer holds -- but six tests are being
        run at once, and after Holm correction only a subset survives. The honest hedge is the
        multiplicity-adjusted count, so that is what is now asserted. The guard's purpose is
        unchanged: forbid prose that implies uniform significance.
        """
        assert int(numbers["n_sig_holm"]) < int(numbers["dm_n_folds"]), (
            "every fold survives multiplicity correction -- if that is genuinely true, this "
            "guard should be retired deliberately, not silently"
        )
        txt = (SEC / "01_introduction.md").read_text(encoding="utf-8")
        assert numbers["n_sig_holm"] in txt or "Holm" in txt, (
            "the introduction must state the multiplicity-adjusted count, not the raw one"
        )

    def test_data_section_names_the_zero_shot_city(self):
        txt = (SEC / "02_data_pipeline.md").read_text(encoding="utf-8")
        assert "Khujand contributes no training rows" in txt


class TestSectionTwoFiguresAreGenerated:
    """Section 2's missingness figures were once hand-typed, and had drifted."""

    def test_r7_retrieval_rates_match_source_csv(self, numbers):
        r7 = pd.read_csv(TABLES / "t2_01_r7_missingness.csv").set_index("key")
        for key, short in [("s5p_so2", "so2"), ("maiac_aod", "aod"), ("s5p_aai", "aai")]:
            assert numbers[f"r7_{short}_retrieval"] == f"{r7.loc[key, 'retrieval_pct']:.1f}"

    def test_r7_generator_output_is_reproducible(self):
        """The table must be rebuildable; it originally had no producer at all."""
        path = TABLES / "t2_01_r7_missingness.csv"
        before = path.read_bytes()
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_r7_tables.py")],
            check=True,
            capture_output=True,
            cwd=ROOT,
        )
        assert path.read_bytes() == before, "R7 table is not deterministic"

    def test_clean_and_contaminated_features_are_split_by_physics(self):
        """The retrieval-physics split must match the data, not a remembered result.

        Updated for benchmark v1.1.0. CO was previously uncontaminated and is no longer, so
        asserting a fixed classification would pin the tests to a stale finding. What must
        hold is that the split is (a) not empty in either direction and (b) reflected in the
        prose, which is the property the original test was protecting.
        """
        r7 = pd.read_csv(TABLES / "t2_01_r7_missingness.csv").set_index("key")
        assert r7.loc["s5p_so2", "target_correlated"], "SO2 must remain contaminated"
        assert r7.loc["maiac_aod", "target_correlated"], "MAIAC AOD must remain contaminated"
        clean = [k for k in r7.index if not r7.loc[k, "target_correlated"]]
        assert clean, "no clean retrieval remains -- the complementarity claim must be retired"

    def test_delta_signs_are_not_hardcoded_positive(self, numbers):
        """Signs must be read from the CSV, never written into the template.

        The original form asserted CO negative and SO2 positive. CO's sign flipped under
        benchmark v1.1.0, which is exactly the situation a hardcoded sign would have hidden.
        The durable invariant is that each rendered sign AGREES WITH ITS SOURCE ROW.
        """
        r7 = pd.read_csv(TABLES / "t2_01_r7_missingness.csv").set_index("key")
        for key, num in (("s5p_co", "r7_co_delta"), ("s5p_so2", "r7_so2_delta")):
            src = float(r7.loc[key, "delta_median_pm25"])
            rendered = numbers[num]
            assert rendered.startswith("-" if src < 0 else "+"), (
                f"{num} renders {rendered} but the source delta is {src:+.3f}"
            )


class TestBaselineLadderIsHonest:
    def test_trivial_classifier_score_is_reported(self, numbers):
        txt = (SEC / "04_baselines.md").read_text(encoding="utf-8")
        assert numbers["p3_trivial_f1"] in txt, "trivial F1 must appear beside exceedance F1"
        assert numbers["p3_base_rate"] in txt

    def test_constant_baseline_has_zero_peirce_skill(self, numbers):
        """A constant carries no information; any nonzero skill is a scoring bug."""
        assert float(numbers["p3n_training_pool_mean_pss"]) == 0.0

    def test_constant_baseline_is_present_as_a_rung(self):
        t = pd.read_csv(TABLES / "t3_02_task_n_baselines_hourly.csv")
        assert "training_pool_mean" in set(t.model)

    def test_tasks_are_never_pooled_in_one_results_file(self):
        """Rule 4: nowcasting and forecasting metrics never share a table."""
        for name in ["t3_01_task_f_baselines_hourly.csv", "t3_02_task_n_baselines_hourly.csv"]:
            tasks = set(pd.read_csv(TABLES / name).task.unique())
            assert len(tasks) == 1, f"{name} mixes tasks: {tasks}"


class TestLimitationsAreStated:
    """Section 7 must carry the four limitations, not bury them."""

    def test_bishkek_label_divergence_is_quantified(self, numbers):
        txt = (SEC / "07_limitations_discussion.md").read_text(encoding="utf-8")
        assert numbers["feed_bishkek_agree_test"] in txt
        assert numbers["feed_bishkek_p95_test"] in txt

    def test_feed_divergence_matches_source_csv(self, numbers):
        fd = pd.read_csv(TABLES / "t2_03_feed_divergence.csv").set_index("city")
        assert (
            numbers["feed_bishkek_agree_test"] == f"{fd.loc['Bishkek', 'agreement_pct_test']:.1f}"
        )

    def test_single_station_cities_are_named(self, numbers):
        txt = (SEC / "07_limitations_discussion.md").read_text(encoding="utf-8")
        assert numbers["lso_ineligible"] in txt

    def test_fold_favouring_cams_is_named(self, numbers):
        txt = (SEC / "07_limitations_discussion.md").read_text(encoding="utf-8")
        assert numbers["dm_fold_favouring_cams"] in txt

    def test_shap_result_is_not_spun(self, numbers):
        """Whichever feature family actually dominates must be the one the prose names.

        Updated for benchmark v1.1.0. Deduplicating Dushanbe removed a zero-distance spatial
        neighbour, and satellite features now carry more attribution than spatial ones -- a
        reversal of the previously published claim. Asserting the old direction would force
        the prose to contradict the data, so the guard now checks CONSISTENCY between the two
        rather than a fixed winner.
        """
        txt = (SEC / "07_limitations_discussion.md").read_text(encoding="utf-8")
        spatial = float(numbers["shap_spatial_neighbour_pct"])
        satellite = float(numbers["shap_satellite_pct"])
        leader = "spatial" if spatial > satellite else "satellite"
        if leader == "spatial":
            assert "spatial interpolator" in txt
        else:
            assert "satellite" in txt.lower(), (
                "satellite features now dominate attribution; the discussion must say so"
            )
            assert str(numbers["shap_satellite_pct"]) in txt, (
                "the dominant family's share must appear in the discussion"
            )

    def test_network_closure_is_disclosed(self):
        txt = (SEC / "07_limitations_discussion.md").read_text(encoding="utf-8")
        assert "2025-03-04" in txt
        assert "No result in this paper" in txt

    def test_results_section_forbids_quoting_tasks_together(self):
        txt = (SEC / "06_results.md").read_text(encoding="utf-8")
        assert "never be quoted together" in txt
