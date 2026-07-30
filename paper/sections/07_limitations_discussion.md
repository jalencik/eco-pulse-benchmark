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
(*p* = 0.0630, not significant) should be read with that in view, and we claim no
improvement there. Merging the feeds, which we do, reduces variance. It cannot manufacture a
label the two publishers agree on. **This limits the data source, not the pipeline, and no
modelling choice removes it.**

## 7.2 Leave-station-out covers a minority of the benchmark

4 leave-station-out folds exist and they span two cities.
**Almaty, Ashgabat, Bishkek, Tashkent each hold a single instrument**, so within-city station holdout is
undefined there.

The consequence runs deeper than reduced coverage. The Q6 timezone check compares
instruments within a city. In a single-station city, a constant lifelong offset is invisible
to every rule in the suite, and the QC output records that explicitly rather than returning
a pass that actually means "not tested". Four of six cities therefore rest on metadata
correctness for their time alignment. We regard this as the benchmark's largest unaudited
assumption.

Leave-city-out stays the primary spatial protocol for one reason: it is available for all
6 cities. Leave-station-out is reported where possible and supports no headline
claim.

## 7.3 The model does not beat CAMS everywhere

3 of 6 leave-city-out folds reach significance. In
**Ashgabat the sign is reversed**: LightGBM 21.34 µg/m³
against CAMS 20.75 µg/m³, DM statistic 0.35,
*p* = 0.7271. Read correctly, the two are indistinguishable there. CAMS does not
win. The honest summary of the fold set is that the pooled result (< 0.0001) rests on
Almaty, Dushanbe and Khujand, while Bishkek (0.0630) and Tashkent
(0.1180) post lower RMSE that never clears significance.

Khujand carrying part of the pooled result is worth pausing on, since it is the fold with no
training label at all. Zero-shot transfer into an unmonitored city is not where a reader
would expect the method to hold up best. It does, and we take that as the strongest evidence
in the paper that the spatial machinery generalises rather than memorising.

Ashgabat is the opposite case, and the one where the model has least to work with.
Turkmenistan operates no national monitoring network, so the fold reduces to a single
embassy instrument with no domestic context, and its nearest benchmark neighbour sits far
outside any plausible interpolation radius. Under exactly those conditions a
chemistry-transport model with a physical emissions inventory is a strong comparator. It
should be.

## 7.4 The satellite record is not what carries the model

Section 6.4 is the result we would most like to have come out differently. Spatial neighbour
features account for 32.5% of attribution and static geography a
further 25.1%. The five satellite products together account for
16.6%. The top single feature is `nbr_idw`,
inverse-distance-weighted neighbour concentration, at more than twice the second-ranked
feature.

**A study assembled around five remote-sensing products turns out, on inspection, to be
largely a well-tuned spatial interpolator with geographic priors.** Three qualifications
follow, none of which overturn that.

1. *This is a property of the protocol as much as of the products.* Leave-city-out asks for
   a concentration where no monitor exists. Neighbour information is the most direct route
   to that answer, and satellite columns are a weak proxy for surface concentration under
   any protocol whatsoever.
2. *Missingness outperforms the values.* Satellite missingness earns
   4.1%, comparable to the 5.1%
   contributed by the entire chemistry-transport forecast. *Whether* a retrieval failed is
   nearly as informative as what CAMS predicted. That is a finding about retrieval physics,
   and at the same time a measure of how little the retrieved values contribute.
3. *SO₂ is structurally absent in the season it exists to observe.* Retrieval needs
   ultraviolet signal; at these latitudes in December it falls to 0.1% against
   93.5% in July. The direct tracer for the region's dominant winter source is
   unavailable throughout that source's season, so its low attribution is partly a
   measurement-geometry artefact rather than evidence that SO₂ carries no information.

We report the attribution as measured. A paper arguing that satellite remote sensing enables
air quality prediction in Central Asia would not be supported by these experiments.

## 7.5 Zero-drift reporting, and the drift it caught

Every number in this manuscript is a double-brace placeholder token resolved at render time
from `paper/tables/*.csv`. An unresolved placeholder is a hard build failure. A test also
checks a sample of manuscript figures directly against the CSVs, bypassing the intermediate
`numbers.json` entirely, so that a bug in the extractor cannot certify itself.

The mechanism earned its place during drafting. Section 2's missingness statistics were
originally transcribed from a console output. When they were finally banked to a table, the
transcribed values proved wrong: SO₂ retrieval had been written as 61.5% against a
recomputed 59.2%, and four further figures were off in the same direction.
The errors were small and none of them changed a conclusion, which is exactly why no reader
would ever have caught them. Regenerating the table also exposed that the two Section 2
tables had no producer script at all and could not be rebuilt by `make reproduce`. Both have
one now.

## 7.6 Scope of the record

- **The reference network is closed.** Six of eight stations end on 2025-03-04 with the
  termination of the US diplomatic-post monitoring programme. **No result in this paper
  speaks to current conditions**, and the benchmark cannot be extended forward from this
  source.
- **Kazakhstan contributes one city.** Astana failed the completeness rule at 42.8%. The
  largest country in the region is represented by Almaty alone.
- **Six cities is a small spatial sample.** Fold-to-fold standard deviation
  (7.74 µg/m³) exceeds seed standard deviation
  (0.85 µg/m³) by roughly an order of magnitude. Conclusions are far more
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

The headline modelling result is modest. R² = 0.07 at unmonitored
locations, a significant but not transformative improvement over CAMS, and an attribution
profile dominated by spatial interpolation. We consider that the appropriate outcome.

The contribution is the fixed evaluation. Before this benchmark existed, a Central Asian air
quality result could be reported on a random split, with reanalysis features unavailable at
inference time, against no baseline ladder, scored with an exceedance F1 that a constant
already achieves (0.764 at a 64.8% base rate, because the region's
air is bad on most days rather than because the classifier is good). Every one of those
choices would have produced a more impressive paper than this one. The splits are frozen and
checksummed. The protocol violations are enforced by failing tests rather than requested in
prose. The numbers above are what survives that. A future model that genuinely improves on
25.70 µg/m³ under this protocol will have demonstrated something
real.
