# 6. Results

All figures are on the frozen test block 2024-01-01 to 2024-12-31, five seeds, with
Task N and Task F reported separately throughout.

## 6.1 Task N — leave-city-out nowcasting

| Model | RMSE (µg/m³) | MAE | R² |
|---|---:|---:|---:|
| best spatial baseline (idw_k5_p2, daily) | 30.10 | — | -0.32 |
| training-pool mean (constant, daily) | 33.83 | — | -0.60 |
| CAMS, pooled debias | 29.77 | 21.19 | -0.14 |
| LightGBM, static only | 28.63 ± 0.17 | 18.39 | -0.15 |
| LightGBM, deployable | 28.56 ± 0.52 | 17.72 | -0.09 |
| LightGBM, retrospective | 28.01 ± 0.35 | 17.81 | -0.04 |

Learned-model RMSE is given as **mean ± standard deviation over 5 seeds**, where the
resampled quantity is the whole leave-city-out protocol per seed. Baseline rungs are
deterministic and carry no seed dispersion. Section 3.6 rule 5 requires this of every
submission to the benchmark; it is applied here to the reference implementation as well.

**Two estimators appear in this paper and they are not the same number.** Section 5 and the
table above report the mean over 5 independently seeded runs. Section 6.2 onward,
and every Diebold–Mariano and significance result, score the **5-seed
ensemble**: the seed predictions are averaged first and the average is scored once. Averaging
reduces variance, so the ensemble is the better estimator and its fold-mean RMSE
(27.91 µg/m³) sits below the mean of the single-seed RMSEs
(28.01 µg/m³). Where a ± appears beside a Section 6.2 figure, the
centre is the ensemble and the spread is the dispersion of the single-seed runs around their
own mean — the spread describes the seed-to-seed variability of the procedure, not the
uncertainty of the ensemble, which is narrower and is not estimated here.

**Two numbers describe this result, and they point in opposite directions.**

*Between cities, the model retains some signal.* Pooled over all evaluation rows — variance
measured against the global mean — it explains **R² = 0.13**. Part of the
contrast between a Dushanbe and a Bishkek is learnable from geography, satellite retrievals
and neighbouring monitors.

*Within a city, it is inconsistent.* The headline **R² = -0.04** is the
**mean of the 6 per-fold R² values**, each computed against *that city's own*
mean. Scored this way the model must explain day-to-day variation inside a city it has never
seen. The spread is wide — **-0.55 to 0.52**, with
3 of 6 folds negative (Section 6.1c). It succeeds in some
held-out cities and does worse than a flat line through the city's own mean in others, and the
average of those outcomes is near zero.

The two statistics are not in conflict; they answer different questions, and only the second
is the task this benchmark defines. The correct summary is that **the model captures some
between-city variation and within-city skill that does not generalise across cities.** A
reader given only the pooled figure would substantially overestimate what it does.

**The learned model has the lowest RMSE of any admissible method, and that ranking is not
robust.** Both halves matter and both are reported.

Scored on identical rows at identical resolution it reaches
28.01 ± 0.35 µg/m³ against
29.44 µg/m³ for the strongest legal rung (`idw_k5_p2`),
a margin of 1.43 µg/m³, and it leads all 6 legal
rungs on the fold mean.

But a fold mean is an average over 6 numbers, and the per-city differences are
much larger than the average of them. Against inverse-distance weighting the model is better
in 4 of 6 cities, with per-fold differences ranging from
−10.73 to +5.10 µg/m³. A paired test over the 6 cities gives
***p* = 0.586** — the margin is **not statistically distinguishable from zero** at
the unit of generalisation this benchmark is built on. Removing any single city and
recomputing, the model still leads inverse-distance weighting in
5 of 6 subsets; in the remaining one the ordering reverses.

The margin is, however, **4.1× the seed standard deviation**
(0.35 µg/m³), so it is not an artefact of random initialisation —
it is fold-to-fold heterogeneity, not run-to-run noise. Restricting to the five
reference-grade cities and excluding the low-cost Khujand fold, the model leads more clearly
(25.84 against 28.51 µg/m³).

**The defensible claim is therefore "lowest RMSE among admissible methods on this fold set",
not "better than spatial interpolation".** With 6 cities the benchmark cannot
separate those two statements, and Section 6.2b makes the same point about the CAMS
comparison. Full robustness table: `t7_05_ranking_robustness.csv`.

For reference, a constant equal to *the held-out city's own test-block mean* scores
28.12 µg/m³. **That predictor is not legal and is not a baseline.** Under
leave-city-out the held-out city contributes no training label anywhere in the record, so its
mean cannot be known at prediction time; it is reported as a diagnostic floor — the share of
error that is pure within-city day-to-day variance — and the model is within
0.11 µg/m³ of it. An earlier version of this manuscript compared the model
against that oracle and reported it as losing to "a constant". That comparison was invalid,
and the correction is stated here rather than quietly dropped.

Three corrections to this comparison were needed:

1. Earlier drafts placed daily model scores beside baselines scored on *hourly* observations.
   Averaging removes within-day variance, so hourly RMSE is structurally larger; the apparent
   margin was arithmetic, not skill.
2. The comparison predated benchmark v1.1.0, in which the two Dushanbe records
   were found to be one instrument and merged (Section 2). Every fold's RMSE rose once the
   duplicate was gone.
3. The constant used was an oracle, as above.

## 6.1b The baseline ladder at a single resolution

Every rung below is scored on **the same daily evaluation rows as the learned model**
(local-calendar daily means, ≥18 hours, the frozen 2024 test block). Table 6.1 above and the
hourly ladder in Section 3 are not comparable to each other and are no longer presented as one
ladder.

| Model (daily, leave-city-out) | RMSE µg/m³ |
|---|---:|
| nearest_monitor | 33.50 |
| training_pool_mean | 32.75 |
| train_global_mean | 32.70 |
| train_global_median | 30.99 |
| ordinary_kriging | 29.75 |
| idw_k5_p2 | 29.44 |
| **LightGBM, retrospective (log target)** | **28.01** |

## 6.1c Per-fold R², including the negative folds

Section 3.6 requires per-city reporting from every submission to this benchmark. The same rule
is applied here.

| Held-out city | R² (vs that city's own mean) |
|---|---:|
| Bishkek | -0.549 |
| Dushanbe | -0.341 |
| Ashgabat | -0.247 |
| Khujand | +0.128 |
| Tashkent | +0.323 |
| Almaty | +0.517 |

3 of 6 folds are negative: in those cities the model is
worse than predicting the city's own average. Averaging them into a single figure conceals
that, which is why both the spread and the mean are reported.

## 6.2 Per-city results and the Diebold–Mariano tests

Pooling six cities into one number hides the finding.

| Held-out city | LightGBM RMSE | CAMS RMSE | DM statistic | *p* |
|---|---:|---:|---:|---:|
| Almaty | 15.30 ± 1.31 | 23.25 | -4.06 | 0.0001 |
| Ashgabat | 20.74 ± 0.20 | 18.83 | 1.17 | 0.2420 |
| Bishkek | 20.21 ± 0.39 | 20.03 | 0.15 | 0.8805 |
| Dushanbe | 46.94 ± 0.79 | 47.96 | -2.65 | 0.0085 |
| Khujand (zero-shot) | 38.81 ± 0.12 | 39.90 | -2.03 | 0.0430 |
| Tashkent | 25.46 ± 0.60 | 28.63 | -2.82 | 0.0050 |
| **pooled** (n = 2214) | **31.49** | **33.07** | **-4.38** | **< 0.0001** |

Tests use Newey–West HAC variance with the Harvey–Leybourne–Newbold small-sample
correction. Negative statistics favour the learned model. One limitation of the test is
stated here rather than left for a reader to raise: Diebold (2015) notes that the DM
procedure was constructed to compare *given* forecasts, and that applying it to *estimated*
models is its most common misuse. Both comparators here are estimated on training data, so
the per-fold DM statistics below are read as descriptive diagnostics. The paper's inferential
claim is the city-level test in Section 6.2b, not these. Six folds are tested, so per-fold
*p*-values are additionally reported with a Holm step-down correction (Holm, 1979) in
`t6_07_per_fold_holm.csv`; **3 of 6 survive it at α = 0.05.**
The correction family is the 6 per-fold comparisons of the same model pair,
declared here because a family chosen after seeing the *p*-values is not a correction. It is
the only corrected family. The deposited tables carry 378 *p*-values in
total, across the hourly ladders, the lag-sensitivity sweeps and the robustness checks; those
are reported as descriptive diagnostics and no inferential claim in this paper rests on any of
them individually. The paper's inference is the city-level primary analysis of Section 6.2b.

### 6.2b Which *p*-value is the paper's claim

The pooled row above treats 2214 station-days from 6 cities as
independent observations. They are not, in either dimension: the loss differential has
first-order autocorrelation 0.25 within station, and station-days cluster within
cities that contribute very unequal row counts. **That pooled figure is reported for
continuity with the per-fold rows above and is not the paper's inferential claim.**

The estimand is the reduction in squared error at *a city with no local training labels*, so
the unit of generalisation is the **city** — as Section 5.4 already argues, and as the
leave-city-out protocol implies. The primary analysis therefore aggregates to one value per
city and tests those 6 numbers.

The quantity tested is the loss differential Δ, the model's squared error minus debiased
CAMS's, in (µg/m³)². Negative values favour the model.

| | Test | Unit | *n* | Δ (95% CI) | *p* |
|---|---|---|---:|---:|---:|
| **Primary** | paired *t* on city means | city | 6 | **-96.2 (-237.0, +44.5)** | **0.1392** |
| **Primary** | exact sign-flip permutation | city | 6 | **-96.2** | **0.1250** |
| Sensitivity | station-day, independence assumed | station-day | 2214 | -101.7 (-133.3, -70.2) | 2.6e-10 |
| Sensitivity | station-day, Newey–West HAC (lag 60 d) | station-day | 2214 | -101.7 (-171.7, -31.7) | 0.0044 |
| Sensitivity | cluster bootstrap over cities | city | 6 | -96.2 (-196.5, -2.9) | 0.0428 |

**The interval is the more informative half of the primary row.** At
(-237.0, +44.5) (µg/m³)² it spans zero and is wide enough to contain both a substantial
improvement over CAMS and a moderate degradation. The study does not establish that the model
is better, and it equally does not establish that it is not: with 6 cities the
design cannot separate those cases. Reporting only *p* = 0.1392 would invite the
reading that no effect exists, which the interval does not support either.

With 6 clusters, cluster-robust asymptotics are unreliable — the cluster-robust
variance estimator is materially downward-biased below roughly 30–50 clusters
(Cameron and Miller, 2015). Two remedies appropriate at this cluster count are reported
together: a *t*-test on 6 city means with 5 degrees of freedom,
and an exact sign-flip permutation test. That test is distribution-free but not
assumption-free: it trades normality for the weaker requirement that each city's mean
differential be sign-symmetric about zero under the null, and at 6 cities that
requirement is no more checkable than normality was. Its smallest attainable two-sided
*p*-value is 0.03125, a floor imposed by having only 6 cities; we state
it rather than let a reader mistake it for evidence.

**The evidence is suggestive and does not reach conventional significance under either
procedure this benchmark treats as primary.** Corrections for serial dependence alone leave
the station-day result significant. At the city level the two primary procedures do not
(paired *t* *p* = 0.1392, exact permutation *p* = 0.1250), while
a percentile cluster bootstrap over the same 6 cities returns
*p* = 0.0428. We report all of them rather than the smallest. The percentile bootstrap
is the least trustworthy of the three here for the same reason the cluster-robust estimator
is: 6 clusters is too few to resample, and the interval it produces is
anti-conservative. The divergence is a real property of a study with six cities, not a defect
to be resolved by choosing a number.

**The pooled improvement is significant (< 0.0001); 4 of
6 individual folds are, and 3 of those survive Holm correction.**
Almaty, Tashkent (*p* = 0.0050) and Dushanbe hold after correction. Khujand
(*p* = 0.0430) is significant uncorrected and is not after it, and we report it on
that footing below.

**In Ashgabat and Bishkek the sign is reversed and CAMS returns the lower RMSE.** At
Ashgabat that is 18.83 against 20.74 µg/m³ (DM statistic
1.17, *p* = 0.2420); at Bishkek the gap is smaller still and the
test cannot separate it from zero (*p* = 0.8805). Neither reversal approaches
significance, so the two methods are indistinguishable in those two cities rather than
CAMS winning them.

**Khujand, the zero-shot fold, clears significance before Holm correction
(0.0430) and not after it** at 38.81 µg/m³ against CAMS at
39.90. A city with no training rows anywhere in the record is predicted at
least as well as the operational chemistry-transport model predicts it, which is the finding
worth having. We stop short of calling it an improvement, because the correction removes it.
It remains among the hardest folds in absolute terms, second only to Dushanbe.

**Truncation-lag sensitivity.** The daily comparisons in Table 6.2 use the automatic
Newey–West bandwidth, floor(4(n/100)^(2/9)), which at n = 2214 is 7 days. An
earlier hourly implementation instead derived the lag from the forecast horizon and passed
`horizon_hours = 1` for the nowcasting task, which
disables the HAC correction entirely and inflated *p*-values by roughly seven orders of
magnitude. We now report the full sensitivity sweep: across truncation lags of
0 to 60 hours the pooled conclusion is stable, with all comparisons significant
(yes) and a worst-case *p* of 0.0056.

**Figure 3** gives the per-city comparison against debiased CAMS, and **Figure 5** the
observed-versus-predicted scatter with the 1:1 line. The compression toward the mean
visible in Figure 5 is the same effect that drives the RMSE/exceedance divergence of
Section 4.3.

![Figure 3](figures/fig3_per_city_rmse.png)

**Figure 3.** Held-out city RMSE (µg/m³), tuned LightGBM against debiased CAMS.
Ashgabat and Bishkek are the folds where the sign reverses; in neither is the
difference statistically separable.

![Figure 5](figures/fig5_obs_vs_pred.png)

**Figure 5.** Observed against predicted daily mean PM2.5 (µg/m³) under leave-city-out,
with the 1:1 line. Compression toward the mean is visible at high observed values and is
the mechanism behind the RMSE/exceedance divergence of Section 4.3.

## 6.3 Task F — forecasting at monitored stations

**What Task F is, precisely.** The learned Task F model predicts the **daily** mean at a
monitored station from that station's own history at lags of 1, 2 and 7 days plus 7- and
30-day rolling means. Its shortest lag is one day, so it is a **single-horizon, next-day
(24 h) forecast evaluated at daily resolution**.

It is therefore **not comparable to the Task F baseline ladder in Section 3**, which is
resolved across three horizons (24, 48 and 72 h) and scored on hourly observations
(115,381 observations, against 2,214 daily rows for the model).
Earlier drafts placed the two in one table. They measure different things at different
resolutions, and the baseline row has been removed rather than rescaled: no honest rescaling
exists, because the model does not produce 48 h or 72 h forecasts at all. Extending it to the
full horizon set is left as future work and is not claimed here.

| Feature set (daily, next-day horizon) | RMSE (µg/m³) | R² |
|---|---:|---:|
| LightGBM, static only | 22.03 | 0.58 |
| LightGBM, deployable | 21.58 | 0.59 |
| LightGBM, retrospective | 21.54 | 0.60 |

Task F is the easier problem and the numbers say so: R² = 0.60 against
-0.04 for Task N. **These two figures must never be quoted together as
though they described one system.** The Task F model may read the station's own recent
history; the Task N model is predicting a city it has never seen. Reporting
21.54 µg/m³ as "the model's accuracy" would describe a capability the
deployment does not have at unmonitored locations, which is the case the artefact exists to
serve.

## 6.4 SHAP attribution: what actually carries the model

Attribution uses SHAP values (Lundberg and Lee, 2017), computed on the tuned model over
the held-out folds.

Mean absolute SHAP over the test block, by feature family:

| Family | Share of total attribution |
|---|---:|
| satellite | **26.6%** |
| calendar | 22.2% |
| static geography | 21.8% |
| spatial neighbour | 20.4% |
| CAMS forecast | 9.0% |

**No feature family dominates.** The five satellite products carry the largest share of
attribution at 26.6%, ahead of calendar terms (22.2%),
static geography (21.8%) and spatial neighbours
(20.4%). The single largest individual feature is
`doy_cos` at 0.18 mean absolute SHAP, a calendar term, ahead of
`nbr_idw` at 0.12, the inverse-distance weighted neighbour
concentration.

The spread across the top four families is narrower than the ranking suggests, and it is not
stable enough to carry an interpretation on its own. Section 7.4 sets out why: on benchmark
v1.0.0 this ordering came out the other way round, with spatial interpolation apparently
ahead of the satellite record, and that ordering was an artefact of one duplicated station.
Merging it moved every family. An attribution ranking computed on 7 instruments
should be read as provisional, and the claim this paper previously drew from it is retracted
in Section 7.4 rather than restated here.

Two further readings follow. First, **satellite retrieval-count features no longer appear at
all**: an ablation on the validation block (Section 5.3) found them city-specific rather than
transferable, and they are excluded from Task N. They remain in Task F, where the held-out
entity is a time block rather than a city. Whether a retrieval failed still carries real
information, which vindicates
modelling missingness rather than dropping it (Section 2.4) and simultaneously indicates how
little the retrieved values themselves add. Second, calendar features at
22.2% confirm that a large part of the signal is seasonal regularity that
any climatology captures — consistent with the same-hour 7-day mean being the only Task F
baseline with positive R².

**Figure 4** shows attribution by feature family.

![Figure 4](figures/fig4_shap_by_family.png)

**Figure 4.** Feature attribution by family, as a share of total mean |SHAP|. Satellite
families are hatched. On benchmark v1.1.0 the five satellite products together carry the
largest share (26.6%), ahead of spatial neighbour features
(20.4%) — a reversal of the pre-deduplication ordering discussed in
Section 7.4.

## 6.5 Summary of what is and is not established

Established:

- **The benchmark itself**: 7 instruments across 6 cities, splits
  frozen and hash-verified, every reported number regenerated by one command.
- Deployability costs almost nothing: 28.56 vs
  28.01 µg/m³. Restricting to features available at inference time is
  close to free, which is the one comfortable result here.
- The task is hard in a way the protocol makes visible. Under leave-city-out, a tuned
  gradient-boosting model with satellite, meteorological and spatial features sits within
  0.11 µg/m³ of an oracle constant equal to the held-out city's own test-block
  mean, a predictor the protocol does not permit it to use. It leads that oracle in
  3 of 6 folds.

Not established — and previously claimed:

- **That the learned model beats pooled-debiased CAMS.** Under the city-level analysis this
  protocol implies, it does not: paired *t* *p* = 0.1392, exact permutation
  *p* = 0.1250. Only 3 of 6 folds survive Holm
  correction. The pooled station-day *p*-value reported in earlier drafts assumed an
  independence the data does not have.
- **That leading the ladder means the model is *useful* at unmonitored locations.** It has the
  lowest RMSE of any admissible method (28.01 µg/m³), but mean per-fold
  R² = -0.04, spread -0.55 to 0.52, with
  3 of 6 folds negative. Lowest error and demonstrated
  within-city skill are different claims; only the first is established.
- **That spatial interpolation rather than satellite data drives the result.** That ordering
  reversed once the duplicated Dushanbe instrument was merged (Section 7.4). Satellite
  products now carry 26.6% against 20.4% for
  spatial neighbours. Neither ordering should be treated as robust: it inverted on the
  removal of a single station.
