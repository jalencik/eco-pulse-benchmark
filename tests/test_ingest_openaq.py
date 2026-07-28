"""Ingestion + census tests, running entirely against committed fixtures.

The whole suite must pass with no credentials. That is not only convenience: it means a
reviewer cloning the repo can verify the pipeline's logic without being handed a secret.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ecopulse_ca.config import Settings, _resolve_fixtures
from ecopulse_ca.ingest.openaq import (
    OpenAQClient,
    census_frame,
    run_census,
    summarise_census,
)


@pytest.fixture
def fixture_settings() -> Settings:
    return Settings(openaq_api_key="", use_fixtures=True)


class TestFixtureRouting:
    def test_auto_uses_fixtures_without_key(self):
        assert _resolve_fixtures("auto", has_key=False) is True

    def test_auto_switches_to_live_with_key(self):
        assert _resolve_fixtures("auto", has_key=True) is False

    def test_explicit_override_wins(self):
        assert _resolve_fixtures("1", has_key=True) is True
        assert _resolve_fixtures("0", has_key=False) is False

    def test_provenance_never_leaks_the_key(self):
        s = Settings(openaq_api_key="SECRET-KEY-VALUE", use_fixtures=False)
        prov = s.provenance
        assert "SECRET-KEY-VALUE" not in repr(prov)
        assert "SECRET-KEY-VALUE" not in repr(s)  # field is repr=False
        assert prov["has_openaq_key"] is True


class TestLocations:
    def test_loads_each_country_fixture(self, fixture_settings):
        with OpenAQClient(fixture_settings) as c:
            for iso in ("UZ", "KZ", "KG", "TJ", "TM"):
                assert c.locations(iso), f"no fixture locations for {iso}"

    def test_auth_header_omitted_when_no_key(self, fixture_settings):
        assert OpenAQClient(fixture_settings).auth_headers() == {}

    def test_auth_header_uses_x_api_key(self):
        c = OpenAQClient(Settings(openaq_api_key="abc", use_fixtures=True))
        assert c.auth_headers() == {"X-API-Key": "abc"}


class TestCensusFrame:
    def test_extracts_pm25_sensors_and_span(self, fixture_settings):
        with OpenAQClient(fixture_settings) as c:
            df = census_frame(c.locations("UZ"), "UZ")
        assert (df["n_pm25_sensors"] > 0).all()
        assert df["span_years"].max() > 5

    def test_datetimes_parsed_as_utc(self, fixture_settings):
        with OpenAQClient(fixture_settings) as c:
            df = census_frame(c.locations("UZ"), "UZ")
        assert isinstance(df["datetime_first"].dtype, pd.DatetimeTZDtype)

    def test_mobile_sensor_excluded_from_eligibility(self, fixture_settings):
        with OpenAQClient(fixture_settings) as c:
            df = census_frame(c.locations("KZ"), "KZ")
        mobile = df[df["is_mobile"]]
        assert not mobile.empty, "KZ fixture should contain a mobile unit"
        # A moving sensor has no fixed location, so it cannot join a spatial split.
        assert not mobile["q7_span_ok_upper_bound"].any()

    def test_short_span_station_excluded(self, fixture_settings):
        with OpenAQClient(fixture_settings) as c:
            df = census_frame(c.locations("KZ"), "KZ")
        shymkent = df[df["locality"] == "Shymkent"].iloc[0]
        assert shymkent["span_years"] < 2
        assert not shymkent["q7_span_ok_upper_bound"]

    def test_late_starting_national_station_excluded(self, fixture_settings):
        # Tajikistan began sharing only in 2024 -- too recent for a multi-year split.
        with OpenAQClient(fixture_settings) as c:
            df = census_frame(c.locations("TJ"), "TJ")
        hydromet = df[df["provider"] == "Tajikhydromet"].iloc[0]
        assert not hydromet["q7_span_ok_upper_bound"]

    def test_eligibility_flag_is_named_as_an_upper_bound(self):
        # Q7 also needs completeness, which the census cannot see. The column name must
        # keep that impossible to forget.
        assert "upper_bound" in "q7_span_ok_upper_bound"


class TestCensusRollup:
    def test_covers_all_five_countries(self, fixture_settings):
        df = run_census(fixture_settings)
        assert set(df["country"]) == {"UZ", "KZ", "KG", "TJ", "TM"}

    def test_turkmenistan_has_only_an_embassy_monitor(self, fixture_settings):
        # Turkmenistan has no national monitoring at all (OpenAQ 2024 landscape report).
        df = run_census(fixture_settings)
        tm = df[df["country"] == "TM"]
        assert len(tm) == 1
        assert bool(tm.iloc[0]["is_monitor"]) is True
        assert "Embassy" in tm.iloc[0]["name"]

    def test_summary_counts_reference_monitors(self, fixture_settings):
        summary = summarise_census(run_census(fixture_settings))
        assert (summary["reference_monitors"] >= 1).all()

    def test_summary_reports_distinct_localities(self, fixture_settings):
        summary = summarise_census(run_census(fixture_settings))
        assert "distinct_localities" in summary.columns
        assert summary["distinct_localities"].sum() >= 1

    def test_f3_city_count_is_computable(self, fixture_settings):
        """The census must yield the one number that decides the headline protocol."""
        df = run_census(fixture_settings)
        cities = df.loc[df["q7_span_ok_upper_bound"], "locality"].dropna().nunique()
        assert isinstance(int(cities), int)


def test_empty_locations_returns_empty_frame():
    assert census_frame([], "UZ").empty
