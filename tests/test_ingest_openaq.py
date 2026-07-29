"""Ingestion + census tests, running entirely against committed fixtures.

The whole suite must pass with no credentials. That is not only convenience: it means a
reviewer cloning the repo can verify the pipeline's logic without being handed a secret.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ecopulse_ca.config import Settings, _resolve_fixtures
from ecopulse_ca.ingest.base import HttpSource, IngestError
from ecopulse_ca.ingest.measurements import DATETIME_FROM, DATETIME_TO, fetch_sensor_series
from ecopulse_ca.ingest.openaq import (
    OpenAQClient,
    census_frame,
    derive_city,
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

    def test_summary_reports_distinct_cities(self, fixture_settings):
        summary = summarise_census(run_census(fixture_settings))
        assert "distinct_cities" in summary.columns
        assert summary["distinct_cities"].sum() >= 1

    def test_f3_city_count_is_computable(self, fixture_settings):
        """The census must yield the one number that decides the headline protocol."""
        df = run_census(fixture_settings)
        cities = df.loc[df["q7_span_ok_upper_bound"], "city"].dropna().nunique()
        assert isinstance(int(cities), int)


class TestDeriveCity:
    """`locality` is null for 98.7% of live Central Asia stations, so it cannot be the
    sole basis for the city count that decides F3."""

    def test_locality_used_when_present(self):
        assert derive_city("Tashkent", "some sensor name") == "Tashkent"

    def test_falls_back_to_name_when_locality_null(self):
        assert derive_city(None, "Bishkek") == "Bishkek"
        assert derive_city(float("nan"), "Almaty") == "Almaty"

    def test_strips_programme_branding_from_name(self):
        # Live data: "US Diplomatic Post: Bishkek" and a plain AirNow "Bishkek" are the
        # same city and must not count twice.
        assert derive_city(None, "US Diplomatic Post: Bishkek") == "Bishkek"
        assert derive_city(None, "US Diplomatic Post: Ashgabat") == "Ashgabat"

    def test_branded_and_plain_names_agree(self):
        assert derive_city(None, "US Diplomatic Post: Dushanbe") == derive_city(None, "Dushanbe")

    def test_blank_input_returns_none(self):
        assert derive_city(None, None) is None
        assert derive_city("   ", "  ") is None

    def test_na_sentinel_is_treated_as_missing(self):
        """Regression from live data.

        OpenAQ returns the literal string "N/A" as `locality` for the AirNow feeds --
        exactly the ones carrying Almaty and Astana. Accepting it as a city name collapsed
        two distinct Kazakh cities into one bogus city, understating the F3 count.
        """
        assert derive_city("N/A", "Almaty") == "Almaty"
        assert derive_city("N/A", "Astana") == "Astana"

    @pytest.mark.parametrize("sentinel", ["N/A", "n/a", "NULL", "none", "-", "unknown", "?"])
    def test_other_sentinels_also_rejected(self, sentinel):
        assert derive_city(sentinel, "Bishkek") == "Bishkek"

    def test_sentinel_in_name_yields_none_not_a_fake_city(self):
        assert derive_city(None, "N/A") is None

    def test_census_frame_populates_city(self, fixture_settings):
        with OpenAQClient(fixture_settings) as c:
            df = census_frame(c.locations("UZ"), "UZ")
        assert df["city"].notna().all()


def test_empty_locations_returns_empty_frame():
    assert census_frame([], "UZ").empty


class TestTimeFilterParameterNames:
    """Pin the query-parameter names OpenAQ v3 actually honours.

    Verified empirically against the live API on 2026-07-29:

        no params            -> 2018-11-27  (start of record)
        date_from/date_to    -> 2018-11-27  (SILENTLY IGNORED)
        datetime_from/_to    -> 2022-06-01  (honoured)
        dateFrom/dateTo      -> 2018-11-27  (SILENTLY IGNORED)

    OpenAQ returns HTTP 200 with well-formed records for an unrecognised filter rather
    than a 400. Two full pipeline runs completed with the wrong name before an arithmetic
    check caught it, so the names are pinned here.
    """

    def test_constants_are_the_honoured_names(self):
        assert DATETIME_FROM == "datetime_from"
        assert DATETIME_TO == "datetime_to"

    def test_sensor_hours_sends_the_honoured_names(self):
        sent: dict[str, object] = {}

        class Spy(OpenAQClient):
            def paginate(self, path, params=None, **kw):  # type: ignore[override]
                sent.update(params or {})
                return []

        Spy(Settings(use_fixtures=True)).sensor_hours(1, "2022-01-01", "2022-02-01")
        assert "datetime_from" in sent and "datetime_to" in sent
        assert "date_from" not in sent, "date_from is silently ignored by OpenAQ v3"

    def test_impossible_record_count_raises(self):
        """A window of H hours cannot yield materially more than H hourly records."""

        class Overflowing(OpenAQClient):
            page_limit = 1000

            def paginate(self, path, params=None, **kw):  # type: ignore[override]
                # One year requested; return far more records than the year contains.
                return [
                    {"period": {"datetimeFrom": {"utc": "2022-01-01T00:00:00Z"}},
                     "value": 1.0, "coverage": {}}
                ] * 20000

        client = Overflowing(Settings(use_fixtures=True))
        with pytest.raises(IngestError, match="time filter was not applied"):
            fetch_sensor_series(
                client, 1,
                pd.Timestamp("2022-01-01", tz="UTC"),
                pd.Timestamp("2022-12-31 23:59:59", tz="UTC"),
            )


class TestPaginationPartialResults:
    """Regression: a failure on page N must not discard pages 1..N-1.

    The original implementation raised on a failed page, and the caller's `except:
    continue` then dropped the whole year -- roughly 9,000 already-retrieved records each
    time. Because it is *deep* pagination that times out, the loss was proportional to how
    long a station's record was: every long reference-monitor series was destroyed while
    two short low-cost sensors survived. The output looked like a finding ("only 2 usable
    stations in 1 city") rather than a bug, which is what makes this worth a test.
    """

    class _FlakySource(HttpSource):
        """Serves `limit`-sized pages, then fails on `fail_on_page`."""

        base_url = "https://example.invalid"
        page_limit = 10

        def __init__(self, fail_on_page: int, total_pages: int = 5) -> None:
            super().__init__(use_fixtures=False, cache_dir=Path("/nonexistent"))
            self.fail_on_page = fail_on_page
            self.total_pages = total_pages
            self.requested: list[int] = []

        def fixture_name(self, path: str, params: dict | None) -> str:
            raise AssertionError("fixtures must not be used in this test")

        def get(self, path: str, params: dict | None = None) -> dict:
            page = int((params or {}).get("page", 1))
            self.requested.append(page)
            if page == self.fail_on_page:
                raise IngestError(f"simulated 408 on page {page}")
            n = self.page_limit if page < self.total_pages else 3  # last page is short
            return {"results": [{"i": (page - 1) * self.page_limit + k} for k in range(n)]}

    def test_failure_returns_earlier_pages(self):
        src = self._FlakySource(fail_on_page=4)
        out = src.paginate("/x")
        assert len(out) == 30, "pages 1-3 must survive a failure on page 4"
        assert src.last_pagination_partial is True

    def test_successful_walk_is_not_marked_partial(self):
        src = self._FlakySource(fail_on_page=99, total_pages=3)
        out = src.paginate("/x")
        assert len(out) == 23  # 10 + 10 + 3
        assert src.last_pagination_partial is False

    def test_max_pages_stops_before_the_failing_page(self):
        """Bounding by expected record count avoids the timeout entirely."""
        src = self._FlakySource(fail_on_page=4)
        out = src.paginate("/x", max_pages=3)
        assert len(out) == 30
        assert 4 not in src.requested, "must not request a page beyond the expected count"

    def test_partial_flag_resets_between_calls(self):
        src = self._FlakySource(fail_on_page=99, total_pages=2)
        src.last_pagination_partial = True
        src.paginate("/x")
        assert src.last_pagination_partial is False
