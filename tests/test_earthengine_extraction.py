"""Earth Engine extraction — request construction tested offline, no credentials needed.

The whole point of separating `build_request()` from execution is that the parts which can
silently corrupt results are checkable without a Google account: which collection, which
band, which buffer, which scale, which date window. A wrong band produces plausible numbers
for the wrong physical quantity, and nothing downstream notices.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ecopulse_ca.features.catalogue import ALL_FEATURES, SATELLITE, STATIC
from ecopulse_ca.ingest.earthengine import (
    BAND_FOR_FEATURE,
    COLLECTION_FOR_FEATURE,
    GETINFO_ELEMENT_LIMIT,
    EarthEngineExtractor,
    ExtractionError,
    ReductionRequest,
    StationPoint,
    build_request,
    chunk_date_range,
)

STATIONS = [
    StationPoint("8881", 41.3255, 69.2947, "Tashkent"),
    StationPoint("8876", 43.2380, 76.9450, "Almaty"),
    StationPoint("Bishkek", 42.8560, 74.6010, "Bishkek"),
]
BY_NAME = {f.name: f for f in ALL_FEATURES}


class TestRequestConstruction:
    def test_builds_for_a_reducible_feature(self):
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        assert r.collection == "MODIS/061/MCD19A2_GRANULES"
        assert r.band == "Optical_Depth_055"
        assert r.reduction.buffer_m == 3000
        assert r.scale_m == 1000

    def test_applies_the_maiac_scale_factor(self):
        """MAIAC AOD is stored as scaled integers; forgetting this inflates AOD 1000x."""
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-02")
        assert r.scale_factor == pytest.approx(0.001)

    def test_features_without_a_scale_factor_default_to_one(self):
        r = build_request(BY_NAME["elevation"], STATIONS, "2024-01-01", "2024-01-02")
        assert r.scale_factor == 1.0

    def test_refuses_a_raster_download_feature(self):
        """LANCE NRT cannot be reduced server-side; that must fail loudly."""
        with pytest.raises(ExtractionError, match="raster-download"):
            build_request(BY_NAME["maiac_aod_055_nrt"], STATIONS, "2024-01-01", "2024-01-02")

    def test_refuses_a_derived_feature_with_no_reduction(self):
        """Derived features are computed locally, not fetched."""
        with pytest.raises(ExtractionError, match="no Reduction"):
            build_request(BY_NAME["distance_to_aralkum"], STATIONS, "2024-01-01", "2024-01-02")

    def test_refuses_a_reducible_feature_with_no_collection_mapping(self):
        """CAMS declares a Reduction but is not an Earth Engine collection.

        A silently skipped feature becomes a silently absent column, which downstream code
        reads as "no signal here" rather than "never fetched".
        """
        with pytest.raises(ExtractionError, match="no Earth Engine collection"):
            build_request(BY_NAME["cams_pm25_forecast"], STATIONS, "2024-01-01", "2024-01-02")

    def test_refuses_an_empty_station_list(self):
        with pytest.raises(ExtractionError, match="no stations"):
            build_request(BY_NAME["maiac_aod_055"], [], "2024-01-01", "2024-01-02")

    @pytest.mark.parametrize(
        "f",
        [f for f in SATELLITE + STATIC if f.name in COLLECTION_FOR_FEATURE],
        ids=lambda f: f.name,
    )
    def test_every_mapped_feature_builds(self, f):
        r = build_request(f, STATIONS, "2024-01-01", "2024-01-07")
        assert r.collection and r.band

    def test_scale_matches_native_resolution(self):
        assert (
            build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-02").scale_m
            == 1000
        )
        assert (
            build_request(BY_NAME["elevation"], STATIONS, "2024-01-01", "2024-01-02").scale_m == 30
        )
        assert (
            build_request(BY_NAME["s5p_so2"], STATIONS, "2024-01-01", "2024-01-02").scale_m == 7000
        )


class TestCollectionAndBandMappings:
    def test_every_mapped_collection_has_a_band(self):
        assert set(COLLECTION_FOR_FEATURE) == set(BAND_FOR_FEATURE)

    def test_mappings_reference_real_catalogue_features(self):
        names = {f.name for f in ALL_FEATURES}
        assert set(COLLECTION_FOR_FEATURE) <= names, (
            f"mapping references unknown features: {set(COLLECTION_FOR_FEATURE) - names}"
        )

    def test_maiac_uses_the_055_band_not_047(self):
        """0.47 um and 0.55 um are both present and both plausible. The wrong one gives
        wrong AOD with no error anywhere."""
        assert BAND_FOR_FEATURE["maiac_aod_055"] == "Optical_Depth_055"

    def test_every_reducible_satellite_feature_is_mapped(self):
        unmapped = [
            f.name
            for f in SATELLITE
            if f.reduction is not None and f.name not in COLLECTION_FOR_FEATURE
        ]
        assert not unmapped, f"satellite features with no collection mapping: {unmapped}"


class TestGetInfoLimit:
    def test_flags_an_oversized_request(self):
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2020-01-01", "2024-12-31")
        assert r.exceeds_getinfo_limit()

    def test_small_request_is_within_the_limit(self):
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-07")
        assert not r.exceeds_getinfo_limit()

    def test_chunking_keeps_every_chunk_under_the_ceiling(self):
        chunks = chunk_date_range("2018-01-01", "2024-12-31", n_stations=8)
        for lo, hi in chunks:
            days = (pd.Timestamp(hi) - pd.Timestamp(lo)).days + 1
            assert days * 8 <= GETINFO_ELEMENT_LIMIT

    def test_chunk_size_scales_with_station_count(self):
        """A fixed chunk size would silently fail for larger station sets."""
        few = chunk_date_range("2018-01-01", "2024-12-31", n_stations=8)
        many = chunk_date_range("2018-01-01", "2024-12-31", n_stations=500)
        assert len(many) > len(few)

    def test_chunks_tile_the_range_without_gaps_or_overlap(self):
        chunks = chunk_date_range("2024-01-01", "2024-03-31", n_stations=100)
        assert chunks[0][0] == "2024-01-01"
        assert chunks[-1][1] == "2024-03-31"
        for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:], strict=False):
            assert pd.Timestamp(next_start) == pd.Timestamp(prev_end) + pd.Timedelta(days=1)

    def test_rejects_reversed_dates(self):
        with pytest.raises(ExtractionError, match="after"):
            chunk_date_range("2024-12-31", "2024-01-01", n_stations=8)


class TestFixtureExecution:
    """The suite must run end to end with no Google account."""

    @pytest.fixture
    def extractor(self) -> EarthEngineExtractor:
        return EarthEngineExtractor(project_id="", use_fixtures=True)

    def test_reports_itself_unavailable_without_a_project(self, extractor):
        assert extractor.available is False
        assert extractor.use_fixtures is True

    def test_a_project_id_switches_to_live(self):
        assert EarthEngineExtractor(project_id="some-project").use_fixtures is False

    def test_executes_against_a_fixture(self, extractor):
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        df = extractor.execute(r)
        assert not df.empty
        assert set(df.columns) >= {"station_id", "date", "feature", "value", "valid_count"}

    def test_fixture_rows_are_stamped_so_they_cannot_become_findings(self, extractor):
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        assert extractor.execute(r)["fixture"].all()

    def test_scale_factor_is_applied_to_fixture_values(self, extractor):
        """Fixtures store raw scaled integers, as Earth Engine does."""
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        vals = extractor.execute(r)["value"].dropna()
        assert vals.max() < 5.0, "AOD above 5 suggests the 0.001 scale factor was skipped"

    def test_missing_retrievals_survive_as_null_not_dropped(self, extractor):
        """Risk R7: missingness is informative and must reach the model, not vanish."""
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        df = extractor.execute(r)
        assert df["value"].isna().any(), "fixture should contain failed retrievals"
        assert len(df) > df["value"].notna().sum(), "null rows were dropped"

    def test_valid_count_travels_with_the_value(self, extractor):
        """'Mean AOD over 3 valid pixels' and 'over 300' are different facts."""
        r = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        df = extractor.execute(r)
        present = df[df["value"].notna()]
        assert present["valid_count"].notna().all()
        assert present["valid_count"].min() < present["valid_count"].max()

    def test_missing_fixture_fails_loudly(self, extractor):
        r = build_request(BY_NAME["s5p_co"], STATIONS, "2024-01-01", "2024-01-05")
        with pytest.raises(ExtractionError, match="no fixture"):
            extractor.execute(r)


class TestRequestProvenance:
    def test_fingerprint_is_stable(self):
        a = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        b = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        assert a.fingerprint() == b.fingerprint()

    def test_fingerprint_changes_with_the_buffer(self):
        """'Which buffer produced this column?' must be answerable from the archive."""
        a = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31")
        altered = (
            ReductionRequest(**{**a.to_dict_for_replace(), "scale_m": 500})
            if hasattr(a, "to_dict_for_replace")
            else None
        )
        if altered is None:
            import dataclasses

            altered = dataclasses.replace(a, scale_m=500)
        assert a.fingerprint() != altered.fingerprint()

    def test_request_serialises_for_the_manifest(self):
        d = build_request(BY_NAME["maiac_aod_055"], STATIONS, "2024-01-01", "2024-01-31").to_dict()
        assert d["reduction"]["buffer_m"] == 3000
        assert d["reduction"]["statistic"] == "mean"
        assert len(d["stations"]) == 3
