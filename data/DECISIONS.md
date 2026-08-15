# Data Decisions Log

Every filtering, dropping, imputation, or correction decision goes here — **with its
effect on n**. A decision without a recorded n-effect is not a decision, it is a silent
bias. This file is append-only: superseded entries are struck through, never deleted.

Template:

```
### D-NNN — <short title>
- **Date:**
- **Decision:**
- **Reason:**
- **Effect on n:** stations X → Y, observations A → B (Z% removed)
- **Alternative considered:**
- **Direction of bias if wrong:**
```

The **direction of bias** field is mandatory. If you cannot say which way a filtering
choice would push the results when it is wrong, you do not understand the choice well
enough to make it.

---

## Pre-registered QC rules

These are declared **before** seeing the data, so they cannot be tuned to improve results.
Each becomes a test in `tests/`. Any rule added *after* data inspection must be logged as a
numbered decision below, with an explicit note that it was post-hoc.

| Rule | Definition | Rationale |
|---|---|---|
| **Q1 Physical range** | Drop PM2.5 < 0 or > 1000 µg/m³ | Negative mass is impossible; > 1000 exceeds credible surface values outside extreme events and is near-universally a sensor fault |
| **Q2 Flatline** | Flag ≥ 24 consecutive identical non-zero values | A real ambient signal is never bit-identical for a day; indicates a stuck sensor |
| **Q3 Zero-run** | Flag ≥ 6 consecutive exact zeros | Distinguished from Q2 because reported zeros usually mean "no data" encoded as 0 |
| **Q4 Unit sanity** | Reject a station-series whose median is < 1 or > 500 µg/m³ | Catches mg/m³ reported as µg/m³ (×1000 error) and AQI reported as concentration |
| **Q5 Duplicate IDs** | Detect distinct coordinates sharing a station ID, and identical coordinates across IDs | Both occur in OpenAQ; silently merging them corrupts spatial splits |
| **Q6 Timezone** | Validate against **diurnal shape**, not metadata (see below) | Metadata offsets are frequently wrong; the diurnal cycle is ground truth |
| **Q7 Completeness** | A station enters the benchmark only with ≥ 2 years of record at ≥ 60% hourly completeness | Needed for blocked-temporal splits with a purge gap |

### Q6 in detail — why timezones are checked against physics

Timezone errors are the classic silent bug in multi-source air quality work: everything
runs, nothing errors, and every temporal feature is quietly wrong. Metadata is not
trusted. Instead each station's mean PM2.5 is composited by hour-of-day and checked for
the expected local signature — a morning traffic peak and a stronger evening
traffic/heating peak, with an afternoon minimum when the boundary layer is deepest. A
series whose composite is shifted by a whole number of hours relative to its neighbours is
flagged, not corrected automatically.

**Known landmine — Kazakhstan.** Kazakhstan is understood to have unified onto a single
UTC+5 offset in early 2024, having previously spanned UTC+5 and UTC+6. If correct, any
multi-year record for Astana **changes offset mid-series**. This must be verified against
a primary source during Phase 1 and handled as a split-in-time in the station record, not
as a single constant offset. Logged here before data collection so the check is not
forgotten. Related: `STATUS.md` risk R3.

---

## Decisions

### D-001 — Station census scope and the F3 verdict
- **Date:** 2026-07-28
- **Decision:** census all OpenAQ v3 locations in UZ/KZ/KG/TJ/TM; treat a station as
  span-eligible if it has ≥1 PM2.5 sensor, is not mobile, and spans ≥2 years.
- **Reason:** F3 (too few cities for leave-city-out) decides whether the headline protocol
  exists. `/v3/locations` carries `datetimeFirst`/`datetimeLast`, so span is established
  without downloading any measurements.
- **Effect on n:** 317 locations → **11 span-eligible feeds → 9 distinct instruments →
  7 distinct cities** (Almaty, Ashgabat, Astana, Bishkek, Dushanbe, Khujand, Tashkent).
- **Alternative considered:** relaxing the 2-year rule to admit more stations. Rejected —
  Q7 was pre-registered before data inspection precisely so it could not be loosened to
  improve a count.
- **Direction of bias if wrong:** the 306 excluded stations are AirGradient (173) and
  Clarity (133) low-cost units with median span 0.59 y, earliest deployment 2023-07. If
  their `datetimeFirst` reflects OpenAQ ingestion rather than sensor deployment, the true
  spans are longer and the benchmark is smaller than it needs to be.
- **Verified 2026-07-30 — risk did not materialise (R10 closed).** `scripts/verify_r10.py`
  queried 60 excluded stations, stratified across both providers, for measurements in the
  three years *before* each reported `datetimeFirst`. **0 of 60 returned any row.** The
  exclusions stand and the eligible pool is not artificially small; **n is unchanged**.
  Verified by probing the archive rather than reading provider documentation, and gated on
  a positive control — an eligible station returned 144 hours from a known-good 7-day
  window, establishing that the probe detects data when data exists. Without that control a
  broken query would have produced the same all-negative sweep and the same conclusion.
  Result banked in `paper/tables/t2_04_r10_span_provenance.csv`.
- **Residual scope:** this closes the question for the archive we are entitled to use. A
  sensor that ran earlier without that history reaching OpenAQ is indistinguishable from
  one that did not, and yields no recoverable benchmark row either way.

### D-002 — Flatline policy: MASK_WINDOW
- **Date:** 2026-07-28
- **Decision:** on detecting a flatline (Q2), mask the stuck hours and retain the station.
- **Reason:** user decision. Least destructive option that still removes values known to
  be wrong.
- **Effect on n:** row-level only; no station lost. Exact n-effect reported per station
  once measurements are ingested.
- **Alternative considered:** REJECT_STATION and KEEP_AND_FLAG (see `FlatlinePolicy` in
  `qc/rules.py`). Both remain unimplemented and raise rather than silently defaulting.
- **Direction of bias if wrong:** a sensor that sticks repeatedly stays in the benchmark
  with its good periods intact, so its apparent reliability is overstated. Given only 9
  distinct instruments exist, rejecting stations would cost whole cities.

### D-003 — Q5b co-location threshold: 150 m, distance-based
- **Date:** 2026-07-28
- **Decision:** treat two location_ids within 150 m as one physical instrument, using
  haversine distance with single-link clustering. Replaces exact-coordinate matching.
- **Reason:** **the original rule missed a real duplicate.** The US Embassy monitors are
  published twice, under both StateAir and AirNow, as separate `location_id`s:
  Bishkek 57 m apart, Ashgabat 40 m apart. Under leave-station-out the "held-out" station
  would be the same device as one in training — total leakage.
- **Effect on n:** eligible feeds 11 → **9 distinct instruments**. Two Q5b findings.
- **Alternative considered:** matching on provider name. Rejected — it happens to work for
  StateAir/AirNow and would fail for any other republication.
- **Direction of bias if wrong:** too large a radius merges genuinely distinct urban
  stations, shrinking the benchmark. Margin is wide: the two real Dushanbe sites are
  **6.06 km** apart, ~40× the threshold.

### D-004 — City labels derived heuristically (interim)
- **Date:** 2026-07-28
- **Decision:** city = `locality` when genuinely present, else the station name with
  programme branding stripped. Sentinel strings are treated as missing.
- **Reason:** `locality` is null for 308/317 stations and the **literal string `"N/A"`**
  for 5 more, leaving 4 real values. The `"N/A"` five are the AirNow feeds — precisely the
  ones carrying **Almaty and Astana**. Accepting `"N/A"` as a city name collapsed two
  distinct Kazakh cities into one bogus city and understated the F3 count as 5 instead of 7.
- **Effect on n:** distinct cities 5 (wrong) → **7 (correct)**.
- **Alternative considered:** spatial clustering of coordinates into urban agglomerations,
  as AQ-Bench does at 50 km. **This is the correct approach and is deferred to Phase 2**,
  where the city definition becomes part of the frozen split and must be reproducible from
  the manifest. Phase 2 must not inherit this heuristic silently.
- **Direction of bias if wrong:** a name-derived label could split one city across two
  spellings (inflating the city count) or merge distinct towns sharing a name. Both change
  leave-city-out fold membership.
- **Diagnostic note worth keeping:** a CSV round-trip masked the cause, because
  `pandas.read_csv` parses the string `"N/A"` back as `NaN`. The bug was only visible in
  the raw cached API response. **Diagnose data-quality faults at the source, not after a
  round-trip through a format with its own null conventions.**

### D-005 — QC applied to the live hourly panel
- **Date:** 2026-07-29
- **Decision:** ran pre-registered rules Q1–Q7 over the 11 census-eligible feeds.
- **Reason:** rules declared before data inspection; flatline policy MASK_WINDOW (D-002).
- **Effect on n:** feeds **11 → 10** (1 station rejected); observations
  **450,817 → 341,321** (24.5% masked by row-level rules Q1–Q3).
  Distinct instruments after Q5b merge: **8**. Distinct cities: **6**.
- **The single rejection:** Astana (AirNow, `7094`) — span 6.60 y but completeness
  **42.8%**, below the pre-registered 60% floor. Its fetch was verified complete
  (`fetch_complete=True`), so this is a genuine property of the record, not a pipeline
  artifact. **Kazakhstan therefore contributes one city (Almaty), not two.**
- **Alternative considered:** lowering the Q7 completeness floor to retain Astana.
  Rejected — Q7 was pre-registered precisely so it could not be relaxed to improve a count,
  and 42.8% would leave a blocked-temporal split with too little on one side of a purge gap.
- **Direction of bias if wrong:** losing Astana removes the only continental-climate
  Kazakh city and the northernmost site, so the benchmark under-represents severe winter
  inversion conditions.

### D-006 — Q6 downgraded from reject to flag when a lag is not identifiable
- **Date:** 2026-07-29
- **Decision:** Q6 now computes `lag_identifiability` — the reference's correlation with
  itself under the candidate rotation — plus a physical cross-check on the positions of the
  daily minimum and maximum. When the lag is unidentifiable, or the physical features
  contradict it, the station is **flagged, not rejected**.
- **Reason:** **the original rule produced a false positive that would have deleted a
  city.** Both Khujand sensors were rejected for an apparent +12 h shift. But Central Asian
  urban PM2.5 is bimodal — a morning traffic peak and an evening traffic/heating peak
  roughly 12 h apart — so the regional reference **self-correlates at r = +0.71 under a
  12 h rotation**. Khujand "won" at lag 12 by a margin of only +0.15 on a signal that
  cannot distinguish the two hypotheses at all. The physical features agreed with
  alignment: reference minimum at hour 10 vs Khujand 11, maximum at 15 vs 17.
- **Effect on n:** stations rejected by Q6: **2 → 0**. Cities: **5 → 6** (Khujand restored).
- **Alternative considered:** raising `min_corr`. Rejected — it does not address the cause;
  a near-symmetric signal is ambiguous at any correlation threshold.
- **Direction of bias if wrong:** if a station *is* genuinely 12 h offset, it now survives
  as a flag rather than being removed, so a real timezone fault could enter the benchmark.
  Mitigated by requiring the flag to be resolved manually before splits are frozen.
- **Known limitation, recorded now:** 6 of 10 surviving feeds carry a Q6 flag, three of them
  for *shape disagreement* with the regional reference (r = 0.31–0.34), not for any shift.
  That is evidence the "regional reference composite" premise is weak here — cities
  hundreds of kilometres apart, with different source mixes (coal heating, basin inversion,
  desert dust), do not share one diurnal shape. **With only 6 cities the median reference is
  dominated by whichever happen to resemble each other.** Q6 should probably become a
  per-city or per-climate-zone check before splits are frozen. → resolved in D-007.

### D-007 — Q6 rebuilt per city (**POST-HOC rule change**)
- **Date:** 2026-07-29
- **Status:** **This rule was changed AFTER data inspection.** Q1–Q7 were pre-registered;
  this revision was not. It is recorded as post-hoc so a reader can discount it accordingly.
  The change makes Q6 strictly *less* able to reject, so it cannot have been motivated by
  improving a headline number.
- **Decision:** replace the single regional-reference comparison with
  (a) **within-city agreement**, which can reject, and
  (b) **cross-city regime labelling**, which is informational and can never reject.
- **Reason:** the evidence says cities genuinely differ. Local-time diurnal minima across
  the 11 feeds ranged 3–16 h; only 6 of 11 had the textbook afternoon minimum. A single
  regional median therefore flags stations in the minority regime *for being correct*. A
  hardcoded physical window ("minimum must be in the afternoon") fails identically — it
  would reject Bishkek and Ashgabat, whose pre-dawn minimum is the expected signature of
  evening residential heating decaying overnight.
- **Effect on n:** Q6 rejections **2 → 0**; cities **5 → 6**. No station lost.
- **Alternative considered:** per-climate-zone reference. Rejected for now — with 6 cities
  the zones would each hold 2–3 stations, which is no better constrained than per-city.
- **Direction of bias if wrong:** a genuine constant offset now survives as a flag rather
  than a rejection, so a real timezone fault could enter the benchmark.
- **Honest limitation — the check is only half-substantive.** Of 8 stations, only **4 were
  genuinely compared against city peers** (Dushanbe ×2, Khujand ×2; all agreed at lag +0 h,
  r = 0.99–1.00, min/max offsets 0 h). The other four cities hold a single instrument each,
  so no within-city check is possible. **A constant, lifelong offset at Almaty, Tashkent,
  Bishkek or Ashgabat is undetectable by any check in this suite**, and is reported as such
  rather than left implicit.
- **Regime finding worth carrying into the paper:** the informational labels split the
  region into more than one regime — Dushanbe, Khujand and Tashkent are dilution-driven
  (afternoon minimum); Bishkek and Ashgabat are evening-source-driven (pre-dawn minimum,
  20:00 maximum). **Almaty fits neither**: pre-dawn minimum but a 13:00 *maximum*. The
  classifier labels it with Bishkek/Ashgabat on the minimum alone, which is misleading.
  Treat Almaty as its own regime in the error analysis.

### D-008 — Co-located feeds merged in Bishkek and Ashgabat
- **Date:** 2026-07-29
- **Decision:** merge each Q5b pair into one series per city by **precedence and gap-fill**,
  never averaging. Primary = the feed with more observations; the other fills gaps only.
  Per-hour provenance retained in `panel_sources.parquet`.
- **Reason:** user decision; the pairs are one physical instrument (57 m and 40 m apart)
  published twice. Averaging two copies of one measurement reduces no noise and, where the
  copies disagree, fabricates a third value no device produced.
- **Effect on n:** Bishkek 39,629 + 37,170 → **44,804** merged (primary `8225`);
  Ashgabat 32,125 + 33,827 → **37,163** merged (primary `8870`). Stations 10 → 8.
- **Agreement, and a serious caveat.** Ashgabat is a clean duplicate: **99.5%** of
  overlapping hours identical, 100% in every year except 2023. **Bishkek is not.** The
  feeds are identical through 2020 and then diverge:

  | year | Bishkek % exact | Ashgabat % exact |
  |---|---:|---:|
  | 2019 | 100.0 | 100.0 |
  | 2020 | 100.0 | 100.0 |
  | 2021 | 28.4 | 100.0 |
  | 2022 | 50.1 | 100.0 |
  | 2023 | 61.2 | 93.8 |
  | **2024** | **11.1** | 100.0 |
  | 2025 | 6.2 | 100.0 |

  **2024 is the temporal test block (D-009), and it is Bishkek's worst year** — 11.1%
  agreement, p95 disagreement 33.6 µg/m³, max 479 µg/m³. The p95 alone is more than twice
  the WHO 2021 24-hour guideline of 15 µg/m³. Bishkek's 2024 test labels therefore depend
  on which publisher is chosen, and no model can see through that. **This is a property of
  the ground truth and must appear in the paper's limitations, not be absorbed silently.**
- **Direction of bias if wrong:** if the non-primary publisher is the more accurate one,
  every Bishkek 2024 error metric is biased by an unknown amount up to the p95 above.
  Mitigated by retaining per-hour provenance so results can be recomputed against either
  publisher and the spread reported.
- **Secondary cost of merging:** it removes the redundancy that made a within-city timing
  check possible. Bishkek and Ashgabat were checked *before* merging (minima agreed within
  1 h: 6 vs 7 and 3 vs 4) and the evidence is preserved in `merge_report.md`, but the check
  cannot be repeated post-merge.

### D-009 — Temporal test block = 2024
- **Date:** 2026-07-29
- **Decision:** the held-out temporal block is calendar year 2024.
- **Reason:** user decision. It is the last full year with reference-grade coverage before
  the US embassy programme ended on 2025-03-04 (risk R9).
- **Wording corrected 2026-08-15.** What ended on 2025-03-04 was the **StateAir publication
  channel**, not the monitoring programme as a whole. A live query that day found Ashgabat
  republished through AirNow to 2025-09-24, Almaty to 2025-11-14 and Dushanbe still
  reporting. The decision stands unchanged — the "alternative considered" below already
  reflected the true post-shutdown coverage — but "the programme ended" overstated it.
- **Effect on n:** all 8 stations and all 6 cities have 2024 data; per-station completeness
  in 2024 ranges **0.722 – 0.946**.
- **Alternative considered:** a post-shutdown block (2025–2026). Rejected — only Dushanbe
  (AirNow) and the two Khujand low-cost sensors report meaningfully after the shutdown, so
  the held-out block would cover 2 cities instead of 6 and could not support leave-city-out.
- **Direction of bias if wrong:** testing on 2024 means the benchmark cannot demonstrate
  performance on *current* data, and any deployment claim for ECO Pulse is extrapolation
  beyond the evaluated period. That constraint is external and permanent — the reference
  network no longer exists.

### D-010 — MAIAC AOD extracted; informative missingness QUANTIFIED
- **Date:** 2026-07-30
- **Decision:** extract daily MAIAC AOD (MCD19A2.061, band `Optical_Depth_055`) for all 8
  benchmark stations over 2018-11-27..2024-12-31, retaining every station-day including
  days with no retrieval.
- **Effect on n:** **17,816 / 17,816 station-days returned** (exact match), 0 failed and 0
  incomplete chunks. **6,148 rows (34.5%) have null AOD and are RETAINED.**
- **Reason:** risk R7. Dropping null-AOD rows is the standard convenience and it is not
  safe here. Measured against ground-truth PM2.5:

  | | days WITH AOD | days WITHOUT |
  |---|---:|---:|
  | n | 7,116 | 3,875 |
  | median PM2.5 | 25.4 | **30.7** |
  | mean PM2.5 | 34.2 | **47.1** |

  Mann-Whitney **p = 1.4e-35**. **On the top PM2.5 decile (>=81 ug/m3) retrieval is only
  45.2%, against 64.7% overall** -- the satellite goes blind on the days that matter most
  for health. Dropping nulls would remove 34.5% of station-days and preferentially remove
  the extreme tail the benchmark exists to evaluate.
- **Mechanism is identifiable, not assumed:** retrieval swings 34.2% (January) to 93.7%
  (July), and 5 of 6 cities show dirtier missing days. **Ashgabat is the exception (-1.2
  ug/m3) and has the HIGHEST retrieval (72%)** -- if bright-desert failure dominated,
  the desert station would be worst, not best. So the dominant mechanism is **winter cloud
  and snow, coinciding with the coal-heating peak**, not the bright-surface problem the
  MAIAC literature emphasises. Retrieval by city: Almaty 53.6%, Bishkek 57.2%,
  Dushanbe 67.4%, Tashkent 68.5%, Khujand 68.9%, Ashgabat 72.0%.
- **Alternative considered:** gap-filling AOD by interpolation. Rejected for now --
  interpolating across a systematically-missing extreme tail invents the values that
  matter most. `maiac_valid_pixel_fraction` is carried as a feature instead so the model
  can condition on retrieval quality.
- **Direction of bias if wrong:** if missingness were in fact random, retaining nulls
  costs only statistical power. The measured association means the opposite error --
  dropping them -- would inflate every satellite result while making the benchmark blind
  to exactly the episodes it should evaluate.
- **Extraction note:** `MCD19A2_GRANULES` yields **68-220 granules per day** over a single
  point (Terra+Aqua, per-tile per-orbit). Granules are composited to one image per day
  **inside Earth Engine** before reduction. The generic extractor's element budget
  (`stations x days`) understated the true count by ~80x and would have declared an
  over-ceiling request safe. Compositing also avoids weighting each day by how many orbits
  happened to cover it.

### D-011 — Q5c: duplicate detection by value identity, not distance
- **Date:** 2026-08-13
- **Decision:** add a pre-registered rule `Q5c` that flags any station pair whose overlapping
  observations are **bit-identical on more than 50% of samples**, regardless of separation.
- **Reason:** Q5b keys on distance (150 m) and therefore catches only the republication case
  where the two records agree on position. It cannot see the inverse — one instrument
  published twice under coordinates that *disagree* — which is what happened in Dushanbe
  (see D-012). Two independent instruments never agree to floating point on any appreciable
  share of samples, so value identity is the invariant that actually holds.
- **Threshold, set from measurement rather than tuned:**

  | pair | resolution | exact-match rate |
  |---|---|---:|
  | Dushanbe 8684/9769 (true duplicate) | hourly | **94.0%** |
  | Khujand 1894632/1924313 (true distinct) | hourly | 0.3% |
  | unrelated station pairs (coincidence floor) | hourly | 2.6% |

  Hourly PM2.5 is frequently reported as rounded integers, so unrelated stations do collide
  on a small share of hours — measured at 2.6%. Daily means (averages of ~24 floats)
  essentially never collide, and the same pairs show 0.0% at daily resolution. **50% sits in
  the middle of the 36x gap between coincidence and duplication and is safe at either
  resolution.** An earlier draft used 2%, which was calibrated on daily data and produced
  two false positives on hourly data; the failure is recorded here rather than quietly fixed.
- **Effect on n:** one new pair detected (Dushanbe). See D-012.
- **Direction of bias if wrong:** too low a threshold merges genuinely distinct stations,
  shrinking the benchmark and destroying real spatial signal. Too high leaves a duplicate in
  place, which is the error this rule exists to prevent. The measured 36x margin means the
  choice is not delicate.
- **Enforced by:** `tests/test_qc_rules.py::TestQ5DuplicateStations` (3 cases, including the
  Khujand negative control).

### D-012 — Dushanbe 8684/9769 merged as one instrument; benchmark v1.1.0
- **Date:** 2026-08-13
- **Decision:** merge Dushanbe `8684` (AirNow) and `9769` (StateAir) into a single station
  under the **D-008 rule — precedence and gap-fill, never averaging**. Primary is `8684`
  (49,305 observations vs 36,243). Benchmark version **1.0.0 → 1.1.0**.
- **Reason:** they are one US-embassy monitor republished by two programmes — the identical
  defect D-003 caught in Bishkek (57 m) and Ashgabat (40 m). It was missed here because the
  two records carry coordinates **6.06 km apart**, so the distance rule passed them. Evidence
  over the 33,462 overlapping hours (2019-10-28 → 2025-03-04):

  - **31,458 hours (94.01%) are bit-identical**;
  - of the remaining 2,004, **2,001 (99.9%) satisfy `9769(t) == 8684(t+5)`** — Dushanbe is
    UTC+5, so these are the same readings stamped in local time instead of UTC;
  - **99.99% of all overlapping hours are therefore the same measurement**;
  - the Khujand control pair, 14.4 km apart, is bit-identical on 0.3% of hours.

  `data/interim/station_census.csv` confirms the provenance directly: `9769` is
  "StateAir Dushanbe / US Diplomatic Post: Dushanbe", `8684` is "AirNow / Dushanbe".
- **A prior claim this retracts.** D-003 justified the 150 m radius by citing this very pair
  as its safety margin ("the two real Dushanbe sites are 6.06 km apart, ~40x the threshold"),
  and `tests/test_qc_rules.py` encoded that belief in a test asserting they were "genuinely
  distinct" — whose own fixture named the two providers as StateAir and AirNow. **The
  negative control was a positive case.** The threshold was validated against the case it
  was missing. The test has been corrected and now documents this.
- **Effect on n:** stations **8 → 7**; merged Dushanbe holds **52,086** observations
  (49,305 primary + 2,781 gap-filled from the secondary — the merge retains more data than
  either feed alone). Cities unchanged at 6. **Leave-station-out loses its two Dushanbe
  folds**, leaving Khujand's two.
- **Alternative considered:** dropping `9769` outright. Rejected — it discards 2,781 hours
  the primary does not cover, and it would be a second, inconsistent rule for the same defect
  D-008 already resolved by merging. Averaging was rejected for D-008's original reason:
  averaging two copies of one measurement reduces no noise and, where the copies disagree,
  fabricates a third value no device produced.
- **Direction of bias if wrong:** if the two records were genuinely distinct instruments,
  merging destroys real within-city spatial variation and removes a leave-station-out fold.
  The 99.99% identity makes this implausible, and per-hour provenance is retained in
  `panel_sources.parquet` so the merge can be undone analytically.
- **Second defect surfaced by the same evidence — a 2023 timezone break.** The +5 h offset
  hours are not spread evenly: 2020 shows 1 misaligned hour in 6,813, while **2023 shows
  2,003 in 4,797 (41.8%)**. D-006's timezone check reported "Dushanbe x2 ... agreed at
  lag +0 h, r = 0.99-1.00" — it was comparing a station against itself, and its diurnal
  composite averaged over all years, diluting a 41.8% single-year break until it vanished.
  The merge resolves the practical consequence (one series now, primary-precedence), but the
  underlying lesson stands: **within-city timing agreement is not evidence of correctness
  when the two series may be the same instrument.**
