# Journal submission notes

The manuscript, the cover letter and the highlights are written to be portable. This file is
the only place that names a venue. Nothing here is a scientific decision; every entry is a
formatting or policy requirement that changes between journals, recorded so the choice can be
made once and applied consistently.

**No venue has been selected.** Until one is, treat every row below as a candidate.

---

## What is portable and what is not

| Artefact | Portable? | Note |
|---|---|---|
| `paper/extended_technical_report.md` | Yes | Standard research-article structure. Venue-neutral throughout. |
| `paper/sdata_descriptor.md` | Structurally venue-shaped | Built to the Data Descriptor section order (Background and Summary, Methods, Data Records, Technical Validation, Usage Notes, Data/Code Availability, Declarations). That order is a requirement of the Data Descriptor article type. Submitting elsewhere means re-sectioning, not rewriting: the prose and every number carry over unchanged. |
| `paper/cover_letter.md` | Yes, with four placeholders | `[ARTICLE TYPE]`, `[JOURNAL]`, and the APC paragraph. |
| `paper/HIGHLIGHTS.md` | Yes | Only some venues ask for it. The file is heading plus bullets and nothing else, because submission systems ingest it verbatim. Three to five bullets, each at most 85 characters including spaces, free of jargon, acronyms and abbreviations; 85 is the strictest known constraint, so bullets that satisfy it satisfy any looser one. `scripts/check_highlights.py` fails the build if a bullet exceeds the limit, which is easy to do while editing and which submission systems reject rather than truncate. |
| `paper/tables/`, `paper/figures/`, `benchmark/` | Yes | Frozen artefacts. Independent of venue. |
| `paper/submission_checklist.md` | No | Written against one venue's submission form. Rewrite when a venue is chosen. |

## Constraints currently enforced in the build

`scripts/check_sdata_limits.py` and `scripts/check_highlights.py` fail the build when these
are exceeded. They encode the strictest limits among the candidates considered, so passing
them keeps every option open. They are guards, not scientific claims.

| Constraint | Limit enforced | Origin |
|---|---:|---|
| Title | 110 characters | Data Descriptor |
| Abstract | 170 words | Data Descriptor |
| Background and Summary | 700 words | Data Descriptor |
| Highlights | 5 bullets, 85 characters each | Elsevier |

If a venue is chosen whose limits are looser, the guards can be relaxed. If one is chosen
with a stricter limit, tighten the guard first and let the build tell you what breaks.

## Per-venue requirements gathered so far

Recorded when encountered. Not exhaustive, and not a recommendation.

| Venue | Article type | Highlights | AI-disclosure placement | APC |
|---|---|---|---|---|
| Data journal (Data Descriptor type) | Data Descriptor | Not used | In Declarations | Charged; a country-based discount applies to Uzbekistan. Must be requested **in the submission form**, not later. |
| Elsevier titles | Research article | Required, separate file, 3–5 bullets at ≤85 chars | Statement immediately above the reference list | Varies by title; several are hybrid. |
| IEEE | Research article | Not used | Must name the system, identify affected sections, and describe the level of use | Varies. |
| Preprint server | Preprint | Not used | Per server policy | None. |

Routine grammar and spelling correction does not require declaration under any of these
policies. The manuscript's disclosure goes well beyond that threshold and stays regardless of
venue.

## Author information

Settled and consistent across every artefact. Co-author agreement is confirmed by the
corresponding author.

| # | Name | Affiliation | ORCID |
|---|---|---|---|
| 1 | Jaloliddin Musayev | International House Tashkent Academic Lyceum, Tashkent, Uzbekistan | 0009-0003-0210-3687 (corresponding) |
| 2 | Asadbek Abdivayitov | First Specialized Boarding School, Karshi, Uzbekistan | 0009-0006-3484-3438 |
| 3 | Ozodbek Yo'ldashev | National University of Uzbekistan, Tashkent, Uzbekistan | not supplied |

Two notes that need the corresponding author rather than a file edit:

- Ozodbek Yo'ldashev's ORCID is outstanding. Submission systems collect ORCIDs per author, so
  this can be left blank at submission if he has none. It is deliberately not printed on the
  title page as an unfilled placeholder.
- The corresponding author's ORCID record registers the surname as "Musaev" while every
  manuscript artefact uses "Musayev". Aligning the two avoids an indexing mismatch.

## Declarations, identical across venues

| Declaration | Value |
|---|---|
| Competing interests | None declared |
| Funding | No specific grant; personal hardware; all sources free to access |
| Author contributions | CRediT, in the manuscript |
| Data availability | Zenodo `10.5281/zenodo.21930669`, CC BY 4.0. Observations not redistributed; retrievable at source |
| Code availability | `github.com/jalencik/eco-pulse-benchmark`, MIT, archived in the same deposit |
| Ethics | Not applicable. Fixed-site ambient air quality monitors; no human or animal subjects, and no personal data |
| Generative AI | Disclosed in the manuscript |
