"""The leave-Khujand-out sensitivity must exist, regenerate, and agree with the manuscript.

Khujand supplies roughly a quarter of every row-level statistic in the paper while being the
one city the manuscript calls incomparable in kind. That combination is the sharpest objection
available against the pooled numbers, so the sensitivity that answers it has to stay wired in
and stay honest. These tests fail if the analysis stops regenerating, if its verdict changes
without the prose changing, or if the permutation floor caveat quietly stops applying.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLE = ROOT / "paper" / "tables" / "t7_06_leave_khujand_out.csv"
NUMBERS = ROOT / "paper" / "numbers.json"


@pytest.fixture(scope="module")
def sens() -> pd.DataFrame:
    if not TABLE.exists():
        pytest.skip("run scripts/build_khujand_sensitivity.py")
    return pd.read_csv(TABLE).set_index("set")


class TestSensitivityExists:
    def test_both_arms_are_present(self, sens):
        assert "all_cities" in sens.index
        assert "excluding_Khujand" in sens.index

    def test_the_excluded_arm_really_dropped_a_city(self, sens):
        assert sens.loc["excluding_Khujand"].n_cities == sens.loc["all_cities"].n_cities - 1
        assert sens.loc["excluding_Khujand"].n_rows < sens.loc["all_cities"].n_rows

    def test_khujand_share_is_material_enough_to_need_this(self, sens):
        """If the share ever drops below a fifth, the framing in 7.4c needs revisiting."""
        assert float(sens.loc["all_cities"].excluded_city_row_share) > 0.2


class TestVerdictMatchesTheManuscript:
    def test_verdict_is_one_of_the_declared_three(self, sens):
        assert sens.loc["all_cities"].verdict in {"ROBUST", "WEAKENED", "CHANGED"}

    def test_numbers_json_carries_the_same_verdict(self, sens):
        """The prose says {{kho_verdict}}. If the table and numbers.json disagree, the
        rendered manuscript is asserting a robustness it did not measure."""
        nums = json.loads(NUMBERS.read_text(encoding="utf-8"))
        assert nums["kho_verdict"] == sens.loc["all_cities"].verdict

    def test_neither_arm_reaches_significance(self, sens):
        """The manuscript states the negative result holds with and without Khujand. If this
        ever fails, Sections 6.2b, 6.5, 7.3, 7.4c, the abstract and the conclusion all need
        rewriting - the paper would then have a positive result it does not currently claim."""
        for arm in ("all_cities", "excluding_Khujand"):
            assert not bool(sens.loc[arm].sig_paired_t), arm
            assert not bool(sens.loc[arm].sig_permutation), arm


class TestThePermutationFloorCaveat:
    def test_five_city_floor_is_above_alpha(self, sens):
        """7.4c tells the reader the five-city permutation test cannot be significant at any
        effect size. That claim is only true while the floor exceeds 0.05."""
        assert float(sens.loc["excluding_Khujand"].permutation_floor) > 0.05

    def test_six_city_floor_is_below_alpha(self, sens):
        """And the six-city test can be, which is why it is worth reporting at all."""
        assert float(sens.loc["all_cities"].permutation_floor) < 0.05
