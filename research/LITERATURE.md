# Literature Review — Phase 0

Date of search: 2026-07-28. Searched in English and Russian.

## How to read this file

Every source carries a **verification depth**. This is not bureaucratic decoration: a
review that presents full-text reading and search-engine snippets at equal confidence is
misleading in exactly the places most likely to be wrong.

| Depth | Meaning |
|---|---|
| **FULL** | PDF or full HTML retrieved and read |
| **ABSTRACT** | Publisher abstract/landing page retrieved |
| **SNIPPET** | Only search-result summary seen. **Claims from these sources are provisional and are not load-bearing in `GAP.md`.** |

**Depth and citation-verification are separate axes** (added 2026-07-30). A source can have
an authoritative DOI and a confirmed author list while its full text stays behind a
paywall. Conflating the two made paywalled sources look uncitable when in fact only their
*content claims* were provisional, never their identity. Bibliographic metadata is now
resolved through scholarly APIs and marked **citation verified**; depth continues to record
only what was actually read.

Several ScienceDirect and MDPI pages returned HTTP 403, so full text remains unavailable
for some entries. Their bibliographic records were recovered via Crossref/OpenAlex — see
§F. Content claims from SNIPPET sources still require institutional access before the paper
relies on them.

---

## A. Central Asia — regional evidence

| # | Source | Depth | What it establishes | Splits / protocol |
|---|---|---|---|---|
| A1 | **OpenAQ, *Air Quality Data: Central Asia* (2025 regional snapshot of the 2024 Global Landscape report)** | **FULL** | The data-sparsity premise, quantified. See below — the single most important source for this project. | n/a (policy report) |
| A2 | **Tursumbayeva, Muratuly, Baimatova & Karaca**, *Cities of Central Asia: New hotspots of air pollution in the world*, **Atmospheric Environment** 2023, `10.1016/j.atmosenv.2023.119901` | SNIPPET (citation verified) | Six capitals (Almaty, Astana, Ashgabat, Bishkek, Dushanbe, Tashkent) exceed the WHO annual guideline by **4.3–12.6×**. Winter peaks in Almaty/Bishkek/Astana; winter *and* summer in Tashkent/Dushanbe. Coal combustion, not transport, is the dominant PM2.5 source — contradicting official inventories. Explicitly notes "limited studies and knowledge" for the region. | Descriptive + HYSPLIT back-trajectories. **No ML, no predictive splits.** |
| A3 | Guttikunda, *A Multi-Pollutant Emissions Inventory ... for Bishkek*, **Zenodo 12720883** (2024), CC-BY | **FULL** | Gridded 2018 emissions inventory, WRF met, CAMx output, GIS layers, **and ambient monitoring: Clarity sensors (2021) + US Embassy (2019–2024)**. ~5,500 t/yr PM2.5 → 48 µg/m³ annual mean. | **No train/test splits. Not an ML benchmark.** Usable as an emissions-proxy predictor and as a source-apportionment cross-check. |
| A4 | *Validation and comparison of high-resolution MAIAC aerosol products over Central Asia*, **Atmospheric Environment** 2021 | SNIPPET | Direct MAIAC validation for the study region. **High priority for full-text retrieval** — it bears directly on whether PR-1 is usable here. | Validation against AERONET, not a prediction task |
| A5 | *Dominant sources of PM2.5 in Kazakhstan's urban cities: PMF and HYSPLIT*, 2025 | SNIPPET | Source apportionment, Kazakhstan | PMF, not predictive |
| A6 | *Air quality challenges in Central Asian urban areas: PM2.5 source apportionment in Dushanbe, Tajikistan* | SNIPPET | Dushanbe source apportionment | PMF, not predictive |
| A7 | Banks et al., *Impacts of the Desiccation of the Aral Sea on the Central Asian Dust Life-Cycle*, **JGR: Atmospheres** 2022 | SNIPPET | Aralkum dry bed added **~7% more dust** over Central Asia in the 2000s–2010s vs. the 1980s–1990s; south-eastward transport bands from the southern basin. Justifies the "distance to Aral bed" static predictor and the dust-regime error analysis. | n/a |
| A8 | *Characteristics of salt dust aerosols and their transport implications in the Aral Sea*, **Scientific Reports** 2025 | SNIPPET | Salt-dust events peak in **spring**, less in autumn/winter — a distinct regime from the winter coal-heating peak. Two separate aerosol regimes must be modelled and error-analysed separately. | n/a |
| A9 | *Particulate Matter (PM2.5) Prediction in Tashkent Using Machine Learning*, **ECAS 2025** (MDPI Sciforum, 30 May 2025) | SNIPPET (403 on full text) | Claims **first** ML PM2.5 prediction for Tashkent. Ten automated stations, weather + seasonal features. | **Unknown split protocol — critical to verify.** Single city; no spatial transfer. |

### A1 in detail — the data-sparsity premise, quantified

This report is the empirical backbone of the project's motivation, and it also *changes the
benchmark design*. Of the five Central Asian countries:

- **4 of 5 (80%) generate air quality data regularly. Turkmenistan does not** — it is the
  only country with *no national-level air quality monitoring*, population 6.5 million.
- **3 of 5 (60%) publicly share** what they generate.
- **Kazakhstan shares its data only with people physically located inside Kazakhstan.**
- **Only Kyrgyzstan shares in a fully open, transparent manner.**
- Tajikistan has monitored since ~2022 and **began sharing only in 2024**.
- Stated barrier: resource constraints — finance and technical expertise.
- The *Air Quality Central Asia* platform supports monitoring in KZ, KG, UZ, TJ.

OpenAQ's own criteria for "fully open" are worth adopting verbatim as a benchmark
inclusion standard: physical units (**an AQI alone does not suffice**), station-specific
coordinates, daily or sub-daily frequency, machine-readable format.

**Three design consequences, carried into Phase 1:**

1. **Turkmenistan cannot supply national ground truth.** If Ashgabat appears in the
   benchmark at all, it is via the US Embassy monitor alone.
2. **Kazakhstan's geo-restriction is a reproducibility hazard.** An open benchmark cannot
   depend on data a third party outside Kazakhstan cannot retrieve. Kazakh stations enter
   only through an independently retrievable path (OpenAQ mirror or US Embassy), and the
   provenance is recorded per station.
3. **The US Embassy network is the only consistent multi-country reference in the region.**
   That elevates GT-2 from "nice supplementary data" to the benchmark's spine, and it is
   why A2 could cover Ashgabat at all despite no national network existing there.

---

## B. Benchmarks and split protocol — the methodological core

| # | Source | Depth | Relevance |
|---|---|---|---|
| B1 | Betancourt, Stomberg, Roscher, Schultz, Stadtler, **AQ-Bench**, *Earth Syst. Sci. Data* 13:3013, 2021 | ABSTRACT | **The precedent for an ML air quality benchmark.** 5,577 stations worldwide, 2010–2014. Task: station metadata → long-term **ozone** metrics. Split: 60/20/20 with **spatial clustering at a 50 km threshold**. Baselines: linear regression, 2-layer MLP, random forest (RF best). |
| B2 | *A review of machine learning for modeling air quality: Overlooked but important issues*, **Atmospheric Research** 2024 | SNIPPET (403) | Directly the methodological critique this project is built around: feature engineering, class imbalance, validation strategy. **High priority for full-text retrieval.** |
| B3 | *Assessing and Validating the Ability of ML to Handle Unrefined Particle Air Pollution Mobile Monitoring Data Randomly, Spatially, and Spatiotemporally* (PMC9408314) | SNIPPET | Compares random vs. spatial vs. spatiotemporal CV on the same data — the empirical demonstration that random splits inflate scores. |
| B4 | *Distributional bias compromises leave-one-out cross-validation* (PMC11177965) | SNIPPET | Caution that LOO-style protocols have their own failure mode; relevant to leave-station-out design. |
| B5 | AirDelhi | SNIPPET | Fine-grained spatiotemporal PM benchmark for Delhi. Second benchmark precedent. |

### How AQ-Bench differs from what is proposed here

This is the closest thing to a precedent, so the distinction must be exact and stated in
the paper rather than glossed:

| | AQ-Bench (2021) | This benchmark |
|---|---|---|
| Pollutant | Tropospheric ozone | **PM2.5** |
| Target | Long-term aggregated metrics | **Hourly/daily concentrations** |
| Task | Static metadata → metric (time-independent) | **Nowcasting + short-horizon forecasting** |
| Region | USA, Europe, East Asia | **Central Asia (absent from AQ-Bench)** |
| Spatial protocol | 50 km spatial clustering | **Leave-city-out + leave-station-out** |
| Temporal protocol | None (time-independent task) | **Blocked, with purge gap** |

AQ-Bench's 50 km spatial-clustering threshold is a defensible precedent for the
leave-station-out design and should be cited as such rather than reinvented.

---

## C. Transfer learning and data-poor regions

| # | Source | Depth | Findings |
|---|---|---|---|
| C1 | **Gupta, Park, Bi, Gupta, Züfle, Wildani, Liu — *Spatial Transfer Learning for Estimating PM2.5 in Data-poor Regions*, ECML-PKDD 2024** (arXiv 2404.07308v2) | **FULL** | **The closest published work to contribution C2.** Proposes a *Latent Dependency Factor* (LDF) capturing spatial/semantic dependencies between source and target domains, generated by a two-stage autoencoder over clusters of similar source/target data, then appended to both feature spaces. Reports **19.34% improvement over baselines**. Evaluation: **10 target sensors with eastern-US source data.** |
| C2 | Jin, Ding, Ge, Liu, Xie, Zhao, Zhao — *Machine learning driven by environmental covariates to estimate high-resolution PM2.5 in data-poor regions*, **PeerJ** 2022 | **FULL** | **The closest environmental analogue to this study region.** Xinjiang, NW China: arid, Taklimakan dust, >1.6M km², 41 stations across 16 cities, hourly 2015–2021, 8-day averaging (n ≈ 1,258–1,398/yr). Nine covariates (AOD, DEM, NDVI, drought index, surface pressure, radiation, wind speed, RH). Random Forest beat Bagging: R² 0.728–0.813. **Limitations stated by the authors: winter inversion accuracy poor because snow cover blocks AOD retrieval; northern Xinjiang has data gaps; extrapolation beyond Xinjiang needs local validation.** |
| C3 | *Explainable PSO-optimised ML for multi-pollutant forecasting in major African cities with transfer learning*, Frontiers 2026 | SNIPPET | Transfer learning in another data-sparse region |
| C4 | *An Improved Hybrid Transfer Learning-Based Deep Learning Model for PM2.5*, Applied Sciences 2022 | SNIPPET | MMD used to select which source station best transfers to a target |
| C5 | Foundation-model / zero-shot PM work (2026) | SNIPPET | Time-series foundation models applied zero-shot are reported competitive at unseen sites. **The field is moving; a 2026 paper must address whether a zero-shot TSFM baseline belongs on the ladder.** |

### Why C1 (Gupta et al.) does not pre-empt this project — and where it constrains it

It is a **method** paper at an ML venue (ECML-PKDD), not a benchmark, and its evaluation is
**10 target sensors** against eastern-US source data. It does not touch Central Asia, does
not define a reusable public split, and does not evaluate under leave-city-out over a
region. It is prior art for the *idea* of spatial transfer for PM2.5 — which means C2's
novelty **cannot** be "we apply transfer learning to PM2.5 in a data-poor region." That
sentence is taken. What remains available is the evaluation protocol and the region.

### Why C2 (Xinjiang) is the most important methodological warning

Xinjiang is the closest environmental analogue available: arid, dust-dominated, sparse
stations, continental winter inversions. Two things follow.

1. **Its validation is 10-fold cross-validation with no stated spatial stratification.**
   With 41 stations in 16 cities and 8-day-averaged samples, ordinary k-fold puts
   observations from the same station — and often the same 8-day window — on both sides of
   the split. Its R² of 0.728–0.813 is therefore **not comparable** to a leave-city-out
   number and must never be cited as a target to beat. This is precisely the flaw the
   benchmark exists to make impossible, and it is a concrete, citable example.
2. **Its stated failure modes predict ours.** Snow cover defeating AOD retrieval during
   exactly the winter-inversion episodes that matter most for health is a structural
   problem, not a tuning problem, and it will recur in Almaty, Astana and Bishkek.

---

## D. MAIAC AOD over bright/arid surfaces (Phase 0 question 4)

Synthesised from A4 and the MAIAC validation literature (mostly SNIPPET depth — flagged
for re-verification):

- MAIAC handles bright surfaces **better than earlier algorithms** through explicit BRDF
  characterisation and time-series separation of surface from aerosol, and has demonstrated
  retrievals over bright desert (e.g. Solar Village, Saudi Arabia).
- **But** accuracy is still lower over arid than vegetated surfaces, and there is **large
  bias under high loading of coarse particles** — i.e. exactly during dust events.
- Lofted dust causes **AOD underestimation**.
- **Missingness is not random.** Retrievals are preferentially absent during dust storms,
  snow, and heavy cloud.

**The consequence for this project is severe and must be designed for, not discovered
later.** MAIAC missingness is correlated with the target: AOD tends to be missing exactly
when PM2.5 is extreme. Any model that drops missing-AOD rows silently conditions on
"retrieval succeeded," which biases evaluation toward calm, clear, low-concentration days
and produces an optimistic headline number. Missingness must therefore be treated as an
informative feature and reported as a stratum in the error analysis — never dropped.

---

## E. Venues (Phase 0 question 5)

The regional work clusters in **Atmospheric Environment** (A2, A4). Source apportionment
appears in Elsevier environmental titles; the benchmark precedent (B1) is in **ESSD**; the
closest method paper (C1) is at an **ML venue** (ECML-PKDD).

What the environmental-science papers contain that a generic ML paper does not: physical
source attribution (PMF, HYSPLIT back-trajectories), explicit seasonal/meteorological
regime analysis, and comparison against emissions inventories. A submission to APR / EM&S /
STOTEN that is only a model comparison will read as out of place. The dust-regime and
inversion-regime error decomposition is therefore not optional garnish — it is the part
that makes the work legible to the target venue.

**ESSD is a serious candidate for C1 specifically**, given AQ-Bench's precedent there.

---

## F. Methodological sources for the machinery this repository already uses

Every statistical method the code implements is cited to its originating source rather than
to a secondary description. These were resolved by exact-title lookup (`M1`–`M12` in
`scripts/fetch_literature.py`), not topical browsing.

| Ref | Work | Used in this repo for |
|---|---|---|
| M1 | Roberts et al., *Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure*, **Ecography** 2016 | The canonical justification for blocked and leave-city-out splits over random k-fold |
| M2 | Meyer et al., *Importance of spatial predictor variable selection in machine learning*, 2019 | Why spatially-derived predictors need spatial validation |
| M3 | Diebold & Mariano, *Comparing Predictive Accuracy*, 1994/1995 | The DM test itself |
| M4 | Harvey, Leybourne & Newbold, *Testing the equality of prediction mean squared errors*, **IJF** 1997 | The small-sample HLN correction applied to every DM statistic |
| M5 | Newey & West, *A Simple, Positive Semi-Definite... Covariance Matrix*, **Econometrica** 1987 | HAC variance under the derived truncation lag |
| M6 | Probst, Wright & Boulesteix, *Hyperparameters and tuning strategies for random forest*, 2019 | Tuning protocol on the 2023 validation block |
| M7 | Xu et al., *Evaluation of machine learning techniques with multiple remote sensing...*, **Env. Pollution** 2018 | Satellite-to-PM2.5 estimation precedent |
| M8 | Zheng et al., *Field evaluation of low-cost particulate matter sensors*, **AMT** 2018 | Low-cost sensor uncertainty, bearing on the excluded-station pool |
| M9 | Inness et al., *The CAMS reanalysis of atmospheric composition*, **ACP** 2019 | The CAMS baseline rung and its debiasing |
| M10 | Ke et al., *LightGBM*, NeurIPS 2017 | The GBDT implementation (no DOI exists; NeurIPS proceedings) |
| M11 | Lundberg & Lee, *A Unified Approach to Interpreting Model Predictions*, 2017 | SHAP attribution in Section 6 |
| M12 | Zang et al., *Estimating ground-level PM2.5 concentrations*, 2017 | AOD-to-surface-PM2.5 precedent |

### Resolved bibliographic records

Generated from `research/sources.json` by `scripts/build_literature_table.py` — see
[`SOURCES_TABLE.md`](SOURCES_TABLE.md). Hand-typed citations drift from their sources
exactly as hand-typed numbers do, so the reference table is produced, not written.

### Two failure modes the resolver had to be hardened against

Both were caught by spot-checking output that looked entirely reasonable.

1. **Relevance is not identity.** Taking the top search hit resolved "PM2.5 prediction in
   Tashkent using machine learning" to a study of the **Brazilian Cerrado** — every generic
   term matched and only the place name did not. Targets defined by a proper noun now
   require that noun outright, and A9 is honestly `UNRESOLVED` rather than wrong.
2. **Fields must not be merged across records.** Combining APIs field-by-field paired
   OpenAlex's title for the LightGBM paper with a Crossref DOI belonging to an unrelated
   *Natural Resources Research* article. A correct title with a wrong DOI is the most
   dangerous citation error, because nothing about it invites checking. Merging now
   requires DOI agreement or near-exact title identity, and 7 rejected cross-source merges
   are recorded in `sources.json`. Fixing this **reduced** the FULL count from 12 to 8
   before other gains — several "full texts" had been open-access links belonging to
   different papers.

---

## Gaps in this review — to close before submission

**Revised 2026-07-30.**

1. **Resolved.** A2, A4, B2 and A5 are no longer citation-blocked: authors, venue, year and
   DOI are confirmed via Crossref/OpenAlex, and **A2's attribution was wrong in this file**
   — recorded as "Kulkarni et al. (?)", it is Tursumbayeva, Muratuly, Baimatova & Karaca.
   Full text is still paywalled, so their *content* claims remain provisional.
2. **A9 (Tashkent ML) is not indexed in any of the four APIs.** It is an ECAS 2025 Sciforum
   conference abstract, and the resolver correctly refuses to guess. Its split protocol
   therefore remains **unknown**, and Section 1 must not assert what that paper did. This is
   the one gap that still constrains the related-work text.
3. **Russian-language search still returned portals and news, not research.** CyberLeninka /
   eLIBRARY.RU are not covered by these APIs. The F4 verdict remains **provisional**.
4. **Uzhydromet / Kazhydromet primary sources** not yet examined for data availability.
5. **Count: 30 distinct sources** — 29 attempted through the resolver, plus A1 (an OpenAQ
   policy report, not a journal article) carried forward from Phase 0. 26 carry an
   authoritative DOI; the exceptions are LightGBM, which has none, and the two grey-
   literature items. Depth across all 30, taking the better of API depth and what was
   actually read in Phase 0: **16 FULL, 6 ABSTRACT, 7 SNIPPET, 1 UNRESOLVED**. The master
   spec's 15–25 sources with full extraction is **met at 16 FULL**; the 7 SNIPPET entries
   are paywalled full texts whose citations are nonetheless verified.
