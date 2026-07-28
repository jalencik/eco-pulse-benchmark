"""Task F rung 3: seasonal climatology.

Predicts the historical mean for the target's (month, hour-of-day) cell. In a region whose
PM2.5 is dominated by a winter coal-heating peak and a strong diurnal boundary-layer cycle,
this is a genuinely strong baseline -- it encodes both dominant periodicities and nothing
else, so beating it demonstrates that a model has learned something beyond "winter nights
are bad".

Two properties are load-bearing:

- **Fitted only on what `fit` receives.** The training fold is the entire universe. A
  climatology accidentally computed over the full record is a textbook leak: the test
  block's own values would enter its prediction.
- **Explicit fallback chain.** A (month, hour) cell can be empty in a sparse record.
  Falling back cell -> hour -> month -> global keeps predictions defined without silently
  inventing a value, and `cell_source()` reports which level was used so the error analysis
  can separate "climatology was well-estimated" from "climatology fell back to the mean".
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from ecopulse_ca.models.base import Forecaster

CellSource = Literal["cell", "hour", "month", "global", "none"]


class Climatology(Forecaster):
    """Mean (or median) PM2.5 by (month, hour-of-day), estimated on the training fold."""

    is_deterministic = True

    def __init__(self, seed: int = 0, use_median: bool = False) -> None:
        super().__init__(seed=seed)
        self.use_median = use_median
        self._cell: pd.Series | None = None
        self._by_hour: pd.Series | None = None
        self._by_month: pd.Series | None = None
        self._global: float = np.nan

    @property
    def name(self) -> str:
        return f"climatology_{'median' if self.use_median else 'mean'}"

    def fit(self, history: pd.Series) -> Climatology:
        observed = history.dropna()
        if observed.empty:
            self._cell = self._by_hour = self._by_month = None
            self._global = np.nan
            self._fitted = True
            return self

        idx = pd.DatetimeIndex(observed.index)
        frame = pd.DataFrame(
            {"value": observed.to_numpy(), "month": idx.month, "hour": idx.hour}
        )
        agg = "median" if self.use_median else "mean"

        self._cell = frame.groupby(["month", "hour"])["value"].agg(agg)
        self._by_hour = frame.groupby("hour")["value"].agg(agg)
        self._by_month = frame.groupby("month")["value"].agg(agg)
        self._global = float(frame["value"].median() if self.use_median else frame["value"].mean())
        self._fitted = True
        return self

    def cell_source(self, timestamp: pd.Timestamp) -> CellSource:
        """Which level of the fallback chain would serve this timestamp.

        Exposed so the error analysis can distinguish a well-estimated climatology from one
        that quietly degraded to a global mean.
        """
        if self._cell is None:
            return "none"
        month, hour = int(timestamp.month), int(timestamp.hour)
        if (month, hour) in self._cell.index:
            return "cell"
        if self._by_hour is not None and hour in self._by_hour.index:
            return "hour"
        if self._by_month is not None and month in self._by_month.index:
            return "month"
        return "global" if np.isfinite(self._global) else "none"

    def _lookup(self, timestamp: pd.Timestamp) -> float:
        month, hour = int(timestamp.month), int(timestamp.hour)
        source = self.cell_source(timestamp)
        if source == "cell" and self._cell is not None:
            return float(self._cell.loc[(month, hour)])
        if source == "hour" and self._by_hour is not None:
            return float(self._by_hour.loc[hour])
        if source == "month" and self._by_month is not None:
            return float(self._by_month.loc[month])
        if source == "global":
            return self._global
        return np.nan

    def predict(self, history: pd.Series, horizons: tuple[int, ...]) -> pd.Series:
        self._require_fitted()
        if history.empty:
            return pd.Series([np.nan] * len(horizons), index=list(horizons), dtype=float)
        origin = pd.DatetimeIndex(history.index)[-1]
        values = [self._lookup(origin + pd.Timedelta(hours=h)) for h in horizons]
        return pd.Series(values, index=list(horizons), dtype=float)
