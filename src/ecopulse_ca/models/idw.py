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

from ecopulse_ca.models.base import Nowcaster, StationMeta, haversine_km

#: Distances below this are treated as co-located, to avoid a 1/0 weight.
MIN_DISTANCE_KM = 1e-6


class _SpatialBase(Nowcaster):
    """Shared fit/neighbour logic for the distance-based nowcasters."""

    is_deterministic = True

    def __init__(self, seed: int = 0) -> None:
        super().__init__(seed=seed)
        self._meta: dict[str, StationMeta] = {}

    def fit(self, panel: pd.DataFrame, meta: dict[str, StationMeta]) -> _SpatialBase:
        # Only stations present in the training panel are usable neighbours. Keeping meta
        # for stations absent from the panel would let a prediction reference a station
        # that contributed no training data.
        self._meta = {sid: m for sid, m in meta.items() if sid in panel.columns}
        self._fitted = True
        return self

    def _neighbours(self, observed: pd.Series, target: StationMeta) -> pd.DataFrame:
        """Usable neighbours with distances, nearest first.

        Excludes the target station, NaN readings, and any station without metadata.
        """
        rows = []
        for sid, value in observed.items():
            sid = str(sid)
            if sid == target.station_id:
                continue  # defensive: the held-out station must never inform itself
            if value is None or not np.isfinite(value):
                continue
            m = self._meta.get(sid)
            if m is None:
                continue
            d = haversine_km(target.latitude, target.longitude, m.latitude, m.longitude)
            rows.append({"station_id": sid, "value": float(value), "distance_km": d})

        if not rows:
            return pd.DataFrame(columns=["station_id", "value", "distance_km"])
        return pd.DataFrame(rows).sort_values("distance_km").reset_index(drop=True)


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
        neighbours = self._neighbours(observed, target)
        if neighbours.empty:
            return np.nan
        return float(neighbours.iloc[0]["value"])


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
        neighbours = self._neighbours(observed, target).head(self.k)
        if neighbours.empty:
            return np.nan

        d = neighbours["distance_km"].to_numpy(dtype=float)
        v = neighbours["value"].to_numpy(dtype=float)

        # A co-located station is the answer; weighting it would divide by zero.
        exact = d <= MIN_DISTANCE_KM
        if exact.any():
            return float(v[exact].mean())

        w = 1.0 / np.power(d, self.p)
        total = w.sum()
        if not np.isfinite(total) or total <= 0:
            return np.nan
        return float(np.dot(w, v) / total)
