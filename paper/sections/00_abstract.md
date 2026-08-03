# A Station-Level Air Quality Benchmark for Central Asia

**Frozen leave-city-out splits, an operational-availability account, and an
honestly-evaluated transfer baseline**

Jaloliddin Musaev

---

## Abstract

Central Asia carries some of the highest particulate burdens on earth and some of the
sparsest monitoring. Annual PM2.5 in the region's capitals runs several times the WHO 2021
guideline, yet no open, station-level benchmark exists against which competing estimation
methods can be compared on identical terms. Published regional results are typically
reported under random cross-validation, which places observations from the same station on
both sides of the split and answers a question about interpolation while appearing to answer
one about extrapolation to unmonitored locations.

We introduce a reproducible benchmark built on 8 reference instruments across
6 Central Asian cities, spanning 2018-11-27 to 2024-12-31. Splits are
frozen and checksummed before any model is fitted: blocked-temporal with a purge gap derived
as 240 hours from the maximum feature lag and forecast horizon, and leave-city-out
across 6 folds. Two tasks are defined and never pooled — nowcasting at
unmonitored locations (Task N) and forecasting at monitored stations (Task F). Ground
observations are fused with satellite retrievals (MAIAC AOD, Sentinel-5P AAI/NO₂/SO₂/CO),
CAMS chemistry-transport forecasts, ERA5 meteorology and static geography, each carrying a
measured acquisition latency that determines whether it may enter a deployable
configuration.

Against a mandatory baseline ladder, tuned gradient boosting reaches R²
0.07 (RMSE 25.70 µg/m³, MAE
17.38 µg/m³) under leave-city-out, improving on bias-corrected CAMS
(31.09 µg/m³) at Diebold–Mariano *p* < 0.0001. Three findings are
reported against interest. No credential-free nowcaster beat a trivial always-exceed
classifier (0.764 F1 at a 64.8% exceedance base rate). SHAP
attribution is dominated by spatial neighbour features (32.5%)
rather than the satellite products (16.6%) the study was assembled around.
Measured latencies invalidated three of five initial availability assumptions, one by more
than three orders of magnitude.

**Keywords:** air quality; PM2.5; Central Asia; machine learning benchmark; spatial
cross-validation; leave-city-out; domain transfer; satellite remote sensing; reproducibility
