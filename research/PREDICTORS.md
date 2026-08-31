# Phase 4: Predictor Specification

18 features across 4 sources. The catalogue is code (`src/ecopulse_ca/features/catalogue.py`),
not prose. This document explains it. `tests/test_feature_availability.py` enforces it.

---

## The distinction everything else hangs on

| | Available at prediction time | Use |
|---|---|---|
| **CAMS forecast** | ✅ ~12 h latency | Deployable. Headline results. |
| **CAMS reanalysis** | ❌ months | **Oracle only.** Mandated baseline comparison, never a deployed input. |
| **ERA5 reanalysis** | ❌ ~5 days | **Oracle only.** |

These describe the *same physical quantities*. The reanalysis is cleaner, better
documented, and already in most atmospheric pipelines, which is exactly why reaching for
it is the easy mistake. A model consuming ERA5 boundary-layer height to predict tomorrow's
PM2.5 is reading the future, will post an excellent number, and cannot be deployed. Nothing
about its RMSE looks wrong.

**Rule 3 is therefore a typed property, not a convention.** `FeatureSet(deployable=True)`
is an assertion checked by test. Adding a reanalysis column to a deployable set fails the
build. A dedicated test constructs a contaminated set and asserts the check catches it,
because a guard that never fires proves nothing.

---

## The catalogue

### Satellite: 7 features (Google Earth Engine)

| Feature | Resolution | Latency | Missingness |
|---|---|---:|---|
| `maiac_aod_055` | 1 km | 6 h | **informative** |
| `maiac_valid_pixel_fraction` | 1 km | 6 h | — |
| `s5p_absorbing_aerosol_index` | ~7 km | 5 h | **informative** |
| `s5p_no2_tropospheric` | 5.5×3.5 km | 5 h | **informative** |
| `s5p_so2` | ~7 km | 5 h | **informative** |
| `s5p_co` | ~7 km | 5 h | **informative** |
| `viirs_active_fire_count` | 375 m | 4 h | — |

**MAIAC missingness is not random and must never be dropped (risk R7).** Retrievals fail
during dust storms, snow and heavy cloud, precisely the extreme-PM2.5 episodes that
matter. Dropping those rows conditions the evaluation on *"retrieval succeeded"* and biases
every result toward calm, clear, low-concentration days. The Xinjiang study (the closest
environmental analogue in the literature) hit exactly this and reported it as a limitation.

So `maiac_valid_pixel_fraction` is **promoted to a feature**, not kept as diagnostics.
Retrieval failure carries atmospheric information (dust/cloud/snow). Discarding it throws
away signal when concentrations are highest.

The same logic applies to TROPOMI, which is cloud-screened: missingness tracks cloud, which
covaries with washout and boundary-layer depth. Winter, when the coal signal is strongest
in Bishkek and Ashgabat, is also the cloudiest season, so SO₂ is most often missing exactly
when it would be most useful.

`s5p_absorbing_aerosol_index` is the key **dust discriminator**: unlike AOD it works over
bright surfaces and responds to absorbing aerosol, so it should separate Aralkum/loess dust
from combustion aerosol, the two regimes Phase 2 found are physically distinct.

### Meteorology: 6 features (Copernicus ADS / CDS)

**Deployable:** `cams_pm25_forecast`, `cams_forecast_blh`, `cams_forecast_wind_speed_10m` (12 h latency)

**Oracle only:** `era5_blh_reanalysis`, `era5_inversion_strength_reanalysis`, `cams_pm25_reanalysis`

The oracle set quantifies **the cost of operational constraints**: what perfect
meteorology would buy. That is a legitimate and interesting ablation. It is not a result.

`era5_inversion_strength_reanalysis` (925 hPa minus 2 m temperature) targets the basin
regimes directly: Phase 2 found Tashkent and Almaty behave unlike the other cities, and
Almaty unlike anything else in the set.

### Static / terrain: 5 features

`ghsl_population_density`, `viirs_nighttime_lights`, `elevation`, `terrain_basin_index`,
`distance_to_aralkum`.

Two are derived and motivated by findings rather than convention:

- **`terrain_basin_index`**: station elevation minus the mean of a 25 km annulus. Negative
  values indicate a basin that traps inversions. Directly motivated by the three-regime
  split.
- **`distance_to_aralkum`**: the Aral dry bed added ~7% more regional dust in the
  2000s–2010s versus the 1980s–1990s, with salt-dust peaking in **spring**, a distinct
  season from the winter coal peak.

---

## Feature sets

| Set | n | Deployable | Credentials | Purpose |
|---|---:|---|---|---|
| `deployable` | 15 | ✅ | EE, ADS | Headline results |
| `reanalysis_oracle` | 18 | ❌ | EE, ADS, CDS | Cost-of-operational-constraints ablation |
| `static_only` | 5 | ✅ | EE | Ablation floor: how much is geography alone? |

Note `deployable` does **not** require `CDS_API_KEY`. ERA5 is oracle-only, and a test
asserts that. If a deployable run ever needs the CDS key, something has leaked.

`static_only` matters more than it looks: given that Phase 3 found *no* credential-free
nowcaster beats a trivial always-exceed predictor, knowing how much leave-city-out signal
is explained by geography with **zero time-varying input** sets the floor a satellite model
must clear.

---

## Architecture: server-side reduction, by construction

The dev machine has **8.6 GB free (95% used)**. MAIAC at 1 km over five countries for seven
years is O(100 GB–TB) of raster. It does not fit and never will.

Every gridded feature therefore declares a `Reduction` (buffer radius plus statistic)
applied **in Earth Engine before anything crosses the network**. What is archived is a small
checksummable table, not a pile of HDFs. A test asserts every non-derived feature has one,
so there is no code path that downloads a raster.

Buffer radii scale with native resolution: 3 km (MAIAC), 7 km (S5P), 25 km (meteorology),
1 km (static). Larger buffers reduce retrieval gaps but blur the urban gradient MAIAC was
chosen to resolve. The trade-off is recorded per feature rather than hidden in a constant.

Features with informative missingness must also emit a valid-pixel count: *"mean AOD over 3
valid pixels"* and *"over 300"* are different facts, and a test enforces it.

---

## Verification debt: read this before any deployment claim

**All 18 latency figures are currently `verified=False`.** They are from memory, not from
provider documentation. A recalled latency and a documented one look identical in a table,
and only one is evidence.

`unverified(ALL_FEATURES)` enumerates them, and the count appears in the catalogue summary
so the debt cannot quietly persist into a deployment claim. Before Phase 4 results are
reported, each needs checking against its provider's published NRT schedule, particularly:

- **MAIAC 6 h**: plausible for MODIS NRT, but the *standard* MCD19A2 collection is far
  slower. If only the standard product is available in Earth Engine, this feature is not
  deployable at 6 h and the `deployable` set is wrong.
- **CAMS forecast 12 h**: depends on which cycle and lead time is used.
- **S5P 5 h**: NRT versus offline processing differ substantially.

The MAIAC item is the one that could invalidate the deployable set outright, so it should be
checked first.
