"""Shared test fixtures.

`synthetic_pm25` builds an hourly series with a realistic bimodal urban diurnal cycle
(morning traffic peak, deeper evening traffic+heating peak, afternoon minimum when the
boundary layer is deepest), plus a winter-heavy seasonal term and lognormal noise. The
shape matters: the Q6 timezone check works by comparing diurnal shape, so a test series
with a flat or sinusoidal cycle would not exercise it meaningfully.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Hour-of-day multipliers: two peaks (08:00 and 20:00), afternoon trough (~15:00).
DIURNAL = np.array(
    [
        1.15,
        1.10,
        1.02,
        0.95,
        0.92,
        0.98,
        1.20,
        1.45,
        1.55,
        1.35,
        1.10,
        0.92,
        0.80,
        0.72,
        0.68,
        0.70,
        0.82,
        1.05,
        1.35,
        1.62,
        1.70,
        1.55,
        1.38,
        1.25,
    ]
)


def synthetic_pm25(
    start: str = "2021-01-01",
    end: str = "2024-12-31",
    *,
    base: float = 45.0,
    shift_hours: int = 0,
    seed: int = 0,
    tz: str = "UTC",
) -> pd.Series:
    """Hourly PM2.5 with a realistic diurnal + seasonal signal.

    `shift_hours` rotates the diurnal cycle, simulating a timezone error.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, end, freq="h", tz=tz)
    hour = idx.hour.to_numpy()
    doy = idx.dayofyear.to_numpy()

    diurnal = np.roll(DIURNAL, shift_hours)[hour]
    # Winter-heavy: peaks around 1 Jan, matching coal-heating season in the region.
    seasonal = 1.0 + 0.6 * np.cos(2 * np.pi * (doy - 1) / 365.25)
    noise = rng.lognormal(mean=0.0, sigma=0.28, size=len(idx))

    values = base * diurnal * seasonal * noise
    return pd.Series(values, index=idx, name="pm25")


@pytest.fixture
def clean_series() -> pd.Series:
    return synthetic_pm25(seed=1)


@pytest.fixture
def reference_composite_series() -> list[pd.Series]:
    """A small regional panel of correctly-aligned stations."""
    return [synthetic_pm25(seed=s, base=40 + 5 * s) for s in range(4)]
