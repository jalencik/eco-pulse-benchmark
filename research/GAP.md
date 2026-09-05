# GAP: What Is Actually New Here

Date: 2026-07-28. Written after the Phase 0 search, before any modelling.

**Verdict: the gap is real, but it is narrower than the project's opening framing, and one
piece of the intended C2 novelty is already taken.** Proceed, with the claim amended as
below, and with one unresolved threat that Phase 1 must settle early.

---

## 1. Falsifier verdicts

Falsifiers were declared in `PAPER_CLAIM.md` before searching.

| ID | Falsifier | Verdict | Evidence |
|---|---|---|---|
| **F1** | An existing open station-level Central Asia AQ benchmark with published splits | **NOT TRIGGERED** | Nothing found. AQ-Bench is ozone, long-term metrics, and excludes Central Asia. The Bishkek Zenodo deposit is an emissions inventory with monitoring data attached (CC-BY and genuinely useful), but it defines no task and no splits. |
| **F2** | A published leave-city-out PM2.5 transfer evaluation covering these countries | **NOT TRIGGERED** | The closest work (Gupta et al., ECML-PKDD 2024) evaluates on 10 target sensors against eastern-US source data. No Central Asia, no reusable regional protocol. |
| **F3** | Ground-truth coverage too thin to support leave-city-out (< ~4 usable cities) | **RESOLVED 2026-07-28: NOT TRIGGERED (7 cities)** | Live census: 317 locations → 11 span-eligible feeds → **9 distinct instruments → 7 cities**. See §3. |
| **F4** | Russian-language or regional literature already establishes the benchmark | **PROVISIONALLY NOT TRIGGERED** | Russian search surfaced monitoring portals and news, not research. **Not yet closed**: CyberLeninka / eLIBRARY.RU unsearched. |

---

## 2. What is genuinely new, and what is not

### Taken. Do not claim these.

- **"First ML prediction of PM2.5 in Tashkent."** Claimed by an ECAS 2025 paper using ten
  automated stations.
- **"Transfer learning for PM2.5 estimation in data-poor regions."** This is precisely
  Gupta et al. (ECML-PKDD 2024). C2 cannot be framed as introducing the idea.
- **"First PM2.5 estimates for Central Asia."** Already false via global gridded products,
  and Atmospheric Environment 2023 characterises all six capitals.
- **"Central Asia's air quality is under-studied."** True, and already *said in print* by
  the 2023 Atmospheric Environment paper. It is background, not contribution.

### Available. This is the actual contribution.

1. **The benchmark artifact (C1): strongest claim.** No open, station-level, split-frozen
   Central Asia PM2.5 benchmark exists. AQ-Bench established that this class of artifact is
   publishable (ESSD, 2021) and simultaneously left this region and this pollutant
   untouched. This is a clean, defensible, *verifiable* first.

2. **The evaluation protocol, applied where it has never been applied.** The regional
   literature is descriptive (source apportionment, back-trajectories, trend analysis); the
   ML literature that touches similar terrain uses protocols that leak. The Xinjiang study
   (the closest environmental analogue) validates with **10-fold CV and no spatial
   stratification**, so its R² of 0.73–0.81 is not a leave-city-out number and cannot be
   compared to one. Being the first to report *honestly evaluated* numbers here is a
   contribution, even when those numbers are worse than the literature's.

3. **A regime the transfer literature has not been tested against.** Gupta et al. transfer
   within the eastern US. Central Asia combines Aralkum salt-dust (spring-peaking), loess
   dust, winter coal-combustion peaks that official inventories under-attribute, and strong
   basin inversions. Whether spatial transfer survives *this* is an open empirical question.

4. **A structural obstacle nobody has addressed for this region.** MAIAC missingness is
   *correlated with the target*: retrievals fail during dust storms, snow, and heavy cloud,
   exactly the extreme-PM2.5 episodes that matter. The Xinjiang authors hit this and
   reported it as a limitation. Treating informative missingness as a modelled quantity
   rather than a dropped row is a concrete methodological contribution with a clear failure
   mode to demonstrate.

### The honest one-sentence version

> Not "we built a model for Central Asia." Rather: **the region has no benchmark, the
> nearest analogous studies use protocols that inflate their scores, and we supply the
> artifact plus the first honestly-evaluated numbers on it, including where it fails.**

---

## 3. The live threat: F3, and why it decides the project's shape

The OpenAQ 2024 landscape report (read in full) establishes:

- **Turkmenistan has no national air quality monitoring at all** (population 6.5M).
- **Kazakhstan shares data only with people physically inside Kazakhstan.**
- **Only Kyrgyzstan shares fully openly.**
- **Tajikistan began sharing only in 2024**, too recent for a multi-year blocked-temporal
  split.

The headline setting (leave-city-out with a purge gap, five seeds, per-city results) needs
enough cities with **≥ 2 years at ≥ 60% completeness** (rule Q7). The plausible pool is
Tashkent, Almaty, Astana, Bishkek, Dushanbe, possibly Ashgabat. If US Embassy records are
the only ones that survive QC, that is **five or six held-out folds**, thin but workable,
provided per-city results are reported individually and never averaged into a single
number that hides the variance.

If it falls below four, the honest response is **not** to loosen Q7 until the number
improves. It is to degrade the protocol to leave-station-out and narrow the claim, exactly
as F3 specifies.

**This is the first question Phase 1 answers**, because it determines whether the headline
result exists at all. It is a data-availability question, not a modelling question, and it
is cheap to settle.

### F3: RESOLVED, 2026-07-28

The live census settles it. **Leave-city-out is viable: 7 cities**, above the threshold of 4.

| | |
|---|---|
| OpenAQ locations in UZ/KZ/KG/TJ/TM | 317 |
| ≥1 PM2.5 sensor, not mobile, ≥2 y span | 11 feeds |
| After Q5b de-duplication | **9 distinct instruments** |
| **Distinct cities** | **7**: Almaty, Ashgabat, Astana, Bishkek, Dushanbe, Khujand, Tashkent |

Three caveats, each material:

1. **Two "stations" were the same instrument.** The US Embassy monitors are published
   twice, under StateAir *and* AirNow, as separate `location_id`s: Bishkek 57 m apart,
   Ashgabat 40 m apart. The original exact-coordinate duplicate check missed both. Under
   leave-station-out, the held-out station would have been the same physical device as one
   in training. Fixed (D-003); the threshold has a wide margin, since the two genuinely
   distinct Dushanbe sites are 6.06 km apart.
2. **Only Khujand is non-reference.** Six of seven cities rest on a single reference-grade
   instrument each. There is no redundancy: lose one station, lose one city.
3. **Q7 completeness is not yet applied.** 7 is an upper bound. The count can only fall.

### The finding that changes the benchmark's shape: R9

**The US State Department terminated its global embassy air quality monitoring programme in
March 2025**, citing funding. Six of nine reference monitors stop at exactly `2025-03-04`,
and the programme's closure is independently documented (CNN, Democracy Now, CBS, NBC,
March 2025; ~34 countries affected).

> **Retracted 2026-08-14, kept here as the Phase-0 record.** "Terminated the programme"
> overstates the evidence. What closed on 2025-03-04 was the **StateAir publication
> channel**; three diplomatic-post monitors continued or resumed publishing through AirNow
> afterwards. The corrected position is in `data/MANIFEST.md` and D-011 of
> `data/DECISIONS.md`. The station counts in this section are also pre-merge and pre-Q7.

This project designated the embassy network as the benchmark's spine. That was correct: it
is the only consistent multi-country reference in the region and the sole route into
Ashgabat. **That spine is now a historical archive, not a live feed.**

Consequences that must be settled in Phase 2, not assumed:

- "Test on the most recent full year" cannot mean 2025 or 2026 for reference-grade data.
  **The last full year with embassy coverage is 2024.**
- A forecasting service deployed today cannot be validated against reference monitors on
  current data. This is a genuine limitation of the deployment claim, not a modelling gap.
- Some AirNow feeds extend past the shutdown (Almaty → 2025-11, Ashgabat → 2025-09,
  Dushanbe → 2026-07). **Cause unverified**: partial resumption, a different pipeline, or
  backfill. Must be established before those months are used.

This strengthens rather than weakens the case for C1: the region's best reference record is
now finite and closed. Curating it into a frozen, documented benchmark is more valuable
after the programme's end than it would have been during it.

An additional consequence already fixed: **Kazakhstan's geo-restriction is a
reproducibility hazard.** A benchmark a third party cannot reconstruct from outside
Kazakhstan is not open. Kazakh stations enter only via an independently retrievable path
(OpenAQ mirror or US Embassy), with per-station provenance recorded.

---

## 4. Required amendments to PAPER_CLAIM.md

1. **Keep** the C1 claim as written. It survived F1 intact.
2. **Reframe C2.** Not "transfer learning for data-poor regions" (taken), but *how far
   spatial transfer carries into an aerosol regime unlike any in the source domain, measured
   under a protocol the region has never had.*
3. **Add a fifth avoided claim:** never cite the Xinjiang R² (0.73-0.81), or any
   random-CV number, as a target to beat. Comparing a leave-city-out result to a random-CV
   result is the exact like-for-like violation the project forbids.
4. **Record F3 as an open risk**, with the degradation path pre-committed *now*, before the
   station counts are known and can influence the decision.

---

## 5. Recommendation

**Proceed to Phase 1**, with the amended claim.

The gap is thinner than "nobody has studied Central Asian air quality." That framing was
never true and is now demonstrably false in print. But the benchmark gap is real, verified
against four declared falsifiers, and the artifact has a publishable precedent in ESSD.

The one thing that would change this recommendation is F3. Phase 1 should therefore begin
by counting usable stations and cities, before any pipeline is built around them.
