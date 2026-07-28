# Data Manifest

Every dataset used in this project, with the information needed to obtain the identical
bytes again. A source is not usable in the paper until it has a complete row here.

Required fields per source: **name, provider, version/collection, spatial extent, temporal
extent, variables, licence, access date, retrieval method, checksum of the archived
extract, n records.**

---

## Ground truth (increment 1)

### GT-1 — OpenAQ

| Field | Value |
|---|---|
| Provider | OpenAQ |
| API version | v3 |
| Endpoint | `https://api.openaq.org/v3/` |
| Auth | `X-API-Key` header — see `REGISTRATION.md` |
| Spatial extent | UZ, KZ, KG, TJ, TM (+ data-rich training pool, TBD) |
| Temporal extent | Station spans 2018-07-27 → 2026-07-28 (census level); measurements not yet retrieved |
| Variables | `pm25` (µg/m³), station metadata, coordinates |
| Licence | Per-location `licenses[]` block; recorded per station in the census. **Not yet transcribed verbatim** |
| Access date | **2026-07-28** (locations endpoint) |
| Checksum | See `data/raw/cache/` — every response cached and hashed; census digest recorded at commit |
| n records | **317 locations** (UZ 5, KZ 206, KG 97, TJ 7, TM 2) |

**Census result (locations endpoint only — no measurements retrieved):**

| Filter | n |
|---|---|
| Locations returned | 317 |
| With ≥1 PM2.5 sensor | 317 |
| Mobile (excluded from spatial splits) | 0 |
| Span ≥ 2 years | 11 |
| **Distinct instruments after Q5b de-duplication** | **9** |
| **Distinct cities** | **7** — Almaty, Ashgabat, Astana, Bishkek, Dushanbe, Khujand, Tashkent |

Providers: AirGradient 173, Clarity 135, AirNow 5, StateAir 4. The 306 stations excluded
for short span are low-cost units with median span 0.59 y and earliest deployment 2023-07 —
a genuine recent rollout, valuable for future work but not for a multi-year split (risk R10).

**Reference monitors end March 2025.** Six of nine stop at exactly `2025-03-04`: the US
State Department terminated its global embassy air quality programme that month. See risk
R9 and `research/GAP.md`. The last full year with reference coverage is **2024**.

### GT-2 — US Embassy / State Department reference monitors

| Field | Value |
|---|---|
| Provider | US Dept. of State / AirNow |
| Sites | Tashkent, Astana, Almaty, Bishkek, Dushanbe |
| Spatial extent | 5 point locations |
| Temporal extent | *pending* |
| Variables | PM2.5 (µg/m³), QC flag |
| Licence | *pending* |
| Access date | *not yet accessed* |
| Checksum | *pending* |
| n records | *pending* |

**Why these matter disproportionately:** these are reference-grade (BAM/FEM-class)
instruments with documented QA, in a region where most other signals are low-cost sensors.
They are the calibration anchor for judging everything else, so any disagreement between an
embassy monitor and a co-located OpenAQ sensor is a finding to investigate, not an
inconvenience to average away.

### GT-3 — National networks (Uzhydromet, Kazhydromet)

Status: **availability unknown.** Phase 1 will document what is actually retrievable
without a data-sharing agreement. If nothing is openly available, that is recorded as a
limitation of the benchmark — not worked around.

---

## Predictors (increment 2 — not yet acquired)

Listed so the manifest structure is fixed in advance. All are blocked on registrations in
`REGISTRATION.md`.

| ID | Source | Product | Role | Retrieval |
|---|---|---|---|---|
| PR-1 | MODIS | MAIAC AOD `MCD19A2`, 1 km | Primary aerosol predictor | Earth Engine, server-side `reduceRegions` |
| PR-2 | Sentinel-5P | NO₂, SO₂, CO, **UV aerosol index** | Anthropogenic + dust discrimination | Earth Engine |
| PR-3 | VIIRS | Active fire | Biomass burning | Earth Engine |
| PR-4 | ERA5 / ERA5-Land | BLH, wind, RH, T, inversion strength, precip | Meteorology | CDS, area-subset at request |
| PR-5 | CAMS | Reanalysis **and forecast** | Mandated baseline + operational feature | ADS |
| PR-6 | MERRA-2 | Aerosol diagnostics | Alternative baseline | Earthdata / GEE |
| PR-7 | GHSL, VIIRS lights, OSM, land cover, DEM | Static emissions proxies + terrain | Basin geometry, Aral distance | Earth Engine |

**Retrieval constraint (binding).** No raster is ever written to local disk. All satellite
predictors are reduced server-side to station-buffer statistics before download. The dev
machine has ~14 GB free; the naive raster pipeline needs O(100 GB–TB). See
`REGISTRATION.md` for the full argument.

**Operational-availability flag.** Every predictor row carries an `available_at_runtime`
boolean. ERA5 and CAMS *reanalysis* are `false` — they do not exist at prediction time.
Any result using them is reported only as a clearly-labelled reanalysis-oracle ablation,
never as a deployed number. Enforced by `tests/test_feature_availability.py`.
