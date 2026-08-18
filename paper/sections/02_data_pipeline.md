# 2. Data, Operational Constraints, and Informative Missingness

## 2.1 Ground truth

PM2.5 comes from 7 instruments across 6 cities: Almaty,
Ashgabat, Bishkek, Dushanbe, Khujand and Tashkent. **5 are
US diplomatic-post reference monitors and 2 are Clarity low-cost
sensors (Khujand)** — see Section 7.2. The embassy monitors are the only consistent
multi-country reference in the region and the sole route to any measurement in Turkmenistan.

That network contracted sharply in March 2025, when the StateAir publication channel closed.
Five of the ten contributing source feeds stop on 2025-03-04, and after co-published feeds
are merged **2 of 7 benchmark stations
(8881, Bishkek) end there**; the rest survive through a longer-lived feed.
Reporting states that seventeen years of archive were subsequently removed from the
originating platform.

The closure was not uniform, and an earlier claim here that the programme had simply ended is
withdrawn. A live query on 2026-08-14 found three of the same diplomatic-post monitors still
republished through the AirNow provider after the StateAir channel closed — Ashgabat to
2025-09-24, Almaty to 2025-11-14, and Dushanbe still reporting — with measurements retrieved
and verified rather than inferred from metadata. The record this benchmark curates is
nevertheless fixed: the panel is frozen, the test year is 2024, and extending it
would change the benchmark and require a version bump rather than a refresh.

**Quality control was pre-registered before the data were inspected**, so no rule could be
tuned to improve a count. Seven rules cover physical range, flatlining, zero-runs, unit
sanity, duplicate identity, timezone correctness and completeness. Two produced findings
worth reporting.

*Duplicate identity, and the case distance could not see.* The embassy monitors are published
twice — once by StateAir, once by AirNow — under distinct identifiers 57 m apart in Bishkek
and 40 m in Ashgabat. Exact coordinate matching does not catch this. Under leave-station-out
the held-out station would have been the same physical device as one in training. Detection is
therefore distance-based at 150 m.

**A distance rule cannot catch the inverse case, and this benchmark contained one.** Dushanbe
was published by the same two programmes, but its two records carry coordinates **6.06 km
apart**, so the 150 m rule passed them and an earlier version of this manuscript cited that
separation as evidence the sites were distinct. They are not. Over the 33,462 hours in which
both report, **94.0% of readings are bit-identical**, and of the remainder 99.9% match exactly
at a five-hour offset — Dushanbe is UTC+5, so those are the same measurements timestamped in
local time rather than UTC. **99.99% of overlapping hours are the same reading.** The
comparable Khujand pair, 14.4 km apart, is bit-identical on 0.3% of hours.

A second rule (Q5c) was therefore added: flag any station pair whose overlapping observations
are bit-identical on more than half of samples, regardless of separation. Two independent
instruments do not agree to floating point. The Dushanbe records are merged under the same
precedence-and-gap-fill rule already applied to Bishkek and Ashgabat, giving
7 instruments rather than eight, and the benchmark is versioned **1.1.0** to mark
that the split changed. Sections 6 and 7 report how the modelling results moved as a result;
they moved against the model.

*Timezone correctness.* Metadata offsets are not trusted. Each station's diurnal composite is
cross-correlated against a regional reference, and an initial implementation rejected both
Khujand sensors for an apparent 12-hour shift. Investigation showed the regional reference
self-correlates at r = +0.71 under a 12-hour rotation, because Central Asian urban PM2.5 is
bimodal with peaks roughly half a day apart. Whole-shape correlation cannot separate a
half-day offset from none in such a signal. The check now reports lag identifiability and
flags rather than rejects when the hypothesis is not distinguishable — a station was nearly
deleted by a discriminator reporting an artefact.

**Figure 1** shows the station geography; marker area is proportional to the number of
retained hourly observations.

![Figure 1](figures/fig1_study_area.png)

**Figure 1.** Benchmark stations across Central Asia. Marker area is proportional to the
number of retained hourly observations. Six cities span five countries; Turkmenistan
(Ashgabat) and Kazakhstan (Almaty) contribute one station each.

## 2.2 The splits

Train 2018-11-27 to 2022-12-31; validation 2023-01-11 to 2023-12-21; test
2024-01-01 to 2024-12-31. Purge gaps of 240 hours separate the blocks.

**The purge is derived, not chosen.** A training sample at *t* reads features over
[*t*−max_lag, *t*] and predicts *t*+*h*, so the gap must satisfy purge ≥ max_lag +
max_horizon = 168 + 72 = 240 hours. A test
recomputes this from the model definitions, so introducing a model with a longer feature
window fails the build rather than silently leaking across the boundary.

**Test year 2024 is forced by the embassy shutdown.** It is the last complete year
with reference-grade coverage. A post-shutdown block would cover two cities, not six.

**Khujand contributes no training rows at all.** Both its stations begin in late 2023, after
the training block closes, so Khujand appears only in validation and test. This passed the
completeness rule because that rule checks span and coverage, not overlap with the training
block. We retain it deliberately: it constitutes a pure zero-shot spatial transfer fold, in
which the model has no local history in any form. Its fold is strictly harder than the
others and is reported separately rather than averaged in.

## 2.3 Operational availability as a typed property

Reanalysis products describe exactly the quantities that drive PM2.5, are better documented
than their forecast counterparts, and already sit in most atmospheric pipelines. A model
consuming ERA5 boundary-layer height to predict tomorrow's air quality will post an
excellent number and cannot be deployed. Nothing in its RMSE looks wrong.

Availability is therefore declared per feature and enforced by test. Every measured latency
in this study is given in Table 2.1; **three of five initial estimates were wrong, one by
more than three orders of magnitude.**

| Product | Claimed | Measured | Status |
|---|---:|---:|---|
| MAIAC AOD (Earth Engine, MCD19A2.061) | 6 h | ~8 days | oracle only |
| Sentinel-5P AAI (OFFL) | 5 h | ~72 h | oracle only |
| Sentinel-5P AAI (NRTI) | — | < 24 h | deployable |
| CAMS forecast PM2.5 | 12 h | ~10 h | **deployable** |
| ERA5 reanalysis | ~5 days | 163 h | oracle only |
| VIIRS active fire (v001) | 4 h | **774 days** | superseded |

The VIIRS case is the instructive one, and the latency was the lesser problem. The
originally-mapped collection is deprecated and its final asset falls on 2024-06-16 — dead
centre of the frozen test year, giving 161 images in January–June and **zero** in
July–December. A model using it would have seen fire signal for half the test period and
structurally none for the other half, producing an apparent regime change on 1 July that
invites a meteorological explanation for a dead data feed. A latency check catches the 774
days; only a coverage check against the *frozen* test block catches the mid-block
termination. Both are now enforced.

CAMS products derive from the Copernicus Atmosphere Monitoring Service assimilation and
forecast system (Inness et al., 2019). CAMS requires a second operational distinction: forecast step zero has assimilated
observations at the valid time, so using it to predict that time is lookahead wearing a
forecast label. All CAMS features use the 24-hour lead, which is what a live service holds.

## 2.4 The R7 phenomenon: missingness correlated with the target

Two aerosol regimes operate here and fail retrieval differently: winter coal combustion,
and spring salt-dust transport from the desiccated Aral bed (Banks et al., 2022; Liu et
al., 2025).

Satellite retrieval does not fail at random. It fails during dust, cloud and snow — the
conditions that accompany the highest concentrations. Dropping incomplete rows therefore
conditions the evaluation on *"retrieval succeeded"* and biases every result toward calm,
clear, low-concentration days.

We quantified this across all five satellite features on daily station-matched data. Each
satellite product is extracted onto a complete station × date grid — the compositor emits a
fully-masked image on days with no usable granule rather than omitting the row — so a failed
retrieval is a masked cell, not an absent one, and the grid is the denominator. Rates below
are conditional on the station-day also carrying a ground observation, since that is the
subset on which the association can be tested at all.

| Feature | Retrieval | Δ median PM2.5 on missing days | *p* | Retrieval on worst decile |
|---|---:|---:|---:|---:|
| Sentinel-5P SO₂ | 57.4% | **+10.3** | 1.6e-138 | **14.0%** |
| MAIAC AOD | 62.9% | +5.6 | 1.4e-44 | 38.1% |
| Sentinel-5P NO₂ | 70.7% | +3.3 | 1.7e-14 | 58.0% |
| Sentinel-5P CO | 81.1% | +2.6 | 7.2e-05 | 81.9% |
| Sentinel-5P AAI | 99.8% | +6.8 | 0.75 | 99.9% |

**SO₂ is blind in the season it exists to observe.** It retrieves on 0.1% of December days against
91.0% in July. Retrieval requires ultraviolet signal, and
at 38–43°N in December the solar zenith angle leaves too little; this is a geometric floor,
not a cloud accident. The direct tracer for the region's dominant winter source is
unavailable throughout that source's season. Additionally, 29.8% of the
retrievals that do occur are negative, sitting below the noise floor — clipping them at zero
would bias the coal tracer upward across a third of its observations.

MAIAC has been validated specifically over Central Asia (Chen et al., 2021), which is why
it was selected over coarser aerosol products.

**The split between clean and contaminated features follows retrieval physics.** CO uses the
2.3 µm shortwave-infrared band and AAI uses ultraviolet reflectance *ratios* rather than
absorption depth; both survive winter geometry and cloud, and neither shows target-correlated
missingness. MAIAC (visible/near-infrared) and the ultraviolet absorption retrievals do not.

**The two clean features are complementary to the contaminated ones.** AOD and AAI are both
present on 62.8% of station-days; AAI alone covers a further 36.9%; neither
is available on 0.1%. Usable satellite coverage therefore rises from
62.8% to 99.9%, and the coverage AAI
adds is concentrated precisely where MAIAC fails.

Consequently missingness is **modelled, never dropped**. Valid-pixel counts are promoted to
features in their own right. They are retained for Task F but **excluded from Task N** — see
Section 5.3, where an ablation showed retrieval-count features to be city-specific rather than
transferable. Section 6 reports attribution for the features actually used, which is
total SHAP attribution — comparable to the 9.0% contributed by the
full chemistry-transport model — confirming that *when* a retrieval failed carries
information about the atmosphere.
