# A Station-Level Air Quality Benchmark for Central Asia

**Frozen leave-city-out splits, an operational-availability account, and an
honestly-evaluated transfer baseline**

**Jaloliddin Musayev**<sup>1,\*</sup>, **Asadbek Abdivayitov**<sup>2</sup>,
**Ozodbek Yo'ldashev**<sup>3</sup>

<sup>1</sup> International House Tashkent Academic Lyceum, Tashkent, Uzbekistan
<sup>2</sup> First Specialized Boarding School, Karshi, Uzbekistan
<sup>3</sup> National University of Uzbekistan, Tashkent, Uzbekistan

<sup>\*</sup> Corresponding author: jaloliddin2009applicant@gmail.com
ORCID 0009-0003-0210-3687

---

## Abstract

Central Asia carries some of the highest particulate burdens on earth and some of the
sparsest monitoring, yet no open station-level benchmark exists against which competing
estimation methods can be compared on identical terms. Regional results are typically
reported under random cross-validation, which places observations from the same station on
both sides of the split, answering a question about interpolation while appearing to answer
one about unmonitored locations.

We present a reproducible benchmark over 8 reference instruments in
6 cities, 2018-11-27 to 2024-12-31. Splits are frozen and checksummed
before any model is fitted: blocked-temporal with a purge gap derived as 240
hours from the maximum feature lag and horizon, plus leave-city-out over 6
folds. Nowcasting at unmonitored sites and forecasting at monitored stations are defined
separately and never pooled. Ground observations are fused with satellite retrievals,
chemistry-transport forecasts, reanalysis meteorology and static geography, each carrying a
measured acquisition latency that governs admissibility.

Against a mandatory baseline ladder, tuned gradient boosting attains R²
0.07 (RMSE 25.70, MAE
17.38 µg/m³), improving on bias-corrected CAMS
(31.09 µg/m³) at Diebold–Mariano *p* < 0.0001. Three results are
reported against interest: no credential-free nowcaster beat a constant always-exceed
classifier at a 64.8% base rate; attribution is dominated by spatial neighbour
features (32.5%) over satellite products
(16.6%); and measured latency invalidated three of five initial
availability assumptions. The benchmark's contribution is the protocol it forecloses.

**Keywords:** air quality; PM2.5; Central Asia; machine learning benchmark; spatial
cross-validation; leave-city-out; satellite remote sensing; reproducibility
