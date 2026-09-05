# A Station-Level Air Quality Benchmark for Central Asia

**Frozen leave-city-out splits, an operational-availability account, and a transfer
baseline evaluated under whole-city holdout**

**Jaloliddin Musayev**<sup>1,\*</sup>, **Asadbek Abdivayitov**<sup>2</sup>,
**Ozodbek Yo'ldashev**<sup>3</sup>

<sup>1</sup> International House Tashkent Academic Lyceum, Tashkent, Uzbekistan
<sup>2</sup> First Specialized Boarding School, Karshi, Uzbekistan
<sup>3</sup> National University of Uzbekistan, Tashkent, Uzbekistan

<sup>\*</sup> Corresponding author: jaloliddin2009applicant@gmail.com
ORCID iDs: Jaloliddin Musayev 0009-0003-0210-3687; Asadbek Abdivayitov 0009-0006-3484-3438.

---

## Abstract

Central Asia carries some of the highest particulate burdens on earth and some of the
sparsest monitoring, yet no open station-level benchmark exists against which competing
estimation methods can be compared on identical terms. Regional results are typically
reported under random cross-validation, which places observations from the same station on
both sides of the split, answering a question about interpolation while appearing to answer
one about unmonitored locations.

We present a reproducible benchmark over 7 instruments in
6 cities -- 5 reference-grade US-embassy monitors and
2 low-cost sensors in Khujand -- 2018-11-27 to 2024-12-31. Splits are frozen and checksummed
before the reported results were produced: blocked-temporal with a purge gap of 240
hours from the maximum feature lag and horizon, plus leave-city-out over 6
folds. Nowcasting at unmonitored sites and forecasting at monitored stations are defined
separately and never pooled. Ground observations are fused with satellite retrievals,
a chemistry-transport forecast and static geography, each carrying a
measured acquisition latency that governs admissibility.

Against a mandatory baseline ladder scored at a single temporal resolution, tuned gradient
boosting reaches RMSE 28.01 ± 0.35 µg/m³ at
unmonitored locations, the lowest of all 6 admissible baselines including
inverse-distance weighting (29.44 µg/m³) — though that ordering is not
statistically separable (paired *p* = 0.586) and reverses if one city is removed.
The advantage over
bias-corrected CAMS is **not statistically significant** once the city — the unit this
protocol generalises over — is the unit of analysis (paired *t* on 6 city means,
*p* = 0.1392; exact permutation *p* = 0.1250), and mean per-fold
R² is -0.04 with 3 of 6 folds
negative: the model ranks first on error while explaining little within-city day-to-day
variation. Further results are
reported against interest: at a 61.8% exceedance base rate a constant
always-exceed classifier already scores F1 = 0.741, and the best credential-free
nowcaster clears that floor by only 0.034; no feature family dominates attribution, with satellite
products (26.6%) ahead of calendar terms (22.2%), static
geography (21.8%) and spatial neighbours
(20.4%); and measured latency invalidated three of five initial
availability assumptions. The contribution is the fixed evaluation protocol, and the
shortcuts fixing it forecloses.

**Keywords:** air quality; PM2.5; Central Asia; machine learning benchmark; spatial
cross-validation; leave-city-out; satellite remote sensing; reproducibility
