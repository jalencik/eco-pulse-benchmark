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

*(none yet — Phase 1 not started)*
