"""Task N rung 3: ordinary kriging with an exponential variogram.

Kriging is the geostatistical standard for interpolating a spatially correlated field, and
is the strongest of the credential-free nowcasting baselines. Unlike IDW it estimates the
field's actual spatial correlation structure from data rather than assuming a fixed
distance decay.

Honest limitation, stated up front
----------------------------------
This benchmark has **at most 9 distinct instruments across 7 cities**, hundreds of
kilometres apart. That is far too sparse to estimate a variogram well: with so few pairs
the empirical variogram is noisy, and the fitted range is barely constrained. Kriging is
included because the ladder demands it and because its *uncertainty* estimate is
informative, **not** because its point predictions should be expected to beat IDW at this
density. If it loses to IDW, that is the finding -- it is not a tuning failure.

Fallback behaviour
------------------
If the kriging system is singular or ill-conditioned -- which sparse, nearly-collinear
station geometry makes likely -- the model falls back to IDW for that prediction and
records it. `fallback_rate` reports how often that happened, so a result table can never
present "kriging" numbers that were mostly IDW underneath.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from ecopulse_ca.models.base import Nowcaster, StationMeta, haversine_km
from ecopulse_ca.models.idw import IDW

#: Above this condition number the kriging system is treated as unsolvable.
MAX_CONDITION = 1e12


def exponential_variogram(h: np.ndarray, nugget: float, sill: float, rng: float) -> np.ndarray:
    """gamma(h) = nugget + sill * (1 - exp(-h / range)), with gamma(0) = 0."""
    rng = max(float(rng), 1e-9)
    out = nugget + sill * (1.0 - np.exp(-np.asarray(h, dtype=float) / rng))
    return np.where(np.asarray(h, dtype=float) == 0.0, 0.0, out)


class OrdinaryKriging(Nowcaster):
    """Ordinary kriging with an exponential variogram fitted by least squares."""

    is_deterministic = True

    def __init__(self, seed: int = 0, n_bins: int = 10, fallback_k: int = 5) -> None:
        super().__init__(seed=seed)
        self.n_bins = n_bins
        self._meta: dict[str, StationMeta] = {}
        self._params: tuple[float, float, float] | None = None
        self._fallback = IDW(k=fallback_k, p=2.0, seed=seed)
        self._n_predictions = 0
        self._n_fallbacks = 0

    @property
    def name(self) -> str:
        return "ordinary_kriging_exp"

    @property
    def fallback_rate(self) -> float:
        """Share of predictions that silently became IDW. Report this alongside metrics."""
        return self._n_fallbacks / self._n_predictions if self._n_predictions else 0.0

    @property
    def variogram_params(self) -> tuple[float, float, float] | None:
        """(nugget, sill, range_km), or None if the variogram could not be fitted."""
        return self._params

    def fit(self, panel: pd.DataFrame, meta: dict[str, StationMeta]) -> OrdinaryKriging:
        self._meta = {sid: m for sid, m in meta.items() if sid in panel.columns}
        self._fallback.fit(panel, meta)
        self._n_predictions = self._n_fallbacks = 0

        stations = [s for s in panel.columns if str(s) in self._meta]
        if len(stations) < 3:
            # Fewer than three stations cannot constrain nugget, sill and range.
            self._params = None
            self._fitted = True
            return self

        # Empirical variogram: half the mean squared difference between station pairs,
        # pooled over time, binned by separation distance.
        dists, semivars = [], []
        for i, a in enumerate(stations):
            for b in stations[i + 1:]:
                pair = panel[[a, b]].dropna()
                if len(pair) < 10:  # too few concurrent observations to be informative
                    continue
                ma, mb = self._meta[str(a)], self._meta[str(b)]
                d = haversine_km(ma.latitude, ma.longitude, mb.latitude, mb.longitude)
                diff = pair[a].to_numpy(dtype=float) - pair[b].to_numpy(dtype=float)
                dists.append(d)
                semivars.append(0.5 * float(np.mean(diff**2)))

        if len(dists) < 3:
            self._params = None
            self._fitted = True
            return self

        d_arr = np.asarray(dists, dtype=float)
        g_arr = np.asarray(semivars, dtype=float)

        sill0 = float(np.nanmax(g_arr)) or 1.0
        range0 = float(np.nanmax(d_arr)) / 3.0 or 1.0

        def residual(theta: np.ndarray) -> np.ndarray:
            return exponential_variogram(d_arr, *theta) - g_arr

        try:
            fit = least_squares(
                residual,
                x0=np.array([0.0, sill0, range0]),
                bounds=([0.0, 1e-9, 1e-3], [sill0 * 2 + 1e-9, sill0 * 10 + 1e-9, np.inf]),
                max_nfev=2000,
            )
            self._params = (float(fit.x[0]), float(fit.x[1]), float(fit.x[2]))
        except (ValueError, np.linalg.LinAlgError):
            self._params = None

        self._fitted = True
        return self

    def _usable(self, observed: pd.Series, target: StationMeta) -> list[tuple[str, float]]:
        out = []
        for sid, value in observed.items():
            sid = str(sid)
            if sid == target.station_id:
                continue  # the held-out station must never inform its own prediction
            if value is None or not np.isfinite(value) or sid not in self._meta:
                continue
            out.append((sid, float(value)))
        return out

    def predict(self, observed: pd.Series, target: StationMeta) -> float:
        self._require_fitted()
        self._n_predictions += 1

        usable = self._usable(observed, target)
        if not usable:
            return np.nan
        if self._params is None or len(usable) < 2:
            self._n_fallbacks += 1
            return self._fallback.predict(observed, target)

        nugget, sill, rng = self._params
        n = len(usable)
        coords = [self._meta[sid] for sid, _ in usable]
        values = np.array([v for _, v in usable], dtype=float)

        # Ordinary kriging system with the Lagrange multiplier enforcing unbiasedness.
        a = np.ones((n + 1, n + 1), dtype=float)
        a[n, n] = 0.0
        for i in range(n):
            for j in range(n):
                d = haversine_km(
                    coords[i].latitude, coords[i].longitude,
                    coords[j].latitude, coords[j].longitude,
                )
                a[i, j] = exponential_variogram(np.array([d]), nugget, sill, rng)[0]

        b = np.ones(n + 1, dtype=float)
        for i in range(n):
            d = haversine_km(
                target.latitude, target.longitude, coords[i].latitude, coords[i].longitude
            )
            b[i] = exponential_variogram(np.array([d]), nugget, sill, rng)[0]

        try:
            if np.linalg.cond(a) > MAX_CONDITION:
                raise np.linalg.LinAlgError("ill-conditioned kriging system")
            weights = np.linalg.solve(a, b)[:n]
        except np.linalg.LinAlgError:
            self._n_fallbacks += 1
            return self._fallback.predict(observed, target)

        estimate = float(np.dot(weights, values))
        return estimate if np.isfinite(estimate) else np.nan
