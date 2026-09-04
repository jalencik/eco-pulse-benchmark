# 1. Introduction

## 1.1 The gap

Central Asia is among the most polluted inhabited regions on earth. It is also among the
least instrumented. Tursumbayeva et al. (2023) put annual PM2.5 in six regional capitals at
4.3–12.6 times the WHO 2021 guideline and trace the burden mainly to coal combustion rather
than transport, contradicting the official emissions inventories. Source-apportionment studies across the region reach the same conclusion independently, in
Kazakhstan (Tursun et al., 2025) and Tajikistan (Papagiannis et al., 2024). The monitoring
base under those numbers is thin and unevenly open. Turkmenistan runs no national air quality network
at all. Kazakhstan releases its data only to users physically inside the country. Only
Kyrgyzstan publishes in a fully open form (OpenAQ, 2025).

Estimates are not what the region lacks. Global gridded products already assign PM2.5 values
across Central Asia, and the epidemiological literature consumes them. What nobody can do is
check those estimates, or set two methods against each other on identical terms. There is no
open station-level benchmark for the region. No frozen splits, no declared protocol, no
shared evaluation.

The cost of that absence is measurable. Consider the closest environmental analogue in the
literature: PM2.5 estimation across Xinjiang, an arid, dust-affected, sparsely monitored
region much like this one. Jin et al. (2022) report R² between 0.73 and 0.81 under 10-fold
cross-validation with no spatial stratification. With 41 stations in 16 cities and 8-day
averaging, that design places observations from the same station, frequently the same
window, on both sides of the split. The number answers one question. How well can we
interpolate among stations we already have? Readers take it as answering a different one:
how well can we estimate where no monitor exists? Nothing in a reported R² separates the two.

This is not a complaint about one paper. Roberts et al. (2016) show that spatially,
temporally or hierarchically structured data require blocked validation, because ordinary
k-fold leaves dependence straddling the split. Meyer et al. (2019) demonstrate the same for
spatially derived predictors. Alazmi and Rakha (2022) measure the effect directly on
particulate data, running random, spatial and spatiotemporal cross-validation side by side.
Tang et al. (2024) place validation strategy among the systematically overlooked issues in
air quality machine learning. The methodological position taken here is therefore not new.
What the region has never had is a benchmark that enforces it.

## 1.2 What this paper contributes

AQ-Bench (Betancourt et al., 2021) is the precedent: 5,577 stations worldwide, split by
spatial clustering at a 50 km threshold. It targets long-term ozone metrics from station
metadata, a time-independent regression, and it excludes Central Asia entirely. We borrow
its spatial clustering rationale for leave-station-out instead of inventing a second one,
and diverge on pollutant, target, temporal protocol and region. Section 3 states the
differences precisely. AirDelhi (Chauhan et al., 2023) offers a second precedent for
fine-grained particulate benchmarking, confined to a single city.

**C1 — a benchmark.** 7 stations across 6 cities. Splits were frozen
and hashed before the results reported here were produced: blocked-temporal with a derived purge gap,
leave-city-out over 6 folds, and leave-station-out where station density
allows it (2 folds; Almaty, Ashgabat, Bishkek, Dushanbe, Tashkent hold one instrument each and are named
ineligible, not quietly dropped). A test enforces immutability. It fails for the
authors exactly as it fails for anyone else.

**C2 — transfer evaluated without flattery.** We offer no new method. We measure how far
spatial transfer survives into an aerosol regime unlike the source domain, under a protocol
the region has never applied. That framing makes a negative result publishable. Several of
ours are negative.

One fold deserves naming here. Khujand's stations begin after the training block closes, so
the city contributes no training label anywhere in the record. Not one row. The model arrives
with no local history of any kind and has to return a concentration regardless. This is the
harshest test the benchmark contains, and it is also the one that matches the deployment
case the work exists for: an unmonitored city asking for a number it has never been given.
A model that collapses on Khujand has not earned the right to be deployed anywhere new. We
report the fold on its own. Averaging it into the other five would report neither.

Estimating surface PM2.5 from satellite columns is itself an established line of work
(Zang et al., 2017; Xu et al., 2018); what is new here is subjecting it to a spatial
protocol that withholds whole cities.

**C3 — an operational-constraint account.** Every predictor carries a measured latency and a
typed availability flag. Anything that cannot exist at prediction time is barred from
deployable configurations by test rather than by convention.

## 1.3 Findings that shaped the work

Three results shaped the work that follows.

**A constant is hard to beat, and that says more about the region than about the models.**
No credential-free nowcaster beat a trivial always-exceed predictor on health-relevant
exceedance. The reason is uncomfortable and entirely physical: PM2.5 in these cities clears
the WHO 24-hour guideline on most days of the year, so a classifier that never varies is
correct most of the time. Chronic pollution, not modelling skill, sets that floor. Beating
it is the only evidence that a model has learned something past the regional mean. Raw CAMS,
a full chemistry-transport model, is improved simply by subtracting a per-city constant, and
even after that correction it reaches only R² -0.11. Across two
phases, every baseline we tried sat below the accuracy of predicting the held-out city's own
mean.

**Metric choice reverses conclusions.** RMSE and exceedance skill rank the same models in
nearly opposite orders. Smoothing toward the mean lowers squared error while destroying the
variance needed to tell a bad day from a good one, so a model wins one metric by losing the
other. Report either alone and the ladder comes out backwards for the other task.

**The headline modelling result is mixed, and both halves are reported.** Tuned gradient
boosting with spatial neighbour encodings reaches RMSE 28.01 ±
0.35 µg/m³ at unmonitored locations, ahead of every admissible
baseline — including inverse-distance weighting at 29.44 µg/m³, a
margin of 1.43 µg/m³. That is a real result on error.

It is not a result on skill. Mean per-fold R² is -0.04, ranging
-0.55 to 0.52, with 3 of 6 folds
negative — in those cities the model does worse than a flat line through the city's own mean.
Ranking first on RMSE while explaining little within-city variation is not a contradiction:
most of the achievable error reduction in this region is in getting a city's *level* right,
which is precisely what a benchmark built on whole-city holdout is designed to expose.

Its comparison against bias-corrected CAMS (29.77 µg/m³) is not significant
under the unit of generalisation this protocol is built on: a paired test over
6 city means gives *p* = 0.1392, and an exact permutation test
0.1250. Per-fold Diebold–Mariano tests do clear 0.05 individually, but six
tests are run and **only 3 of 6 survive Holm correction**. We
report the corrected count, not the raw one.

## 1.4 What this paper does not claim

We do not claim state of the art. No like-for-like comparison exists on these splits, for
the plain reason that we are the ones creating them. Nor do we claim to introduce transfer
learning for data-poor regions. Gupta et al. (2024) hold that ground already, proposing a
latent dependency factor for spatial transfer of PM2.5 estimation and reporting a 19.34%
gain over baselines across ten target sensors against eastern-US source data. Theirs is a
method paper, not a benchmark, and it defines no reusable public split. What remains
available to us is the evaluation protocol and the region, not the idea. Related transfer approaches have since been reported for other data-sparse settings,
including African cities (Mazuruse et al., 2026) and hybrid deep architectures
(Ni et al., 2022). We also decline to
compare our figures against published R² values obtained under random cross-validation. A
leave-city-out number and a random-CV number are not commensurable, and treating them as
though they were is the precise error this benchmark exists to prevent.

**One piece of prior art we cannot resolve.** A 2025 conference abstract claims the first
machine-learning PM2.5 prediction for Tashkent, using ten automated stations with weather
and seasonal inputs. We could not obtain it. The publisher returns HTTP 403, and the record
appears in none of OpenAlex, Crossref, Semantic Scholar or Europe PMC. **Its split protocol
is unverified.** We therefore make no claim about what that work did or did not do, and we
specifically do not assert priority for applying leave-city-out to Tashkent. Should it prove
to be spatially stratified, the novelty of C1 narrows to the multi-city benchmark, not
the city. Section 7 carries this as an open item.
