# ECO Pulse CA Benchmark v1.1.0

An open, station-level PM2.5 benchmark for Central Asia with **frozen** spatial and temporal
splits.

**7 instruments · 6 cities · 247,075 retained hourly observations · test year 2024**

Five of the instruments are US diplomatic-post reference monitors, and two are Clarity
low-cost sensors in Khujand.

---

## Verify before you use it

```bash
cd benchmark/splits && sha256sum -c splits.sha256
```

You should get `splits.json: OK`. If it fails then the splits have been modified, and any
result computed against them is not comparable to the published numbers.

## The splits are immutable

`tests/test_splits_immutable.py` builds the splits fresh, compares against the committed
hash, and fails on any difference. That includes differences made by us.

The failure this guards against is not somebody cheating. It is the reasonable-looking
decision to adjust a split after seeing the results, one justified step at a time. If a city
turns out to have poor satellite coverage, that gets **reported as a property of the
benchmark** rather than fixed by re-freezing.

To amend the splits legitimately: bump `BENCHMARK_VERSION`, record why in
`data/DECISIONS.md`, regenerate the hash, and **re-run every published number**. Old results
are not comparable to new splits. This is deliberately more annoying than editing a JSON
file, and it is supposed to be.

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

168 h is the longest feature window on the ladder (`SameHourMean(n_days=7)`) and 72 h is the
longest horizon. `tests/test_purge_gap.py` recomputes this from the model definitions, so if
somebody adds a model with a longer window the build fails instead of leaking quietly.

**Why 2024 is the test block.** It is the last full year with reference-grade coverage. The
US State Department closed its StateAir publication channel on **2025-03-04**. Five of the
ten contributing source feeds stop on that date, and after co-published feeds are merged,
2 of the 7 benchmark stations (`8881` and Bishkek) end there. The rest survive through a
longer-lived feed.

**Why post-2024 data is reserved and unused.** Coverage after the shutdown is uneven across
cities, so it cannot test, and it sits after the 2024 test block, so it cannot train either
without lookahead. It is labelled and excluded rather than quietly dropped.

## Spatial splits

**Leave-city-out, 6 folds.** Each fold holds out one city completely, and the held-out city
contributes no training station. This is the headline protocol.

| Fold | Held out | Training cities |
|---:|---|---:|
| 0 | Almaty | 5 |
| 1 | Ashgabat | 5 |
| 2 | Bishkek | 5 |
| 3 | Dushanbe | 5 |
| 4 | Khujand | 5 |
| 5 | Tashkent | 5 |

**Leave-station-out, 2 folds, covering 1 of the 6 cities.** Only Khujand holds two genuinely
distinct instruments. Almaty, Ashgabat, Bishkek, Dushanbe and Tashkent hold one each and are
listed in `ineligible_cities`, which is a stated coverage gap rather than an unexplained
absence. Dushanbe used to be in this protocol with two folds of its own, until D-012
established that its two records were one embassy monitor published twice.

**Combined (headline).** Leave-city-out folds evaluated only on the test block, so an unseen
city in an unseen period.

---

## Known limitations, read these before reporting numbers

1. **Bishkek's 2024 ground truth depends on who published it.** Bishkek is a merge of two
   feeds of one physical instrument, 57 m apart, published by StateAir and by AirNow. They
   are identical through 2020 and then they diverge. **In 2024, which is the test block, they
   agree on only 11.1% of overlapping hours, with p95 disagreement 33.6 µg/m³ and a maximum
   of 479.** The p95 on its own is more than twice the WHO 2021 24-hour guideline of
   15 µg/m³. Per-hour provenance is kept in `data/interim/panel_sources.parquet` so results
   can be recomputed against either publisher and the spread reported. Ashgabat's merge is
   clean by comparison, 99.5% identical.

2. **Timezone correctness is unverifiable at five of the six cities.** The within-city check
   needs two instruments in one city, and after the Dushanbe merge only Khujand has that. So
   a constant, lifelong offset at **Almaty, Tashkent, Bishkek, Ashgabat or Dushanbe** would
   not be caught by anything in this suite. This is the benchmark's largest unaudited
   assumption and I would rather say it plainly than bury it.

3. **Three diurnal regimes, not one.** Dushanbe, Khujand and Tashkent are dilution-driven,
   with an afternoon minimum around 14 to 16 local. Bishkek and Ashgabat are
   evening-source-driven, with a pre-dawn minimum and a 20:00 maximum, which is the signature
   of residential coal heating decaying overnight. **Almaty fits neither**, it has a pre-dawn
   minimum but a 13:00 *maximum*. Error analysis should treat these separately. A single
   regional model assumption is wrong here.

4. **Kazakhstan contributes one city.** Astana was rejected by pre-registered rule Q7, with a
   6.60-year span but 42.8% completeness against a 60% floor. So the benchmark
   under-represents severe continental winter inversions.

5. **No result here can speak to current conditions.** The reference network no longer exists
   in the form that produced this record. Any deployment claim is extrapolation past the
   evaluated period.

6. **Two of the `notes` strings inside `splits.json` are stale.** They say leave-station-out
   covers 2 of 6 cities, and that 4 stations report after the shutdown. Both were written
   before the v1.1.0 Dushanbe merge. The fold *data* in the same file is correct, and the
   notes are left alone on purpose, because editing them would change the hash and invalidate
   every published score. Reported here instead of silently re-frozen, which is the rule this
   benchmark applies to itself.

## Reproducing from the manifest

`data/MANIFEST.md` records every source with access dates and checksums. `data/DECISIONS.md`
records every filtering decision with its effect on *n* and the direction of the bias if the
decision is wrong. Rebuild with:

```bash
python -m ecopulse_ca.ingest.openaq --out data/interim/station_census.csv
python scripts/pull_panel.py
python scripts/build_benchmark_panel.py
python -m ecopulse_ca.splits.builder --freeze
```

That last command has to reproduce the same `sha256`. If it does not, something upstream
changed, so investigate before you go any further.
