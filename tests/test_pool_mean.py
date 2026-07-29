"""The achievable-constant rung.

The property that matters most is negative: this model must be fitted on the training
block only. A pool mean computed over the full record would leak the test period into the
reference that every other rung is judged against -- and because it is a *reference*, that
leak would make the whole ladder look better without any model changing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ecopulse_ca.models.base import StationMeta
from ecopulse_ca.models.pool_mean import TrainingPoolMean
from tests.conftest import synthetic_pm25

META = {
    "a": StationMeta("a", 41.3, 69.3, "Tashkent", True),
    "b": StationMeta("b", 43.2, 76.9, "Almaty", True),
    "c": StationMeta("c", 42.9, 74.6, "Bishkek", True),
}
TARGET = StationMeta("held", 38.6, 68.8, "Dushanbe", True)


@pytest.fixture
def panel() -> pd.DataFrame:
    return pd.DataFrame(
        {s: synthetic_pm25("2021-01-01", "2024-12-31", seed=i, base=30 + 10 * i)
         for i, s in enumerate(META)}
    )


class TestFittedValue:
    def test_equals_the_mean_of_what_it_was_given(self, panel):
        m = TrainingPoolMean().fit(panel, META)
        expected = float(np.nanmean(panel.to_numpy(dtype=float)))
        assert m.fitted_value == pytest.approx(expected)

    def test_median_variant(self, panel):
        m = TrainingPoolMean(use_median=True).fit(panel, META)
        flat = panel.to_numpy(dtype=float).ravel()
        assert m.fitted_value == pytest.approx(float(np.median(flat[np.isfinite(flat)])))

    def test_ignores_nan(self, panel):
        holey = panel.copy()
        holey.iloc[:500, 0] = np.nan
        m = TrainingPoolMean().fit(holey, META)
        assert np.isfinite(m.fitted_value)
        assert m.n_training_observations < holey.size

    def test_empty_panel_yields_nan_not_zero(self):
        empty = pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))
        m = TrainingPoolMean().fit(empty, META)
        assert np.isnan(m.fitted_value)


class TestNoLeakage:
    def test_constant_reflects_only_the_slice_it_was_fitted_on(self, panel):
        """The harness passes the train block; the model must not see beyond it."""
        train = panel.loc[:"2022-12-31"]
        m_train = TrainingPoolMean().fit(train, META)

        perturbed = panel.copy()
        perturbed.loc["2024":] = perturbed.loc["2024":] * 10.0
        m_train_again = TrainingPoolMean().fit(perturbed.loc[:"2022-12-31"], META)

        assert m_train.fitted_value == pytest.approx(m_train_again.fitted_value), (
            "changing the test period altered the fitted constant -- the slice leaked"
        )

    def test_full_record_fit_differs_from_train_fit(self, panel):
        """Guards the test above: if these were equal, that test would prove nothing."""
        train = TrainingPoolMean().fit(panel.loc[:"2022-12-31"], META).fitted_value
        allrec = TrainingPoolMean().fit(panel, META).fitted_value
        assert not np.isclose(train, allrec, rtol=1e-6)

    def test_prediction_ignores_the_held_out_station(self, panel):
        m = TrainingPoolMean().fit(panel, META)
        without = m.predict(pd.Series({"a": 10.0, "b": 20.0}), TARGET)
        with_leak = m.predict(pd.Series({"a": 10.0, "b": 20.0, "held": 999.0}), TARGET)
        assert without == pytest.approx(with_leak)

    def test_prediction_ignores_current_observations_entirely(self, panel):
        """By design: this rung answers 'what does knowing nothing about now get you?'"""
        m = TrainingPoolMean().fit(panel, META)
        assert m.predict(pd.Series({"a": 5.0}), TARGET) == pytest.approx(
            m.predict(pd.Series({"a": 500.0}), TARGET)
        )


class TestContract:
    def test_predict_before_fit_raises(self):
        with pytest.raises(RuntimeError, match="before fit"):
            TrainingPoolMean().predict(pd.Series({"a": 1.0}), TARGET)

    def test_is_declared_deterministic(self, panel):
        a = TrainingPoolMean(seed=0).fit(panel, META).predict(pd.Series({"a": 1.0}), TARGET)
        b = TrainingPoolMean(seed=99).fit(panel, META).predict(pd.Series({"a": 1.0}), TARGET)
        assert a == pytest.approx(b)
        assert TrainingPoolMean().is_deterministic is True

    def test_name_distinguishes_the_variants(self):
        assert TrainingPoolMean().name == "training_pool_mean"
        assert TrainingPoolMean(use_median=True).name == "training_pool_median"

    def test_adds_no_lag_requirement_to_the_purge_gap(self):
        """A constant has no feature window, so the frozen purge stays valid."""
        assert not hasattr(TrainingPoolMean(), "n_days")
