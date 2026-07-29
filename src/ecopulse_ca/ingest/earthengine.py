"""Earth Engine extraction: server-side reduction to station buffers.

Architecture: request construction is separated from execution
--------------------------------------------------------------
`build_request()` is pure Python -- no `ee` import, no credentials -- and produces a fully
specified description of what will be computed. `EarthEngineExtractor.execute()` turns that
into Earth Engine calls.

That split is not tidiness. It means the part that can be wrong in a way that silently
corrupts results -- which collection, which band, which buffer, which date window, which
reducer -- is testable offline, by anyone, with no Google account. Only the network call
itself requires credentials.

The disk constraint is structural, not a discipline
---------------------------------------------------
Every request reduces imagery to per-station statistics **inside Earth Engine** via
`reduceRegions`, and downloads only the resulting table. There is no code path here that
fetches an image. With 8.6 GB free and MAIAC at 1 km over five countries running to
O(100 GB-TB), a raster download would not merely be slow -- it would not complete.

`getInfo()` has a hard 5,000-element response limit, so requests are chunked by time and
the chunk size is derived from the station count rather than guessed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from ecopulse_ca.features.spec import FeatureSpec, Reduction, Statistic

#: Earth Engine's getInfo() response ceiling. Exceeding it fails the whole request.
GETINFO_ELEMENT_LIMIT = 5_000

#: Earth Engine collection IDs. Kept in one place so a wrong ID is a one-line fix rather
#: than a hunt, and so tests can assert them without importing `ee`.
COLLECTION_FOR_FEATURE: dict[str, str] = {
    "maiac_aod_055": "MODIS/061/MCD19A2_GRANULES",
    "maiac_valid_pixel_fraction": "MODIS/061/MCD19A2_GRANULES",
    "s5p_absorbing_aerosol_index": "COPERNICUS/S5P/OFFL/L3_AER_AI",
    "s5p_absorbing_aerosol_index_nrt": "COPERNICUS/S5P/NRTI/L3_AER_AI",
    "s5p_no2_tropospheric": "COPERNICUS/S5P/OFFL/L3_NO2",
    "s5p_so2": "COPERNICUS/S5P/OFFL/L3_SO2",
    "s5p_co": "COPERNICUS/S5P/OFFL/L3_CO",
    # v002, NOT the deprecated NOAA/VIIRS/001/VNP14A1. See COLLECTION_COVERAGE below:
    # v001 stopped at 2024-06-16, dead centre of the frozen test block.
    "viirs_active_fire_count": "NASA/VIIRS/002/VNP14A1",
    "ghsl_population_density": "JRC/GHSL/P2023A/GHS_POP",
    "viirs_nighttime_lights": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
    "elevation": "USGS/SRTMGL1_003",
}

#: Band within each collection. Wrong band = plausible numbers for the wrong quantity,
#: which is the failure mode hardest to notice downstream.
BAND_FOR_FEATURE: dict[str, str] = {
    "maiac_aod_055": "Optical_Depth_055",
    "maiac_valid_pixel_fraction": "Optical_Depth_055",  # counted, not averaged
    "s5p_absorbing_aerosol_index": "absorbing_aerosol_index",
    "s5p_absorbing_aerosol_index_nrt": "absorbing_aerosol_index",
    "s5p_no2_tropospheric": "tropospheric_NO2_column_number_density",
    "s5p_so2": "SO2_column_number_density",
    "s5p_co": "CO_column_number_density",
    "viirs_active_fire_count": "FireMask",
    "ghsl_population_density": "population_count",
    "viirs_nighttime_lights": "avg_rad",
    "elevation": "elevation",
}

#: MAIAC AOD is stored scaled; the raw integer must be multiplied to get optical depth.
SCALE_FACTOR_FOR_FEATURE: dict[str, float] = {
    "maiac_aod_055": 0.001,
}

#: Measured coverage per collection: (first asset, last asset, measurement date).
#:
#: Recorded because a latency check alone is not sufficient. `NOAA/VIIRS/001/VNP14A1` was
#: originally mapped here with a claimed 4 h latency; measurement showed **774 days**, and
#: -- far worse -- its final asset is **2024-06-16**, dead centre of the frozen 2024 test
#: block: 161 images in Jan-Jun, **zero** in Jul-Dec. A model trained on it would see fire
#: signal for half the test year and structurally none for the other half, producing a
#: spurious regime change on 1 July that invites a meteorological explanation for a data
#: artefact. Earth Engine also flags v001 as deprecated in favour of v002.
#:
#: `tests/test_collection_coverage.py` asserts every mapped collection spans the frozen
#: test block, so a collection that dies mid-block fails the build offline.
COLLECTION_COVERAGE: dict[str, tuple[str, str, str]] = {
    "MODIS/061/MCD19A2_GRANULES": ("2000-02-24", "2026-07-21", "2026-07-29"),
    "COPERNICUS/S5P/OFFL/L3_AER_AI": ("2018-07-04", "2026-07-26", "2026-07-29"),
    "COPERNICUS/S5P/NRTI/L3_AER_AI": ("2018-07-10", "2026-07-29", "2026-07-29"),
    "COPERNICUS/S5P/OFFL/L3_NO2": ("2018-06-28", "2026-07-26", "2026-07-29"),
    "COPERNICUS/S5P/OFFL/L3_SO2": ("2018-07-10", "2026-07-26", "2026-07-29"),
    "COPERNICUS/S5P/OFFL/L3_CO": ("2018-06-28", "2026-07-26", "2026-07-29"),
    "NASA/VIIRS/002/VNP14A1": ("2012-01-19", "2026-07-28", "2026-07-29"),
    # Last OBSERVED epoch, not last asset. The collection also carries 2025 and 2030
    # epochs, but those are PROJECTIONS -- modelled future population. Recording 2030 here
    # would assert coverage the data does not have, and the bookkeeping test caught it.
    "JRC/GHSL/P2023A/GHS_POP": ("1975-01-01", "2020-01-01", "2026-07-29"),
    "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG": ("2014-01-01", "2026-04-01", "2026-07-29"),
    "USGS/SRTMGL1_003": ("2000-02-11", "2000-02-22", "2026-07-29"),  # static DEM
}

#: Collections Earth Engine reports as deprecated. Mapping one is a build failure: a
#: deprecated collection is frozen, so it silently stops covering recent periods.
DEPRECATED_COLLECTIONS: frozenset[str] = frozenset({
    "NOAA/VIIRS/001/VNP14A1",  # superseded by NASA/VIIRS/002/VNP14A1; last asset 2024-06-16
})

#: Collections exempt from the test-block coverage check, with the reason.
#: Static products have no time dimension, so "coverage" is not meaningful for them.
COVERAGE_EXEMPT: dict[str, str] = {
    "USGS/SRTMGL1_003": "single-epoch DEM; terrain is time-invariant",
    "JRC/GHSL/P2023A/GHS_POP": "5-year epochs, selected not date-filtered",
}


class ExtractionError(RuntimeError):
    """Raised when a request cannot be built or executed."""


@dataclass(frozen=True)
class StationPoint:
    station_id: str
    latitude: float
    longitude: float
    city: str = ""


@dataclass(frozen=True)
class ReductionRequest:
    """A fully specified server-side reduction. Pure data -- no Earth Engine objects.

    Serialisable, so a request can be recorded in the manifest alongside the values it
    produced. "Which buffer did this column use?" should be answerable from the archive,
    not by re-reading code that may since have changed.
    """

    feature_name: str
    collection: str
    band: str
    reduction: Reduction
    date_from: str
    date_to: str
    stations: tuple[StationPoint, ...]
    scale_m: int
    scale_factor: float = 1.0
    emit_valid_count: bool = True
    #: Extra reducers requested alongside the primary statistic.
    extra_statistics: tuple[Statistic, ...] = field(default_factory=tuple)

    @property
    def n_elements(self) -> int:
        """Rough element count for the getInfo ceiling: stations x days."""
        days = (pd.Timestamp(self.date_to) - pd.Timestamp(self.date_from)).days + 1
        return len(self.stations) * max(days, 1)

    def exceeds_getinfo_limit(self) -> bool:
        return self.n_elements > GETINFO_ELEMENT_LIMIT

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reduction"] = {
            "buffer_m": self.reduction.buffer_m,
            "statistic": self.reduction.statistic.value,
            "emit_valid_count": self.reduction.emit_valid_count,
        }
        d["stations"] = [asdict(s) for s in self.stations]
        d["extra_statistics"] = [s.value for s in self.extra_statistics]
        return d

    def fingerprint(self) -> str:
        """Stable identity for caching and for the data manifest."""
        import hashlib

        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_request(
    feature: FeatureSpec,
    stations: list[StationPoint],
    date_from: str,
    date_to: str,
) -> ReductionRequest:
    """Construct the reduction request for one feature over one date window.

    Pure and offline. Raises rather than guessing when a feature is not extractable this
    way -- a silently skipped feature becomes a silently absent column, which downstream
    code will happily treat as "no signal here" rather than "never fetched".
    """
    if feature.requires_raster_download:
        raise ExtractionError(
            f"{feature.name} is a raster-download feature (source {feature.source.value}) "
            "and cannot be reduced server-side by Earth Engine. It belongs to the "
            "deployment path, not the local benchmark build."
        )
    if feature.reduction is None:
        raise ExtractionError(f"{feature.name} declares no Reduction")
    if feature.name not in COLLECTION_FOR_FEATURE:
        raise ExtractionError(
            f"{feature.name} has no Earth Engine collection mapping. Add it to "
            "COLLECTION_FOR_FEATURE rather than letting the column go silently missing."
        )
    if not stations:
        raise ExtractionError("no stations supplied")

    return ReductionRequest(
        feature_name=feature.name,
        collection=COLLECTION_FOR_FEATURE[feature.name],
        band=BAND_FOR_FEATURE[feature.name],
        reduction=feature.reduction,
        date_from=date_from,
        date_to=date_to,
        stations=tuple(stations),
        scale_m=_native_scale_m(feature),
        scale_factor=SCALE_FACTOR_FOR_FEATURE.get(feature.name, 1.0),
        emit_valid_count=feature.reduction.emit_valid_count,
    )


def _native_scale_m(feature: FeatureSpec) -> int:
    """Reduction scale in metres, taken from the product's native resolution.

    Reducing at a finer scale than the source resamples noise and inflates Earth Engine
    cost for nothing; reducing coarser throws away the resolution the product was chosen
    for. Neither is detectable in the output values.
    """
    res = feature.native_resolution.lower()
    if "1 km" in res or "1km" in res:
        return 1000
    if "500 m" in res:
        return 500
    if "375 m" in res:
        return 375
    if "100 m" in res:
        return 100
    if "30 m" in res:
        return 30
    if "km" in res:  # e.g. "~7 km", "~5.5 x 3.5 km"
        return 7000
    return 1000


def chunk_date_range(
    date_from: str, date_to: str, n_stations: int, limit: int = GETINFO_ELEMENT_LIMIT
) -> list[tuple[str, str]]:
    """Split a date range so each chunk stays under the getInfo element ceiling.

    Chunk length is derived from the station count, not fixed. With 8 stations a chunk can
    span years; with 500 it cannot span a month. A hard-coded chunk size would silently
    fail for larger station sets.
    """
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    if start > end:
        raise ExtractionError(f"date_from {date_from} is after date_to {date_to}")
    if n_stations <= 0:
        raise ExtractionError("n_stations must be positive")

    days_per_chunk = max(1, limit // n_stations)
    chunks: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=days_per_chunk - 1), end)
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)
    return chunks


class EarthEngineExtractor:
    """Executes reduction requests. Requires `earthengine-api` and EE_PROJECT_ID.

    Falls back to committed fixtures when credentials are absent, so the pipeline and the
    full test suite run end to end with no Google account -- the same contract the OpenAQ
    client already honours. Fixture-derived values are stamped `fixture=True` and are
    barred from being reported as findings.
    """

    FIXTURE_DIR = Path(__file__).parent / "fixtures"

    def __init__(self, project_id: str = "", use_fixtures: bool | None = None) -> None:
        self.project_id = project_id.strip()
        self.use_fixtures = (not self.project_id) if use_fixtures is None else use_fixtures
        self._ee: Any = None

    @property
    def available(self) -> bool:
        return bool(self.project_id)

    def _import_ee(self) -> Any:
        if self._ee is not None:
            return self._ee
        try:
            import ee  # noqa: PLC0415 - optional dependency, imported only when used
        except ImportError as exc:
            raise ExtractionError(
                "earthengine-api is not installed. Install with:\n"
                "  uv pip install earthengine-api\n"
                "It is deliberately not a hard dependency: the benchmark's ground-truth "
                "pipeline and full test suite run without it."
            ) from exc
        self._ee = ee
        return ee

    def initialise(self) -> None:
        if self.use_fixtures:
            return
        ee = self._import_ee()
        try:
            ee.Initialize(project=self.project_id)
        except Exception as exc:  # noqa: BLE001 - surface auth failure with a usable hint
            raise ExtractionError(
                f"Earth Engine init failed for project {self.project_id!r}: {exc}\n"
                "Run `earthengine authenticate` once, and confirm the Earth Engine API is "
                "enabled for that Cloud project."
            ) from exc

    def execute(self, request: ReductionRequest) -> pd.DataFrame:
        """Run one reduction. Returns tidy rows: station_id, date, value, valid_count."""
        if self.use_fixtures:
            return self._from_fixture(request)
        if request.exceeds_getinfo_limit():
            raise ExtractionError(
                f"request spans {request.n_elements} elements, over the "
                f"{GETINFO_ELEMENT_LIMIT} getInfo limit. Use chunk_date_range()."
            )
        return self._execute_live(request)

    def _execute_live(self, request: ReductionRequest) -> pd.DataFrame:
        ee = self._import_ee()
        points = ee.FeatureCollection([
            ee.Feature(
                ee.Geometry.Point([s.longitude, s.latitude]).buffer(
                    request.reduction.buffer_m
                ),
                {"station_id": s.station_id},
            )
            for s in request.stations
        ])
        collection = (
            ee.ImageCollection(request.collection)
            .filterDate(request.date_from, request.date_to)
            .select(request.band)
        )

        reducer = _ee_reducer(ee, request.reduction.statistic)
        if request.emit_valid_count:
            reducer = reducer.combine(ee.Reducer.count(), sharedInputs=True)

        def reduce_image(image: Any) -> Any:
            # reduceRegions runs INSIDE Earth Engine; only the table crosses the network.
            return image.reduceRegions(
                collection=points, reducer=reducer, scale=request.scale_m
            ).map(lambda f: f.set("date", image.date().format("YYYY-MM-dd")))

        table = collection.map(reduce_image).flatten()
        rows = table.getInfo().get("features", [])
        return _rows_to_frame(rows, request)

    def _from_fixture(self, request: ReductionRequest) -> pd.DataFrame:
        path = self.FIXTURE_DIR / f"gee_{request.feature_name}.json"
        if not path.exists():
            raise ExtractionError(
                f"no fixture for {request.feature_name} at {path}. Fixtures are committed "
                "so the suite runs without credentials; a missing one means the repo is "
                "incomplete."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        df = _rows_to_frame(payload.get("features", []), request)
        df["fixture"] = True
        return df


def _ee_reducer(ee: Any, statistic: Statistic) -> Any:
    mapping = {
        Statistic.MEAN: "mean", Statistic.MEDIAN: "median", Statistic.MAX: "max",
        Statistic.MIN: "min", Statistic.COUNT: "count", Statistic.STDDEV: "stdDev",
    }
    return getattr(ee.Reducer, mapping[statistic])()


def _rows_to_frame(rows: list[dict], request: ReductionRequest) -> pd.DataFrame:
    """Flatten Earth Engine features into tidy rows, applying the product scale factor."""
    out = []
    for row in rows:
        props = row.get("properties", row)
        value = props.get(request.reduction.statistic.value, props.get("mean"))
        out.append({
            "station_id": props.get("station_id"),
            "date": props.get("date"),
            "feature": request.feature_name,
            "value": None if value is None else float(value) * request.scale_factor,
            "valid_count": props.get("count"),
        })
    df = pd.DataFrame(out, columns=["station_id", "date", "feature", "value", "valid_count"])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    df["fixture"] = False
    return df
