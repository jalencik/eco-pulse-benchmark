"""Task F rungs 1-2: persistence and its diurnal variants.

These are the baselines a forecasting model must beat before anything else is worth
reporting. They are cheap, they are deterministic, and in short-horizon air quality they
are much harder to beat than newcomers expect.

A degeneracy worth stating plainly
----------------------------------
`DiurnalPersistence` predicts the most recent observation sharing the target's hour of day:

    yhat(t+h) = y(t + h - 24 * ceil(h/24))

For every horizon in this project -- 24, 48, 72 -- ``h`` is a multiple of 24, so
``h - 24*ceil(h/24) == 0`` and the prediction is **exactly ``y(t)``: identical to plain
persistence.** The rung only separates from persistence at horizons that are not multiples
of 24.

This is documented rather than hidden because the alternative is two rows in a results
table with bit-identical numbers and no explanation, which reads as a copy-paste error.
`SameHourMean` is provided as the rung that *is* genuinely distinct at these horizons.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecopulse_ca.models.base import Forecaster


class Persistence(Forecaster):
    """yhat(t+h) = y(t) for every horizon -- the last observed value."""

    is_deterministic = True

    @property
    def name(self) -> str:
        return "persistence"

    def fit(self, history: pd.Series) -> Persistence:
        # Nothing to learn. fit() still records state so that the predict()-before-fit()
        # contract is enforced uniformly across the ladder.
        self._fitted = True
        return self

    def predict(self, history: pd.Series, horizons: tuple[int, ...]) -> pd.Series:
        self._require_fitted()
        observed = history.dropna()
        last = float(observed.iloc[-1]) if not observed.empty else np.nan
        return pd.Series([last] * len(horizons), index=list(horizons), dtype=float)


class DiurnalPersistence(Forecaster):
    """yhat(t+h) = the most recent observation at the target's hour of day.

    See the module docstring: for h in {24, 48, 72} this reduces exactly to `Persistence`.
    The implementation is written for general h so the reduction is a consequence of the
    arithmetic rather than a special case, and so the equivalence is testable.
    """

    is_deterministic = True

    @property
    def name(self) -> str:
        return "diurnal_persistence"

    def fit(self, history: pd.Series) -> DiurnalPersistence:
        self._fitted = True
        return self

    def predict(self, history: pd.Series, horizons: tuple[int, ...]) -> pd.Series:
        self._require_fitted()
        observed = history.dropna()
        if observed.empty:
            return pd.Series([np.nan] * len(horizons), index=list(horizons), dtype=float)

        origin = observed.index[-1]
        out: list[float] = []
        for h in horizons:
            # Step back whole days from the target until at or before the forecast origin.
            offset = h - 24 * int(np.ceil(h / 24)) if h % 24 else 0
            lookup = origin + pd.Timedelta(hours=offset)
            prior = observed.loc[:lookup]
            out.append(float(prior.iloc[-1]) if not prior.empty else np.nan)
        return pd.Series(out, index=list(horizons), dtype=float)


class SameHourMean(Forecaster):
    """yhat(t+h) = mean of the last `n_days` observations at the target's hour of day.

    The rung that genuinely differs from persistence at multiples of 24. Averaging over
    recent same-hour values keeps the diurnal shape while damping single-day noise, which
    is what makes it a meaningfully stronger naive baseline than persistence alone.

    Median is offered because Central Asian PM2.5 is heavily right-skewed -- a single dust
    or inversion episode inside the window can dominate a mean.
    """

    is_deterministic = True

    def __init__(self, n_days: int = 7, seed: int = 0, use_median: bool = False) -> None:
        super().__init__(seed=seed)
        if n_days < 1:
            raise ValueError("n_days must be >= 1")
        self.n_days = n_days
        self.use_median = use_median

    @property
    def name(self) -> str:
        stat = "median" if self.use_median else "mean"
        return f"same_hour_{stat}_{self.n_days}d"

    def fit(self, history: pd.Series) -> SameHourMean:
        self._fitted = True
        return self

    def predict(self, history: pd.Series, horizons: tuple[int, ...]) -> pd.Series:
        self._require_fitted()
        observed = history.dropna()
        if observed.empty:
            return pd.Series([np.nan] * len(horizons), index=list(horizons), dtype=float)

        origin = pd.DatetimeIndex(observed.index)[-1]
        hours = pd.DatetimeIndex(observed.index).hour
        out: list[float] = []
        for h in horizons:
            target_hour = int((origin + pd.Timedelta(hours=h)).hour)
            same_hour = observed[hours == target_hour]
            # Only history at or before the origin is admissible: reaching past the origin
            # would be lookahead inside the block, which the purge gap does not protect.
            same_hour = same_hour.loc[:origin].tail(self.n_days)
            if same_hour.empty:
                out.append(np.nan)
            else:
                out.append(
                    float(same_hour.median()) if self.use_median else float(same_hour.mean())
                )
        return pd.Series(out, index=list(horizons), dtype=float)
