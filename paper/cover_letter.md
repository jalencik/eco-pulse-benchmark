# Cover letter — *Scientific Data*

**Manuscript title:** A quality-controlled PM2.5 dataset with frozen cross-city evaluation
splits for six Central Asian cities

**Article type:** Data Descriptor

**Corresponding author:** Jaloliddin Musayev, International House Tashkent Academic Lyceum,
Tashkent, Uzbekistan — jaloliddin2009applicant@gmail.com — ORCID 0009-0003-0210-3687

---

Dear Editors,

We submit the manuscript above for consideration as a Data Descriptor.

The dataset is a quality-controlled record of daily PM2.5 for seven instruments across six
Central Asian cities (Almaty, Ashgabat, Bishkek, Dushanbe, Khujand and Tashkent), together
with frozen, checksummed evaluation splits, a mandatory baseline ladder, and reference model
outputs. Central Asia is among the most polluted regions in the world and among the least
monitored. The US diplomatic-post network was for years the only open reference-grade source
in these cities, and its publication channel closed on 2025-03-04. The record is therefore
finite, and curating it carefully is more useful than curating a live feed that anyone can
re-pull.

We think it suits *Scientific Data* for three reasons.

First, the processing decisions are documented rather than assumed. Every quality-control
rule records its effect on *n* and the direction of bias if it is wrong, and the full decision
log is released with the data. One rule was added during validation after it revealed that two
records 6.06 km apart were a single US-embassy monitor republished under two programmes; that
correction, and the earlier claim it retracts, are both stated in the manuscript rather than
quietly fixed.

Second, the evaluation splits are immutable by test. `splits.sha256` is compared against a
fresh build on every run, and the test fails for the authors exactly as it does for anyone
else. Changing a split requires raising the benchmark version and regenerating every published
number, which is deliberately harder than editing a JSON file.

Third, the reference results are reproducible. A single command runs lint, type checking, the
full test suite, checksum verification, split regeneration, the baseline ladder, the model
layer, table regeneration and manuscript rendering, and two consecutive runs reproduce all
result tables byte-identically under SHA-256.

Two things we would rather you heard from us than found for yourself.

**The reference implementation is a reference point, not a result.** It records the lowest
error of six legal baselines, but the paired difference across six cities is not
statistically separable, mean per-fold R² is negative, and errors grow with a city's mean
concentration. We report all three plainly. A benchmark whose reference implementation is
reported honestly is more useful to the next group than one tuned until it wins, and the
dataset's value does not rest on the model performing well.

**One data-rights question is open.** Six of the ten source feeds carry explicit licences
permitting redistribution (US Public Domain, CC0 1.0), and two more are demonstrably the same
measurements as licensed feeds. For the remaining two, the diplomatic-post feeds at Bishkek
and Tashkent, no licence record has been issued by the platform that serves them, and the
only US Department of State air-quality data-use statement we could locate is scoped to a
different programme. We have written to the Department at its published air-quality address
(`airpollution@state.gov`) requesting clarification, and as of 2026-08-18 have not received a
reply. Accordingly the deposit contains the derived benchmark artefacts and the
complete pipeline code, but **not** the underlying observations, which remain publicly
retrievable at source without credentials. The Data Availability statement sets this out, and
`data/MANIFEST.md` documents the evidence and its limits per feed. We will update the
manuscript when the Department responds, and we are glad to discuss the arrangement if it
affects your assessment.

The manuscript is not under consideration elsewhere, and all authors have approved this
submission. Use of generative AI in preparing the software and text is disclosed in the
manuscript.

As the corresponding author is based in Uzbekistan, we request the 50% APC discount available
for lower-middle-income locations, at the point of submission as your policy requires.

Thank you for your consideration.

Jaloliddin Musayev, on behalf of all authors
