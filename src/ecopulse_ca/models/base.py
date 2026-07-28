"""Frozen interface for every model on the baseline ladder.

**This file is the contract. Do not change it to accommodate a model** -- if a model does
not fit, that is information about the model, not a reason to loosen the interface.

Two tasks, deliberately separate types, because the project forbids mixing their metrics in
one table:

- `Forecaster` (Task F): at a monitored station, predict t+h from that station's own past.
- `Nowcaster`  (Task N): estimate the value at a location with **no local training labels**,
  from other stations observed at the same timestamp.

The split is not cosmetic. A forecaster may look at the target station's history and must
not look at the future; a nowcaster may look at the present everywhere else and must not
look at the target station at all. Sharing one `fit/predict` signature would make those two
very different prohibitions impossible to enforce or to test.

Determinism contract
--------------------
Every model takes a `seed`, and `fit` must be deterministic given `(data, seed)`. Models
with no stochastic component -- persistence, climatology, IDW, kriging -- have **zero seed
variance by construction**. That is reported as exactly zero, never disguised as a small
spread. `is_deterministic` declares which case a model is in so the results table can say
so honestly rather than implying five independent runs happened.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StationMeta:
    """Static description of a station. No time-varying content by design."""

    station_id: str
    latitude: float
    longitude: float
    city: str | None = None
    is_reference: bool = False


class Model(ABC):
    """Common base. Subclass `Forecaster` or `Nowcaster`, not this."""

    #: False only for models with a genuine stochastic component.
    is_deterministic: bool = True

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self._fitted = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in results tables and the run log."""

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError(f"{self.name}: predict() called before fit()")


class Forecaster(Model):
    """Task F: predict a station's own future from its own past.

    Contract:
      `fit(history)`   -- history is a single station's hourly series, train fold only.
      `predict(history, horizons)` -- for each h, the value at `history.index[-1] + h` hours.

    **Must never index beyond the last timestamp of `history`.** The purge gap in the split
    protects against block-boundary bleed; this contract protects against a model reaching
    forward within a block.
    """

    @abstractmethod
    def fit(self, history: pd.Series) -> Forecaster:
        """Fit on one station's training-fold history. Returns self."""

    @abstractmethod
    def predict(self, history: pd.Series, horizons: tuple[int, ...]) -> pd.Series:
        """Return one prediction per horizon, indexed by horizon in hours."""


class Nowcaster(Model):
    """Task N: estimate a target station's value from *other* stations at the same time.

    Contract:
      `fit(panel, meta)`  -- panel is a wide frame (hourly index x station columns) over
                             training stations only. The target station must not appear.
      `predict(observed, target)` -- `observed` is one timestamp's values at the training
                             stations; `target` is the held-out station's metadata.

    The held-out station contributes **no labels at any point**. A nowcaster that reads
    `target.station_id` out of `panel` is leaking, and `tests/` will catch it.
    """

    @abstractmethod
    def fit(self, panel: pd.DataFrame, meta: dict[str, StationMeta]) -> Nowcaster:
        """Fit on the training stations' panel. Returns self."""

    @abstractmethod
    def predict(self, observed: pd.Series, target: StationMeta) -> float:
        """Estimate the target station's value from one timestamp of observations.

        `observed` is indexed by training station_id. It may contain NaN where a station
        has no reading at that hour; a model must handle that rather than assume density.
        Return `np.nan` when no estimate is possible -- never a silent zero or a fill value,
        which would be scored as a confident wrong answer.
        """


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres. Shared by the spatial baselines."""
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))
