# STATUS

Last updated: 2026-07-28

## Current phase

**Phase 0 — adversarial literature review.** In progress.

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
| 0 — Literature review | **in progress** | `research/LITERATURE.md`, `research/GAP.md` |
| 1 — Data (ground truth only) | not started | `data/MANIFEST.md`, `data/DECISIONS.md` |
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
