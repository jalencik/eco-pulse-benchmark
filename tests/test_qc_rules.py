"""Tests for pre-registered QC rules Q1-Q5, Q7.

Each test asserts on the **n-effect** as well as the verdict, because a rule that reports
the wrong n would silently corrupt data/DECISIONS.md while still appearing to work.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ecopulse_ca.qc.rules import (
    QCReport,
    haversine_m,
    q1_physical_range,
    q2_flatline,
    q3_zero_run,
    q4_unit_sanity,
    q5_duplicate_stations,
    q7_completeness,
)
from tests.conftest import synthetic_pm25


class TestQ1PhysicalRange:
    def test_clean_series_passes(self, clean_series):
        f = q1_physical_range(clean_series, "s1")
        assert f.verdict == "pass"
        assert f.n_flagged == 0

    def test_flags_negative_and_extreme(self, clean_series):
        s = clean_series.copy()
        s.iloc[10] = -5.0
        s.iloc[20] = 5000.0
        f = q1_physical_range(s, "s1")
        assert f.verdict == "flag"
        assert f.n_flagged == 2
        assert f.mask.iloc[10] and f.mask.iloc[20]

    def test_nan_is_not_flagged_as_out_of_range(self, clean_series):
        # NaN means "missing", which is Q7's concern, not Q1's. Conflating them would
        # double-count the same gap in two different n-effects.
        s = clean_series.copy()
        s.iloc[5] = np.nan
        assert q1_physical_range(s, "s1").n_flagged == 0


class TestQ2Flatline:
    def test_detects_24h_stuck_value(self, clean_series):
        s = clean_series.copy()
        s.iloc[100:130] = 37.5
        f = q2_flatline(s, "s1")
        assert f.verdict == "flag"
        assert f.n_flagged == 30

    def test_short_run_not_flagged(self, clean_series):
        s = clean_series.copy()
        s.iloc[100:110] = 37.5  # 10 < 24
        assert q2_flatline(s, "s1").n_flagged == 0

    def test_zeros_are_left_to_q3(self, clean_series):
        # Q2 excludes zeros by design: a run of zeros is missing-data-as-zero, a different
        # fault with a different remedy.
        s = clean_series.copy()
        s.iloc[100:140] = 0.0
        assert q2_flatline(s, "s1").n_flagged == 0


class TestQ3ZeroRun:
    def test_detects_zero_run(self, clean_series):
        s = clean_series.copy()
        s.iloc[50:60] = 0.0
        f = q3_zero_run(s, "s1")
        assert f.verdict == "flag"
        assert f.n_flagged == 10

    def test_isolated_zero_kept(self, clean_series):
        s = clean_series.copy()
        s.iloc[50] = 0.0
        assert q3_zero_run(s, "s1").n_flagged == 0


class TestQ4UnitSanity:
    def test_normal_median_passes(self, clean_series):
        assert q4_unit_sanity(clean_series, "s1").verdict == "pass"

    def test_mg_per_m3_mislabelled_is_rejected(self, clean_series):
        # ug/m3 values divided by 1000 -- the classic unit error.
        assert q4_unit_sanity(clean_series / 1000.0, "s1").verdict == "reject"

    def test_aqi_reported_as_concentration_is_rejected(self, clean_series):
        assert q4_unit_sanity(clean_series * 12.0, "s1").verdict == "reject"

    def test_rejection_reports_whole_series_as_n_effect(self, clean_series):
        f = q4_unit_sanity(clean_series / 1000.0, "s1")
        assert f.n_flagged == f.n_total  # whole-series fault, not a subset


class TestQ5DuplicateStations:
    def test_colocated_distinct_ids_flagged(self):
        census = pd.DataFrame(
            [
                {"location_id": 1, "latitude": 41.36, "longitude": 69.289},
                {"location_id": 2, "latitude": 41.36, "longitude": 69.289},
                {"location_id": 3, "latitude": 43.24, "longitude": 76.945},
            ]
        )
        findings = q5_duplicate_stations(census)
        assert [f.rule for f in findings] == ["Q5b"]
        assert findings[0].verdict == "flag"

    def test_one_id_at_two_coordinates_rejected(self):
        census = pd.DataFrame(
            [
                {"location_id": 7, "latitude": 41.36, "longitude": 69.289},
                {"location_id": 7, "latitude": 42.00, "longitude": 70.000},
            ]
        )
        findings = q5_duplicate_stations(census)
        assert any(f.rule == "Q5a" and f.verdict == "reject" for f in findings)

    def test_clean_census_no_findings(self):
        census = pd.DataFrame(
            [
                {"location_id": 1, "latitude": 41.36, "longitude": 69.289},
                {"location_id": 2, "latitude": 43.24, "longitude": 76.945},
            ]
        )
        assert q5_duplicate_stations(census) == []

    def test_catches_the_real_embassy_duplicate_57m_apart(self):
        """Regression test from live data.

        The StateAir and AirNow feeds of the Bishkek US Embassy monitor are 57 m apart --
        one physical instrument, two location_ids. Exact-coordinate matching missed this,
        and under leave-station-out it would leak the held-out station into training.
        """
        census = pd.DataFrame(
            [
                {
                    "location_id": 4001,
                    "latitude": 42.85600,
                    "longitude": 74.60100,
                    "provider": "StateAir Bishkek",
                },
                {
                    "location_id": 4002,
                    "latitude": 42.85651,
                    "longitude": 74.60123,
                    "provider": "AirNow",
                },
            ]
        )
        findings = q5_duplicate_stations(census)
        assert [f.rule for f in findings] == ["Q5b"]
        assert "probably one instrument" in findings[0].detail

    def test_genuinely_distinct_sites_6km_apart_not_flagged(self):
        """The two Dushanbe sites are 6.06 km apart and are genuinely different stations.

        Pairs with the test above: the threshold must separate 57 m from 6 km.
        """
        census = pd.DataFrame(
            [
                {
                    "location_id": 5001,
                    "latitude": 38.5730,
                    "longitude": 68.7860,
                    "provider": "StateAir Dushanbe",
                },
                {
                    "location_id": 5002,
                    "latitude": 38.5590,
                    "longitude": 68.7250,
                    "provider": "AirNow",
                },
            ]
        )
        assert q5_duplicate_stations(census) == []

    def test_haversine_matches_known_distance(self):
        # ~111.19 km per degree of latitude at the equator.
        d = haversine_m(0.0, 0.0, 1.0, 0.0)
        assert 111_000 < d < 111_400

    def test_colocation_clusters_transitively(self):
        # A~B and B~C means all three are one site, even if A and C exceed the radius.
        census = pd.DataFrame(
            [
                {"location_id": 1, "latitude": 42.8560, "longitude": 74.6010},
                {"location_id": 2, "latitude": 42.8570, "longitude": 74.6010},
                {"location_id": 3, "latitude": 42.8580, "longitude": 74.6010},
            ]
        )
        findings = q5_duplicate_stations(census)
        assert len(findings) == 1
        assert findings[0].station_id.count(",") == 2  # all three in one cluster


class TestQ7Completeness:
    def test_long_complete_series_passes(self):
        assert q7_completeness(synthetic_pm25("2021-01-01", "2024-12-31"), "s1").verdict == "pass"

    def test_short_series_rejected(self):
        assert q7_completeness(synthetic_pm25("2025-01-01", "2025-06-30"), "s1").verdict == "reject"

    def test_gappy_series_rejected(self):
        s = synthetic_pm25("2021-01-01", "2024-12-31")
        s.iloc[: int(len(s) * 0.7)] = np.nan  # only 30% present
        assert q7_completeness(s, "s1").verdict == "reject"

    def test_completeness_measured_against_span_not_row_count(self):
        # A series with a huge interior gap must not score 100% merely because every row
        # that exists is non-null. Dropping the gap rows first would do exactly that.
        s = synthetic_pm25("2021-01-01", "2024-12-31")
        s.iloc[1000:20000] = np.nan
        f = q7_completeness(s, "s1")
        assert "completeness=" in f.detail
        assert f.verdict == "reject"

    def test_empty_series_rejected(self):
        empty = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
        assert q7_completeness(empty, "s1").verdict == "reject"


class TestQCReport:
    def test_aggregates_and_reports_n_effects(self, clean_series):
        s = clean_series.copy()
        s.iloc[10] = -1.0
        s.iloc[200:240] = 33.3
        report = QCReport().add(q1_physical_range(s, "s1"), q2_flatline(s, "s1"))
        df = report.to_frame()
        assert set(df["rule"]) == {"Q1", "Q2"}
        assert (df["n_total"] == len(s)).all()

    def test_row_mask_is_union_of_row_rules(self, clean_series):
        s = clean_series.copy()
        s.iloc[10] = -1.0
        s.iloc[200:240] = 33.3
        report = QCReport().add(q1_physical_range(s, "s1"), q2_flatline(s, "s1"))
        mask = report.row_mask("s1", s.index)
        assert mask.iloc[10]
        assert mask.iloc[220]
        assert mask.sum() == 41  # 1 out-of-range + 40 flatlined

    def test_markdown_contains_n_effect_columns(self, clean_series):
        report = QCReport().add(q4_unit_sanity(clean_series / 1000.0, "s1"))
        md = report.to_markdown()
        assert "n_flagged" in md
        assert "reject" in md

    def test_rejected_stations_collected(self, clean_series):
        report = QCReport().add(
            q4_unit_sanity(clean_series / 1000.0, "bad"),
            q4_unit_sanity(clean_series, "good"),
        )
        assert report.rejected_stations == {"bad"}


@pytest.mark.parametrize("rule_fn", [q1_physical_range, q2_flatline, q3_zero_run])
def test_row_rules_never_lose_observations(clean_series, rule_fn):
    """A row rule reports on the full series; it must not silently shrink n_total."""
    assert rule_fn(clean_series, "s1").n_total == len(clean_series)
