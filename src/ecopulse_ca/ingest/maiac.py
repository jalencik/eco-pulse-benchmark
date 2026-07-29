"""MAIAC AOD extraction: daily composite, then server-side reduction.

Why this is not just `earthengine.execute()`
--------------------------------------------
`MODIS/061/MCD19A2_GRANULES` is split per MODIS tile **and per orbit**. Measured
2026-07-29: **68-102 granules intersect a single point on a single day**, because Terra and
Aqua cross Central Asia many times daily.

The generic extractor maps over every image and flattens, so the true element count for the
full pull is `stations x days x ~80` = **~1.6 million**, not the `stations x days` = 20,456
that `exceeds_getinfo_limit()` computes. That guard would have declared the request safe
while it was ~80x over the ceiling.

So granules are composited to **one image per day inside Earth Engine** before any
reduction. That fixes the element arithmetic and is also the physically correct operation:
reducing per-granule and averaging afterwards would weight each day by how many orbits
happened to cover it, so a day with 100 overpasses would carry more influence than a day
with 40 for reasons that have nothing to do with air quality.

Informative missingness is preserved, not dropped
-------------------------------------------------
Risk R7: MAIAC retrievals fail during dust storms, snow and heavy cloud -- exactly the
extreme-PM2.5 episodes that matter most. Every station-day therefore appears in the output,
including days with no retrieval, where `aod` is null and `valid_pixels` is 0. The caller
must never inner-join these away; `data/DECISIONS.md` records this and
`tests/test_maiac_extraction.py` asserts it.

`valid_pixels` travels beside every value because "mean AOD over 3 valid pixels" and "over
300" are different facts that a single float cannot distinguish.
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

COLLECTION = "MODIS/061/MCD19A2_GRANULES"
BAND = "Optical_Depth_055"
#: MAIAC stores AOD as scaled integers.
SCALE_FACTOR = 0.001
#: Station buffer for the reduction.
BUFFER_M = 3_000
#: Native resolution; reducing finer resamples noise, coarser discards the resolution
#: MAIAC was chosen for.
SCALE_M = 1_000
#: getInfo response ceiling.
GETINFO_LIMIT = 5_000


@dataclass(frozen=True)
class MaiacChunkResult:
    frame: pd.DataFrame
    date_from: str
    date_to: str
    n_expected: int
    n_returned: int

    @property
    def complete(self) -> bool:
        """Every requested station-day must come back, present or null."""
        return self.n_returned == self.n_expected


def month_chunks(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Calendar-month chunks.

    Monthly rather than "as large as the element budget allows": each chunk still has to
    composite ~80 granules per day server-side, and a 600-day chunk times out even though
    its element count is legal. 8 stations x 31 days = 248 elements, comfortably inside the
    5,000 ceiling with room for the composite work.
    """
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    if start > end:
        raise ExtractionError(f"date_from {date_from} after date_to {date_to}")
    out: list[tuple[str, str]] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        nxt = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        lo, hi = max(cursor, start), min(nxt - timedelta(days=1), end)
        out.append((lo.isoformat(), hi.isoformat()))
        cursor = nxt
    return out


def _retry(fn: Any, tries: int = 5, base: float = 3.0) -> Any:
    """Transient DNS/network failures must not abort a multi-hour extraction.

    Observed twice in this project: `getaddrinfo failed` mid-pull. Without retry a single
    blip discards the whole chunk -- and the first version of the OpenAQ pull lost ~9,000
    records per failed year exactly that way.
    """
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - retry on anything transient
            if attempt == tries - 1:
                raise
            wait = base * 2**attempt
            log.warning("EE call failed (%s); retry %d/%d in %.0fs",
                        type(exc).__name__, attempt + 1, tries - 1, wait)
            time.sleep(wait)
    raise ExtractionError("unreachable")


def extract_maiac_chunk(
    ee: Any,
    stations: list[StationPoint],
    date_from: str,
    date_to: str,
) -> MaiacChunkResult:
    """Daily MAIAC AOD per station for one date window."""
    points = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([s.longitude, s.latitude]).buffer(BUFFER_M),
            {"station_id": s.station_id},
        )
        for s in stations
    ])
    region = points.geometry()

    start = ee.Date(date_from)
    n_days = (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1
    granules = ee.ImageCollection(COLLECTION).select(BAND).filterBounds(region)

    def daily_composite(offset: Any) -> Any:
        """Collapse a day's granules into ONE image, inside Earth Engine."""
        day = start.advance(ee.Number(offset), "day")
        same_day = granules.filterDate(day, day.advance(1, "day"))
        # mean() over granules; an empty day yields an image with no bands, which
        # reduceRegions reports as null -- exactly the behaviour we want to preserve.
        composite = same_day.mean().rename(BAND)
        return composite.set("date", day.format("YYYY-MM-dd")).set("n_granules",
                                                                   same_day.size())

    daily = ee.ImageCollection(ee.List.sequence(0, n_days - 1).map(daily_composite))

    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)

    def reduce_day(image: Any) -> Any:
        return image.reduceRegions(
            collection=points, reducer=reducer, scale=SCALE_M
        ).map(lambda f: f.set("date", image.get("date"))
                        .set("n_granules", image.get("n_granules")))

    table = _retry(lambda: daily.map(reduce_day).flatten().getInfo())
    rows = []
    for feat in table.get("features", []):
        p = feat.get("properties", {})
        raw = p.get("mean")
        rows.append({
            "station_id": p.get("station_id"),
            "date": p.get("date"),
            "aod_055": None if raw is None else float(raw) * SCALE_FACTOR,
            "valid_pixels": p.get("count") or 0,
            "n_granules": p.get("n_granules"),
        })

    df = pd.DataFrame(rows, columns=["station_id", "date", "aod_055",
                                     "valid_pixels", "n_granules"])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values(["station_id", "date"]).reset_index(drop=True)

    expected = len(stations) * n_days
    if expected > GETINFO_LIMIT:
        raise ExtractionError(
            f"chunk {date_from}..{date_to} requests {expected} elements, over the "
            f"{GETINFO_LIMIT} ceiling. Use month_chunks()."
        )
    return MaiacChunkResult(df, date_from, date_to, expected, len(df))
