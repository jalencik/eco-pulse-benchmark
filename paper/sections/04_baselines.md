# 4. The Baseline Ladder

A learned model is only interesting relative to what it beats. This section reports the
mandatory ladder — persistence, climatology, raw chemistry-transport, and the spatial
interpolators — before any learned model appears. Every rung is credential-free and
deterministic, so seed variance is zero by construction and is reported as `(det.)` rather
than as a measured `± 0.000`.

## 4.1 Task F — forecasting at monitored stations

Test block 2024, horizons t+24 h, t+48 h, t+72 h, pooled across stations.

| Model | RMSE (µg/m³) | R² |
|---|---:|---:|
| persistence, y(t) | 42.78 | -0.30 |
| diurnal persistence, y(t−24 h) | 42.78 | -0.30 |
| climatology (station mean) | 38.15 | -0.09 |
| same-hour 7-day mean | 35.58 | 0.13 |

**Persistence and diurnal persistence are numerically identical, and this is correct.** All
three evaluated horizons are multiples of 24 h, so "the same hour yesterday" and "lag-24
persistence" resolve to the same timestamp. The Diebold–Mariano procedure reports them as
exact ties — the loss differential is identically zero and the test statistic is undefined
rather than insignificant. We report the degeneracy rather than dropping a rung, because a
ladder in which two rungs coincide at the evaluated horizons is a property of the horizon
grid that a reader needs in order to interpret the table.

Degradation with lead time is visible only in the persistence family
(40.27 → 44.26 µg/m³ from t+24 h to t+72 h).
Climatology is flat by construction at 38.15 µg/m³, since it
does not read the recent past. **Only the same-hour 7-day mean achieves positive R²**
(0.13); every other rung is worse than predicting the test-block
mean.

## 4.2 Task N — nowcasting under leave-city-out

The held-out city contributes no label. These are pure spatial interpolators, fitted on the
remaining five cities.

| Model | RMSE (µg/m³) | R² | Exceedance F1 | Peirce skill |
|---|---:|---:|---:|---:|
| nearest monitor | 48.03 | -0.71 | 0.737 | 0.414 |
| IDW (k=5, p=2) | 43.65 | -0.32 | 0.762 | 0.317 |
| training-pool mean | 43.09 | -0.27 | 0.764 | 0.000 |
| ordinary kriging | 40.92 | -0.14 | 0.728 | 0.295 |

**Every spatial baseline has negative R².** Interpolating between Central Asian cities
hundreds of kilometres apart is worse than predicting a constant. This is the honest floor
the task sits on, and it is the reason the leave-city-out result in Section 6 is modest
rather than impressive.

**The training-pool mean is an explicit rung, not an afterthought.** It is a constant: the
mean of all training-block labels. It was promoted to the ladder after we observed that it
outranks two of the three genuine interpolators on RMSE (43.09 vs
43.65 and 48.03). Any model that does not clear a
constant has not demonstrated spatial skill, and without this rung in the table the reader
cannot check that.

Kriging attains the best RMSE (40.92) and the **worst** exceedance
F1 (0.728). Optimising squared error pulls predictions toward the
mean, which suppresses exactly the excursions the exceedance metric scores. Reporting one
number without the other would support two opposite conclusions about the same model. We
additionally report the kriging fallback rate: where the system is singular the
implementation silently degrades to IDW, and a column labelled "kriging" that is
substantially IDW underneath is a reporting error rather than a modelling one.

## 4.3 Exceedance F1 does not measure skill

The WHO 2021 24-hour guideline is 15 µg/m³, scored on local-calendar daily means because
that is what the guideline defines. In this region the exceedance base rate is
**64.8%** — exceedance is the common case, not the rare one.

A classifier that predicts "exceeds" unconditionally therefore scores F1 =
**0.764**. The training-pool mean — a constant, carrying no information
whatsoever — scores 0.764, and is the **highest-F1 model in the
entire Task N ladder**. Its Peirce skill is 0.000, exactly zero, as
it must be for any constant.

This is not a curiosity about one table. It means a paper reporting only exceedance F1 on
this region could present a constant as its best classifier and the number would look
respectable. We therefore report, alongside every exceedance F1:

- `f1_trivial_always` — the score of the unconditional classifier on the same rows
- `beats_trivial` — whether the model exceeds it at all
- `base_rate` — so the reader can compute the trivial score independently
- `peirce_skill` — TPR − FPR, which is base-rate independent and **zero for any constant**

Peirce skill separates the ladder in the way F1 does not: nearest monitor
(0.414) and IDW (0.317) carry genuine discriminative
information, while the constant carries none, and the F1 column ranks them in the opposite
order.

## 4.4 CAMS as a baseline

CAMS is the operational chemistry-transport forecast for the region and the strongest
credential-free comparator. It is used at the 24-hour lead throughout: forecast step zero
has assimilated observations at the valid time, so scoring it against that time is lookahead
wearing a forecast label.

| Variant | RMSE (µg/m³) | R² | Bias (µg/m³) |
|---|---:|---:|---:|
| raw | 37.21 | -0.42 | -22.79 |
| locally debiased | 31.10 | -0.12 | -0.38 |
| pooled debiased | 32.57 | -0.22 | -0.38 |

**Raw CAMS under-predicts by -22.79 µg/m³** — a large systematic deficit
consistent with an emissions inventory that does not capture residential coal and biomass
combustion at Central Asian intensity. Removing that bias improves RMSE substantially
(37.21 → 31.10) while R² remains negative
(-0.12): the correction fixes the level, not the timing.

The two debiasing variants are distinguished by protocol. **Local debiasing is admissible
only in Task F**, since it fits a per-city offset on that city's training labels. Under
leave-city-out no such labels exist, so Task N uses the pooled correction fitted with the
held-out city excluded. The pooled variant is the weaker of the two
(32.57 vs 31.10), and reporting the local
figure under a leave-city-out heading would overstate the baseline the learned model must
beat — making the model's margin in Section 6 look smaller than it is, in this direction,
but the protocol violation is the same either way. A test asserts that a bias fitted on the
full record differs from one fitted on the training block, so that a silently-leaking
implementation cannot pass.
