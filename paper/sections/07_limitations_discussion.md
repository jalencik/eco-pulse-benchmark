# 7. Limitations and Discussion

This section is written for a reader hunting the study's weakest point. We would rather
state it than have it found.

## 7.1 The labels themselves are provider-dependent in one city

The embassy monitors are published twice, by StateAir and by AirNow, under distinct
identifiers. Ashgabat's pair is a clean duplicate: the two feeds agree to 0.1 µg/m³ on
100.0% of overlapping test-block hours. **Bishkek's pair is not.**

Across the full record the Bishkek feeds agree on 52.0% of overlapping
hours, and the divergence concentrates in the frozen test year. Over
5389.00 overlapping hours in 2024 they agree on only
**11.1%**, with a 95th-percentile disagreement of
**33.6 µg/m³**. That is comparable to the RMSE of every model in this
paper.

The implication is uncomfortable and irreducible. For Bishkek in the test block there is no
single ground truth. Choosing the other provider's feed would shift the reported error by
roughly the margin that separates our models from each other. Bishkek's DM result
(*p* = 0.8805, not significant) should be read with that in view, and we claim no
improvement there. Merging the feeds, which we do, reduces variance. It cannot manufacture a
label the two publishers agree on. **This limits the data source, not the pipeline, and no
modelling choice removes it.**

## 7.2 Leave-station-out covers a minority of the benchmark

2 leave-station-out folds exist and both are the Khujand pair, so the
protocol is evaluated entirely on low-cost sensors.
**Almaty, Ashgabat, Bishkek, Dushanbe, Tashkent each hold a single instrument**, so within-city station holdout is
undefined there.

The consequence runs deeper than reduced coverage. The Q6 timezone check compares
instruments within a city. In a single-station city, a constant lifelong offset is invisible
to every rule in the suite, and the QC output records that explicitly instead of returning
a pass that actually means "not tested". Five of the 6 cities therefore rest on
metadata correctness for their time alignment. We regard this as the benchmark's largest unaudited
assumption.

A related constraint sits upstream: 306 candidate stations were excluded for insufficient
span, almost all of them low-cost units whose measurement uncertainty is well documented
(Zheng et al., 2018; Crilley et al., 2018).

That exclusion was not applied uniformly, and the exception matters. **Khujand's two
instruments are Clarity low-cost sensors** (`is_monitor = false` in the OpenAQ census), not
reference-grade monitors. Every other city in the benchmark is a US-embassy BAM/FEM-class
monitor published by AirNow or StateAir. Khujand is therefore the one city whose labels carry
the measurement uncertainty the paragraph above cites, and it is also the city that
contributes no training rows -- so its fold reports low-cost labels scored against a model
that never saw them.

The mechanism matters for where this benchmark sits. Optical sensors size particles by light
scattering, so their response depends on humidity and on aerosol composition: Crilley et al.
(2018) attribute the dominant positive bias in this sensor class to hygroscopic growth, and
Barkjohn et al. (2021) show that removing the resulting bias needs a correction fitted
against reference monitors across a network. Neither condition is met here. The published
corrections are derived in humid, sulphate- and organic-dominated environments, and this
region is arid and dust-dominated, so their coefficients do not transfer; and Khujand has no
co-located reference instrument to fit a local correction against. We therefore report the
Clarity readings as published, label the fold, and treat its errors as carrying an
instrument-uncertainty component we cannot separate from model error.

Two consequences follow. First, results for the Khujand
fold are not comparable in kind to the other five and should not be read as a reference-grade
generalisation test. Second, the pre-registered 2-year span rule is satisfied
for these two stations only by counting observations after the benchmark record ends: inside
the window their spans are **1.09 y and 1.07 y**,
against a stated minimum of 2 y. Admitting them was a coverage decision, and it
is recorded here as one.

Leave-city-out stays the primary spatial protocol for one reason: it is available for all
6 cities. Leave-station-out is reported where possible and supports no headline
claim.

## 7.3 The model does not beat CAMS everywhere

4 of 6 leave-city-out folds reach significance before correction
and 3 after it. In **Ashgabat and Bishkek the sign is reversed**: at
Ashgabat, LightGBM returns 20.74 µg/m³ against CAMS at
18.83 µg/m³, DM statistic 1.17, *p* = 0.2420.
Read correctly, the two are indistinguishable there. CAMS does not win. Across the fold
set, the pooled result (< 0.0001) rests on
Almaty, Tashkent (*p* = 0.0050) and Dushanbe, the three folds that survive Holm
correction. Khujand is significant uncorrected and not after correction. Bishkek
(*p* = 0.8805) returns a marginally higher RMSE than CAMS, not a lower one, and the
difference is indistinguishable from zero either way.

Khujand is worth pausing on even though the correction removes it, since it is the fold
with no training label at all. Zero-shot transfer into an unmonitored city is not where a
reader would expect the method to hold up best, and it does not collapse there: the fold is
significant before Holm and the model's RMSE sits below the chemistry-transport model's. We
draw the weaker of the two available conclusions from that. It is evidence that the spatial
machinery is not simply memorising the training cities, and it is not evidence of an
improvement, because a correction the paper itself imposes takes the improvement away.

Ashgabat is the opposite case, and the one where the model has least to work with.
Turkmenistan operates no national monitoring network, so the fold reduces to a single
embassy instrument with no domestic context, and its nearest benchmark neighbour sits far
outside any plausible interpolation radius. Under exactly those conditions a
chemistry-transport model with a physical emissions inventory is a strong comparator. It
should be.

## 7.4 What carries the model, and how that changed

Section 6.4 reports mean absolute SHAP by feature family. On benchmark v1.1.0 the five
satellite products together account for **26.6%** of attribution, spatial
neighbour features for 20.4%, and static geography a further
21.8%. The top single feature is `doy_cos`.

**This reverses the ordering reported in earlier drafts of this work, and the reason is
instructive rather than incidental.** Under benchmark v1.0.0 the two Dushanbe records were
treated as separate stations when they are one instrument republished twice (Section 2,
D-012). Every other city therefore had an additional neighbour at effectively zero distance
from an existing one, which inflated the apparent value of spatial interpolation. Once the
duplicate is merged, satellite attribution overtakes it.

The earlier claim — that a study assembled around remote sensing was "really" a spatial
interpolator — was an artefact of a duplicated station. We state that plainly because it was
published as a finding reported against interest, and it is no longer supported. Three
qualifications apply to the current ordering.

1. *This is a property of the protocol as much as of the products.* Leave-city-out asks for
   a concentration where no monitor exists. Neighbour information is the most direct route
   to that answer, and satellite columns are a weak proxy for surface concentration under
   any protocol whatsoever.
2. *Missingness is informative but does not transfer between cities.* Retrieval-count
   features were promoted to predictors on the evidence that missingness is target-correlated.
   A validation-block ablation (Section 5.3) then showed they **hurt** leave-city-out
   generalisation, because retrieval success depends on local surface brightness, snow cover
   and solar geometry — properties of a particular city. They are excluded from Task N and
   retained for Task F. That is a finding about retrieval physics,
   and at the same time a measure of how little the retrieved values contribute.
3. *SO₂ is structurally absent in the season it exists to observe.* Retrieval needs
   ultraviolet signal; at these latitudes in December it falls to 0.1% against
   91.0% in July. The direct tracer for the region's dominant winter source is
   unavailable throughout that source's season, so its low attribution is partly a
   measurement-geometry artefact, not evidence that SO₂ carries no information.

We report the attribution as measured. A paper arguing that satellite remote sensing enables
air quality prediction in Central Asia would not be supported by these experiments.

## 7.4b Where the error is, and what it scales with

Leave-city-out error is not spread evenly, and the robust half of that statement is not the
obvious one. Fold RMSE does rise with the held-out city's mean concentration
(Spearman rho = 0.94), but RMSE scales with the variability of the target, and
dividing each fold's RMSE by that city's own observed standard deviation removes the relation
entirely (rho = -0.03). We report that rather than let the raw coefficient
stand for more than it shows.

What survives normalisation is the bias. It falls monotonically across every fold without
exception (rho = -1.00), from 14.4 µg/m³ in
Bishkek, the cleanest city in the benchmark, to -25.3 µg/m³ in
Dushanbe, the most polluted. That is the regression-toward-the-training-mean
signature: a model fitted on five cities and asked for a sixth predicts toward the levels it
was trained on, over-predicting clean cities and under-predicting dirty ones.

The same gradient holds inside the concentration range rather than only between cities. Bias
is 10.1 µg/m³ on days below the WHO 24-hour guideline and
-90.4 µg/m³ above six times it, where RMSE reaches
100.9 µg/m³ on the 6.6% of rows in that band. Seasonally,
winter RMSE is 51.0 µg/m³ against 16.0 µg/m³ in summer, which is the same
effect seen through the region's winter coal season.

This is a property of the region and the network rather than of one model, and it is the
clearest thing the benchmark shows: transferring a PM2.5 model to an unmonitored Central
Asian city fails first on the city's overall level, not on its day-to-day pattern. In the
terms of Section 3.1 it is an area-of-applicability statement measured rather than named.
Per-fold, per-band and per-season figures are in `t7_01`–`t7_03`.

## 7.5 Zero-drift reporting, and the drift it caught

Every number in this manuscript is a double-brace placeholder token resolved at render time
from `paper/tables/*.csv`. An unresolved placeholder is a hard build failure. A test also
checks a sample of manuscript figures directly against the CSVs, bypassing the intermediate
`numbers.json` entirely, so that a bug in the extractor cannot certify itself.

The mechanism earned its place during drafting. Section 2's missingness statistics were
originally transcribed from a console output. When they were finally banked to a table, the
transcribed values proved wrong: SO₂ retrieval had been written as 61.5% against a
recomputed 57.4%, and four further figures were off in the same direction.
The errors were small and none of them changed a conclusion, which is exactly why no reader
would ever have caught them. Regenerating the table also exposed that the two Section 2
tables had no producer script at all and could not be rebuilt by `make reproduce`. Both have
one now.

## 7.6 Scope of the record

- **The record ends before the source does.** Five of the ten contributing source feeds stop
  on 2025-03-04, when the StateAir publication channel closed, and at benchmark-station level
  **2 of 7 stations
  (8881, Bishkek) end there**; the rest survive through a longer-lived feed.
  **No result in this paper speaks to current conditions.** The monitors did not all stop,
  though: as of 2026-08-14 the same
  diplomatic-post instruments are still republished through AirNow at Ashgabat (to
  2025-09-24), Almaty (to 2025-11-14) and Dushanbe (still reporting). The record *can*
  therefore be extended for those cities, but doing so would change the benchmark and
  requires a version bump, not a silent refresh.
- **Kazakhstan contributes one city.** Astana failed the completeness rule at
  42.8% against a required 60%. The
  largest country in the region is represented by Almaty alone.
- **Six cities is a small spatial sample.** Fold-to-fold standard deviation
  (11.38 µg/m³) exceeds seed standard deviation
  (1.79 µg/m³) by roughly an order of magnitude. Conclusions are far more
  sensitive to which cities are in the set than to any training randomness.
- **ERA5 is oracle-only and incompletely retrieved.** Its measured latency (163 h) exceeds
  every evaluated horizon, so it cannot enter the deployable set. The multi-year retrieval
  was stopped once that was established.
- **One item of prior art is unresolved.** A 2025 conference abstract claims the first
  machine-learning PM2.5 prediction for Tashkent. The publisher page returns HTTP 403 and
  the record is absent from OpenAlex, Crossref, Semantic Scholar and Europe PMC, so **its
  split protocol could not be verified**. Section 1.4 states what we consequently do not
  claim. Should that work prove spatially stratified, the contribution of C1 narrows from
  "first such protocol in the region" to "first multi-city benchmark in the region". The
  benchmark is unaffected either way. Only the framing of its novelty moves.
- **Literature depth is uneven, and recorded as such.** Of 30 sources, 16 were read in full
  and 6 at abstract depth; 7 remain at snippet depth behind publisher paywalls. For those,
  bibliographic identity is verified against Crossref/OpenAlex but *content* claims are not
  independently confirmed. `research/LITERATURE.md` records the two axes separately rather
  than averaging them into a single confidence.
- **Russian-language coverage is incomplete.** CyberLeninka and eLIBRARY.RU are not indexed
  by the APIs used here, so the falsifier F4 verdict, that no equivalent regional benchmark
  exists in the Russian-language literature, remains provisional.

## 7.7 Train/serve skew is measured but not eliminated

The deployable set uses near-real-time satellite products while the benchmark is built on
standard-latency ones. These are different processing streams over the same instrument, and
we have not quantified the distributional difference between them. A service trained on
standard products and served NRT products is exposed to skew that this study bounds only
indirectly, through the small deployable/retrospective gap of Section 5.5. That gap is
evidence that latency-restricted *feature sets* cost little. It is not evidence that NRT and
standard versions of the same product are interchangeable. Quantifying the difference is the
most immediate piece of follow-up work, and it needs a parallel NRT archive we did not have.

## 7.8 What the benchmark is for

The headline modelling result is modest. R² = -0.04 at unmonitored
locations, no improvement over CAMS that separates from zero once cities rather than
station-days are treated as the unit of generalisation (paired *t* *p* =
0.1392; exact permutation *p* = 0.1250), and an attribution
profile in which no feature family dominates. We consider that the appropriate outcome.

The contribution is the fixed evaluation. Before this benchmark existed, a Central Asian air
quality result could be reported on a random split, with reanalysis features unavailable at
inference time, against no baseline ladder, scored with an exceedance F1 that a constant
already achieves (0.741 at a 61.8% base rate, because the region's
air is bad on most days, not because the classifier is good). Every one of those
choices would have produced a more impressive paper than this one. The splits are frozen and
checksummed. The protocol violations are enforced by failing tests rather than requested in
prose. The numbers above are what survives that. A future model that genuinely improves on
28.01 µg/m³ under this protocol will have demonstrated something
real.
