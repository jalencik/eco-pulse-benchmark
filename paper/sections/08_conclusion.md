# 8. Conclusion

We built the benchmark this region did not have. 7 instruments across
6 cities (5 reference-grade, 2 low-cost), splits frozen and checksummed before the reported results were produced, two tasks
kept separate, and a baseline ladder that every future submission has to climb. The splits
are immutable by test, and that test fails for us exactly as it fails for anyone else.

The modelling result is modest and is reported without inflation. Tuned gradient boosting
reaches RMSE 28.01 ± 0.35 µg/m³ at
unmonitored locations, the lowest of any admissible baseline including inverse-distance
weighting (29.44 µg/m³) — but that ordering is not statistically
separable (paired *p* = 0.586) and is not robust to removing a single city. Its
advantage over bias-corrected CAMS is likewise **not
statistically significant** when the city is the unit of analysis
(*p* = 0.1392), and mean per-fold R² is -0.04 with
3 of 6 folds negative. Lowest error and demonstrated
skill are not the same claim, and only the first is supported here. Every protocol choice
available to us would have produced a larger one: a random split, reanalysis features
unavailable at inference, no baseline ladder, an exceedance F1 that a constant classifier
already achieves. The number reported here is what survives after those escapes are closed
by failing tests.

Three findings run against the study's own framing and are reported anyway. A trivial
always-exceed classifier is not beaten by any credential-free nowcaster, because these
cities exceed the WHO 24-hour guideline on most days — a fact about the region, not about
the models. Attribution is carried chiefly by the five satellite
products (26.6%) rather than by spatial interpolation
(20.4%) — a reversal of the ordering reported before the duplicate
Dushanbe instrument was found and merged (Section 7.4). And measured acquisition latency
invalidated three of five initial availability assumptions, one of them by a factor of
roughly 4,600.

**For practitioners.** The clearest practical signal in this work is not an ordering of
feature families — that ordering proved fragile, reversing once a single duplicated
instrument was removed. It is that with 7 instruments across 6
cities, a learned model does not beat knowing a city's own average, and the attribution
ranking is unstable to one station. Both point the same way: the binding constraint is
network density, not modelling technique or choice of remote-sensing product. The single most
valuable investment for Central Asian air quality modelling is more stations — particularly
in Turkmenistan, which has none, and Kazakhstan, which contributes one city here.

**For the field.** The benchmark's value is that it forecloses the shortcuts. A future
model that genuinely improves on 28.01 µg/m³ under this protocol will
have demonstrated something real, and the comparison will be like-for-like because the
splits cannot move. Priorities for extension, in order: additional cities to reduce the
fold-to-fold variance that presently exceeds seed variance by an order of magnitude; a
parallel near-real-time satellite archive to quantify train/serve skew; and a
post-2025 ground-truth source to replace the publication channel that closed on 2025-03-04.
