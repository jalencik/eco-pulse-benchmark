"""Derived features computed locally -- no credentials, no network, no Earth Engine.

`distance_to_aralkum` is pure geometry, so it is the one Phase 4 feature that can be built
and checked today. It also happens to be the one with the clearest physical motivation:
the Aral Sea dry bed is the region's dominant salt-dust source, and salt-dust events peak
in **spring**, a different season from the winter coal-combustion peak that drives Bishkek
and Ashgabat. If the benchmark's cities separate by distance to the Aralkum, that is a
regime signal no amount of meteorology would supply.

Why a set of points rather than one centroid
--------------------------------------------
The Aralkum is roughly 60,000 km^2. A single centroid would place Tashkent and Nukus at
misleadingly similar distances when Nukus sits on the desert's edge. Distance is therefore
computed to the **nearest** of several points spanning the exposed bed, which is what a
dust-transport argument actually depends on.

The coordinates below are approximate, drawn from the documented extent of the former sea,
and are declared as such. They are a source of error in the feature, not a hidden constant.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ecopulse_ca.models.base import haversine_km

#: Representative points across the exposed Aral Sea bed (the Aralkum).
#:
#: APPROXIMATE. The former sea spanned roughly 43.5-46.8 N, 58-62 E; the eastern basin of
#: the South Aral is the most active dust source and is weighted with more points here.
#: These are literature-informed estimates, not a surveyed boundary -- treat the resulting
#: distances as accurate to tens of kilometres, which is well inside what a dust-transport
#: gradient over hundreds of kilometres requires.
ARALKUM_POINTS: tuple[tuple[float, float], ...] = (
    (45.20, 59.00),  # North Aral / Small Aral southern shore
    (44.60, 58.80),  # western South Aral, exposed bed
    (44.30, 59.60),  # central South Aral, eastern basin
    (44.90, 60.20),  # north-eastern exposed bed -- most active dust source
    (43.90, 59.20),  # southern exposed bed, toward Amu Darya delta
    (45.60, 60.50),  # north-eastern margin
)


@dataclass(frozen=True)
class AralkumDistance:
    station_id: str
    distance_km: float
    nearest_point: tuple[float, float]


def distance_to_aralkum(latitude: float, longitude: float) -> float:
    """Great-circle distance in km to the nearest point on the Aral dry bed."""
    return min(haversine_km(latitude, longitude, lat, lon) for lat, lon in ARALKUM_POINTS)


def nearest_aralkum_point(latitude: float, longitude: float) -> tuple[float, float]:
    return min(
        ARALKUM_POINTS,
        key=lambda p: haversine_km(latitude, longitude, p[0], p[1]),
    )


def build_aralkum_distances(stations: pd.DataFrame) -> pd.DataFrame:
    """Per-station distance to the Aralkum.

    `stations` needs `station_id`, `latitude`, `longitude`. Returns one row per station --
    static, so no time dimension.
    """
    required = {"station_id", "latitude", "longitude"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"stations frame is missing {sorted(missing)}")

    rows = []
    for _, s in stations.iterrows():
        lat, lon = float(s["latitude"]), float(s["longitude"])
        if not (np.isfinite(lat) and np.isfinite(lon)):
            raise ValueError(f"station {s['station_id']} has non-finite coordinates")
        near = nearest_aralkum_point(lat, lon)
        rows.append(
            {
                "station_id": str(s["station_id"]),
                "city": s.get("city"),
                "feature": "distance_to_aralkum",
                "value": round(distance_to_aralkum(lat, lon), 2),
                "nearest_aralkum_lat": near[0],
                "nearest_aralkum_lon": near[1],
                "fixture": False,
            }
        )
    return pd.DataFrame(rows).sort_values("value").reset_index(drop=True)
