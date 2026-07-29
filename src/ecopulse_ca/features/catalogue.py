"""The declared predictor catalogue for Phase 4.

Every feature the project intends to use, with its operational availability stated. Nothing
here fetches data; this is the contract that `tests/test_feature_availability.py` enforces
and that `research/PREDICTORS.md` documents for readers.

**Latency figures marked `verified=False` are from memory and must be checked against
provider documentation before any deployment claim rests on them.** They are flagged rather
than silently trusted because a recalled latency and a documented one are indistinguishable
in a table, and only one is evidence.

The central distinction in this file
------------------------------------
ERA5 and CAMS *reanalysis* are **not available at prediction time**. CAMS *forecast* is.
Both describe the same physical quantities, so it is trivially easy to reach for the
reanalysis -- it is cleaner, better documented, and already in most people's pipelines --
and thereby build a model that cannot be deployed. The two are declared as separate
features with different availability flags so that mistake fails the build.
"""

from __future__ import annotations

from ecopulse_ca.features.spec import (
    FeatureSet,
    FeatureSpec,
    Reduction,
    Source,
    Statistic,
)

# Buffer radii. 1 km resolves the urban gradient MAIAC is chosen for; coarser products get
# larger buffers because a sub-pixel buffer would just resample one cell.
BUF_AOD = 3_000
BUF_S5P = 7_000
BUF_MET = 25_000
BUF_STATIC = 1_000

# --------------------------------------------------------------------------- satellite
SATELLITE = (
    FeatureSpec(
        name="maiac_aod_055",
        source=Source.GEE_MODIS,
        description="MAIAC aerosol optical depth at 550 nm (MCD19A2), the primary "
                    "column-aerosol predictor",
        units="dimensionless",
        available_at_runtime=True,
        latency_hours=6.0,  # NRT MODIS; standard collection is far slower
        missingness_informative=True,
        reduction=Reduction(BUF_AOD, Statistic.MEAN),
        native_resolution="1 km",
        caveat="Retrievals fail during dust storms, snow and heavy cloud -- exactly the "
               "extreme-PM2.5 episodes of interest (risk R7). Accuracy is also lower over "
               "bright arid surfaces, and lofted dust causes underestimation. Missing rows "
               "must be modelled, never dropped.",
        verified=False,
    ),
    FeatureSpec(
        name="maiac_valid_pixel_fraction",
        source=Source.GEE_MODIS,
        description="Share of buffer pixels with a successful MAIAC retrieval -- the "
                    "informative-missingness signal itself, promoted to a feature",
        units="fraction",
        available_at_runtime=True,
        latency_hours=6.0,
        missingness_informative=False,
        reduction=Reduction(BUF_AOD, Statistic.COUNT),
        native_resolution="1 km",
        caveat="Deliberately a feature, not just diagnostics. Retrieval failure carries "
               "information about the atmosphere (dust/cloud/snow) and discarding it "
               "throws away signal precisely when concentrations are extreme.",
        verified=False,
    ),
    FeatureSpec(
        name="s5p_absorbing_aerosol_index",
        source=Source.GEE_SENTINEL5P,
        description="Sentinel-5P TROPOMI UV absorbing aerosol index",
        units="dimensionless",
        available_at_runtime=True,
        latency_hours=5.0,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~7 km",
        caveat="The key dust discriminator: unlike AOD, the UV AAI is available over "
               "bright surfaces and responds to absorbing aerosol, so it should separate "
               "Aralkum/loess dust from combustion aerosol.",
        verified=False,
    ),
    FeatureSpec(
        name="s5p_no2_tropospheric",
        source=Source.GEE_SENTINEL5P,
        description="TROPOMI tropospheric NO2 column -- combustion/traffic proxy",
        units="mol/m^2",
        available_at_runtime=True,
        latency_hours=5.0,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~5.5 x 3.5 km",
        caveat="TROPOMI products are cloud-screened, so missingness tracks cloud cover -- "
               "which itself covaries with washout, frontal passage and boundary-layer "
               "depth. Dropping missing rows conditions on clear skies and removes exactly "
               "the meteorological variability the model should learn.",
        verified=False,
    ),
    FeatureSpec(
        name="s5p_so2",
        source=Source.GEE_SENTINEL5P,
        description="TROPOMI SO2 column -- coal combustion proxy, relevant to the winter "
                    "heating regime in Bishkek and Ashgabat",
        units="mol/m^2",
        available_at_runtime=True,
        latency_hours=5.0,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~7 km",
        caveat="Cloud-screened like all TROPOMI products, and additionally noisy at the "
               "low column amounts typical away from large point sources. Winter -- when "
               "the coal signal is strongest -- is also the cloudiest season here, so "
               "missingness is worst precisely when the feature would be most useful.",
        verified=False,
    ),
    FeatureSpec(
        name="s5p_co",
        source=Source.GEE_SENTINEL5P,
        description="TROPOMI CO column -- incomplete combustion and biomass burning",
        units="mol/m^2",
        available_at_runtime=True,
        latency_hours=5.0,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~7 km",
        caveat="Cloud-screened. CO has a long atmospheric lifetime (weeks), so the column "
               "reflects regional accumulation rather than local emission -- useful for "
               "transport, weak for local attribution.",
        verified=False,
    ),
    FeatureSpec(
        name="viirs_active_fire_count",
        source=Source.GEE_VIIRS,
        description="VIIRS active fire detections within the buffer -- biomass burning",
        units="count",
        available_at_runtime=True,
        latency_hours=4.0,
        reduction=Reduction(50_000, Statistic.COUNT),
        native_resolution="375 m",
        verified=False,
    ),
)

# ------------------------------------------------------- meteorology: the rule-3 hazard
MET_REANALYSIS = (
    FeatureSpec(
        name="era5_blh_reanalysis",
        source=Source.CDS_ERA5,
        description="ERA5 boundary layer height -- the dominant control on dilution",
        units="m",
        available_at_runtime=False,
        latency_hours=None,
        reduction=Reduction(BUF_MET, Statistic.MEAN),
        native_resolution="~31 km",
        caveat="ERA5 lags roughly five days. ORACLE ONLY. Results using this must be "
               "labelled a reanalysis-oracle ablation and never presented as deployable.",
        verified=False,
    ),
    FeatureSpec(
        name="era5_inversion_strength_reanalysis",
        source=Source.CDS_ERA5,
        description="Temperature difference between 925 hPa and 2 m -- inversion proxy, "
                    "central to the Tashkent and Almaty basin regimes",
        units="K",
        available_at_runtime=False,
        latency_hours=None,
        reduction=Reduction(BUF_MET, Statistic.MEAN),
        native_resolution="~31 km",
        caveat="ORACLE ONLY, same reason as ERA5 BLH.",
        verified=False,
    ),
    FeatureSpec(
        name="cams_pm25_reanalysis",
        source=Source.ADS_CAMS_REANALYSIS,
        description="CAMS global reanalysis surface PM2.5 -- the mandated 'raw model "
                    "output' baseline",
        units="ug/m^3",
        available_at_runtime=False,
        latency_hours=None,
        reduction=Reduction(BUF_MET, Statistic.MEAN),
        native_resolution="~40 km",
        caveat="ORACLE ONLY. The baseline ladder requires beating raw CAMS, but the "
               "REANALYSIS is not a deployable input -- only a reference. The deployable "
               "counterpart is cams_pm25_forecast.",
        verified=False,
    ),
)

MET_FORECAST = (
    FeatureSpec(
        name="cams_pm25_forecast",
        source=Source.ADS_CAMS_FORECAST,
        description="CAMS global forecast surface PM2.5 -- the deployable counterpart to "
                    "the reanalysis",
        units="ug/m^3",
        available_at_runtime=True,
        latency_hours=12.0,
        reduction=Reduction(BUF_MET, Statistic.MEAN),
        native_resolution="~40 km",
        caveat="This is what a deployed ECO Pulse can actually consume. Any comparison "
               "against cams_pm25_reanalysis must state which was used.",
        verified=False,
    ),
    FeatureSpec(
        name="cams_forecast_blh",
        source=Source.ADS_CAMS_FORECAST,
        description="Forecast boundary layer height -- deployable substitute for ERA5 BLH",
        units="m",
        available_at_runtime=True,
        latency_hours=12.0,
        reduction=Reduction(BUF_MET, Statistic.MEAN),
        native_resolution="~40 km",
        verified=False,
    ),
    FeatureSpec(
        name="cams_forecast_wind_speed_10m",
        source=Source.ADS_CAMS_FORECAST,
        description="Forecast 10 m wind speed -- ventilation",
        units="m/s",
        available_at_runtime=True,
        latency_hours=12.0,
        reduction=Reduction(BUF_MET, Statistic.MEAN),
        native_resolution="~40 km",
        verified=False,
    ),
)

# ----------------------------------------------------------------------------- static
STATIC = (
    FeatureSpec(
        name="ghsl_population_density",
        source=Source.GEE_STATIC,
        description="GHSL population density",
        units="persons/km^2",
        available_at_runtime=True,
        latency_hours=0.0,
        reduction=Reduction(BUF_STATIC, Statistic.MEAN),
        native_resolution="100 m",
        verified=False,
    ),
    FeatureSpec(
        name="viirs_nighttime_lights",
        source=Source.GEE_STATIC,
        description="VIIRS night-time lights -- activity and settlement intensity",
        units="nW/cm^2/sr",
        available_at_runtime=True,
        latency_hours=0.0,
        reduction=Reduction(BUF_STATIC, Statistic.MEAN),
        native_resolution="500 m",
        verified=False,
    ),
    FeatureSpec(
        name="elevation",
        source=Source.GEE_STATIC,
        description="Terrain elevation (SRTM/Copernicus DEM)",
        units="m",
        available_at_runtime=True,
        latency_hours=0.0,
        reduction=Reduction(BUF_STATIC, Statistic.MEAN),
        native_resolution="30 m",
        verified=False,
    ),
    FeatureSpec(
        name="terrain_basin_index",
        source=Source.DERIVED,
        description="Station elevation minus the mean elevation of a 25 km annulus -- "
                    "negative values indicate a basin that traps inversions",
        units="m",
        available_at_runtime=True,
        latency_hours=0.0,
        native_resolution="derived from DEM",
        caveat="Motivated by the regime split found in Phase 2: Tashkent and Almaty sit in "
               "basins; the diurnal analysis showed Almaty behaving unlike any other city.",
        verified=False,
    ),
    FeatureSpec(
        name="distance_to_aralkum",
        source=Source.DERIVED,
        description="Great-circle distance to the Aral Sea dry bed -- the region's "
                    "dominant salt-dust source",
        units="km",
        available_at_runtime=True,
        latency_hours=0.0,
        native_resolution="derived",
        caveat="The Aralkum added ~7% more dust over Central Asia in the 2000s-2010s vs "
               "the 1980s-1990s, with salt-dust events peaking in spring -- a distinct "
               "regime from the winter coal peak.",
        verified=False,
    ),
)

ALL_FEATURES: tuple[FeatureSpec, ...] = SATELLITE + MET_REANALYSIS + MET_FORECAST + STATIC


# ------------------------------------------------------------------------ feature sets
DEPLOYABLE = FeatureSet(
    name="deployable",
    features=SATELLITE + MET_FORECAST + STATIC,
    deployable=True,
    purpose="Everything a live ECO Pulse service can actually obtain at prediction time. "
            "Headline results come from this set.",
)

REANALYSIS_ORACLE = FeatureSet(
    name="reanalysis_oracle",
    features=SATELLITE + MET_REANALYSIS + MET_FORECAST + STATIC,
    deployable=False,
    purpose="Adds ERA5 and CAMS reanalysis. Quantifies the cost of operational "
            "constraints by measuring what perfect meteorology would buy. Reported ONLY "
            "as a clearly-labelled ablation, never as a deployed number.",
)

STATIC_ONLY = FeatureSet(
    name="static_only",
    features=STATIC,
    deployable=True,
    purpose="Ablation floor: how much of the leave-city-out signal is explained by "
            "geography alone, with no time-varying input?",
)

FEATURE_SETS = (DEPLOYABLE, REANALYSIS_ORACLE, STATIC_ONLY)
