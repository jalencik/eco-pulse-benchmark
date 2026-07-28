# PLAN

Living document. Updated as phases complete. Progress state lives in `STATUS.md`; this
file holds the *intent* and the *gates*.

## Scope of the current increment

`benchmark v1.0.0` — contribution **C1 only**: an open station-level Central Asia air
quality benchmark with pre-registered splits, plus the baseline ladder rungs that require
no external credentials.

C2 (transfer methods) and C3 (deployment) are deferred by design. C2 cannot be evaluated
before the benchmark it is measured against exists; building them together risks
invalidating every transfer result if a split definition changes late.

## Ordering principle

Each phase ends at a **gate**. A gate is a condition that must hold before the next phase
starts. Gates exist to make one specific failure impossible: discovering a design flaw
after enough work has accumulated that fixing it honestly becomes expensive.

---

## Phase 0 — Adversarial literature review

**Goal:** determine whether the claimed gap is real, before any engineering.

Deliverables:
- `research/LITERATURE.md` — 15–25 papers, each with task definition, data, **split
  protocol**, baselines, headline metric, stated limitations.
- `research/GAP.md` — one page, brutally honest, on what is actually new.

Specific questions:
1. Recent PM2.5 estimation/forecasting with satellite + ML; spatial transfer; low-data regions.
2. What exists **specifically for Central Asia** — searched in English *and Russian*.
3. Which split protocols the strongest papers use; which papers have known leakage.
4. State of the art on MAIAC AOD → surface PM2.5, and its documented failure modes over
   bright desert surfaces. Critical here: much of the study region is exactly that surface.
5. Which journals published the closest work, and what their papers contain that a generic
   ML paper does not.

**Gate G0:** `GAP.md` concludes the gap is real, **or** the project stops and reports.
Falsifiers F1–F4 in `PAPER_CLAIM.md` are checked explicitly. If any fires, the claim is
rewritten before Phase 1 begins.

---

## Phase 1 — Ground truth

**Goal:** a trustworthy PM2.5 record. Not a large one — a trustworthy one.

- OpenAQ v3 ingestion for UZ/KZ/KG/TJ/TM + a data-rich training pool.
- US Embassy reference monitors: Tashkent, Astana, Almaty, Bishkek, Dushanbe.
- Document what, if anything, is retrievable from Uzhydromet / Kazhydromet.
- QC per pre-registered rules Q1–Q7 in `data/DECISIONS.md`.
- Complete `data/MANIFEST.md` rows with checksums and access dates. Write the data card.

**Interrogate before trusting.** Flatlines, stuck values, unit confusion, duplicated
station IDs, and timezone correctness validated against diurnal shape rather than
metadata. Kazakhstan's suspected mid-record UTC offset change is checked explicitly.

**Gate G1:** every station entering the benchmark has a QC verdict with a logged n-effect,
and no station is dropped without an entry in `data/DECISIONS.md`.

---

## Phase 2 — Benchmark construction

**Goal:** freeze the splits as a committed, hashed artifact — before any model exists.

- **Temporal:** train on earlier years, validate on a middle block, test on the most recent
  full year, with a purge gap ≥ (max lag + max horizon) at every boundary.
- **Spatial:** leave-city-out across Central Asian cities; leave-station-out within cities.
- **Combined:** unseen city × unseen period. This is the headline setting.
- `benchmark/README.md` reproduces the exact splits from the manifest for a third party.

**Gate G2:** `benchmark/splits/splits.sha256` is committed and
`tests/test_splits_immutable.py` passes. From this point the splits are immutable. If later
predictor coverage is poor for some frozen city, that is **reported as a property of the
benchmark**, never fixed by re-freezing. Split-shopping is the failure mode this gate
exists to prevent.

---

## Phase 3 — Credential-free baseline ladder

Two tasks, scored separately, never mixed in one table.

**Task F — forecasting.** At monitored station `s`, given data to `t`, predict PM2.5 at
`t+24/48/72 h`. Ladder: persistence → diurnal persistence (`y_{t-24}`) → station×hour×month
climatology (train-fold only) → ridge → LightGBM, on lagged targets and temporal encodings.

**Task N — nowcasting.** Estimate PM2.5 at station `s` in a held-out city with **zero**
local training labels. Ladder: nearest-monitor → IDW over k neighbours → ordinary kriging.

These spatial-interpolation rungs are the ones reviewers use to attack satellite models —
*does it beat interpolating from nearby monitors?* — and they are frequently omitted.
Establishing them now means every later model is born with its hardest comparison in place.

Reporting rules: 5 seeds, mean ± std. Deterministic baselines have zero seed variance **by
construction** — that is stated, not disguised as a spread. Diebold–Mariano for forecast
comparisons. Exceedance F1 against the WHO 2021 24-hour guideline (15 µg/m³) alongside
RMSE/MAE/R².

**Gate G3:** every reported number traces to a `run_id` + git SHA + config hash in the run
log, and the test suite passes.

---

## Phase 4+ — Deferred to increment 2

Predictor acquisition (blocked on registrations), the full model ladder, transfer methods,
conformal intervals, interrogation, deployment, paper artifacts. Re-specced once C1 freezes.

---

## Standing rules

Encoded as tests, not intentions:

| Rule | Test |
|---|---|
| No random splits, ever | `test_no_random_splits.py` |
| Splits immutable once frozen | `test_splits_immutable.py` |
| Purge gap ≥ max lag + horizon | `test_purge_gap.py` |
| No same-timestamp target leakage | `test_no_target_leakage.py` |
| No non-operational features in deployed numbers | `test_feature_availability.py` |
| Timezones validated against diurnal shape | `test_timezone_diurnal.py` |
| Every number traceable to a run | `test_run_traceability.py` |
| Makefile and Windows shim do not drift | `test_makefile_shim_parity.py` |

Stop and ask when: the gap looks weak, a design decision changes the paper's claim,
results look suspiciously good (assume leakage first), account access or money is needed,
or the same failure persists past ~30 minutes.
