# 6. Results

All figures are on the frozen test block 2024-01-01 to 2024-12-31, five seeds, with
Task N and Task F reported separately throughout.

## 6.1 Task N — leave-city-out nowcasting

| Model | RMSE (µg/m³) | MAE | R² |
|---|---:|---:|---:|
| best spatial baseline (kriging) | 40.92 | — | -0.14 |
| training-pool mean (constant) | 43.09 | — | -0.27 |
| CAMS, pooled debias | 31.09 | 23.29 | -0.30 |
| LightGBM, static only | 28.31 | 19.22 | -0.24 |
| LightGBM, deployable | 25.75 | 17.25 | 0.04 |
| LightGBM, retrospective | 25.70 | 17.38 | 0.07 |

**The learned model beats every baseline, and its R² is 0.07.** Both
statements are load-bearing. It improves on pooled-debiased CAMS by
31.09 → 25.70 µg/m³ and on the best spatial
interpolator by a wider margin. It also explains almost none of the variance in a
never-seen city. We report this as the result: predicting urban PM2.5 at a location with no
local monitor, from a training set of five other cities, is close to unsolved in this
region, and the benchmark exists to make that measurable rather than to conceal it.

## 6.2 Per-city results and the Diebold–Mariano tests

Pooling six cities into one number hides the finding.

| Held-out city | LightGBM RMSE | CAMS RMSE | DM statistic | *p* |
|---|---:|---:|---:|---:|
| Almaty | 15.73 | 25.69 | -5.48 | 0.0000 |
| Ashgabat | 21.34 | 20.75 | 0.35 | 0.7271 |
| Bishkek | 20.92 | 23.64 | -1.87 | 0.0630 |
| Dushanbe | 38.58 | 48.81 | -2.82 | 0.0050 |
| Khujand (zero-shot) | 31.55 | 39.08 | -2.51 | 0.0124 |
| Tashkent | 26.35 | 28.56 | -1.57 | 0.1180 |
| **pooled** (n = 2480) | **28.97** | **35.68** | **-4.52** | **< 0.0001** |

Tests use Newey–West HAC variance with the Harvey–Leybourne–Newbold small-sample
correction. Negative statistics favour the learned model.

**The pooled improvement is significant (< 0.0001); only 3 of
6 individual folds are.** Bishkek (0.0630) and Tashkent
(0.1180) show lower RMSE that does not clear significance, and we do not describe
those as improvements. **Ashgabat favours CAMS outright**
(21.34 vs 20.75 µg/m³, DM statistic
0.35, *p* = 0.7271) — the sign is reversed and the result is far
from significant, so the honest summary is that the two are indistinguishable there rather
than that CAMS wins.

**Khujand, the zero-shot fold, is significant (0.0124)** at
31.55 µg/m³ against CAMS at 39.08. A city with no training
rows at all is predicted better than by the operational chemistry-transport model. It
remains among the hardest folds in absolute terms, second only to Dushanbe.

**Truncation-lag sensitivity.** The DM truncation lag is derived from the forecast horizon,
and an early implementation passed `horizon_hours = 1` for the nowcasting task, which
disables the HAC correction entirely and inflated *p*-values by roughly seven orders of
magnitude. We now report the full sensitivity sweep: across truncation lags of
0 to 60 hours the pooled conclusion is stable, with all comparisons significant
(yes) and a worst-case *p* of 0.0019.

## 6.3 Task F — forecasting at monitored stations

| Feature set | RMSE (µg/m³) | R² |
|---|---:|---:|
| best Task F baseline (same-hour 7-day mean) | 35.58 | 0.13 |
| LightGBM, static only | 23.08 | 0.57 |
| LightGBM, deployable | 21.48 | 0.63 |
| LightGBM, retrospective | 20.94 | 0.65 |

Task F is the easier problem and the numbers say so: R² = 0.65 against
0.07 for Task N. **These two figures must never be quoted together as
though they described one system.** The Task F model may read the station's own recent
history; the Task N model is predicting a city it has never seen. Reporting
20.94 µg/m³ as "the model's accuracy" would describe a capability the
deployment does not have at unmonitored locations, which is the case the artefact exists to
serve.

## 6.4 SHAP attribution: what actually carries the model

Mean absolute SHAP over the test block, by feature family:

| Family | Share of total attribution |
|---|---:|
| spatial neighbour | **32.5%** |
| static geography | 25.1% |
| calendar | 16.8% |
| satellite | 16.6% |
| CAMS forecast | 5.1% |
| satellite missingness | 4.1% |

**Spatial interpolation drives the model, not the satellite record.** The single largest
feature is `nbr_idw` at 11.54 mean absolute SHAP — inverse-distance
weighted neighbour concentration — more than twice the second-ranked feature
(`doy_cos`, 4.84). Spatial neighbours and static geography
together account for
32.5% + 25.1% of attribution, while the
five satellite products contribute 16.6% between them.

This is the paper's least comfortable result and we state it plainly: **the model is largely
a well-tuned spatial interpolator with geographic priors.** The satellite features are not
inert — 16.6% is not nothing, and Section 5.5 shows the deployable set
loses little — but a reader would be entitled to expect, from a study built on five
remote-sensing products, that those products carried the prediction. They do not.

Two further readings follow. First, **satellite missingness earns
4.1% — comparable to the 5.1%
contributed by the entire chemistry-transport model.** Whether a retrieval failed carries
nearly as much information as what the atmospheric model predicted, which vindicates
modelling missingness rather than dropping it (Section 2.4) and simultaneously indicates how
little the retrieved values themselves add. Second, calendar features at
16.8% confirm that a large part of the signal is seasonal regularity that
any climatology captures — consistent with the same-hour 7-day mean being the only Task F
baseline with positive R².

## 6.5 Summary of what is and is not established

Established:

- The learned model beats pooled-debiased CAMS across the 6-fold leave-city-out
  protocol, pooled *p* = < 0.0001.
- Deployability costs almost nothing: 25.75 vs
  25.70 µg/m³.
- Zero-shot transfer to a city with no training rows beats CAMS significantly
  (0.0124).

Not established:

- Per-city superiority. 3 of 6 folds reach significance;
  Ashgabat does not favour the model at all.
- Useful absolute accuracy at unmonitored locations. R² = 0.07.
- That satellite remote sensing drives the result. Section 6.4 shows it does not.
