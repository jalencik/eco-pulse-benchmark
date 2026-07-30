"""The vectorised forecast path must agree with each model's own `predict()`.

`runner.forecast_batch` computes forecasts as shifts because looping `predict()` over
8,760 origins x 8 stations x 4 models is prohibitively slow. That optimisation is only
legitimate if the two paths produce the same numbers. If they diverged, every reported
metric would describe a model that exists nowhere in `models/` -- and nothing else in the
suite would notice, because both paths would still run cleanly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ecopulse_ca.eval.runner import HORIZONS, forecast_batch
from ecopulse_ca.models.climatology import Climatology
from ecopulse_ca.models.persistence import DiurnalPersistence, Persistence, SameHourMean
from tests.conftest import synthetic_pm25

MODELS = {
    "persistence": lambda: Persistence(),
    "diurnal_persistence": lambda: DiurnalPersistence(),
    "same_hour_mean_7d": lambda: SameHourMean(n_days=7),
    "climatology_mean": lambda: Climatology(),
}


@pytest.fixture(scope="module")
def series() -> pd.Series:
    return synthetic_pm25("2021-01-01", "2024-12-31", seed=7)


@pytest.fixture(scope="module")
def train(series) -> pd.Series:
    return series.loc[:"2022-12-31"]


@pytest.mark.parametrize("model_name", sorted(MODELS))
@pytest.mark.parametrize("horizon", HORIZONS)
def test_batch_matches_per_origin_predict(series, train, model_name, horizon):
    batch = forecast_batch(series, model_name, horizon, train)

    rng = np.random.default_rng(0)
    test_index = series.loc["2024-01-01":"2024-12-31"].index
    targets = rng.choice(len(test_index), size=40, replace=False)

    mismatches = []
    for i in sorted(targets):
        target_ts = test_index[i]
        origin_ts = target_ts - pd.Timedelta(horizon, unit="h")
        if origin_ts not in series.index:
            continue

        model = MODELS[model_name]()
        model.fit(train)
        history = series.loc[:origin_ts]
        expected = float(model.predict(history, (horizon,)).iloc[0])
        actual = float(batch.loc[target_ts])

        if np.isnan(expected) and np.isnan(actual):
            continue
        if not np.isclose(expected, actual, rtol=1e-9, atol=1e-9, equal_nan=True):
            mismatches.append((target_ts, expected, actual))

    assert not mismatches, (
        f"{model_name} h={horizon}: batch path disagrees with predict() at "
        f"{len(mismatches)} sampled origins, e.g. {mismatches[:3]}"
    )


def test_batch_respects_the_forecast_origin(series, train):
    """The batch path must never read a value at or after the target timestamp."""
    batch = forecast_batch(series, "persistence", 24, train)
    target = pd.Timestamp("2024-06-15 12:00", tz="UTC")
    assert batch.loc[target] == pytest.approx(series.loc[target - pd.Timedelta(24, unit="h")])


def test_persistence_and_diurnal_coincide_at_multiples_of_24(series, train):
    """Documented ladder degeneracy -- asserted so it cannot change silently."""
    for h in HORIZONS:
        a = forecast_batch(series, "persistence", h, train)
        b = forecast_batch(series, "diurnal_persistence", h, train)
        pd.testing.assert_series_equal(a, b)


def test_climatology_batch_is_fit_on_train_only(series):
    """A climatology fitted on the whole record would leak the test block into itself."""
    train = series.loc[:"2022-12-31"]
    scaled = series.copy()
    scaled.loc["2024":] = scaled.loc["2024":] * 10.0  # perturb the test period only

    a = forecast_batch(series, "climatology_mean", 24, train)
    b = forecast_batch(scaled, "climatology_mean", 24, train)
    # Predictions depend only on the training fit, so perturbing 2024 must change nothing.
    pd.testing.assert_series_equal(
        a.loc["2024-01-01":"2024-12-31"], b.loc["2024-01-01":"2024-12-31"]
    )


def test_same_hour_mean_uses_the_right_hours(series, train):
    """Spot-check the shift arithmetic that the batch path depends on."""
    h = 48
    batch = forecast_batch(series, "same_hour_mean_7d", h, train)
    target = pd.Timestamp("2024-06-15 09:00", tz="UTC")
    expected = np.mean([series.loc[target - pd.Timedelta(h + 24 * k, unit="h")] for k in range(7)])
    assert batch.loc[target] == pytest.approx(expected)
