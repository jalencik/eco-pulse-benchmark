# STATUS

Last updated: 2026-07-28

## Current phase

**Phase 0 — adversarial literature review. COMPLETE (first pass).** Gate G0 passed: the gap
is real. See `research/GAP.md`.

Outcome: F1 and F2 did not trigger — no open station-level Central Asia PM2.5 benchmark
exists, and no leave-city-out transfer evaluation covers these countries. Two intended
framings were found to be already claimed and have been struck from `PAPER_CLAIM.md`.
**F3 is unresolved and is the live threat to the headline result.**

Phase 0 debt (does not block Phase 1, must close before submission):
- 4 sources at FULL depth; the master spec asks 15–25 with full extraction. Four key
  papers returned HTTP 403 from ScienceDirect and need institutional access.
- Russian-language search covered general web only; CyberLeninka / eLIBRARY.RU outstanding,
  so the F4 verdict stays provisional.

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

- [ ] All tests in `tests/` pass, including leakage, split-integrity, feature-availability
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
| 1 — Data (ground truth only) | **next — starts with station census** | `data/MANIFEST.md`, `data/DECISIONS.md` |
| 2 — Benchmark construction | not started | `benchmark/splits/`, `benchmark/README.md` |
| 3 — Credential-free baseline ladder | not started | `paper/tables/` |
| 4 — Predictors + full ladder | deferred to increment 2 | — |
| 5 — Interrogation | deferred | — |
| 6 — Deployment | deferred | — |
| 7 — Paper artifacts | deferred | — |

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
