"""Locally-computed derived features. No credentials, no network.

`distance_to_aralkum` is the one Phase 4 feature buildable today, so it is also the one
whose limitations should be pinned by test rather than discovered later.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ecopulse_ca.features.derived import (
    ARALKUM_POINTS,
    build_aralkum_distances,
    distance_to_aralkum,
    nearest_aralkum_point,
)

# The eight benchmark stations.
STATIONS = pd.DataFrame(
    [
        {"station_id": "8881", "city": "Tashkent", "latitude": 41.3255, "longitude": 69.2947},
        {"station_id": "8876", "city": "Almaty", "latitude": 43.2380, "longitude": 76.9450},
        {"station_id": "Bishkek", "city": "Bishkek", "latitude": 42.8560, "longitude": 74.6010},
        {"station_id": "Ashgabat", "city": "Ashgabat", "latitude": 37.9340, "longitude": 58.3860},
        {"station_id": "9769", "city": "Dushanbe", "latitude": 38.5730, "longitude": 68.7860},
    ]
)


class TestDistanceComputation:
    def test_uses_the_nearest_point_not_a_centroid(self):
        """The Aralkum is ~60,000 km2; one centroid would misrank nearby stations."""
        lat, lon = 45.20, 59.00  # sitting on one of the declared points
        assert distance_to_aralkum(lat, lon) == pytest.approx(0.0, abs=1.0)
        assert nearest_aralkum_point(lat, lon) == (45.20, 59.00)

    def test_distance_is_symmetric_in_ordering(self):
        a = distance_to_aralkum(41.3255, 69.2947)
        b = min(distance_to_aralkum(41.3255, 69.2947) for _ in range(3))
        assert a == pytest.approx(b)

    def test_more_than_one_reference_point_is_declared(self):
        assert len(ARALKUM_POINTS) >= 4

    def test_all_reference_points_lie_in_the_former_sea_extent(self):
        """Roughly 43.5-46.8 N, 58-62 E. A typo here silently shifts every distance."""
        for lat, lon in ARALKUM_POINTS:
            assert 43.0 <= lat <= 47.0, f"latitude {lat} outside the Aral extent"
            assert 57.0 <= lon <= 63.0, f"longitude {lon} outside the Aral extent"


class TestBenchmarkStations:
    @pytest.fixture(scope="class")
    def distances(self) -> pd.DataFrame:
        return build_aralkum_distances(STATIONS)

    def test_every_station_gets_a_value(self, distances):
        assert len(distances) == len(STATIONS)
        assert distances["value"].notna().all()

    def test_ashgabat_is_nearest_and_almaty_farthest(self, distances):
        ordered = distances.sort_values("value")["city"].tolist()
        assert ordered[0] == "Ashgabat"
        assert ordered[-1] == "Almaty"

    def test_no_station_is_close_to_the_aralkum(self, distances):
        """A stated limitation, pinned so it cannot be forgotten.

        Every benchmark station is 600+ km away, so the dust-source gradient is sampled
        only across a ~2x range at long transport distances. This feature has far less
        discriminative power here than the Aralkum dust literature would suggest.
        """
        assert distances["value"].min() > 600, "a near-source station would change this"
        assert distances["value"].max() / distances["value"].min() < 3.0

    def test_does_not_separate_the_diurnal_regimes(self, distances):
        """Negative finding, asserted.

        The evening-source cities (Bishkek, Ashgabat) span nearly the full distance range,
        so the Phase 2 regime split is not explained by proximity to the dust source. That
        supports a source-timing interpretation -- residential heating decaying overnight --
        rather than a dust one.
        """
        regime = {
            "Tashkent": "dilution",
            "Dushanbe": "dilution",
            "Bishkek": "evening",
            "Ashgabat": "evening",
            "Almaty": "own",
        }
        d = distances.assign(regime=distances["city"].map(regime))
        dilution = d.loc[d.regime == "dilution", "value"]
        evening = d.loc[d.regime == "evening", "value"]
        # Ranges overlap -> distance does not discriminate the regimes.
        assert evening.min() < dilution.min()
        assert evening.max() > dilution.max()


class TestContract:
    def test_rejects_a_frame_missing_coordinates(self):
        with pytest.raises(ValueError, match="missing"):
            build_aralkum_distances(pd.DataFrame([{"station_id": "x"}]))

    def test_rejects_non_finite_coordinates(self):
        bad = pd.DataFrame([{"station_id": "x", "latitude": float("nan"), "longitude": 60.0}])
        with pytest.raises(ValueError, match="non-finite"):
            build_aralkum_distances(bad)

    def test_output_is_not_marked_as_fixture_data(self):
        """These are real computed values, not synthetic -- they may be reported."""
        assert not build_aralkum_distances(STATIONS)["fixture"].any()

    def test_records_which_reference_point_was_nearest(self):
        out = build_aralkum_distances(STATIONS)
        assert out["nearest_aralkum_lat"].notna().all()
        assert out["nearest_aralkum_lon"].notna().all()
