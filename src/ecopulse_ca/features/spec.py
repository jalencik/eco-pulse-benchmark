"""Feature declarations, with operational availability as a first-class property.

Rule 3 of the project spec: **no lookahead in operational features.** ERA5 and CAMS
reanalysis do not exist at prediction time -- ERA5 lags roughly five days, CAMS reanalysis
months. A model that consumes them is reading the future. It will post an excellent number
and be undeployable, and nothing in a metrics table reveals this.

So availability is declared per feature and enforced by test, not by memory. Every feature
carries:

- ``available_at_runtime`` -- can a deployed service obtain this at prediction time?
- ``latency_hours`` -- how stale is the freshest value when a forecast is issued?
- ``missingness_informative`` -- is missingness correlated with the target?

That last flag exists because of a specific finding (risk R7): MAIAC retrievals fail
during dust storms, snow and heavy cloud -- exactly the extreme-PM2.5 episodes that matter
most. Dropping missing-AOD rows silently conditions the evaluation on "retrieval
succeeded", biasing every result toward calm, clear, low-concentration days. Features with
this flag must have their missingness modelled and reported as an error-analysis stratum.

Reduction happens server-side by construction
---------------------------------------------
The dev machine has ~8.6 GB free. MAIAC at 1 km over five countries for seven years is
O(100 GB-TB) of raster. Every satellite feature therefore declares a `Reduction` describing
how it is collapsed to a station-buffer statistic **before** anything crosses the network.
There is no code path that downloads a raster; that is a property of the design, not a
discipline anyone has to remember.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Source(StrEnum):
    """Where a feature comes from, and therefore which credential it needs."""

    OPENAQ = "openaq"
    GEE_MODIS = "gee_modis"
    GEE_SENTINEL5P = "gee_sentinel5p"
    GEE_VIIRS = "gee_viirs"
    GEE_STATIC = "gee_static"
    CDS_ERA5 = "cds_era5"
    ADS_CAMS_REANALYSIS = "ads_cams_reanalysis"
    ADS_CAMS_FORECAST = "ads_cams_forecast"
    EARTHDATA_MERRA2 = "earthdata_merra2"
    #: NASA LANCE near-real-time. Raster granules, NOT server-side reducible.
    LANCE_NRT = "lance_nrt"
    DERIVED = "derived"


#: Environment variable that unlocks each source. Checked by the registration report.
CREDENTIAL_FOR: dict[Source, str] = {
    Source.OPENAQ: "OPENAQ_API_KEY",
    Source.GEE_MODIS: "EE_PROJECT_ID",
    Source.GEE_SENTINEL5P: "EE_PROJECT_ID",
    Source.GEE_VIIRS: "EE_PROJECT_ID",
    Source.GEE_STATIC: "EE_PROJECT_ID",
    Source.CDS_ERA5: "CDS_API_KEY",
    Source.ADS_CAMS_REANALYSIS: "ADS_API_KEY",
    Source.ADS_CAMS_FORECAST: "ADS_API_KEY",
    Source.EARTHDATA_MERRA2: "EARTHDATA_USERNAME",
    Source.LANCE_NRT: "EARTHDATA_USERNAME",
    Source.DERIVED: "",
}


class Statistic(StrEnum):
    MEAN = "mean"
    MEDIAN = "median"
    MAX = "max"
    MIN = "min"
    COUNT = "count"
    STDDEV = "stdDev"


@dataclass(frozen=True)
class Reduction:
    """How a gridded product is collapsed to a per-station value, server-side.

    `buffer_m` is the radius around the station. Larger buffers reduce retrieval gaps but
    blur the urban gradient the model is meant to resolve; the choice is recorded per
    feature so it is auditable rather than a hidden constant.
    """

    buffer_m: int
    statistic: Statistic = Statistic.MEAN
    #: Also emit the count of valid pixels. Essential wherever missingness is informative:
    #: "AOD mean over 3 valid pixels" and "over 300" are different facts.
    emit_valid_count: bool = True

    def describe(self) -> str:
        extra = " + valid-pixel count" if self.emit_valid_count else ""
        return f"{self.statistic.value} within {self.buffer_m} m{extra}"


@dataclass(frozen=True)
class FeatureSpec:
    """One column in the feature table."""

    name: str
    source: Source
    description: str
    units: str
    available_at_runtime: bool
    #: Staleness of the freshest available value when a forecast is issued. None when the
    #: feature is not obtainable at runtime at all.
    latency_hours: float | None
    missingness_informative: bool = False
    reduction: Reduction | None = None
    native_resolution: str = ""
    #: Free-text note on anything a reviewer would need in order to trust the column.
    caveat: str = ""
    #: Set when the latency or availability figure still needs checking against the
    #: provider's documentation rather than being taken from memory.
    verified: bool = False
    #: True when obtaining this feature means downloading raster granules -- no server-side
    #: reduction is possible. Such features CANNOT run on the dev machine (8.6 GB free) and
    #: belong only to server-side deployment. NASA LANCE NRT is the case that forced this
    #: field to exist: it is the only low-latency AOD source, and it is raster-only.
    requires_raster_download: bool = False

    def __post_init__(self) -> None:
        if self.available_at_runtime and self.latency_hours is None:
            raise ValueError(
                f"{self.name}: available_at_runtime=True requires a latency_hours value. "
                "'Available' without a latency is not a checkable claim."
            )
        if not self.available_at_runtime and self.latency_hours is not None:
            raise ValueError(
                f"{self.name}: latency_hours is meaningless when the feature is not "
                "available at runtime. Set it to None."
            )
        gridded_without_reduction = self.reduction is None and self.source is not Source.DERIVED
        if gridded_without_reduction and not self.requires_raster_download:
            raise ValueError(
                f"{self.name}: a gridded feature with no Reduction would have to be "
                "downloaded as a raster. Either declare a Reduction (server-side) or "
                "set requires_raster_download=True to state that explicitly."
            )

    @property
    def credential(self) -> str:
        return CREDENTIAL_FOR[self.source]

    @property
    def is_oracle(self) -> bool:
        """True for features that can only appear in a clearly-labelled oracle ablation."""
        return not self.available_at_runtime


@dataclass(frozen=True)
class FeatureSet:
    """A named collection of features, with an explicit deployment claim.

    `deployable=True` asserts every member is obtainable at prediction time. That assertion
    is checked by `tests/test_feature_availability.py`, so a reanalysis column cannot be
    added to a deployable set without failing the build.
    """

    name: str
    features: tuple[FeatureSpec, ...]
    deployable: bool
    purpose: str = ""

    def oracle_features(self) -> tuple[FeatureSpec, ...]:
        return tuple(f for f in self.features if f.is_oracle)

    def max_latency_hours(self) -> float:
        """Worst-case staleness. A forecast horizon shorter than this is not achievable."""
        lats = [f.latency_hours for f in self.features if f.latency_hours is not None]
        return max(lats) if lats else 0.0

    def credentials_required(self) -> tuple[str, ...]:
        return tuple(sorted({f.credential for f in self.features if f.credential}))

    @property
    def locally_reproducible(self) -> bool:
        """True when every member can be built on the dev machine without raster downloads.

        The disk budget is 8.6 GB. A set containing a raster-download feature cannot be
        reproduced here at all, which matters for `make reproduce` and for any reviewer
        trying to rebuild the benchmark.
        """
        return not any(f.requires_raster_download for f in self.features)

    def raster_features(self) -> tuple[FeatureSpec, ...]:
        return tuple(f for f in self.features if f.requires_raster_download)

    def validate(self) -> list[str]:
        """Return reasons this set is inconsistent with its own deployment claim."""
        problems = []
        if self.deployable:
            for f in self.oracle_features():
                problems.append(
                    f"{self.name} claims deployable but includes {f.name!r} "
                    f"({f.source.value}), which is not available at runtime"
                )
        return problems


def unverified(features: tuple[FeatureSpec, ...]) -> tuple[FeatureSpec, ...]:
    """Features whose availability/latency claims still need checking against provider docs.

    Surfaced deliberately: a latency number recalled from memory and one read from
    documentation look identical in a table, and only one of them is evidence.
    """
    return tuple(f for f in features if not f.verified)
