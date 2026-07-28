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
  spans are longer and the benchmark is smaller than it needs to be. **Unverified.**

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
  per-city or per-climate-zone check before splits are frozen.
