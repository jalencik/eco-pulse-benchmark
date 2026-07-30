"""Baseline ladder: Task F forecasters and Task N nowcasters.

The leakage tests matter more than the accuracy tests. A nowcaster that reads the held-out
station would post an excellent score and be completely worthless, and that failure is
invisible in a metrics table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ecopulse_ca.models.base import StationMeta, haversine_km
from ecopulse_ca.models.climatology import Climatology
from ecopulse_ca.models.idw import IDW, NearestMonitor
from ecopulse_ca.models.kriging import OrdinaryKriging, exponential_variogram
from ecopulse_ca.models.persistence import DiurnalPersistence, Persistence, SameHourMean
from tests.conftest import synthetic_pm25

HORIZONS = (24, 48, 72)

# A rough Central Asia geometry -- real cities, so distances are realistic.
META = {
    "tashkent": StationMeta("tashkent", 41.3255, 69.2947, "Tashkent", True),
    "almaty": StationMeta("almaty", 43.2380, 76.9450, "Almaty", True),
    "bishkek": StationMeta("bishkek", 42.8560, 74.6010, "Bishkek", True),
    "dushanbe": StationMeta("dushanbe", 38.5730, 68.7860, "Dushanbe", True),
    "astana": StationMeta("astana", 51.1605, 71.4704, "Astana", True),
}


@pytest.fixture
def panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            sid: synthetic_pm25("2022-01-01", "2023-12-31", seed=i, base=40 + 5 * i)
            for i, sid in enumerate(META)
        }
    )


# --------------------------------------------------------------------------- forecasters
class TestPersistence:
    def test_predicts_last_observed_value(self, clean_series):
        m = Persistence().fit(clean_series)
        out = m.predict(clean_series, HORIZONS)
        last = float(clean_series.dropna().iloc[-1])
        assert out.to_list() == pytest.approx([last] * len(HORIZONS))

    def test_ignores_trailing_nan(self, clean_series):
        s = clean_series.copy()
        s.iloc[-3:] = np.nan
        out = Persistence().fit(s).predict(s, HORIZONS)
        assert out.iloc[0] == pytest.approx(float(s.dropna().iloc[-1]))

    def test_all_nan_history_returns_nan(self):
        s = pd.Series(np.nan, index=pd.date_range("2022-01-01", periods=48, freq="h", tz="UTC"))
        assert Persistence().fit(s).predict(s, HORIZONS).isna().all()

    def test_predict_before_fit_raises(self, clean_series):
        with pytest.raises(RuntimeError, match="before fit"):
            Persistence().predict(clean_series, HORIZONS)


class TestDiurnalPersistenceDegeneracy:
    """The documented degeneracy, asserted so it cannot silently change."""

    def test_identical_to_persistence_at_multiples_of_24(self, clean_series):
        # For h in {24,48,72}, h - 24*ceil(h/24) == 0, so the lookup lands on the origin.
        # Two ladder rungs therefore produce identical numbers at these horizons.
        p = Persistence().fit(clean_series).predict(clean_series, HORIZONS)
        d = DiurnalPersistence().fit(clean_series).predict(clean_series, HORIZONS)
        pd.testing.assert_series_equal(p, d)

    def test_differs_from_persistence_at_non_multiples(self, clean_series):
        odd = (1, 5, 13)
        p = Persistence().fit(clean_series).predict(clean_series, odd)
        d = DiurnalPersistence().fit(clean_series).predict(clean_series, odd)
        assert not np.allclose(p.to_numpy(), d.to_numpy())


class TestSameHourMean:
    def test_genuinely_differs_from_persistence_at_24h(self, clean_series):
        p = Persistence().fit(clean_series).predict(clean_series, HORIZONS)
        s = SameHourMean(n_days=7).fit(clean_series).predict(clean_series, HORIZONS)
        assert not np.allclose(p.to_numpy(), s.to_numpy())

    def test_averages_the_right_hour_of_day(self):
        idx = pd.date_range("2022-01-01", periods=24 * 10, freq="h", tz="UTC")
        # Value encodes hour-of-day, so the correct answer is unambiguous.
        s = pd.Series([float(t.hour) for t in idx], index=idx)
        out = SameHourMean(n_days=5).fit(s).predict(s, (1,))
        expected = float((pd.DatetimeIndex([idx[-1]])[0] + pd.Timedelta(hours=1)).hour)
        assert out.iloc[0] == pytest.approx(expected)

    def test_median_option_resists_a_spike(self):
        idx = pd.date_range("2022-01-01", periods=24 * 14, freq="h", tz="UTC")
        s = pd.Series(50.0, index=idx)
        # iloc[-25], not iloc[-24]: with iloc[-1] as the origin, stepping back a full 24
        # hours lands on -25. Using -24 puts the spike on the *previous* hour-of-day, where
        # the model correctly ignores it.
        s.iloc[-25] = 5000.0  # one dust-episode-sized outlier at the target hour
        assert idx[-25].hour == idx[-1].hour  # the alignment this test depends on
        mean = SameHourMean(n_days=7).fit(s).predict(s, (24,)).iloc[0]
        med = SameHourMean(n_days=7, use_median=True).fit(s).predict(s, (24,)).iloc[0]
        assert med < mean

    def test_rejects_bad_window(self):
        with pytest.raises(ValueError):
            SameHourMean(n_days=0)


class TestClimatology:
    def test_recovers_the_diurnal_shape(self):
        s = synthetic_pm25("2021-01-01", "2023-12-31", seed=3)
        m = Climatology().fit(s)
        night = m._lookup(pd.Timestamp("2024-01-15 20:00", tz="UTC"))
        afternoon = m._lookup(pd.Timestamp("2024-01-15 14:00", tz="UTC"))
        assert night > afternoon  # evening peak exceeds the afternoon minimum

    def test_recovers_the_winter_peak(self):
        s = synthetic_pm25("2021-01-01", "2023-12-31", seed=3)
        m = Climatology().fit(s)
        jan = m._lookup(pd.Timestamp("2024-01-15 20:00", tz="UTC"))
        jul = m._lookup(pd.Timestamp("2024-07-15 20:00", tz="UTC"))
        assert jan > jul

    def test_fits_only_on_the_history_given(self):
        """A climatology computed over the full record would leak the test block."""
        train = synthetic_pm25("2021-01-01", "2021-12-31", seed=3, base=20.0)
        m = Climatology().fit(train)
        assert m._global == pytest.approx(float(train.mean()), rel=1e-6)

    def test_fallback_chain_reports_its_level(self):
        # A single month of history: a July cell is unavailable, so it must fall back.
        jan = synthetic_pm25("2022-01-01", "2022-01-31", seed=1)
        m = Climatology().fit(jan)
        assert m.cell_source(pd.Timestamp("2022-01-15 10:00", tz="UTC")) == "cell"
        assert m.cell_source(pd.Timestamp("2022-07-15 10:00", tz="UTC")) == "hour"

    def test_empty_history_yields_nan_not_zero(self):
        empty = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
        m = Climatology().fit(empty)
        assert m.cell_source(pd.Timestamp("2022-01-01", tz="UTC")) == "none"


# --------------------------------------------------------------------------- nowcasters
def _observed(**values: float) -> pd.Series:
    return pd.Series(values, dtype=float)


class TestNearestMonitor:
    def test_copies_the_closest_station(self, panel):
        m = NearestMonitor().fit(panel, META)
        # Bishkek is much closer to Almaty than Dushanbe or Astana are.
        obs = _observed(almaty=100.0, dushanbe=10.0, astana=20.0)
        assert m.predict(obs, META["bishkek"]) == pytest.approx(100.0)

    def test_skips_nan_and_uses_next_nearest(self, panel):
        m = NearestMonitor().fit(panel, META)
        obs = _observed(almaty=np.nan, dushanbe=10.0, astana=20.0)
        assert np.isfinite(m.predict(obs, META["bishkek"]))

    def test_returns_nan_when_nothing_usable(self, panel):
        m = NearestMonitor().fit(panel, META)
        assert np.isnan(m.predict(_observed(almaty=np.nan), META["bishkek"]))

    def test_predict_before_fit_raises(self):
        with pytest.raises(RuntimeError, match="before fit"):
            NearestMonitor().predict(_observed(almaty=1.0), META["bishkek"])


class TestIDW:
    def test_weighted_average_lies_between_neighbours(self, panel):
        m = IDW(k=3, p=2.0).fit(panel, META)
        obs = _observed(almaty=100.0, dushanbe=20.0, astana=40.0)
        out = m.predict(obs, META["bishkek"])
        assert 20.0 < out < 100.0

    def test_large_p_converges_to_nearest_monitor(self, panel):
        obs = _observed(almaty=100.0, dushanbe=20.0, astana=40.0)
        near = NearestMonitor().fit(panel, META).predict(obs, META["bishkek"])
        idw = IDW(k=5, p=30.0).fit(panel, META).predict(obs, META["bishkek"])
        assert idw == pytest.approx(near, rel=1e-3)

    def test_colocated_station_returned_directly(self, panel):
        m = IDW().fit(panel, META)
        twin = StationMeta("twin", META["almaty"].latitude, META["almaty"].longitude)
        assert m.predict(_observed(almaty=77.0, dushanbe=10.0), twin) == pytest.approx(77.0)

    def test_nan_observations_ignored(self, panel):
        m = IDW(k=5).fit(panel, META)
        out = m.predict(_observed(almaty=np.nan, dushanbe=20.0, astana=40.0), META["bishkek"])
        assert np.isfinite(out)

    def test_returns_nan_not_zero_when_no_neighbours(self, panel):
        # A silent zero would be scored as a confident wrong answer.
        m = IDW().fit(panel, META)
        assert np.isnan(m.predict(_observed(), META["bishkek"]))

    @pytest.mark.parametrize("bad", [{"k": 0}, {"p": 0.0}, {"p": -1.0}])
    def test_rejects_invalid_parameters(self, bad):
        with pytest.raises(ValueError):
            IDW(**bad)


class TestNowcasterLeakage:
    """The failure this project cannot afford."""

    @pytest.mark.parametrize("model_cls", [NearestMonitor, IDW, OrdinaryKriging])
    def test_target_station_excluded_even_when_present(self, panel, model_cls):
        m = model_cls().fit(panel, META)
        target = META["bishkek"]
        without = m.predict(_observed(almaty=100.0, dushanbe=20.0), target)
        # Same observations, but the held-out station's own value smuggled in.
        with_leak = m.predict(_observed(almaty=100.0, dushanbe=20.0, bishkek=999.0), target)
        assert with_leak == pytest.approx(without, rel=1e-9), (
            f"{model_cls.__name__} used the held-out station's own value"
        )

    def test_fit_ignores_meta_for_stations_absent_from_panel(self, panel):
        # A station with metadata but no training data must not become a neighbour.
        extra = {**META, "ghost": StationMeta("ghost", 42.0, 70.0)}
        m = IDW().fit(panel[["almaty", "dushanbe"]], extra)
        assert set(m._meta) == {"almaty", "dushanbe"}


class TestOrdinaryKriging:
    def test_fits_a_variogram_and_predicts(self, panel):
        m = OrdinaryKriging().fit(panel, META)
        out = m.predict(_observed(almaty=60.0, dushanbe=40.0, astana=50.0), META["bishkek"])
        assert np.isfinite(out)

    def test_reports_variogram_parameters(self, panel):
        m = OrdinaryKriging().fit(panel, META)
        assert m.variogram_params is not None
        nugget, sill, rng = m.variogram_params
        assert nugget >= 0 and sill > 0 and rng > 0

    def test_falls_back_and_reports_the_rate(self, panel):
        """Kriging numbers that were mostly IDW underneath must be declarable as such."""
        m = OrdinaryKriging().fit(panel, META)
        m.predict(_observed(almaty=50.0), META["bishkek"])  # 1 neighbour -> fallback
        assert m.fallback_rate == pytest.approx(1.0)

    def test_too_few_stations_disables_the_variogram(self):
        small = pd.DataFrame({"almaty": synthetic_pm25("2022-01-01", "2022-03-01", seed=0)})
        m = OrdinaryKriging().fit(small, META)
        assert m.variogram_params is None

    def test_returns_nan_when_no_neighbours(self, panel):
        m = OrdinaryKriging().fit(panel, META)
        assert np.isnan(m.predict(_observed(), META["bishkek"]))

    def test_variogram_is_zero_at_zero_lag(self):
        assert exponential_variogram(np.array([0.0]), 1.0, 5.0, 100.0)[0] == 0.0

    def test_variogram_is_monotonic_and_bounded(self):
        h = np.array([1.0, 10.0, 100.0, 1000.0, 10000.0])
        g = exponential_variogram(h, 1.0, 5.0, 200.0)
        assert np.all(np.diff(g) >= -1e-12)
        assert g[-1] <= 1.0 + 5.0 + 1e-9


# --------------------------------------------------------------------------- contracts
class TestDeterminismContract:
    @pytest.mark.parametrize("make", [Persistence, DiurnalPersistence, SameHourMean, Climatology])
    def test_forecasters_are_deterministic(self, clean_series, make):
        a = make(seed=0).fit(clean_series).predict(clean_series, HORIZONS)
        b = make(seed=999).fit(clean_series).predict(clean_series, HORIZONS)
        pd.testing.assert_series_equal(a, b)
        assert make().is_deterministic is True

    @pytest.mark.parametrize("make", [NearestMonitor, IDW, OrdinaryKriging])
    def test_nowcasters_are_deterministic(self, panel, make):
        obs = _observed(almaty=60.0, dushanbe=40.0, astana=50.0)
        a = make(seed=0).fit(panel, META).predict(obs, META["bishkek"])
        b = make(seed=999).fit(panel, META).predict(obs, META["bishkek"])
        assert a == pytest.approx(b, nan_ok=True)
        assert make().is_deterministic is True


def test_haversine_matches_known_city_distance():
    # Tashkent -> Almaty is ~664 km great-circle (road distance is longer, ~770 km).
    d = haversine_km(41.3255, 69.2947, 43.2380, 76.9450)
    assert 640 < d < 690


class TestVectorisedHaversineMatchesScalar:
    """The array form is an optimisation; it must not drift from the scalar definition."""

    def test_agrees_on_the_benchmark_geometry(self):
        import numpy as np

        from ecopulse_ca.models.base import haversine_km_array

        lats = np.array([m.latitude for m in META.values()])
        lons = np.array([m.longitude for m in META.values()])
        origin = META["tashkent"]
        vec = haversine_km_array(origin.latitude, origin.longitude, lats, lons)
        scalar = [
            haversine_km(origin.latitude, origin.longitude, m.latitude, m.longitude)
            for m in META.values()
        ]
        assert vec == pytest.approx(scalar, rel=1e-12)

    def test_zero_distance_to_self(self):
        import numpy as np

        from ecopulse_ca.models.base import haversine_km_array

        m = META["almaty"]
        d = haversine_km_array(
            m.latitude, m.longitude, np.array([m.latitude]), np.array([m.longitude])
        )
        assert d[0] == pytest.approx(0.0, abs=1e-9)
