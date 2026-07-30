"""Autoregressive and spatial features, separated by which task may legally use them.

The distinction this module exists to enforce
---------------------------------------------
**Local lags (`pm25_lag*`) are Task F only.** They use the target station's own history,
which is the definition of forecasting at a monitored station -- and is *illegal* under
leave-city-out, where the held-out city has no sensor by construction. Feeding a held-out
city its own lagged PM2.5 turns the protocol into "leave-city-out of training, but install
a sensor at test time", a different and far easier problem.

That applies to EVERY fold, not only Khujand. When Almaty is held out, Almaty is an
unmonitored city for that fold, exactly as Khujand always is.

**Spatial neighbour features are Task N legal.** They aggregate PM2.5 from OTHER stations,
with the held-out city excluded, so no label from the target city informs its own
prediction. `build_spatial_features` takes `exclude_city` and the resulting columns are the
only target-derived information a leave-city-out model may see.

Daily resolution
----------------
All satellite inputs are daily composites, so lags are in DAYS (t-1d, t-2d, t-7d) rather
than the hours used by the Phase 3 hourly ladder.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecopulse_ca.models.base import haversine_km

LAG_DAYS = (1, 2, 7)
ROLL_WINDOWS = (7, 30)


def build_local_lags(df: pd.DataFrame, target: str = "pm25") -> pd.DataFrame:
    """Per-station autoregressive features. TASK F ONLY -- never under leave-city-out.

    Shifted strictly into the past: `pm25_lag1d` at date D is the value at D-1, so no row
    can see its own target. Rolling means are computed on the shifted series for the same
    reason -- a window including D would contain the answer.
    """
    out = df.sort_values(["station_id", "date"]).copy()
    g = out.groupby("station_id")[target]
    for lag in LAG_DAYS:
        out[f"pm25_lag{lag}d"] = g.shift(lag)
    shifted = g.shift(1)
    for w in ROLL_WINDOWS:
        out[f"pm25_roll{w}d"] = (
            shifted.groupby(out["station_id"]).rolling(w, min_periods=max(2, w // 3))
            .mean().reset_index(level=0, drop=True)
        )
    out["pm25_delta_1d"] = out["pm25_lag1d"] - out["pm25_lag2d"]
    return out


def build_spatial_features(
    df: pd.DataFrame,
    coords: dict[str, tuple[float, float]],
    exclude_city: str,
    target: str = "pm25",
    power: float = 2.0,
) -> pd.DataFrame:
    """Neighbour-derived target features. TASK N LEGAL.

    For each station-day, aggregates PM2.5 from stations in OTHER cities. `exclude_city` is
    dropped from the donor pool entirely, so a held-out city never contributes to its own
    features -- the same guarantee the nowcasting models enforce in `_neighbours`.

    Emits an IDW-weighted regional estimate, a plain regional mean, and the donor count.
    The count matters: an estimate from one reporting neighbour is a different fact from one
    built on five, and without it the model cannot tell them apart.
    """
    donors = df[df.city != exclude_city][["station_id", "date", target]].dropna()
    if donors.empty:
        base = df.copy()
        base["nbr_idw"] = np.nan
        base["nbr_mean"] = np.nan
        base["nbr_count"] = 0
        return base

    by_date: dict[pd.Timestamp, pd.DataFrame] = dict(tuple(donors.groupby("date")))
    idw_vals, mean_vals, counts = [], [], []

    for _, row in df.iterrows():
        day = by_date.get(row["date"])
        if day is None or day.empty:
            idw_vals.append(np.nan); mean_vals.append(np.nan); counts.append(0)
            continue
        day = day[day.station_id != row["station_id"]]
        if day.empty:
            idw_vals.append(np.nan); mean_vals.append(np.nan); counts.append(0)
            continue
        lat, lon = coords[row["station_id"]]
        d = np.array([
            haversine_km(lat, lon, *coords[s]) for s in day.station_id
        ], dtype=float)
        v = day[target].to_numpy(dtype=float)
        d = np.maximum(d, 1e-6)
        w = 1.0 / np.power(d, power)
        idw_vals.append(float(np.dot(w, v) / w.sum()))
        mean_vals.append(float(v.mean()))
        counts.append(int(len(v)))

    out = df.copy()
    out["nbr_idw"] = idw_vals
    out["nbr_mean"] = mean_vals
    out["nbr_count"] = counts
    return out


LOCAL_LAG_COLS = (
    [f"pm25_lag{l}d" for l in LAG_DAYS]
    + [f"pm25_roll{w}d" for w in ROLL_WINDOWS]
    + ["pm25_delta_1d"]
)
SPATIAL_COLS = ["nbr_idw", "nbr_mean", "nbr_count"]
