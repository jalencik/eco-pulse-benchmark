# Submission Package

Everything needed to submit, per venue. Strategy agreed: **arXiv first, then Environmental
Modelling & Software.** Both Elsevier journals permit prior posting of preprints, so this
costs nothing and establishes a priority date immediately.

## Authors

| # | Name | Affiliation | ORCID | Role |
|---|---|---|---|---|
| 1 | **Jaloliddin Musayev** (corresponding) | International House Tashkent Academic Lyceum, Tashkent | `0009-0003-0210-3687` | Lead author |
| 2 | Asadbek Abdivayitov | First Specialized Boarding School, Karshi | *not yet registered* | Data curation; Investigation |
| 3 | Ozodbek Yo'ldashev, PhD | National University of Uzbekistan, Tashkent | *not yet registered* | Supervision; Writing – review & editing |

**Blocking on submission — do these two first:**

1. **Both co-authors must read and approve the final PDF.** This is not a formality: Elsevier
   requires the corresponding author to confirm it, and adding someone who has not seen the
   manuscript is an authorship violation. Send them `paper/final_manuscript.pdf`.
2. **Co-author ORCIDs.** Only the corresponding author's is strictly required by Elsevier,
   so this does not block submission, but registration is free and takes two minutes at
   [orcid.org](https://orcid.org).

---

## Stage 1 — arXiv (do this first; ~30 minutes)

**Why first.** It is free, posts within about one business day, and gives you a permanent
citable link with a date stamp. If anyone else publishes a Central Asian air quality
benchmark next month, your priority is already established.

| Item | Value |
|---|---|
| Primary category | `physics.ao-ph` (Atmospheric and Oceanic Physics) |
| Cross-list | `cs.LG` (Machine Learning) — reaches the ML benchmark audience |
| Abstract | 228 words / 1,653 characters — **within the 1,920-character limit** |
| Licence | CC BY 4.0 recommended; permits reuse and is compatible with later journal submission |
| Format | PDF upload is accepted; `paper/final_manuscript.pdf` is ready as-is |

**Endorsement.** First-time submitters to `physics.ao-ph` may need an endorsement from an
existing arXiv author. Ozodbek Yo'ldashev, as a PhD at the National University of
Uzbekistan, is the natural person to ask — or to submit under. Plan for this; it is the
single most common reason a first arXiv submission stalls.

---

## Stage 2 — Environmental Modelling & Software (Elsevier)

**Why this journal.** It publishes benchmarks, reproducible software and evaluation
protocols as first-class contributions. That is precisely what C1 is. A paper whose headline
model result is modest but whose *protocol* contribution is strong fits EM&S far better than
a venue that expects a state-of-the-art number.

### Files to upload

| File | Source | Status |
|---|---|---|
| Manuscript PDF | `paper/final_manuscript.pdf` | ready (30 pp) |
| Highlights | `paper/HIGHLIGHTS.md` | ready — 5 bullets, all ≤85 characters |
| Figures | `paper/figures/fig1..5*.png` | ready — 300 dpi, greyscale-legible |
| Cover letter | below | ready — paste into the submission form |
| Data availability | §9.1 of the manuscript | complete |
| CRediT | §9.3 | complete |
| Declaration of generative AI | §9.2 | complete |
| Competing interests | §9.5 | complete |

### Cover letter

> Dear Editors,
>
> We submit *A Station-Level Air Quality Benchmark for Central Asia* for consideration in
> Environmental Modelling & Software.
>
> Central Asia has among the highest particulate burdens and the sparsest monitoring of any
> inhabited region, and no open, station-level benchmark exists for it. Regional results are
> typically reported under random cross-validation, which places observations from the same
> station on both sides of the split. Such a figure answers a question about interpolation
> while being read as answering one about unmonitored locations. The methodological point is
> not new — Roberts et al. (2016) and others have made it — but the region has had no
> benchmark that enforces it.
>
> Our contribution is that benchmark: eight reference instruments across six cities, with
> splits frozen and checksummed before any model was fitted, a purge gap derived rather than
> chosen, leave-city-out and leave-station-out protocols, and a mandatory baseline ladder.
> The splits are immutable by test. Every reported number regenerates from a single command.
>
> We wish to be direct about the headline modelling result. Under leave-city-out our tuned
> model reaches R² = 0.07. This is a low number and we report it deliberately. Every protocol
> choice available to us would have produced a larger one — a random split, reanalysis
> features unavailable at inference time, no baseline ladder, an exceedance F1 that a
> constant classifier already achieves at a 64.8% base rate. What the figure measures is the
> genuine difficulty of estimating concentrations in a city with no local monitor, in a
> region where six cities span five distinct aerosol regimes. We consider establishing that
> difficulty honestly to be the paper's value, and we report three further findings that run
> against our own framing: no credential-free method beats a constant classifier on
> exceedance; attribution is carried by spatial interpolation rather than by the satellite
> products the study was assembled around; and measured acquisition latency invalidated
> three of five initial availability assumptions, one by more than three orders of magnitude.
>
> The work is fully reproducible. The frozen splits, all analysis code, and the scripts that
> regenerate every table and figure are openly available, and the benchmark is fixed by a
> published SHA-256 checksum.
>
> This manuscript is not under consideration elsewhere. A preprint is posted on arXiv. All
> authors have approved the submission and we declare no competing interests.
>
> Yours sincerely,
> Jaloliddin Musayev (corresponding author), on behalf of all authors

### Suggested reviewers

Editors ask for these. Do not suggest anyone you have collaborated with.

- An author of AQ-Bench (Betancourt et al., 2021, *ESSD*) — closest benchmark precedent.
- An author of Roberts et al. (2016), *Ecography* — the spatial cross-validation position.
- A Central Asian air quality researcher, e.g. from Tursumbayeva et al. (2023),
  *Atmospheric Environment*.

---

## Stage 2b — Atmospheric Pollution Research (fallback)

Same Elsevier system, so the package transfers unchanged. If EM&S declines, APR is the
better second target: a stronger fit for the atmospheric-science and regional framing, and
typically a somewhat lower bar. In the cover letter, shift emphasis from *benchmark and
software* toward *regional characterisation and the coal-combustion winter regime*.

---

## Defending R² = 0.07

A reviewer will raise this first. The defence is not to apologise for it.

1. **State what the number measures.** Leave-city-out R² is variance explained at a location
   with **no local monitor** — a genuinely harder problem than the interpolation task most
   reported figures describe.
2. **Give the comparison that matters.** RMSE 25.70 against 31.09 µg/m³ for bias-corrected
   CAMS, a full chemistry-transport model, at Diebold–Mariano *p* < 0.0001. Beating a
   physics-based operational model significantly is the meaningful result; R² is a poor
   summary statistic when between-city variance dominates.
3. **Name what a higher number would have cost.** Section 1.3 and Section 8 already list the
   four protocol relaxations that would have inflated it. Point the reviewer there.
4. **Do not compare against published random-CV R² values.** Xinjiang's 0.73–0.81
   (Jin et al., 2022) is not commensurable, and saying so is a strength, not a weakness.

If a reviewer insists the model is too weak to publish, the correct reply is that the
contribution is C1 — the benchmark — and the model is the reference implementation that
establishes the floor. That is the framing throughout the manuscript, and it is why EM&S is
the right venue.

---

## Pre-flight checklist

- [ ] Both co-authors have read and approved `paper/final_manuscript.pdf`
- [ ] Co-author ORCIDs registered (optional, recommended)
- [ ] `python tasks.py reproduce` exits 0
- [ ] `cd benchmark/splits && sha256sum -c splits.sha256` passes
- [ ] `python scripts/build_pdf.py` reports no outstanding `[TO COMPLETE]` fields
- [ ] `python scripts/check_highlights.py` passes
- [ ] Repository is public, or made public at acceptance (currently **private**)
- [ ] arXiv endorsement arranged if required
- [ ] Cover letter pasted and the R² framing above rehearsed
