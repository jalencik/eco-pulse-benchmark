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
| Licence | Per-location `licenses[]` block — **transcribed 2026-08-14, see the licence matrix below.** Not carried in `station_census.csv`; the earlier claim that it was is retracted |
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

### Per-feed licence matrix — retrieved from OpenAQ `/v3/locations/{id}`, 2026-08-14

Raw API responses are archived under `review/licence_evidence/`. Licence definitions come
from `/v3/licenses`; the flags below are OpenAQ's own fields, not our interpretation.

| feed | city | provider | OpenAQ licence | redistribution | attribution | modification |
|---|---|---|---|---|---|---|
| 8876 | Almaty | AirNow | US Public Domain (33) | allowed | not required | allowed |
| 8870 | Ashgabat | AirNow | US Public Domain (33) | allowed | not required | allowed |
| 8827 | Bishkek | AirNow | US Public Domain (33) | allowed | not required | allowed |
| 8684 | Dushanbe | AirNow | US Public Domain (33) | allowed | not required | allowed |
| 1894632 | Khujand | Clarity | CC0 1.0 (38) | allowed | not required | allowed |
| 1924313 | Khujand | Clarity | CC0 1.0 (38) | allowed | not required | allowed |
| 8170 | Ashgabat | StateAir Ashgabat | **none recorded** | — | — | — |
| 8225 | Bishkek | StateAir Bishkek | **none recorded** | — | — | — |
| 9769 | Dushanbe | StateAir Dushanbe | **none recorded** | — | — | — |
| 8881 | Tashkent | StateAir Tashkent | **none recorded** | — | — | — |

**The absent StateAir licence is a provider-labelling artifact, not a rights determination.**
Four independent lines of evidence, all gathered 2026-08-14:

1. **It is perfectly systematic.** Across all 33 StateAir providers in OpenAQ, **0 of 36**
   locations carry any licence, against 200/200 for AirNow and 200/200 for Clarity. The
   absence correlates with the provider *label*, not with any property of the data.
2. **The labels are interchangeable for the same location.** OpenAQ's own issue tracker
   (`openaq/openaq-ingestor` issue #8, "Multiple providers for one source leads to issues
   with data exports") documents location **8047** being ingested under *both* AirNow and
   StateAir, flipping between them up to 74 times a day. That location — "Khartoum Embassy" —
   today reads `provider: AirNow, licence: US Public Domain`. Had the flip settled on the
   StateAir label instead, it would read null. The licence follows the label.
3. **The schema cannot express "rights not established."** `openaq-db`
   (`openaqdb/tables/licenses.sql`) attaches licences through join tables —
   `providers_licenses` and `sensor_nodes_licenses` — each requiring
   `licenses_id int NOT NULL REFERENCES licenses`. A licence exists only as a row. There is
   no default, no status column and no "unknown" licence, so the *absence of a row* is the
   only way the model can represent anything, and it necessarily means "nothing assigned"
   rather than "assessed and refused." The ingestion layer confirms this: the
   `openaq-fetch` source-definition format (`sources/*.json`) carries
   `url, adapter, name, city, country, description, resolution, sourceURL, contacts, active`
   — **no licence field at all**. Licences were retro-fitted at the database layer (issue
   #139, PR #337) after StateAir was already ingested.
4. **OpenAQ itself redistributes the data.** All four StateAir feeds are published in the
   openaq-data-archive S3 bucket, registered with the AWS Registry of Open Data and
   downloadable anonymously; retrieval was verified for each on 2026-08-14. A platform that
   had determined it lacked redistribution rights would not publish the data this way.

Independently of OpenAQ's metadata, the underlying observations are US diplomatic-post
measurements, and the producing agency's own policy states: "Unless a copyright is indicated,
information on State Department websites is in the public domain and may be copied and
distributed without permission" (state.gov, *Copyright Information*, accessed 2026-08-14).

### The US Department of State Data Use Statement — recovered 2026-08-15

Both original hosts are dead (`stateair.net` refuses connections; `dosairnowdata.org` no
longer resolves), but the Internet Archive preserves them. The official
`USDOS_AQDataUseStatement.pdf` was recovered and is archived at
`review/licence_evidence/USDOS_AQDataUseStatement_archived20140512.pdf`. Verbatim, the
operative clauses:

> "State Air observational data are not fully verified or validated; these data are subject
> to change, error, and correction. **The data and information are in no way official.**"
>
> "If observational data are used for analyses… the analysis results, displays, or products
> **must indicate that these data are not fully verified or validated.**"
>
> "**Air quality data should not be altered in any way and should be disseminated as
> received.**"
>
> "Publications, analyses, products, presentations, and/or derived information that rely on
> these data **must give attribution to the U.S. Department of State.**"
>
> "By accessing this data you attest to having read, understood, and agreed to the data use
> conditions stated above."

**Scope, and why it matters.** The statement opens: "The U.S. Department of State Data Use
Statement applies to data available from the **Mission China** air quality monitoring
program, which includes the data portal www.stateair.net." That wording is unchanged across
every capture from 2014-04-15 to 2025-10-11. The four StateAir feeds used here are **not**
Mission China and were not served from `stateair.net`: OpenAQ's `stateair.js` adapter reads
`dosairnowdata.org/dos/AllPosts24Hour.json`, and the archived `dosairnowdata.org` carries no
data-use statement — its index is a 623-byte application shell and its `app.js` contains no
terms text.

So the statement **does not govern these four feeds on its own stated scope**, and it was
never accepted by this project, which obtained the observations through OpenAQ. It is
nevertheless the clearest available expression of the producing agency's expectations for its
air-quality observations, and two of its conditions are honoured here on that basis:
attribution to the U.S. Department of State, and the statement that the data are not fully
verified or validated.

**The clause that cuts the other way.** "Air quality data should not be altered in any way
and should be disseminated as received" is incompatible with redistributing a QC-masked,
merged, daily-aggregated panel — the same conflict the EPA AirNow guidelines raise. Where
that expectation extends to the global programme, it is a reason not to redistribute the
derived panel, and it supports the decision to keep observations out of the deposit.

This recovery **weakens** the earlier reading that the StateAir observations are
attribution-free public domain. The Department attaches conditions to its air-quality data
wherever it has stated any.

**Exhaustive negative result for the portal that did serve these feeds.** Every archived path
under `dosairnowdata.org` was enumerated (172 snapshots, 2018-02 to 2025-04): one application
shell at `/dos/index.htm`, CSS/JS assets, absent i18n stubs, JSON endpoints, RSS feeds and
historical CSVs. There is **no terms page, no data-use statement, no licence, no PDF and no
copyright notice**; `robots.txt` and `sitemap.xml` both 404. Two archived data files
(`KuwaitCity_PM2.5_2023_YTD.csv`, `EmbassyKathmandu_PM2.5_2019_YTD.csv`) were retrieved and
contain no copyright, terms, data-use or attribution text — header plus observations only.

This matters for one specific reason. The Department's general policy is conditional: "**Unless
a copyright is indicated**, information on State Department websites is in the public domain
and may be copied and distributed without permission." Earlier passes recorded that condition
as unverifiable because the sites were dead. It is now **verified negatively**: across the
portal's entire archived footprint and in the data files themselves, no copyright was
indicated. The condition is satisfied.

What remains unestablished is narrower than before: whether `dosairnowdata.org` — a
Department-operated `.org` host, not a `.gov` one — is a "State Department website" for the
purposes of that policy, and whether the Mission China conditions were intended to extend to
the global programme. Both are questions only the Department can answer. **Absence of a
prohibition is not a grant, and these four feeds are recorded as unresolved rather than
restricted: no evidence anywhere indicates redistribution is forbidden.**

**Second public-source sweep, 2026-08-15 — negative.** A further search targeted specifically
at Tashkent and Bishkek returned no affirmative evidence:

| Source | Result |
|---|---|
| `AllPostsHistorical.json`, `AllPosts24Hour.json` (archived; the endpoints OpenAQ actually read) | No copyright, licence, terms, data-use, attribution or disclaimer text |
| 725 archived snapshots (172 `dosairnowdata.org` + 553 `stateair.net`) | **Zero** mention Tashkent or Bishkek — an archive coverage gap for these two posts |
| US Embassy Bishkek air-quality page (`kg.usembassy.gov`, live official `.gov`) | No data-use, terms, copyright, attribution, redistribution or preliminary language; health information only |
| US Embassy Tashkent and Dushanbe air-quality pages | HTTP 404 — removed after the 2025 shutdown |
| archive.today | `stateair.net` held 2013–2024; `dosairnowdata.org` not archived at all |
| Third-party scraper of `dosairnowdata.org` (`mfalfafa/web-scraping-airnow`) | Preserves no terms or licence text from the source |
| Peer-reviewed papers using the same six-city embassy data | Paywalled (HTTP 403); data-availability statements not readable |

No public source examined states data-use conditions for the Central Asian diplomatic-post
observations. The Mission China statement remains the only Departmental data-use document
located, and its stated scope excludes these feeds.

**What is still absent:** no party has issued a written licence record for the StateAir feeds
specifically, and the one condition attached to the Department's policy cannot be checked
against a decommissioned site. The conclusion above rests on converging evidence and agency
policy, not on a grant. That distinction is preserved deliberately.

By contributing hours, **63.6%** of the ground-truth panel carries an explicit OpenAQ
redistribution grant (51.0% US Public Domain, 12.6% CC0) and **36.4%** rests on the DoS
policy above.

**Reference monitors end March 2025 *in this panel*.** Six of nine stop at exactly
`2025-03-04`, when the StateAir publication channel closed. The last full year of reference
coverage in the frozen panel is **2024**. See risk R9 and `research/GAP.md`.

**Corrected 2026-08-14 — the programme did not end uniformly.** A live OpenAQ query on that
date shows three of these US diplomatic-post monitors still republished through the AirNow
provider after 2025-03-04, with real measurements retrieved and verified via
`/v3/sensors/{id}/measurements`:

| feed | provider | last observation (2026-08-14) |
|---|---|---|
| 8684 Dushanbe | AirNow | **still reporting** |
| 8876 Almaty | AirNow | 2025-11-14 |
| 8870 Ashgabat | AirNow | 2025-09-24 |
| 8827 Bishkek | AirNow | 2025-03-04 (`found=0` after) |
| 7094 Astana | AirNow | 2025-03-04 |
| 8170 / 8225 / 9769 / 8881 | StateAir | 2025-03-04 (all four) |

What closed on 2025-03-04 was the **StateAir channel**, not every monitor. This does not
affect the benchmark — the test year is 2024 and the panel is frozen — but the earlier
blanket claim that the programme "terminated" was wrong and is retracted here.

### Archival urgency — the source record has been deleted

Reporting on the shutdown states that **17 years of data were removed from airnow.gov**.
**Revised 2026-08-14:** the earlier claim here that "the programme was not merely suspended"
and that "no resumption is evidenced" is retracted — see the correction above. Historical
observations for these posts remain retrievable through OpenAQ, and three posts resumed or
continued publishing via AirNow. The cache should still be preserved and checksummed, but
the stronger claim that the source record is irrecoverable is not supported by evidence.

This changes the status of the cached responses under `data/raw/cache/`. They are no longer
a convenience cache that could be refetched on demand — for the embassy record they are
**a copy of an archive that may no longer exist at source**, obtained through OpenAQ's
mirror. Three consequences:

1. **The cache must be checksummed and preserved**, not treated as regenerable. A future
   `make reproduce` cannot assume the upstream API will still serve these years.
2. **Provenance must distinguish "retrieved from OpenAQ's mirror" from "retrieved from the
   originating programme."** They are no longer the same claim, and only the former is
   currently possible.
3. **Completeness cannot be verified against the original publisher.** If OpenAQ's mirror
   is itself partial, that gap is now unmeasurable. This is a real limitation of the
   benchmark and belongs in the paper's limitations section, not in a footnote.

It also sharpens the case for C1. A benchmark curating a finite, closed, partially-deleted
reference record is more valuable than one curating a live feed anyone could re-pull.

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

**Scope of that claim — corrected 2026-08-13.** The sentence above applies to the US-embassy
feeds (AirNow and StateAir), which is **five of the benchmark's seven instruments**. It does
**not** apply to Khujand. Both Khujand stations (`1894632`, `1924313`) are **Clarity low-cost
sensors**, carrying `is_monitor = false` in the OpenAQ census, and the manuscript previously
described all instruments as reference-grade. Per-instrument provenance:

| station | city | provider | `is_monitor` | grade |
|---|---|---|---|---|
| 8876 | Almaty | AirNow | true | reference |
| Bishkek (merged 8225+8827) | Bishkek | StateAir + AirNow | true | reference |
| Ashgabat (merged 8870+8170) | Ashgabat | StateAir + AirNow | true | reference |
| Dushanbe (merged 8684+9769) | Dushanbe | AirNow + StateAir | true | reference |
| 8881 | Tashkent | StateAir | true | reference |
| 1894632 | Khujand | **Clarity** | **false** | **low-cost** |
| 1924313 | Khujand | **Clarity** | **false** | **low-cost** |

Across the whole census the mapping is exact: AirNow and StateAir are `is_monitor = true`;
Clarity (135 stations) and AirGradient (173) are `is_monitor = false`.

Two consequences are carried into the paper rather than left here. First, Khujand is the
benchmark's zero-shot fold *and* its only low-cost city, so that fold's labels carry the
measurement uncertainty the exclusion of 306 low-cost stations was designed to avoid. Second,
both Khujand stations satisfy the pre-registered 2-year Q7 span rule only by counting
observations after the benchmark record ends; inside the window their spans are 1.09 y and
1.07 y.

**Dushanbe is one instrument, not two** (D-012, benchmark v1.1.0). `8684` (AirNow) and `9769`
(StateAir) are the same US-embassy monitor republished under coordinates 6.06 km apart:
99.99% of their 33,462 overlapping hours are the identical reading. They are merged under the
D-008 precedence-and-gap-fill rule. The benchmark holds **7 instruments across 6 cities**, not
8.

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
