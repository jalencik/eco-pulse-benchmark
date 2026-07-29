"""Static feature extraction from Earth Engine.

Static features have three different dataset shapes, and treating them uniformly produces
silent errors rather than exceptions:

- **`USGS/SRTMGL1_003` is a single `ee.Image`.** Wrapping it in an `ImageCollection` and
  date-filtering yields an empty collection, hence no rows -- which downstream reads as
  "no signal at this station", not "wrong query".
- **`JRC/GHSL/P2023A/GHS_POP` is 12 epoch images** (1975-2030, 5-year steps). Epochs are
  *selected*, never date-filtered. Filtering it to 2024 returns nothing.
- **`NOAA/VIIRS/DNB/MONTHLY_V1` is 148 monthly images** and genuinely varies over time, so
  it must be *aggregated* over a declared window.

Two choices below are scientific, not incidental
------------------------------------------------
**GHSL epoch 2020, not 2025.** The catalogue offers 2025 and 2030, but those are
*projections* -- modelled future population. Using them would inject a forecast of the
future into a feature declared static, and 2020 is also the closest observed epoch to the
2018-2024 record.

**VIIRS aggregated over the TRAIN block only.** Night-time lights are declared static but
actually vary year to year. Averaging across the full record would put test-period
information into a feature every model sees at training time. Restricting to the train
block keeps the "static" declaration honest -- the same rule climatology follows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ecopulse_ca.ingest.earthengine import ExtractionError, StationPoint

#: Buffer for point-scale static context.
BUF_STATIC_M = 1_000
#: Inner radius, excluded so the station's own valley floor does not dominate its reference.
BASIN_INNER_M = 5_000
#: Outer radii for the basin index, emitted as SEPARATE features.
#:
#: A single radius does not measure "is this a basin" -- it measures "is this a basin at
#: radius R". Measured on Tashkent: +13.5 m at 25 km (not a basin), -85.2 m at 50 km,
#: -339.1 m at 100 km (deep basin). At 25 km the ring never reaches the Tian Shan, so the
#: inversion-trapping terrain that motivates the feature is invisible. Rather than pick one
#: radius arbitrarily, all three are emitted and the ablation decides.
BASIN_OUTER_RADII_M = (25_000, 50_000, 100_000)

#: GHS_POP band `population_count` is people PER 100 m CELL, not per km^2 (verified:
#: nominalScale = 100 m). The catalogue declares persons/km^2, so the raw value must be
#: multiplied by 100. Without it Almaty reads 183.8 rather than 18,380 people/km^2 -- a
#: model trains identically on either, and only the units claim is false.
GHSL_CELL_M = 100
GHSL_COUNT_TO_DENSITY = (1000 / GHSL_CELL_M) ** 2  # = 100

#: Observed GHSL epoch nearest the 2018-2024 record. 2025/2030 are PROJECTIONS.
GHSL_EPOCH = "2020"


@dataclass(frozen=True)
class StaticExtractionResult:
    frame: pd.DataFrame
    provenance: dict[str, Any]


def _ee(project_id: str) -> Any:
    try:
        import ee  # noqa: PLC0415
    except ImportError as exc:
        raise ExtractionError("earthengine-api not installed") from exc
    try:
        ee.Initialize(project=project_id)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(
            f"Earth Engine init failed: {exc}\nRun `earthengine authenticate` once."
        ) from exc
    return ee


def _points(ee: Any, stations: list[StationPoint], buffer_m: int) -> Any:
    return ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([s.longitude, s.latitude]).buffer(buffer_m),
            {"station_id": s.station_id},
        )
        for s in stations
    ])


def _annuli(ee: Any, stations: list[StationPoint], outer_m: int) -> Any:
    """Ring geometries: surrounding terrain with the immediate area removed."""
    return ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([s.longitude, s.latitude]).buffer(outer_m)
            .difference(ee.Geometry.Point([s.longitude, s.latitude]).buffer(BASIN_INNER_M)),
            {"station_id": s.station_id},
        )
        for s in stations
    ])


def _reduce_to_frame(ee: Any, image: Any, regions: Any, scale: int, column: str) -> pd.DataFrame:
    """reduceRegions server-side; only the resulting table crosses the network."""
    table = image.reduceRegions(
        collection=regions, reducer=ee.Reducer.mean(), scale=scale
    ).getInfo()
    rows = [
        {"station_id": f["properties"].get("station_id"),
         column: f["properties"].get("mean")}
        for f in table.get("features", [])
    ]
    return pd.DataFrame(rows)


def extract_static(
    stations: list[StationPoint],
    project_id: str,
    train_start: str,
    train_end: str,
) -> StaticExtractionResult:
    """Extract elevation, basin index, GHSL population and night-time lights."""
    if not stations:
        raise ExtractionError("no stations supplied")
    ee = _ee(project_id)

    srtm = ee.Image("USGS/SRTMGL1_003").select("elevation")

    # -- elevation, and the annulus reference for the basin index ---------------------
    elev = _reduce_to_frame(ee, srtm, _points(ee, stations, BUF_STATIC_M), 30, "elevation")
    rings = {}
    for outer in BASIN_OUTER_RADII_M:
        km = outer // 1000
        rings[km] = _reduce_to_frame(
            ee, srtm, _annuli(ee, stations, outer), 200, f"annulus_elev_{km}km"
        )

    # -- GHSL population: epoch SELECTION, never a date filter ------------------------
    ghsl_img = (
        ee.ImageCollection("JRC/GHSL/P2023A/GHS_POP")
        .filter(ee.Filter.eq("system:index", GHSL_EPOCH))
        .first()
        .select("population_count")
    )
    pop = _reduce_to_frame(
        ee, ghsl_img, _points(ee, stations, BUF_STATIC_M), 100, "ghsl_population_density"
    )

    # -- VIIRS night lights: mean over the TRAIN block only ---------------------------
    vnl_col = (
        ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG")
        .filterDate(train_start, train_end)
        .select("avg_rad")
    )
    n_vnl = int(vnl_col.size().getInfo())
    if n_vnl == 0:
        raise ExtractionError(
            f"VIIRS-DNB returned 0 images for {train_start}..{train_end}. An empty "
            "collection yields no rows, which downstream misreads as 'no signal'."
        )
    lights = _reduce_to_frame(
        ee, vnl_col.mean(), _points(ee, stations, BUF_STATIC_M), 500,
        "viirs_nighttime_lights",
    )

    df = elev
    for ring in rings.values():
        df = df.merge(ring, on="station_id")
    df = df.merge(pop, on="station_id").merge(lights, on="station_id")

    # Negative basin index = station sits below the surrounding terrain, so inversions pool.
    for km in (r // 1000 for r in BASIN_OUTER_RADII_M):
        df[f"terrain_basin_index_{km}km"] = df["elevation"] - df[f"annulus_elev_{km}km"]

    # Convert per-cell counts to the density the catalogue declares.
    df["ghsl_population_density"] = df["ghsl_population_density"] * GHSL_COUNT_TO_DENSITY
    df["fixture"] = False

    meta = {s.station_id: s for s in stations}
    df["city"] = df["station_id"].map(lambda s: meta[s].city if s in meta else None)

    provenance = {
        "srtm": "USGS/SRTMGL1_003 (single Image, scale 30 m)",
        "ghsl_epoch": f"JRC/GHSL/P2023A/GHS_POP index={GHSL_EPOCH} (observed, not projected)",
        "viirs_window": f"{train_start}..{train_end} ({n_vnl} monthly images, mean)",
        "basin_annulus_m": f"inner {BASIN_INNER_M}, outer {list(BASIN_OUTER_RADII_M)}",
        "ghsl_units": f"raw band is count per {GHSL_CELL_M} m cell; "
                      f"multiplied by {GHSL_COUNT_TO_DENSITY:.0f} to give persons/km^2",
        "buffer_m": BUF_STATIC_M,
        "note": "VIIRS restricted to the TRAIN block so a 'static' feature carries no "
                "test-period information.",
    }
    return StaticExtractionResult(frame=df, provenance=provenance)
