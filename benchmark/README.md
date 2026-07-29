# ECO Pulse CA Benchmark v1.0.0

An open, station-level PM2.5 benchmark for Central Asia with **frozen** spatial and
temporal splits.

**8 stations · 6 cities · 280,537 hourly observations · test year 2024**

---

## Verify before you use it

```bash
cd benchmark/splits && sha256sum -c splits.sha256
```

Expect `splits.json: OK`. If it fails, the splits have been modified and any result
computed against them is not comparable to published numbers.

## The splits are immutable

`tests/test_splits_immutable.py` compares a fresh build against the committed hash and
fails on any difference — **including changes made by the benchmark's own authors.**

The failure this guards against is not malice. It is the reasonable-looking decision to
adjust a split after seeing results, one justified step at a time. If a city turns out to
have poor satellite coverage, that is **reported as a property of the benchmark**, never
fixed by re-freezing.

To amend the splits legitimately: bump `BENCHMARK_VERSION`, record why in
`data/DECISIONS.md`, regenerate the hash, and **re-run every published number**. Old
results are not comparable to new splits. This is deliberately harder than editing JSON.

---

## Temporal blocks

| Block | From | To |
|---|---|---|
| `train` | 2018-11-27T22:00Z | 2022-12-31T23:00Z |
| `purge_train_val` | 2023-01-01T00:00Z | 2023-01-10T23:00Z |
| `val` | 2023-01-11T00:00Z | 2023-12-21T23:00Z |
| `purge_val_test` | 2023-12-22T00:00Z | 2023-12-31T23:00Z |
| **`test`** | **2024-01-01T00:00Z** | **2024-12-31T23:00Z** |
| `reserved_post_test` | 2025-01-01T00:00Z | 2026-07-28T18:00Z |

**The purge gap is derived, not chosen.** A training sample at `t` reads features from
`[t − max_lag, t]` and predicts `t + h`, so

```
purge ≥ max_lag + max_horizon = 168 + 72 = 240 hours
```

168 h is the longest feature window on the ladder (`SameHourMean(n_days=7)`); 72 h is the
longest horizon. `tests/test_purge_gap.py` recomputes this from the model definitions, so
adding a model with a longer window fails the build rather than silently leaking.

**Why 2024 is the test block.** It is the last full year with reference-grade coverage: the
US State Department ended its global embassy air quality programme on **2025-03-04**, and
six of this benchmark's stations stop on exactly that date.

**Why post-2024 data is reserved and unused.** Only four stations report afterwards. It
cannot train (lookahead relative to the 2024 test block) and cannot test (coverage would be
uneven across cities). It is labelled and excluded rather than quietly dropped.

## Spatial splits

**Leave-city-out — 6 folds.** Each fold holds out one city entirely; the held-out city
contributes no training station. This is the headline protocol.

| Fold | Held out | Training cities |
|---:|---|---:|
| 0 | Almaty | 5 |
| 1 | Ashgabat | 5 |
| 2 | Bishkek | 5 |
| 3 | Dushanbe | 5 |
| 4 | Khujand | 5 |
| 5 | Tashkent | 5 |

**Leave-station-out — 4 folds, covering 2 of 6 cities.** Only Dushanbe and Khujand hold two
instruments. Almaty, Ashgabat, Bishkek and Tashkent hold one each and are listed in
`ineligible_cities` — a stated coverage gap, not an unexplained absence.

**Combined (headline).** Leave-city-out folds evaluated only on the test block: unseen city
× unseen period.

---

## Known limitations — read before reporting numbers

1. **Bishkek's 2024 ground truth is publisher-dependent.** Bishkek is a merge of two feeds
   of one physical instrument (57 m apart), published by StateAir and AirNow. They are
   identical through 2020 and then diverge; **in 2024 — the test block — they agree on only
   11.1% of overlapping hours, with p95 disagreement 33.6 µg/m³ and a maximum of 479.** The
   p95 alone exceeds twice the WHO 2021 24-hour guideline of 15 µg/m³. Per-hour provenance
   is retained in `data/interim/panel_sources.parquet` so results can be recomputed against
   either publisher and the spread reported. Ashgabat's merge is clean (99.5% identical).

2. **Timezone correctness is unverifiable at four cities.** The Q6 within-city check needs
   two instruments. It genuinely validated Dushanbe and Khujand (lag +0 h, r = 0.99–1.00).
   A constant, lifelong offset at **Almaty, Tashkent, Bishkek or Ashgabat** would not be
   detected by anything in this suite.

3. **Three diurnal regimes, not one.** Dushanbe, Khujand and Tashkent are dilution-driven
   (afternoon minimum, 14–16 local). Bishkek and Ashgabat are evening-source-driven
   (pre-dawn minimum, 20:00 maximum) — the signature of residential coal heating decaying
   overnight. **Almaty fits neither**: pre-dawn minimum but a 13:00 *maximum*. Error
   analysis should treat these separately; a single regional model assumption is wrong here.

4. **Kazakhstan contributes one city.** Astana was rejected by pre-registered rule Q7 —
   6.60-year span but 42.8% completeness against a 60% floor. The benchmark therefore
   under-represents severe continental winter inversions.

5. **No results here can speak to current conditions.** The reference network no longer
   exists. Any deployment claim is extrapolation beyond the evaluated period.

## Reproducing from the manifest

`data/MANIFEST.md` records every source with access dates and checksums; `data/DECISIONS.md`
records every filtering decision with its effect on *n* and the direction of bias if wrong.
Rebuild with:

```bash
python -m ecopulse_ca.ingest.openaq --out data/interim/station_census.csv
python scripts/pull_panel.py
python scripts/build_benchmark_panel.py
python -m ecopulse_ca.splits.builder --freeze
```

The final command must reproduce the same `sha256`. If it does not, something upstream has
changed — investigate before proceeding.
