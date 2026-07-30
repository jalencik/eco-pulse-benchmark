# 1. Introduction

## 1.1 The gap

Central Asia is among the most polluted inhabited regions on earth and among the least
instrumented. Published work places annual PM2.5 in the region's capitals at 4.3–12.6× the
WHO 2021 guideline, yet the monitoring base supporting those figures is thin and unevenly
open. Of the five states, one — Turkmenistan — operates no national air quality monitoring
at all; another, Kazakhstan, shares its data only with users physically inside the country;
only Kyrgyzstan publishes in a fully open form.

The scientific consequence is not an absence of estimates. Global gridded products already
assign PM2.5 values across the region, and the epidemiological literature uses them. What is
absent is the ability to *check* those estimates, or to compare methods against one another
on identical terms. There is no open, station-level benchmark for Central Asia: no frozen
splits, no declared protocol, no shared evaluation.

That absence has a measurable cost. The closest environmental analogue in the literature —
PM2.5 estimation across Xinjiang, a comparably arid, dust-affected, sparsely-monitored
region — reports R² of 0.73–0.81 under 10-fold cross-validation with no spatial
stratification. With 41 stations across 16 cities and 8-day-averaged samples, that protocol
places observations from the same station, frequently the same window, on both sides of the
split. The resulting figure answers *"how well can we interpolate within known stations?"*
It is routinely read as answering *"how well can we estimate at an unmonitored location?"*
Those are different questions with very different answers, and nothing in a reported R²
distinguishes them.

## 1.2 What this paper contributes

**C1 — a benchmark.** 8 stations across 6 cities, with splits frozen
and hashed before any model was fitted: blocked-temporal with a derived purge gap,
leave-city-out across 6 folds, and leave-station-out where station density
permits (4 folds; Almaty, Ashgabat, Bishkek, Tashkent hold a single instrument each and are
named as ineligible rather than silently omitted). The splits are immutable by test, and
that test fails for the authors as readily as for anyone else.

**C2 — honestly-evaluated transfer.** Rather than claiming a method, we characterise how far
spatial transfer carries into an aerosol regime unlike the source domain, under a protocol
the region has never had. A negative result is publishable under this framing, and several
of ours are.

**C3 — an operational-constraint account.** Every predictor carries a measured latency and a
typed availability flag. Features that cannot exist at prediction time are barred from
deployable configurations by test, not by convention.

## 1.3 Findings that shaped the work

Three results recur and are worth stating before the methods.

**Cheap references are strong, and expensive ones are not.** No credential-free nowcaster
beat a trivial always-exceed predictor on health-relevant exceedance. Raw CAMS — a full
chemistry-transport model — is beaten by subtracting a per-city constant, and even
bias-corrected it reaches only R² -0.22. Every baseline we tried,
across two phases, sat below the accuracy of predicting the held-out city's own mean.

**Metric choice reverses conclusions.** RMSE and exceedance skill rank the same models in
nearly opposite orders. Smoothing toward the mean lowers squared error while destroying the
variance needed to distinguish a bad day from a good one, so a model can win one metric by
losing the other. Reporting either alone would rank the ladder backwards for the other task.

**The first positive leave-city-out R² required removing two handicaps, not a better model.**
Tuned gradient boosting with spatial neighbour encodings reaches R² 0.07
(RMSE 25.70) against 31.09 for bias-corrected CAMS,
Diebold–Mariano -4.52, p < 0.0001. The same architecture untuned and
without neighbours scored RMSE 31.99 and R²
-0.64 — worse than the baseline it now beats.

## 1.4 What this paper does not claim

We do not claim state of the art: no like-for-like comparison exists on these splits, because
we are creating them. We do not claim to introduce transfer learning for data-poor regions;
that framing is held by prior work. We do not compare against published R² values obtained
under random cross-validation, because a leave-city-out number and a random-CV number are
not commensurable, and treating them as such is the error this benchmark exists to prevent.
