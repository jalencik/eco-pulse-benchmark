# STATUS

Last updated: 2026-07-28

## Current phase

**Phase 0 — adversarial literature review. COMPLETE (first pass).** Gate G0 passed: the gap
is real. See `research/GAP.md`.

Outcome: F1 and F2 did not trigger — no open station-level Central Asia PM2.5 benchmark
exists, and no leave-city-out transfer evaluation covers these countries. Two intended
framings were found to be already claimed and have been struck from `PAPER_CLAIM.md`.
**F3 is unresolved and is the live threat to the headline result.**

Phase 0 debt — **largely closed 2026-07-30** (`scripts/fetch_literature.py`):
- **Source count target met.** 30 distinct sources, **16 at FULL depth** against a 15–25
  target; 24 carry an authoritative DOI. The publisher 403s were routed around via
  Crossref / OpenAlex / Semantic Scholar / Europe PMC rather than defeated.
- **A2's attribution in `LITERATURE.md` was wrong** — recorded as "Kulkarni et al. (?)",
  the paper is Tursumbayeva, Muratuly, Baimatova & Karaca (*Atmos. Env.* 2023). Corrected.
- **Every method the code implements now cites its originating source** (Newey–West 1987,
  Harvey–Leybourne–Newbold 1997, Diebold–Mariano, Roberts et al. 2016, Inness et al. 2019,
  Lundberg & Lee 2017, Ke et al. 2017).
- **Still open — A9 (Tashkent ML) is not indexed in any of the four APIs.** It is an ECAS
  2025 Sciforum conference abstract. Its split protocol remains unknown and Section 1 must
  not assert what that paper did.
- **Still open — Russian-language search.** CyberLeninka / eLIBRARY.RU are not covered by
  these APIs, so the F4 verdict stays provisional.
- A2/A4/B2 full text remains paywalled: their *citations* are verified, their *content*
  claims are not. `tests/test_literature_integrity.py` enforces the distinction.

**Next: Phase 1, beginning with the station census** — because F3 determines whether the
leave-city-out headline setting exists at all, and it is cheap to settle.

## Increment scope

`benchmark v1.0.0` = contribution **C1 only** (open benchmark + credential-free baseline
ladder). C2 (transfer methods) and C3 (deployment) are deliberately out of scope for this
increment and will be re-specced once C1 is frozen. Rationale: C2 is unevaluable until the
benchmark it is measured on exists.

---

## Stopping criteria

These are the project-level criteria from the master spec. **None may be checked
optimistically.** A box is checked only when a named artifact exists in the repo and the
test suite passes.

- [x] **All tests in `tests/` pass** — 211 passing, ruff clean, including leakage, split-integrity, purge-gap and immutability. *(Feature-availability test still pending: no non-operational features exist yet, so it has nothing to guard.)*
- [ ] Leave-city-out results for every held-out Central Asian city, 5 seeds, std reported
- [ ] Model beats persistence, climatology, raw CAMS with Diebold–Mariano p < 0.05 — **or** the failure is documented and explained
- [ ] Prediction-interval empirical coverage within 3 pp of nominal on held-out cities
- [ ] Ablation table isolating each feature family
- [ ] Error analysis: dust storms, winter inversions, Ramadan/Navruz, low-concentration regime, high tail
- [ ] `make reproduce` runs end to end from a clean checkout
- [ ] Inference API serves in < 200 ms with point estimate + interval
- [ ] `paper/` figures and tables regenerated from code, not hand-edited

### Blocked criteria and why

Recorded here so that "not done" is never confused with "forgotten".

| Criterion | Blocked on | Unblocks when |
|---|---|---|
| Beat **raw CAMS** | CAMS requires a Copernicus ADS account + licence acceptance | User registers (see `REGISTRATION.md`) |
| Prediction-interval coverage | Needs a fitted probabilistic model; conformal layer is increment 2 | C1 frozen |
| Ablation over feature families | Satellite/met feature families do not exist yet by design | Predictors phase |
| Dust-storm / inversion error analysis | Requires met + aerosol-index predictors | Predictors phase |
| Inference API < 200 ms | C3, out of increment-1 scope | C1 + C2 complete |

---

## Phase log

| Phase | State | Artifact |
|---|---|---|
| 0 — Literature review | **complete (1st pass), G0 passed** | `research/LITERATURE.md`, `research/GAP.md` |
| 1a — Ingestion + QC (fixtures) | **complete — 82 tests pass, no credentials needed** | `src/ecopulse_ca/{ingest,qc}`, `tests/` |
| 1b — Live census | **complete — F3 RESOLVED, 7 cities, leave-city-out is viable** | `data/MANIFEST.md`, `data/DECISIONS.md`, `data/interim/station_census.csv` |
| 1c — Measurement ingestion + QC on real series | **complete — 10 feeds / 8 instruments / 6 cities** | `data/interim/panel.parquet`, `panel_provenance.csv`, `qc_findings.csv` |
| 2 — Benchmark construction | **COMPLETE — splits frozen, gate G2 passed** | `benchmark/splits/` (sha256 `544a044c…`), `benchmark/README.md` |
| 3 — Credential-free baseline ladder | **next** | `paper/tables/` |
| 2 — Benchmark construction | not started | `benchmark/splits/`, `benchmark/README.md` |
| 3 — Credential-free baseline ladder | not started | `paper/tables/` |
| 4 — Predictors + full ladder | deferred to increment 2 | — |
| 5 — Interrogation | deferred | — |
| 6 — Deployment | deferred | — |
| 7 — Paper artifacts | deferred | — |

## Open decisions awaiting the user

| # | Decision | Where | Current default |
|---|---|---|---|
| D1 | **Flatline policy** — mask the stuck window, reject the whole station, or keep-and-flag. Rejecting stations preferentially removes low-cost sensors, which in this region means removing whole cities, which tightens F3. | `apply_flatline_policy` in `src/ecopulse_ca/qc/pipeline.py` | `MASK_WINDOW` — least destructive option that still removes values known to be wrong. The other two branches raise `NotImplementedError` rather than silently doing something. |

## Open risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Novelty gap thinner than assumed | Phase 0 falsifiers F1–F4 in `PAPER_CLAIM.md`; stop and report if triggered |
| R2 | Too few stations for leave-city-out | Falsifier F3; protocol degrades to leave-station-out, claim narrows |
| R3 | Kazakhstan UTC offset changed mid-record (~Mar 2024) | Timezone QC validates against diurnal shape, not metadata — see `data/DECISIONS.md` |
| R4 | Frozen splits include cities with poor later satellite coverage | Coverage reported as a benchmark property; splits are **never** re-frozen (`tests/test_splits_immutable.py`) |
| R5 | 14 GB free disk on dev machine | Server-side reduction only; no raster ever lands on disk |
| R6 | **Kazakhstan shares AQ data only inside its borders** — a benchmark a third party cannot reconstruct is not open | Kazakh stations enter only via an independently retrievable path (OpenAQ mirror / US Embassy); per-station provenance recorded in `MANIFEST.md` |
| R7 | **MAIAC missingness is correlated with the target** — retrievals fail during dust storms, snow and heavy cloud, i.e. exactly the extreme-PM2.5 episodes | Missingness modelled as an informative feature and reported as an error-analysis stratum. **Never drop missing-AOD rows** — doing so conditions on "retrieval succeeded" and biases results toward calm, clear, low-concentration days |
| R8 | Turkmenistan has no national monitoring; Ashgabat can enter only via the US Embassy monitor | Recorded as a benchmark coverage property, not worked around |
| **R9** | **The US State Department terminated its global embassy air quality programme in March 2025 (funding).** 6 of 9 reference monitors stop at exactly 2025-03-04. The benchmark's designated spine is now a historical archive, not a live feed. | The temporal test block cannot be "the most recent full year" for reference-grade data — the last full year with embassy coverage is **2024**. Forces an explicit split design decision in Phase 2. Some AirNow feeds run later (Almaty→2025-11, Ashgabat→2025-09, Dushanbe→2026-07); **cause unverified** — partial resumption or a different pipeline. |
| ~~R10~~ **CLOSED** | 306 of 317 stations excluded for <2 y span are AirGradient/Clarity low-cost units, median span 0.59 y. If `datetimeFirst` reflected OpenAQ ingestion rather than deployment, true spans would be longer and the benchmark smaller than necessary. | **Verified empirically, not against documentation** (`scripts/verify_r10.py`). 60 excluded stations, stratified across both providers, were queried for measurements in the 3 years *before* their reported start: **0 of 60 returned any**. A positive control on an eligible station returned 144 hours from a known-good 7-day window, so the probe demonstrably detects data when data exists. `datetimeFirst` reflects the archive's true start; the exclusions stand and the eligible pool is not artificially small. Banked in `paper/tables/t2_04_r10_span_provenance.csv`. **Scope:** this closes R10 for the archive we can use — a sensor whose earlier history never reached OpenAQ yields no recoverable benchmark row either way. |
