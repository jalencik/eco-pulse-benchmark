"""Co-located feed merging, and Q6 rebuilt per city."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ecopulse_ca.qc.merge import EXACT_TOL, choose_primary, merge_colocated
from ecopulse_ca.qc.timezone import diurnal_composite
from ecopulse_ca.qc.timezone_percity import (
    peak_hours,
    q6_cross_city_informational,
    q6_within_city,
    run_q6_per_city,
)
from tests.conftest import synthetic_pm25


def _pair(shift_b: int = 0, gap_a: slice | None = None, gap_b: slice | None = None):
    a = synthetic_pm25("2022-01-01", "2023-12-31", seed=1)
    b = a.copy() if shift_b == 0 else synthetic_pm25("2022-01-01", "2023-12-31", seed=1) + shift_b
    if gap_a:
        a.iloc[gap_a] = np.nan
    if gap_b:
        b.iloc[gap_b] = np.nan
    return a, b


class TestMergeColocated:
    def test_never_averages_values(self):
        """Two feeds of ONE instrument must never be averaged -- that fabricates a value."""
        a, b = _pair(shift_b=10.0)
        vals, src, _ = merge_colocated(a, b, merged_id="m", primary_id="A", secondary_id="B")
        # Every merged hour equals the primary exactly where the primary reports.
        overlap = a.notna() & b.notna()
        assert np.allclose(vals[overlap], a[overlap])
        assert (src[overlap] == "A").all()

    def test_secondary_fills_only_gaps(self):
        a, b = _pair(gap_a=slice(100, 200))
        vals, src, rep = merge_colocated(a, b, merged_id="m", primary_id="A", secondary_id="B")
        assert (src.iloc[100:200] == "B").all()
        assert rep.n_filled_from_secondary == 100
        assert rep.n_merged > rep.n_primary

    def test_merge_increases_coverage(self):
        a, b = _pair(gap_a=slice(0, 500), gap_b=slice(500, 900))
        _, _, rep = merge_colocated(a, b, merged_id="m", primary_id="A", secondary_id="B")
        assert rep.n_merged > max(rep.n_primary, rep.n_secondary)

    def test_identical_feeds_report_clean_duplicate(self):
        a, b = _pair()
        _, _, rep = merge_colocated(a, b, merged_id="m", primary_id="A", secondary_id="B")
        assert rep.pct_exact == pytest.approx(100.0)
        assert rep.is_clean_duplicate is True

    def test_divergent_feeds_are_not_clean_duplicates(self):
        """The Bishkek case: same instrument, publishers disagree."""
        a, b = _pair(shift_b=20.0)
        _, _, rep = merge_colocated(a, b, merged_id="m", primary_id="A", secondary_id="B")
        assert rep.pct_exact < 95.0
        assert rep.is_clean_duplicate is False
        assert "DIVERGENT" in rep.to_markdown()

    def test_per_year_agreement_is_reported(self):
        a, b = _pair()
        b.loc["2023"] = b.loc["2023"] + 30.0  # diverges only in the second year
        _, _, rep = merge_colocated(a, b, merged_id="m", primary_id="A", secondary_id="B")
        assert rep.per_year_pct_exact[2022] == pytest.approx(100.0)
        assert rep.per_year_pct_exact[2023] < 5.0

    def test_source_series_is_blank_where_neither_reports(self):
        a, b = _pair(gap_a=slice(0, 50), gap_b=slice(0, 50))
        vals, src, _ = merge_colocated(a, b, merged_id="m", primary_id="A", secondary_id="B")
        assert vals.iloc[:50].isna().all()
        assert (src.iloc[:50] == "").all()

    def test_exact_tolerance_is_explicit(self):
        assert EXACT_TOL == 0.1


class TestChoosePrimary:
    def test_prefers_more_observations(self):
        a, b = _pair(gap_a=slice(0, 1000))
        assert choose_primary(a, b, "A", "B") == ("B", "A")

    def test_tie_breaks_deterministically(self):
        a, b = _pair()
        assert choose_primary(a, b, "A", "B") == ("A", "B")
        assert choose_primary(a, b, "B", "A") == ("A", "B")  # same answer either way


class TestQ6WithinCity:
    def test_agreeing_instruments_pass(self):
        comps = {s: diurnal_composite(synthetic_pm25(seed=i)) for i, s in enumerate(["s1", "s2"])}
        out = q6_within_city("Dushanbe", comps, {"s1": 1000, "s2": 1000})
        assert all(f.verdict == "pass" for f in out)

    def test_disagreeing_instrument_rejected(self):
        comps = {
            "s1": diurnal_composite(synthetic_pm25(seed=0)),
            "s2": diurnal_composite(synthetic_pm25(seed=1)),
            "bad": diurnal_composite(synthetic_pm25(seed=2, shift_hours=6)),
        }
        out = q6_within_city("Bishkek", comps, dict.fromkeys(comps, 1000))
        verdicts = {f.station_id: f.verdict for f in out}
        assert verdicts["bad"] == "reject"
        assert verdicts["s1"] == "pass"

    def test_single_instrument_city_records_that_it_could_not_check(self):
        """Silence must not be mistaken for a passed check."""
        comps = {"only": diurnal_composite(synthetic_pm25(seed=0))}
        out = q6_within_city("Tashkent", comps, {"only": 1000})
        assert len(out) == 1
        assert out[0].verdict == "pass"
        assert "not possible" in out[0].detail
        assert "undetectable" in out[0].detail


class TestQ6CrossCityIsInformationalOnly:
    def test_never_rejects_even_for_opposite_regimes(self):
        """Cities genuinely differ; the old rule rejected stations for being correct."""
        comps = {
            "dilution": diurnal_composite(synthetic_pm25(seed=0)),
            "heating": diurnal_composite(synthetic_pm25(seed=0, shift_hours=12)),
        }
        out = q6_cross_city_informational(comps, {"dilution": "Tashkent", "heating": "Bishkek"})
        assert all(f.verdict == "pass" for f in out)
        assert all(f.n_flagged == 0 for f in out)
        assert all("informational" in f.detail for f in out)

    def test_labels_the_regime(self):
        comps = {"x": diurnal_composite(synthetic_pm25(seed=0))}
        out = q6_cross_city_informational(comps, {"x": "Tashkent"})
        assert "minimum" in out[0].detail


class TestRunQ6PerCity:
    def test_groups_by_city_and_covers_every_station(self):
        panel = pd.DataFrame(
            {
                "a1": synthetic_pm25(seed=0), "a2": synthetic_pm25(seed=1),
                "b1": synthetic_pm25(seed=2),
            }
        )
        city = {"a1": "Dushanbe", "a2": "Dushanbe", "b1": "Tashkent"}
        tzs = {"a1": "Asia/Dushanbe", "a2": "Asia/Dushanbe", "b1": "Asia/Tashkent"}
        out = run_q6_per_city(panel, city, tzs)
        checked = {f.station_id for f in out if f.rule == "Q6a"}
        assert checked == {"a1", "a2", "b1"}

    def test_a_single_instrument_city_is_never_rejected_by_q6a(self):
        panel = pd.DataFrame({"solo": synthetic_pm25(seed=0)})
        out = run_q6_per_city(panel, {"solo": "Almaty"}, {"solo": "Asia/Almaty"})
        assert all(f.verdict != "reject" for f in out)


def test_peak_hours_returns_min_and_max():
    comp = diurnal_composite(synthetic_pm25(seed=0))
    amin, amax = peak_hours(comp)
    assert 0 <= amin < 24 and 0 <= amax < 24
    assert amin != amax
