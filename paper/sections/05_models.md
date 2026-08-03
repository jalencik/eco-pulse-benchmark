# 5. Models and Training Protocol

## 5.1 Model class

Gradient-boosted decision trees (LightGBM) are the learned model. The choice is deliberate
and is not a claim that trees are the strongest possible architecture. Three properties
matter for this benchmark:

1. **Native missing-value handling.** Section 2 established that satellite retrieval failure
   is correlated with the target. A model that requires imputation forces a choice between
   discarding the informative rows and inventing values for them; LightGBM learns a default
   direction per split, so missingness is used rather than filled.
2. **Sample efficiency.** Six cities is a small spatial sample. A deep architecture would be
   tuned on validation folds of a few hundred station-days, and the tuning variance would
   exceed the effect being measured.
3. **Attribution that survives inspection.** Section 6 depends on being able to say which
   feature families carry the model, and to show that the answer is uncomfortable.

Reporting a deep model here would require a like-for-like comparison we cannot yet support
at this sample size; the benchmark exists so that such a comparison can be made later on
fixed splits.

## 5.2 Feature families

- **spatial neighbour** — inverse-distance-weighted neighbour concentration, neighbour mean,
  neighbour count. Under leave-city-out the neighbour set **excludes the held-out city**,
  which is enforced by passing the held-out label into the constructor rather than by
  filtering afterwards.
- **static geography** — elevation, terrain basin indices at
  6-city scale, population density, distance to the Aralkum.
- **calendar** — cyclical day-of-year and hour encodings, weekday.
- **satellite** — MAIAC AOD, S5P AAI/NO₂/SO₂/CO.
- **satellite missingness** — valid-pixel counts and retrieval indicators, promoted to
  features in their own right.
- **CAMS forecast** — the 24-hour-lead chemistry-transport prediction.

Autoregressive lags of the target are **Task F only**. They are not merely optimistic under
leave-city-out; they are undefined, because the held-out city supplies no history. For Task N
the spatial features above are the only route to target information, and they are
constructed with the held-out city removed.

## 5.3 Tuning

Hyperparameters are selected on the 2023-01-11 to 2023-12-21 validation block and then
frozen. The test block 2024-01-01 to 2024-12-31 is read exactly once per reported
configuration. The tuning protocol follows established guidance for tree ensembles (Probst et al., 2019).
No hyperparameter, feature-set choice, or early-stopping decision is made
against test-block performance.

Tuning was not cosmetic. Untuned defaults produce a Task N leave-city-out RMSE of
31.99 µg/m³ with R² = -0.64 — worse than the
training-pool-mean constant of Section 4. Tuned, the same feature set reaches
25.70 µg/m³ at R² = 0.07.

| Feature set | Untuned RMSE | Tuned RMSE | Untuned R² | Tuned R² |
|---|---:|---:|---:|---:|
| static only | 33.22 | 28.31 | -1.03 | -0.24 |
| deployable | 31.15 | 25.75 | -0.57 | 0.04 |
| retrospective | 31.99 | 25.70 | -0.64 | 0.07 |

An untuned GBDT would have supported the conclusion that gradient boosting cannot beat a
constant on this task. That conclusion would have been an artefact of the defaults, and it
is the reason the untuned column is retained in the paper rather than discarded once better
numbers existed.

## 5.4 Seeds and variance

Every configuration is run with five seeds and reported as mean ± standard deviation. Seed
variance is small: the maximum across configurations is 0.24 µg/m³ for
Task F and 0.85 µg/m³ for Task N.

**Fold-to-fold variance is an order of magnitude larger than seed variance.** The standard
deviation of Task N RMSE across the 6 leave-city-out folds is
7.74 µg/m³, against 0.85 µg/m³ across seeds. Which
city is held out dominates which seed was drawn. A study reporting seed error bars alone
would communicate a precision this benchmark does not have, and per-city results are
therefore mandatory (Section 3.6).

## 5.5 Operational cost of deployability

The deployable feature set excludes every product whose latency exceeds the forecast
horizon; the retrospective set adds them back. The difference is the price of being
deployable:

| Task | Deployable | Retrospective | Cost |
|---|---:|---:|---:|
| N (leave-city-out) | 25.75 | 25.70 | small |
| F (forecasting) | 21.48 | 20.94 | small |

**The cost is negligible in both tasks** — 25.75 against
25.70 µg/m³ under leave-city-out, well inside the fold-to-fold spread
of 7.74 µg/m³. This is a positive result for deployment and a
deflationary one for the satellite features: products that arrive too late to be operational
are also contributing little when they are available. Section 6.4 shows why.
