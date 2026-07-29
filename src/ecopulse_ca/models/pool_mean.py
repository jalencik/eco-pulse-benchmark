"""Task N rung 0: the achievable constant.

Why this rung exists
--------------------
Negative R² on leave-city-out means "worse than the held-out city's own mean". But that
mean is computed from the held-out city's test-block labels -- exactly what leave-city-out
forbids a model from seeing. It is an **oracle** reference: informative about how hard the
target is, useless as a baseline, and impossible to beat by legitimate means in a
zero-local-label setting.

`TrainingPoolMean` is the *achievable* version: the mean concentration across the training
cities over the training block. It uses no local labels and no future data, so any model
claiming to have learned something about an unmonitored city must beat it. On this
benchmark it sits at RMSE 43.09 -- between ordinary kriging (40.92, which beats it) and IDW
(43.65, which does not).

Reporting "nothing beats a constant" without distinguishing these two references would have
been wrong, and would have understated the one nowcasting rung that actually works.

Why it is a `Nowcaster` and not a special case
----------------------------------------------
It implements the same interface as every other rung, so the evaluation harness, leakage
tests and Diebold-Mariano comparisons apply to it unchanged. A reference model exempted
from the contract is a reference nobody can check.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecopulse_ca.models.base import Nowcaster, StationMeta


class TrainingPoolMean(Nowcaster):
    """Predict a single constant: the mean over training stations in the training block.

    The constant is whatever `fit()` is given. The harness passes the training-block slice
    of the training cities, so the value never touches the held-out city or the test
    period. `fitted_value` is exposed so the reported number can be checked by hand.
    """

    is_deterministic = True

    def __init__(self, seed: int = 0, use_median: bool = False) -> None:
        super().__init__(seed=seed)
        self.use_median = use_median
        self._value: float = float("nan")
        self._n_train: int = 0

    @property
    def name(self) -> str:
        return f"training_pool_{'median' if self.use_median else 'mean'}"

    @property
    def fitted_value(self) -> float:
        """The constant this model predicts. Checkable against the manifest by hand."""
        return self._value

    @property
    def n_training_observations(self) -> int:
        return self._n_train

    def fit(self, panel: pd.DataFrame, meta: dict[str, StationMeta]) -> TrainingPoolMean:
        flat = panel.to_numpy(dtype=float).ravel()
        flat = flat[np.isfinite(flat)]
        self._n_train = int(flat.size)
        if flat.size == 0:
            self._value = float("nan")
        else:
            self._value = float(np.median(flat) if self.use_median else np.mean(flat))
        self._fitted = True
        return self

    def predict(self, observed: pd.Series, target: StationMeta) -> float:
        """Return the fitted constant.

        `observed` is deliberately unused: this rung exists to answer "how much does a
        model gain over knowing nothing about the current hour?" Reading `observed` at all
        would make it a different, stronger model and destroy that interpretation.
        """
        self._require_fitted()
        return self._value
