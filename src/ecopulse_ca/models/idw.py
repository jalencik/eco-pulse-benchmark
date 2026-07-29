"""Task N rungs 1-2: nearest-monitor and inverse-distance weighting.

These are the baselines that decide whether a satellite PM2.5 model is worth anything. The
question a reviewer asks -- *does it beat just interpolating from the nearest monitors?* --
is answered here, and it is answered before any satellite data exists, so the comparison
cannot be tuned after the fact.

Both models defensively drop the target station from `observed` even though the interface
forbids it being there. Belt and braces: a leak of the held-out station into its own
prediction would inflate the nowcasting result silently and completely, and it is the one
error this project cannot afford to make.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecopulse_ca.models.base import Nowcaster, StationMeta, haversine_km_array

#: Distances below this are treated as co-located, to avoid a 1/0 weight.
MIN_DISTANCE_KM = 1e-6


class _SpatialBase(Nowcaster):
    """Shared fit/neighbour logic for the distance-based nowcasters.

    Station geometry is fixed once at `fit`, and distances to a given target are cached,
    because the target does not move between timestamps. Only the *values* change hour to
    hour. Recomputing the geometry 788k times was the dominant cost of evaluating the
    ladder and produced identical numbers every time.
    """

    is_deterministic = True

    def __init__(self, seed: int = 0) -> None:
        super().__init__(seed=seed)
        self._meta: dict[str, StationMeta] = {}
        self._ids: list[str] = []
        self._lats: np.ndarray = np.empty(0)
        self._lons: np.ndarray = np.empty(0)
        self._dist_cache: dict[str, np.ndarray] = {}

    def fit(self, panel: pd.DataFrame, meta: dict[str, StationMeta]) -> _SpatialBase:
        # Only stations present in the training panel are usable neighbours. Keeping meta
        # for stations absent from the panel would let a prediction reference a station
        # that contributed no training data.
        cols = {str(c) for c in panel.columns}
        self._meta = {sid: m for sid, m in meta.items() if sid in cols}
        self._ids = sorted(self._meta)
        self._lats = np.array([self._meta[s].latitude for s in self._ids], dtype=float)
        self._lons = np.array([self._meta[s].longitude for s in self._ids], dtype=float)
        self._dist_cache = {}
        self._fitted = True
        return self

    def _distances_to(self, target: StationMeta) -> np.ndarray:
        cached = self._dist_cache.get(target.station_id)
        if cached is None:
            cached = haversine_km_array(
                target.latitude, target.longitude, self._lats, self._lons
            )
            self._dist_cache[target.station_id] = cached
        return cached

    def _neighbours(
        self, observed: pd.Series, target: StationMeta
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """`(values, distances_km, ids)` for usable neighbours, nearest first.

        Excludes the target station, NaN readings, and any station without metadata.
        """
        if not self._ids:
            return np.empty(0), np.empty(0), []

        values = observed.reindex(self._ids).to_numpy(dtype=float)
        dists = self._distances_to(target)

        usable = np.isfinite(values)
        for i, sid in enumerate(self._ids):
            if sid == target.station_id:
                usable[i] = False  # the held-out station must never inform itself
        if not usable.any():
            return np.empty(0), np.empty(0), []

        v, d = values[usable], dists[usable]
        ids = [s for s, ok in zip(self._ids, usable, strict=True) if ok]
        order = np.argsort(d, kind="stable")
        return v[order], d[order], [ids[i] for i in order]


class NearestMonitor(_SpatialBase):
    """Copy the value of the nearest station that has a reading this hour.

    The floor of the nowcasting ladder. If a model cannot beat this, it has not learned
    anything about space that a map could not have told you.
    """

    @property
    def name(self) -> str:
        return "nearest_monitor"

    def predict(self, observed: pd.Series, target: StationMeta) -> float:
        self._require_fitted()
        values, _dists, _ids = self._neighbours(observed, target)
        if values.size == 0:
            return np.nan
        return float(values[0])


class IDW(_SpatialBase):
    """Inverse-distance weighting over the k nearest stations, weight = 1 / d**p.

    As ``p`` grows the weighting concentrates on the closest station, so IDW converges to
    `NearestMonitor`. That limit is a useful sanity check and is asserted in the tests.
    """

    def __init__(self, k: int = 5, p: float = 2.0, seed: int = 0) -> None:
        super().__init__(seed=seed)
        if k < 1:
            raise ValueError("k must be >= 1")
        if p <= 0:
            raise ValueError("p must be > 0")
        self.k = k
        self.p = p

    @property
    def name(self) -> str:
        return f"idw_k{self.k}_p{self.p:g}"

    def predict(self, observed: pd.Series, target: StationMeta) -> float:
        self._require_fitted()
        values, dists, _ids = self._neighbours(observed, target)
        if values.size == 0:
            return np.nan
        v, d = values[: self.k], dists[: self.k]

        # A co-located station is the answer; weighting it would divide by zero.
        exact = d <= MIN_DISTANCE_KM
        if exact.any():
            return float(v[exact].mean())

        w = 1.0 / np.power(d, self.p)
        total = w.sum()
        if not np.isfinite(total) or total <= 0:
            return np.nan
        return float(np.dot(w, v) / total)
