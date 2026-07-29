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
        description="MAIAC aerosol optical depth at 550 nm (MCD19A2.061 via Earth "
                    "Engine) -- the primary column-aerosol predictor for the retrospective "
                    "benchmark",
        units="dimensionless",
        available_at_runtime=False,
        latency_hours=None,
        missingness_informative=True,
        reduction=Reduction(BUF_AOD, Statistic.MEAN),
        native_resolution="1 km",
        caveat="ORACLE ONLY for deployment purposes -- but the correct choice for the "
               "retrospective benchmark. VERIFIED 2026-07-29: the Earth Engine catalogue "
               "reports MCD19A2.061 coverage ending 2026-07-21 against a query date of "
               "2026-07-29, i.e. an observed latency of ~8 DAYS (192 h), not the 6 h "
               "originally claimed. That exceeds the shortest forecast horizon, so this "
               "product cannot inform a live t+24 forecast. The deployable counterpart is "
               "maiac_aod_055_nrt. "
               "Separately (risk R7): retrievals fail during dust storms, snow and heavy "
               "cloud -- exactly the extreme-PM2.5 episodes of interest -- and accuracy is "
               "lower over bright arid surfaces, with lofted dust causing underestimation. "
               "Missing rows must be modelled, never dropped.",
        verified=True,
    ),
    FeatureSpec(
        name="maiac_aod_055_nrt",
        source=Source.LANCE_NRT,
        description="MAIAC AOD 550 nm from the NASA LANCE near-real-time stream "
                    "(MCD19A2N) -- the deployable counterpart to the Earth Engine product",
        units="dimensionless",
        available_at_runtime=True,
        latency_hours=2.1,  # LANCE publishes within 60-125 minutes of observation
        missingness_informative=True,
        reduction=None,
        native_resolution="1 km",
        caveat="TRAIN/SERVE SKEW -- the most important caveat in this catalogue. A model "
               "trained on the fully-reprocessed standard MCD19A2 would be SERVED the NRT "
               "MCD19A2N, which is a different product: not reprocessed, using predicted "
               "rather than definitive geolocation and ancillary inputs. Retrospective "
               "metrics cannot see this gap. Any deployment claim must either quantify the "
               "standard-vs-NRT difference on overlapping dates or state the skew as an "
               "unquantified risk. "
               "ARCHITECTURAL CONFLICT: LANCE serves HDF granules, so there is no "
               "server-side reduction -- this feature requires raster download and does "
               "NOT fit the 8.6 GB dev machine. It is a server-side deployment concern, "
               "not something reproducible locally.",
        verified=True,
        requires_raster_download=True,
    ),
    FeatureSpec(
        name="maiac_valid_pixel_fraction",
        source=Source.GEE_MODIS,
        description="Share of buffer pixels with a successful MAIAC retrieval -- the "
                    "informative-missingness signal itself, promoted to a feature",
        units="fraction",
        available_at_runtime=False,
        latency_hours=None,
        missingness_informative=False,
        reduction=Reduction(BUF_AOD, Statistic.COUNT),
        native_resolution="1 km",
        caveat="ORACLE ONLY: shares the ~8-day Earth Engine latency of its parent product. "
               "Deliberately a feature, not just diagnostics -- retrieval failure carries "
               "information about the atmosphere (dust/cloud/snow) and discarding it "
               "throws away signal precisely when concentrations are extreme.",
        verified=True,
    ),
    FeatureSpec(
        name="s5p_absorbing_aerosol_index",
        source=Source.GEE_SENTINEL5P,
        description="Sentinel-5P TROPOMI UV absorbing aerosol index",
        units="dimensionless",
        available_at_runtime=False,
        latency_hours=None,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~7 km",
        caveat="The key dust discriminator: unlike AOD, the UV AAI is available over "
               "bright surfaces and responds to absorbing aerosol, so it should separate "
               "Aralkum/loess dust from combustion aerosol. VERIFIED 2026-07-29 by catalogue end-date: the OFFL collection's latest asset was 2026-07-26T19:10Z against a 2026-07-29 query, i.e. ~72 h latency, not the 5 h originally claimed (wrong by ~13x). That exceeds the 24 h horizon, so OFFL is ORACLE ONLY. The NRTI collection is same-day (<24 h) and is the deployable counterpart -- and unlike MAIAC, BOTH S5P variants live in Earth Engine, so both are server-side reducible. NRTI's cost is smaller per-orbit coverage, which increases retrieval gaps in a feature whose missingness is already informative.",
        verified=True,
    ),
    FeatureSpec(
        name="s5p_no2_tropospheric",
        source=Source.GEE_SENTINEL5P,
        description="TROPOMI tropospheric NO2 column -- combustion/traffic proxy",
        units="mol/m^2",
        available_at_runtime=False,
        latency_hours=None,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~5.5 x 3.5 km",
        caveat="TROPOMI products are cloud-screened, so missingness tracks cloud cover -- "
               "which itself covaries with washout, frontal passage and boundary-layer "
               "depth. Dropping missing rows conditions on clear skies and removes exactly "
               "the meteorological variability the model should learn. VERIFIED 2026-07-29 by catalogue end-date: the OFFL collection's latest asset was 2026-07-26T19:10Z against a 2026-07-29 query, i.e. ~72 h latency, not the 5 h originally claimed (wrong by ~13x). That exceeds the 24 h horizon, so OFFL is ORACLE ONLY. The NRTI collection is same-day (<24 h) and is the deployable counterpart -- and unlike MAIAC, BOTH S5P variants live in Earth Engine, so both are server-side reducible. NRTI's cost is smaller per-orbit coverage, which increases retrieval gaps in a feature whose missingness is already informative.",
        verified=True,
    ),
    FeatureSpec(
        name="s5p_so2",
        source=Source.GEE_SENTINEL5P,
        description="TROPOMI SO2 column -- coal combustion proxy, relevant to the winter "
                    "heating regime in Bishkek and Ashgabat",
        units="mol/m^2",
        available_at_runtime=False,
        latency_hours=None,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~7 km",
        caveat="Cloud-screened like all TROPOMI products, and additionally noisy at the "
               "low column amounts typical away from large point sources. Winter -- when "
               "the coal signal is strongest -- is also the cloudiest season here, so "
               "missingness is worst precisely when the feature would be most useful. VERIFIED 2026-07-29 by catalogue end-date: the OFFL collection's latest asset was 2026-07-26T19:10Z against a 2026-07-29 query, i.e. ~72 h latency, not the 5 h originally claimed (wrong by ~13x). That exceeds the 24 h horizon, so OFFL is ORACLE ONLY. The NRTI collection is same-day (<24 h) and is the deployable counterpart -- and unlike MAIAC, BOTH S5P variants live in Earth Engine, so both are server-side reducible. NRTI's cost is smaller per-orbit coverage, which increases retrieval gaps in a feature whose missingness is already informative.",
        verified=True,
    ),
    FeatureSpec(
        name="s5p_co",
        source=Source.GEE_SENTINEL5P,
        description="TROPOMI CO column -- incomplete combustion and biomass burning",
        units="mol/m^2",
        available_at_runtime=False,
        latency_hours=None,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~7 km",
        caveat="Cloud-screened. CO has a long atmospheric lifetime (weeks), so the column "
               "reflects regional accumulation rather than local emission -- useful for "
               "transport, weak for local attribution. VERIFIED 2026-07-29 by catalogue end-date: the OFFL collection's latest asset was 2026-07-26T19:10Z against a 2026-07-29 query, i.e. ~72 h latency, not the 5 h originally claimed (wrong by ~13x). That exceeds the 24 h horizon, so OFFL is ORACLE ONLY. The NRTI collection is same-day (<24 h) and is the deployable counterpart -- and unlike MAIAC, BOTH S5P variants live in Earth Engine, so both are server-side reducible. NRTI's cost is smaller per-orbit coverage, which increases retrieval gaps in a feature whose missingness is already informative.",
        verified=True,
    ),
    FeatureSpec(
        name="s5p_absorbing_aerosol_index_nrt",
        source=Source.GEE_SENTINEL5P,
        description="TROPOMI UV absorbing aerosol index from the NRTI collection -- the "
                    "deployable dust discriminator",
        units="dimensionless",
        available_at_runtime=True,
        latency_hours=20.0,
        missingness_informative=True,
        reduction=Reduction(BUF_S5P, Statistic.MEAN),
        native_resolution="~7 km",
        caveat="VERIFIED 2026-07-29: COPERNICUS/S5P/NRTI/L3_AER_AI had assets dated "
               "2026-07-29 -- the query date -- so latency is under 24 h. 20 h is a "
               "conservative bound, not a documented figure. "
               "Unlike the MAIAC case there is NO reduction-vs-latency conflict: NRTI is "
               "in Earth Engine and reduces server-side. The trade-off is coverage -- NRTI "
               "assets span a smaller area per orbit than OFFL, so retrieval gaps are more "
               "frequent in a feature whose missingness is already informative. Compare "
               "against s5p_absorbing_aerosol_index (OFFL) before trusting it.",
        verified=True,
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
        caveat="ORACLE ONLY. Results using this must be labelled a reanalysis-oracle "
               "ablation and never presented as deployable. "
               "VERIFIED 2026-07-29 against the CDS API: reanalysis-era5-pressure-levels "
               "end_datetime was 2026-07-23T00:00Z, a MEASURED latency of 6 days (163 h) "
               "rather than the recalled 'roughly five days'. That is ~7x the shortest "
               "forecast horizon, confirming the oracle classification.",
        verified=True,
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
        caveat="ORACLE ONLY, same reason as ERA5 BLH -- VERIFIED 2026-07-29: measured "
               "CDS latency 6 days (163 h), ~7x the shortest forecast horizon.",
        verified=True,
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
               "against cams_pm25_reanalysis must state which was used. "
               "VERIFIED 2026-07-29 against the ADS API: collection end_datetime was "
               "2026-07-29T00:00Z at 18:48Z -- the 00 UTC cycle published, the 12 UTC "
               "cycle not yet -- matching the documented schedule (00 UTC by 10:00 UTC, "
               "12 UTC by 22:00 UTC, ~10 h delay). The declared 12 h is a conservative "
               "bound above that, so this feature is genuinely deployable. "
               "DELIVERY RISK, which a latency figure alone hides: ECMWF states delivery "
               "times vary due to the non-operational nature of the ADS service, that "
               "earlier availability is without guarantee, and that time-critical users "
               "should use ECMWF SFTP or paid Dissemination. Deployable in principle over "
               "a channel documented as best-effort -- a production service must either "
               "source CAMS from SFTP/Dissemination or degrade gracefully when a cycle "
               "is late.",
        verified=True,
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
        caveat="Same ADS cycle as cams_pm25_forecast: verified ~10 h documented delay, "
               "12 h declared as a conservative bound. Carries the same best-effort "
               "delivery risk -- see cams_pm25_forecast.",
        verified=True,
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
        caveat="Same ADS cycle as cams_pm25_forecast: verified ~10 h documented delay, "
               "12 h declared as a conservative bound. Carries the same best-effort "
               "delivery risk -- see cams_pm25_forecast.",
        verified=True,
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
        caveat="UNITS: the GHS_POP band `population_count` is people per 100 m CELL, not "
               "per km^2 (verified: nominalScale=100 m). The extractor multiplies by 100. "
               "Without that Almaty reads 183.8 instead of 18,379 people/km^2 -- a model "
               "trains identically on either and only the units claim is false. "
               "Epoch 2020 is used: the catalogue also offers 2025 and 2030, but those are "
               "PROJECTIONS and would inject a forecast of the future into a static feature.",
        verified=True,
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
        name="terrain_basin_index_25km",
        source=Source.DERIVED,
        description="Station elevation minus the mean elevation of a 5-25 km annulus; "
                    "negative values indicate a basin that traps inversions",
        units="m",
        available_at_runtime=True,
        latency_hours=0.0,
        native_resolution="derived from SRTM 30 m",
        caveat="EMITTED AT THREE RADII BECAUSE THE ANSWER DEPENDS ON THE RADIUS. Measured "
               "on Tashkent: -1 m at 25 km, -83 m at 50 km, -327 m at 100 km. A single "
               "radius measures 'is this a basin at radius R', not 'is this a basin'. "
               "This one is too small to reach the Tian Shan from Tashkent. "
               "Do NOT claim basin depth explains Almaty's anomalous 13:00-maximum "
               "regime: at 25 km Almaty is the deepest station (-466 m vs -241/-207 m "
               "group means), but at 100 km it is not (-762 m vs -799 m for the "
               "dilution group). The conclusion flips with the radius.",
        verified=True,
    ),
    FeatureSpec(
        name="terrain_basin_index_50km",
        source=Source.DERIVED,
        description="Station elevation minus the mean elevation of a 5-50 km annulus; "
                    "negative values indicate a basin that traps inversions",
        units="m",
        available_at_runtime=True,
        latency_hours=0.0,
        native_resolution="derived from SRTM 30 m",
        caveat="EMITTED AT THREE RADII BECAUSE THE ANSWER DEPENDS ON THE RADIUS. Measured "
               "on Tashkent: -1 m at 25 km, -83 m at 50 km, -327 m at 100 km. A single "
               "radius measures 'is this a basin at radius R', not 'is this a basin'. "
               "This one is intermediate. "
               "Do NOT claim basin depth explains Almaty's anomalous 13:00-maximum "
               "regime: at 25 km Almaty is the deepest station (-466 m vs -241/-207 m "
               "group means), but at 100 km it is not (-762 m vs -799 m for the "
               "dilution group). The conclusion flips with the radius.",
        verified=True,
    ),
    FeatureSpec(
        name="terrain_basin_index_100km",
        source=Source.DERIVED,
        description="Station elevation minus the mean elevation of a 5-100 km annulus; "
                    "negative values indicate a basin that traps inversions",
        units="m",
        available_at_runtime=True,
        latency_hours=0.0,
        native_resolution="derived from SRTM 30 m",
        caveat="EMITTED AT THREE RADII BECAUSE THE ANSWER DEPENDS ON THE RADIUS. Measured "
               "on Tashkent: -1 m at 25 km, -83 m at 50 km, -327 m at 100 km. A single "
               "radius measures 'is this a basin at radius R', not 'is this a basin'. "
               "This one is captures regional orography; non-monotonic at Almaty, where the Kazakh steppe partly offsets the Tian Shan. "
               "Do NOT claim basin depth explains Almaty's anomalous 13:00-maximum "
               "regime: at 25 km Almaty is the deepest station (-466 m vs -241/-207 m "
               "group means), but at 100 km it is not (-762 m vs -799 m for the "
               "dilution group). The conclusion flips with the radius.",
        verified=True,
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

#: Everything served by Earth Engine. Server-side reducible, but subject to Earth Engine's
#: ingestion lag -- which measurement showed is ~8 days for MAIAC, not hours.
SATELLITE_GEE = tuple(f for f in SATELLITE if f.source is not Source.LANCE_NRT)
#: Near-real-time streams. Deployable, but raster-based and not server-side reducible.
SATELLITE_NRT = tuple(f for f in SATELLITE if f.source is Source.LANCE_NRT)

ALL_FEATURES: tuple[FeatureSpec, ...] = SATELLITE + MET_REANALYSIS + MET_FORECAST + STATIC


# ------------------------------------------------------------------------ feature sets
#
# The split below exists because of a measurement, not a preference.
#
# Verifying the MAIAC latency claim (2026-07-29) showed Earth Engine's MCD19A2.061 runs
# ~8 days behind, not the 6 hours originally assumed. Latency is irrelevant to the
# RETROSPECTIVE benchmark -- evaluating 2024 with 2026 data, the fully-reprocessed standard
# product is strictly the better choice. Latency constrains only the DEPLOYMENT claim.
#
# Conflating those two questions is what produced the wrong number, so they are now
# separate sets with separate names.

BENCHMARK_RETROSPECTIVE = FeatureSet(
    name="benchmark_retrospective",
    features=SATELLITE_GEE + MET_FORECAST + STATIC,
    deployable=False,
    purpose="What the benchmark is built and evaluated on. Uses Earth Engine's standard, "
            "fully-reprocessed products -- correct for retrospective evaluation, and "
            "server-side reducible so it fits the disk budget. NOT a deployment claim: "
            "the Earth Engine latency is days, so this set is marked non-deployable.",
)

DEPLOYABLE = FeatureSet(
    name="deployable",
    features=SATELLITE_NRT + MET_FORECAST + STATIC,
    deployable=True,
    purpose="What a live ECO Pulse service can actually obtain at prediction time: LANCE "
            "near-real-time AOD (~2 h) plus CAMS forecast and static layers. "
            "DELIBERATELY MINIMAL. Sentinel-5P and VIIRS are excluded because their Earth "
            "Engine latencies remain UNVERIFIED -- the one latency claim that was checked "
            "turned out wrong by a factor of ~32, so the others are not assumed correct. "
            "They move here individually as each is verified against provider docs.",
)

REANALYSIS_ORACLE = FeatureSet(
    name="reanalysis_oracle",
    features=SATELLITE_GEE + MET_REANALYSIS + MET_FORECAST + STATIC,
    deployable=False,
    purpose="Adds ERA5 and CAMS reanalysis on top of the retrospective set. Quantifies "
            "the cost of operational constraints by measuring what perfect meteorology "
            "would buy. Reported ONLY as a labelled ablation, never as a deployed number.",
)

STATIC_ONLY = FeatureSet(
    name="static_only",
    features=STATIC,
    deployable=True,
    purpose="Ablation floor: how much of the leave-city-out signal is explained by "
            "geography alone, with no time-varying input? Given that Phase 3 found no "
            "credential-free nowcaster beats a trivial always-exceed predictor, this floor "
            "matters more than it looks.",
)

FEATURE_SETS = (BENCHMARK_RETROSPECTIVE, DEPLOYABLE, REANALYSIS_ORACLE, STATIC_ONLY)
