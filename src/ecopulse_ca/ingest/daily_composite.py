"""Generic daily-composite extraction from Earth Engine.

Both MAIAC and Sentinel-5P are published as many assets per day -- MAIAC per MODIS tile and
orbit (68-220 slices over one point), S5P per orbit slice (14-15). Mapping over every asset
and flattening overruns the 5,000-element `getInfo` ceiling by one to two orders of
magnitude, and the generic extractor's `stations x days` budget does not see it.

So granules are composited to **one image per day inside Earth Engine** before any
reduction. Two reasons, and the second matters more:

1. It restores the element arithmetic: `stations x days`, which the chunker can bound.
2. It is the physically correct operation. Reducing per-slice and averaging afterwards
   weights each day by how many overpasses happened to cover it, so a 15-slice day would
   outweigh a 9-slice day for reasons unrelated to air quality.

Missingness is preserved everywhere. Every station-day appears in the output; a day with no
retrieval has a null value and `valid_pixels = 0`. For MAIAC this is quantified (risk R7):
missing days are dirtier (median +5.3, mean +12.9 ug/m3, Mann-Whitney p = 1.4e-35) and
retrieval on the worst PM2.5 decile is 45.2% against 64.7% overall.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from ecopulse_ca.ingest.earthengine import ExtractionError, StationPoint

log = logging.getLogger(__name__)

GETINFO_LIMIT = 5_000


@dataclass(frozen=True)
class CompositeSpec:
    """Everything needed to extract one daily-composited band."""

    name: str
    collection: str
    band: str
    buffer_m: int
    scale_m: int
    scale_factor: float = 1.0
    #: False for indices that legitimately go negative -- the S5P absorbing aerosol index
    #: is negative for scattering aerosol (sulfate, sea salt) and positive for absorbing
    #: aerosol (dust, smoke). Clipping it at zero would erase the sign that carries the
    #: dust-versus-combustion information this feature exists to provide.
    non_negative: bool = True
    plausible_max: float = 10.0

    def value_column(self) -> str:
        return self.name


@dataclass(frozen=True)
class ChunkResult:
    frame: pd.DataFrame
    date_from: str
    date_to: str
    n_expected: int
    n_returned: int

    @property
    def complete(self) -> bool:
        return self.n_returned == self.n_expected


def month_chunks(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Calendar-month chunks.

    Monthly rather than element-maximal: a 600-day chunk is inside the element budget but
    times out, because it still composites tens of slices per day server-side.
    """
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    if start > end:
        raise ExtractionError(f"date_from {date_from} after date_to {date_to}")
    out: list[tuple[str, str]] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        nxt = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((max(cursor, start).isoformat(),
                    min(nxt - timedelta(days=1), end).isoformat()))
        cursor = nxt
    return out


def retry(fn: Any, tries: int = 5, base: float = 3.0) -> Any:
    """Transient DNS/network failures must not abort a multi-hour extraction.

    Observed twice in this project (`getaddrinfo failed` mid-pull). An earlier version of
    the OpenAQ pull discarded ~9,000 records per failed year for exactly this reason.
    """
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - retry anything transient
            if attempt == tries - 1:
                raise
            wait = base * 2**attempt
            log.warning("EE call failed (%s); retry %d/%d in %.0fs",
                        type(exc).__name__, attempt + 1, tries - 1, wait)
            time.sleep(wait)
    raise ExtractionError("unreachable")


def extract_daily_chunk(
    ee: Any,
    spec: CompositeSpec,
    stations: list[StationPoint],
    date_from: str,
    date_to: str,
) -> ChunkResult:
    """Daily-composited values per station for one date window."""
    n_days = (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1
    expected = len(stations) * n_days
    if expected > GETINFO_LIMIT:
        raise ExtractionError(
            f"{spec.name} chunk {date_from}..{date_to} requests {expected} elements, over "
            f"the {GETINFO_LIMIT} ceiling. Use month_chunks()."
        )

    points = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([s.longitude, s.latitude]).buffer(spec.buffer_m),
            {"station_id": s.station_id},
        )
        for s in stations
    ])
    start = ee.Date(date_from)
    slices = ee.ImageCollection(spec.collection).select(spec.band).filterBounds(
        points.geometry()
    )

    # A fully-masked single-band image, used for days with no orbit slices at all.
    #
    # This is not defensive padding -- it fixes a bug that destroyed whole months. An
    # earlier version returned `same_day.mean()` directly and asserted in a comment that an
    # empty day "reports as null". It does not: mean() over an empty collection yields a
    # BAND-LESS image, reduceRegions raises `Image has no bands`, and map() propagates that
    # failure across the entire chunk. NO2 lost all of May 2022 and SO2 lost late Nov 2018
    # to a single empty day each.
    #
    # Structurally the same failure as the OpenAQ pagination bug in Phase 1c: a LOCAL
    # failure destroying a BATCH. A masked image has a band, so reduceRegions succeeds and
    # returns null -- which is the semantics originally intended.
    empty_day = ee.Image.constant(0).rename(spec.band).updateMask(ee.Image.constant(0))

    def daily(offset: Any) -> Any:
        day = start.advance(ee.Number(offset), "day")
        same_day = slices.filterDate(day, day.advance(1, "day"))
        composite = ee.Image(
            ee.Algorithms.If(same_day.size().gt(0), same_day.mean().rename(spec.band),
                             empty_day)
        )
        return (
            composite
            .set("date", day.format("YYYY-MM-dd"))
            .set("n_slices", same_day.size())
        )

    composited = ee.ImageCollection(ee.List.sequence(0, n_days - 1).map(daily))
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)

    def reduce_day(image: Any) -> Any:
        return image.reduceRegions(
            collection=points, reducer=reducer, scale=spec.scale_m
        ).map(lambda f: f.set("date", image.get("date"))
                        .set("n_slices", image.get("n_slices")))

    table = retry(lambda: composited.map(reduce_day).flatten().getInfo())

    rows = []
    for feat in table.get("features", []):
        p = feat.get("properties", {})
        raw = p.get("mean")
        rows.append({
            "station_id": p.get("station_id"),
            "date": p.get("date"),
            spec.value_column(): None if raw is None else float(raw) * spec.scale_factor,
            "valid_pixels": p.get("count") or 0,
            "n_slices": p.get("n_slices"),
        })

    cols = ["station_id", "date", spec.value_column(), "valid_pixels", "n_slices"]
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values(["station_id", "date"]).reset_index(drop=True)

    return ChunkResult(df, date_from, date_to, expected, len(df))


# --------------------------------------------------------------------------- specs
MAIAC_AOD = CompositeSpec(
    name="aod_055",
    collection="MODIS/061/MCD19A2_GRANULES",
    band="Optical_Depth_055",
    buffer_m=3_000,
    scale_m=1_000,
    scale_factor=0.001,  # MAIAC stores scaled integers
    non_negative=True,
    plausible_max=6.0,
)

S5P_AAI = CompositeSpec(
    name="absorbing_aerosol_index",
    collection="COPERNICUS/S5P/OFFL/L3_AER_AI",
    band="absorbing_aerosol_index",
    buffer_m=7_000,
    scale_m=7_000,
    scale_factor=1.0,
    # AAI is SIGNED: negative for scattering aerosol (sulfate, sea salt), positive for
    # absorbing (dust, smoke). The sign is the dust-vs-combustion discriminator, so
    # clipping at zero would destroy the feature's entire purpose.
    non_negative=False,
    plausible_max=8.0,
)


# The cloud-screened trio. Unlike AAI, these products ARE masked where cloud is retrieved,
# so target-correlated missingness (risk R7) is expected to return -- worst for SO2, whose
# signal peaks in the same winter months that are cloudiest here.
#
# All three carry non_negative=False. Trace-gas column retrievals go negative when the true
# column is near the noise floor, and SO2 does so routinely away from large point sources.
# Clipping at zero would bias the coal tracer upward exactly where it is weakest.
S5P_NO2 = CompositeSpec(
    name="no2_tropospheric",
    collection="COPERNICUS/S5P/OFFL/L3_NO2",
    band="tropospheric_NO2_column_number_density",
    buffer_m=7_000,
    scale_m=7_000,
    non_negative=False,
    plausible_max=1e-3,
)

S5P_SO2 = CompositeSpec(
    name="so2_column",
    collection="COPERNICUS/S5P/OFFL/L3_SO2",
    band="SO2_column_number_density",
    buffer_m=7_000,
    scale_m=7_000,
    non_negative=False,
    plausible_max=1e-2,
)

S5P_CO = CompositeSpec(
    name="co_column",
    collection="COPERNICUS/S5P/OFFL/L3_CO",
    band="CO_column_number_density",
    buffer_m=7_000,
    scale_m=7_000,
    non_negative=False,
    plausible_max=1.0,
)
