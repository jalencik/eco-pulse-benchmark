"""Copernicus (CDS/ADS) extraction: CAMS forecasts and ERA5 reanalysis.

A fundamentally different pipeline from Earth Engine. Copernicus delivers NetCDF files, so
there is no server-side reduction -- files land on disk and must be reduced locally, then
deleted. With 8.2 GB free that is workable only because requests are area-subset to the
station bounding box and each chunk is removed after extraction.

Three properties measured on 2026-07-30, each of which would corrupt results if assumed
-------------------------------------------------------------------------------------
**1. CAMS PM2.5 arrives in kg m^-3, not ug/m^3.** Values are ~1e-8. A model trains
identically either way, but the mandated "beat raw CAMS" comparison is only meaningful in
the target's units -- 1e-8 against 25 ug/m^3 would make CAMS look infinitely wrong. The
x1e9 conversion is applied here and asserted by test. This is the GHSL per-cell-count error
in a new costume.

**2. `leadtime_hour` is the deployability lever, and step 0 would quietly cheat.** CAMS
"forecast" at leadtime 0 has assimilated observations at the valid time, so using it to
predict that time is lookahead wearing a forecast label. `DEPLOYABLE_LEADTIME_H = 24` is
the forecast issued a day earlier -- what a live service actually holds, and the only choice
consistent with the 12 h latency the catalogue claims.

**3. ERA5 splits instantaneous and accumulated variables into SEPARATE files** inside one
zip (`stepType-instant` and `stepType-accum`). `total_precipitation` is an hourly
accumulation with a different timestamp convention, so merging the two naively misaligns
precipitation by an hour.

Resolution mismatch, recorded not hidden
----------------------------------------
ERA5 gives 26x78 cells over the station box; CAMS gives 16x49 (~0.4 deg). Several stations
therefore fall in the SAME CAMS cell and cannot be distinguished by it. Extraction takes the
containing cell and records collisions, rather than interpolating -- bilinear would hand
each station a distinct value that is an artefact of interpolation, not information.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CDS_URL = "https://cds.climate.copernicus.eu/api"
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"

#: Forecast step used for CAMS. NOT 0 -- see module docstring.
DEPLOYABLE_LEADTIME_H = 24

#: kg m^-3 -> ug m^-3.
KG_M3_TO_UG_M3 = 1e9

#: Measured CDS/ADS per-request cost ceilings (2026-07-30). Rejection is instant, so these
#: were probed rather than guessed: 4 months x 5 vars ACCEPTED, 6 x 5 REJECTED, 6 x 3
#: ACCEPTED -- cost scales as months x variables.
ERA5_MAX_MONTHS_PER_REQUEST = 4
CAMS_MAX_MONTHS_PER_REQUEST = 3


@dataclass(frozen=True)
class StationCell:
    """Which grid cell a station falls in, and who it shares it with."""

    station_id: str
    city: str
    lat_idx: int
    lon_idx: int
    cell_lat: float
    cell_lon: float
    offset_km: float
    shares_cell_with: tuple[str, ...] = field(default_factory=tuple)


def station_bbox(lats: list[float], lons: list[float], pad_deg: float = 0.5) -> list[float]:
    """CDS `area` order is [North, West, South, East] -- not a lat/lon pair."""
    return [max(lats) + pad_deg, min(lons) - pad_deg, min(lats) - pad_deg, max(lons) + pad_deg]


def month_blocks(start: str, end: str, months_per_block: int) -> list[list[tuple[int, int]]]:
    """Group (year, month) pairs into request-sized blocks, NEVER spanning a year boundary.

    CDS treats `year` and `month` as a CROSS PRODUCT, not a sequence. A block of
    [(2018,11), (2018,12), (2019,1), (2019,2)] becomes years=[2018,2019] x
    months=[01,02,11,12] -- eight month-units instead of four. That doubles the request cost
    (every block failed with `cost limits exceeded`) and, more insidiously, silently
    requests months NOT in the block at all: 2018-01, 2018-02, 2019-11, 2019-12. Had the
    ceiling been slightly higher those requests would have SUCCEEDED and returned
    overlapping data across blocks, which the downstream groupby().first() would have
    absorbed without complaint.

    Blocks are therefore confined to a single calendar year, so cross product and sequence
    coincide and the cost is exactly `months x variables`.

    The original probe missed this because it tested year=["2024"], month=[1,2,3,4] -- a
    single year, where the two interpretations are identical.
    """
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    pairs = [(d.year, d.month) for d in pd.date_range(lo.replace(day=1), hi, freq="MS")]
    by_year: dict[int, list[tuple[int, int]]] = {}
    for y, m in pairs:
        by_year.setdefault(y, []).append((y, m))
    blocks: list[list[tuple[int, int]]] = []
    for year in sorted(by_year):
        months = by_year[year]
        for i in range(0, len(months), months_per_block):
            blocks.append(months[i : i + months_per_block])
    return blocks


def unzip_members(path: Path, dest: Path) -> list[Path]:
    """Return NetCDF members. ERA5 wraps instant/accum in a zip even for `unarchived`."""
    if not zipfile.is_zipfile(path):
        return [path]
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.extractall(dest)
        return [dest / n for n in zf.namelist()]


def assign_cells(
    ds_lats: np.ndarray,
    ds_lons: np.ndarray,
    stations: list[tuple[str, str, float, float]],
) -> list[StationCell]:
    """Nearest containing grid cell per station, with collisions recorded.

    No interpolation: at ~0.4 deg CAMS resolution, bilinear would give each station a
    distinct value that reflects the interpolation scheme rather than the model.
    """
    cells: list[StationCell] = []
    for sid, city, lat, lon in stations:
        i = int(np.abs(ds_lats - lat).argmin())
        j = int(np.abs(ds_lons - lon).argmin())
        clat, clon = float(ds_lats[i]), float(ds_lons[j])
        # Rough great-circle offset from station to cell centre.
        dlat_km = (clat - lat) * 111.0
        dlon_km = (clon - lon) * 111.0 * np.cos(np.radians(lat))
        cells.append(StationCell(sid, city, i, j, clat, clon, float(np.hypot(dlat_km, dlon_km))))

    by_cell: dict[tuple[int, int], list[str]] = {}
    for c in cells:
        by_cell.setdefault((c.lat_idx, c.lon_idx), []).append(c.station_id)
    return [
        StationCell(
            c.station_id,
            c.city,
            c.lat_idx,
            c.lon_idx,
            c.cell_lat,
            c.cell_lon,
            c.offset_km,
            tuple(s for s in by_cell[(c.lat_idx, c.lon_idx)] if s != c.station_id),
        )
        for c in cells
    ]


def extract_points(
    ds: Any,
    variables: dict[str, str],
    cells: list[StationCell],
    time_dim: str,
    scale: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Pull each station's cell out of an open dataset. Nulls are preserved as NaN."""
    scale = scale or {}
    times = pd.to_datetime(ds[time_dim].to_numpy())
    rows = []
    for cell in cells:
        block: dict[str, Any] = {
            "station_id": cell.station_id,
            "city": cell.city,
            "time": times,
            "cell_offset_km": round(cell.offset_km, 2),
            "shares_cell": ",".join(cell.shares_cell_with),
        }
        for src, out in variables.items():
            if src not in ds:
                log.warning("variable %s absent from dataset", src)
                continue
            arr = ds[src].isel(latitude=cell.lat_idx, longitude=cell.lon_idx).to_numpy()
            block[out] = np.asarray(arr, dtype=float).ravel() * scale.get(out, 1.0)
        rows.append(pd.DataFrame(block))
    return pd.concat(rows, ignore_index=True)


def wind_speed(u: pd.Series, v: pd.Series) -> pd.Series:
    """Scalar wind speed. Direction is intentionally not averaged -- averaging a circular
    quantity across time or space produces a value pointing nowhere real."""
    return np.hypot(u.to_numpy(dtype=float), v.to_numpy(dtype=float))


def inversion_strength(t_925hpa_k: pd.Series, t_2m_k: pd.Series) -> pd.Series:
    """T(925 hPa) - T(2 m), in kelvin.

    POSITIVE means warmer aloft than at the surface -- a temperature inversion, which caps
    vertical mixing and traps emissions near the ground. This is the mechanism behind the
    Tashkent and Almaty basin regimes, and the sign convention matters: negative values are
    the normal, well-mixed lapse-rate case.
    """
    return t_925hpa_k.to_numpy(dtype=float) - t_2m_k.to_numpy(dtype=float)
