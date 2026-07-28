# Paper Claim

> **STATUS: PROVISIONAL — Phase 0 gated.**
> This claim was written before the literature review completed, as an anchor against
> drift. It is falsifiable. Section 3 lists the specific findings that would force it to
> change. Do not treat it as settled until `research/GAP.md` exists and this banner is
> removed.

---

## 1. The claim sentence

> **We introduce the first open, station-level air quality benchmark for Central Asia
> with pre-registered spatial (leave-city-out) and blocked-temporal splits, and use it to
> characterise how well PM2.5 estimation and short-horizon forecasting transfer into
> cities that contribute no training labels.**

That is the whole claim. Everything in the paper either supports it or is cut.

## 2. What this claim deliberately does NOT say

Each of these is a stronger claim that the evidence will probably not support. They are
listed so that no one — including future me — quietly upgrades the claim mid-project.

| Tempting claim | Why it is not made |
|---|---|
| "First PM2.5 estimates for Central Asia" | Almost certainly false. Global gridded products (ACAG / van Donkelaar–Hammer; GBD exposure surfaces) already cover the region, and a dust/aerosol literature exists around the Aral Sea. |
| "State of the art on PM2.5 estimation" | Cannot be claimed without like-for-like comparison on identical splits. No such comparison will exist for a benchmark we are creating. |
| "Deep/graph models beat gradient boosting" | Unknown, and quite possibly false at this data volume. If LightGBM wins, that is the reported result. |
| "Accurate air quality prediction for Central Asia" | "Accurate" is unfalsifiable. The paper reports errors against a baseline ladder, per regime. |
| "Our method generalises to data-sparse regions" | We test five countries. Generalisation beyond the tested domain is not evidenced. |

## 3. Falsifiers — findings that force this claim to change

Phase 0 must actively look for each. If any is found, the claim is rewritten **before**
any modelling begins, and the change is logged in this file with a date.

- **F1.** An existing open, station-level Central Asia AQ benchmark with published splits
  → the word "first" is deleted and the contribution becomes a *comparison against* it.
- **F2.** A published leave-city-out PM2.5 transfer evaluation covering these countries
  → C2 is repositioned as a replication/extension, not a novel protocol.
- **F3.** Ground-truth station coverage too thin to support leave-city-out at all
  (fewer than ~4 cities with usable multi-year records) → the spatial protocol collapses
  to leave-station-out and the claim narrows to forecasting only.
- **F4.** Russian-language or regional-journal literature already establishing the
  benchmark → claim narrows to the open/reproducible aspect, with explicit credit.

## 4. Claim-to-evidence map

Each clause must be discharged by a named artifact. If an artifact does not exist, the
clause comes out of the sentence.

| Clause | Discharged by |
|---|---|
| "open, station-level benchmark" | `benchmark/splits/*.json` + `splits.sha256`, `data/MANIFEST.md`, `benchmark/README.md` |
| "pre-registered splits" | Splits committed, hashed, and hash-tested *before* first model run (`tests/test_splits_immutable.py`) |
| "leave-city-out" | Per-held-out-city results, 5 seeds, mean ± std |
| "blocked-temporal" | Purge gap ≥ max lag + max horizon, enforced by `tests/test_purge_gap.py` |
| "characterise how well ... transfer" | Baseline ladder + ablations + per-regime error decomposition |
| "cities that contribute no training labels" | Zero-label leave-city-out, plus k ∈ {0, 10, 100} local-label curve |

## 5. Amendment log

| Date | Change | Trigger |
|---|---|---|
| 2026-07-28 | Initial provisional claim written. | Project start, pre-Phase-0. |
