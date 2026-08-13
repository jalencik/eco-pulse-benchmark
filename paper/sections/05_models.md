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

The untuned and tuned configurations are reported side by side below. **They differ in four
respects, not one, and the gap between them must not be read as the effect of hyperparameter
tuning alone.** An earlier version of this manuscript described them as sharing "the same
feature set". That was incorrect. The differences are:

| | Untuned (`train_gbdt.py`) | Tuned (`train_phase5.py`) |
|---|---|---|
| features | tier columns only | tier columns **+ 3 spatial neighbour features** |
| trees | 600 | 800 |
| training rows | train block only (to 2022-12-31) | train block **+ validation block** (to 2023-12-21) |
| hyperparameters | library defaults | grid search, 16 combinations |

Because the feature set, the tree count and the training window all change together, the
untuned-to-tuned difference is a **combined** effect. This paper does not run the ablation
that would separate them, and no causal attribution to tuning is claimed.

| Feature set | Untuned RMSE | Tuned RMSE | Untuned R² | Tuned R² |
|---|---:|---:|---:|---:|
| static only | 32.19 | 28.63 | -0.73 | -0.15 |
| deployable | 29.25 | 28.56 | -0.21 | -0.09 |
| retrospective | 29.51 | 28.01 | -0.25 | -0.04 |

The untuned column is retained because it was once used to argue that a poor result would
have been an artefact of library defaults. On benchmark v1.1.0 that argument no longer holds:
the tuned configuration now leads every admissible baseline (Section 6.1), while both
configurations explain little within-city day-to-day variation. The honest statement is that
the combined feature-plus-window-plus-hyperparameter change improves RMSE, and that RMSE
leadership is not by itself evidence of skill.

## 5.4 Seeds and variance

Every configuration is run with five seeds and reported as mean ± standard deviation. Seed
variance is small: the maximum across configurations is 0.25 µg/m³ for
Task F and 1.79 µg/m³ for Task N.

**Fold-to-fold variance is an order of magnitude larger than seed variance.** The standard
deviation of Task N RMSE across the 6 leave-city-out folds is
11.38 µg/m³, against 1.79 µg/m³ across seeds. Which
city is held out dominates which seed was drawn. A study reporting seed error bars alone
would communicate a precision this benchmark does not have, and per-city results are
therefore mandatory (Section 3.6).

## 5.5 Operational cost of deployability

The deployable feature set excludes every product whose latency exceeds the forecast
horizon; the retrospective set adds them back. The difference is the price of being
deployable:

| Task | Deployable | Retrospective | Cost |
|---|---:|---:|---:|
| N (leave-city-out) | 28.56 | 28.01 | small |
| F (forecasting) | 21.58 | 21.54 | small |

**The cost is negligible in both tasks** — 28.56 against
28.01 µg/m³ under leave-city-out, well inside the fold-to-fold spread
of 11.38 µg/m³. This is a positive result for deployment and a
deflationary one for the satellite features: products that arrive too late to be operational
are also contributing little when they are available. Section 6.4 shows why.
