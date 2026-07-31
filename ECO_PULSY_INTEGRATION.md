# ECO-PULSY Integration Guide

How the ECO-PULSY production application consumes this benchmark: which artifacts to pull,
how to train against the frozen splits without leaking, and what a candidate model must
clear before it ships.

> **Artifact naming.** There is no `splits.parquet`. The benchmark deliverable is
> **`benchmark/splits/splits.json`** plus its checksum. The `.parquet` files in this
> repository live under `data/interim/`, are gitignored, and are *intermediate* products of
> the ingestion pipeline — not the benchmark, and not redistributed. Integrate against the
> JSON. If an ECO-PULSY job currently fetches `splits.parquet`, it is fetching a path that
> does not exist on any branch.

---

## 1. What to pull

Five files, all under `benchmark/splits/`:

| File | Role |
|---|---|
| `splits.json` | Canonical definition: stations, temporal blocks, LOCO folds, LSO folds, config |
| `splits.sha256` | Checksum over `splits.json`. **Verify on every pull.** |
| `temporal_blocks.json` | Derived view — blocks only |
| `leave_city_out.json` | Derived view — LOCO folds only |
| `leave_station_out.json` | Derived view — LSO folds and ineligible cities |

```bash
git clone --depth 1 https://github.com/jalencik/eco-pulse-ca-benchmark.git /tmp/bench
cd /tmp/bench/benchmark/splits && sha256sum -c splits.sha256
```

`sha256sum -c` must pass before any training job reads the file. A mismatch means the
benchmark moved, and every metric ECO-PULSY has recorded against the old splits is
incomparable to metrics recorded against the new one.

**Pin both the version and the hash** in ECO-PULSY's config. `benchmark_version` alone is
insufficient — it is a human-assigned string; the hash is the identity.

```python
import hashlib, json
from pathlib import Path

SPLITS = Path("/tmp/bench/benchmark/splits/splits.json")
EXPECTED_SHA = "544a044c2037c6e6707883b468fcda3b3ba334a3d6cde86d6fcc582f6f9e0c6c"

raw = SPLITS.read_bytes()                      # bytes, not text: CRLF translation
actual = hashlib.sha256(raw).hexdigest()       # would change the digest on Windows
if actual != EXPECTED_SHA:
    raise RuntimeError(f"benchmark moved: {actual} != {EXPECTED_SHA}")

splits = json.loads(raw)
assert splits["benchmark_version"] == "1.0.0"
```

Read the file as **bytes**. Reading as text on Windows applies CRLF translation and the
digest will not match — this exact fault cost a day during benchmark construction.

## 2. Structure of `splits.json`

```
benchmark_version : str            "1.0.0"
config            : dict           max_lag_hours, max_horizon_hours, purge_hours,
                                   purge_rule, seeds[5], test_year
stations          : list[8]        station_id, city, latitude, longitude, n_observations
temporal_blocks   : list[6]        name, start, end  (ISO-8601 UTC)
leave_city_out    : list[6]        fold, held_out_city, held_out_stations,
                                   train_stations, n_train_cities
leave_station_out : dict           folds[], ineligible_cities[]
combined_headline : dict
notes             : list
```

The six temporal blocks are ordered `train → purge_train_val → val → purge_val_test →
test → reserved_post_test`. **The purge blocks are not padding.** They are derived:
`purge_hours == max_lag_hours + max_horizon_hours` (240 = 168 + 72). A model whose feature
window exceeds `max_lag_hours` invalidates the gap and must not use these splits unchanged.

Note that `train_stations` mixes numeric station IDs with two city-name identifiers
(`"Ashgabat"`, `"Bishkek"`). Those are merged feeds: each of those cities publishes the same
physical instrument under two provider IDs, and the benchmark merges them into one series
keyed by city. Treat station IDs as opaque strings. Do not cast to `int`.

## 3. Training a production model

```python
import pandas as pd

blocks = {b["name"]: b for b in splits["temporal_blocks"]}

def window(df: pd.DataFrame, block: str) -> pd.DataFrame:
    b = blocks[block]
    return df[(df.index >= pd.Timestamp(b["start"])) & (df.index <= pd.Timestamp(b["end"]))]

train = window(panel, "train")     # 2018-11-27 .. 2022-12-31
val   = window(panel, "val")       # 2023-01-11 .. 2023-12-21
test  = window(panel, "test")      # 2024 — DO NOT TOUCH until the model is frozen
```

Rules ECO-PULSY inherits by using these splits:

1. **Tune on `val`, never on `test`.** The 2023 validation block exists for hyperparameters.
   A number produced by selecting on `test` is not comparable to anything in the paper.
2. **Never train across a purge block.** Skipping the gap re-introduces the leakage the gap
   removes: a 168-hour rolling feature evaluated at the first test timestamp reads 168 hours
   of training labels.
3. **Never reshuffle.** Random k-fold on this panel inflates scores by putting the same
   station, often the same hour, on both sides of the split.
4. **`reserved_post_test` is not a second test set.** It runs past the 2025-03-04 shutdown of
   the reference network and covers two cities, not six.

## 4. Evaluation gate before deployment

A candidate model must be scored on **both** tasks. They are different problems and their
metrics are never pooled into one table.

| | **Task N — nowcasting** | **Task F — forecasting** |
|---|---|---|
| Question | concentration at an **unmonitored** location, now | concentration at a **monitored** station, later |
| Protocol | leave-city-out, 6 folds | blocked temporal, t+24/48/72 h |
| Target history (lags) | **illegal** — the held-out city has no label | legal |
| Spatial neighbour features | legal, but neighbours **must exclude the held-out city** | legal |

Under leave-city-out the held-out city contributes no label at all, so an autoregressive lag
is not merely optimistic — it is undefined at inference. Any ECO-PULSY feature builder that
computes lags must be disabled for Task N, and its spatial encoders must be fitted with the
held-out city removed from the neighbour pool.

### Metrics

Use the benchmark's own implementations so definitions cannot drift:

```python
from ecopulse_ca.eval.metrics import regression_metrics, exceedance_metrics, to_daily_mean

reg = regression_metrics(obs, pred)                    # rmse, mae, bias, r2, n
daily_obs, daily_pred = to_daily_mean(obs, tz), to_daily_mean(pred, tz)
exc = exceedance_metrics(daily_obs, daily_pred)        # WHO 2021 24-h guideline, 15 µg/m³
```

Exceedance is scored on **local-calendar daily means**, because that is what the WHO
guideline defines. Scoring it hourly, or in UTC, answers a different question.

### The four gates

A model ships only if it clears all four.

1. **Beats the constant.** `exc.f1_exceed > exc.f1_trivial_always` and
   `exc.peirce_skill > 0`. A trivial always-exceed classifier scores F1 ≈ 0.76 on this
   region because the air is bad on most days. F1 alone certifies nothing.
2. **Beats the pooled mean.** RMSE below `TrainingPoolMean` — predicting the training pool's
   own mean. Every credential-free baseline in the paper failed this.
3. **Significantly beats the incumbent.** Diebold–Mariano with Newey–West HAC at truncation
   lag `h−1` and the Harvey–Leybourne–Newbold small-sample correction. **A lower RMSE with
   *p* ≥ 0.05 is not an improvement** and must not trigger a rollout.
4. **Uses only deployable features.** Every predictor carries `available_at_runtime` and a
   measured `latency_hours`. ERA5 (163 h measured) and MAIAC (~8 days) cannot exist at
   prediction time. A model scoring well on `reanalysis_oracle` is unshippable by
   construction; that feature set exists to quantify the gap, not to be served.

### Per-city reporting is mandatory

Report all six folds, never the pooled figure alone. Fold-to-fold standard deviation exceeds
seed-to-seed standard deviation by roughly an order of magnitude, so a pooled number hides
the variation that actually determines production behaviour. **Khujand is reported
separately** in every ECO-PULSY evaluation: it contributes no training label anywhere in the
record, making it the only true zero-shot fold and the closest analogue to onboarding a city
ECO-PULSY has never monitored.

## 5. Continuous integration

```yaml
- name: Verify benchmark integrity
  run: cd benchmark/splits && sha256sum -c splits.sha256

- name: Reject random splits
  run: pytest tests/test_no_random_splits.py     # static scan of the model source

- name: Gate on Task N / Task F
  run: python -m ecopulsy.eval.gate --splits benchmark/splits/splits.json --strict
```

Fail the build on checksum mismatch. Do not auto-refresh the pinned hash — a benchmark that
silently updates is not a benchmark, and every historical ECO-PULSY metric becomes
incomparable the moment it moves.

## 6. What this benchmark cannot tell you

State these in any ECO-PULSY model card that cites it.

- **No result speaks to current conditions.** Six of eight reference stations end
  2025-03-04. The benchmark is a historical archive.
- **Bishkek's 2024 labels are provider-dependent.** The two feeds of that one instrument
  agree on a minority of overlapping test-block hours. Bishkek error bars are irreducibly
  wider than they appear.
- **One city per country in most cases.** Kazakhstan is represented by Almaty alone.
- **Performance is carried by spatial interpolation, not satellite retrieval.** Neighbour
  features dominate attribution. Do not size ECO-PULSY's satellite ingestion budget on the
  assumption that those products drive accuracy here.
- **Train/serve skew is unquantified.** The benchmark uses standard-latency satellite
  products; a live service uses near-real-time streams. These are different processing
  chains over the same instrument and the distributional gap between them has not been
  measured.
