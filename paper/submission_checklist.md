# Submission checklist — data-journal route (Data Descriptor)

> **This file is venue-specific and no venue has been selected.** It is kept as a worked
> example of one candidate route, because the legwork behind it is real. The portable
> material lives in [`journal_submission_notes.md`](journal_submission_notes.md); rewrite
> this file once a venue is chosen, and treat any figure here as needing re-checking against
> that venue's current guidelines.

Prepared 2026-08-15 against that journal's then-current submission guidelines. Every value below is
taken from the repository; nothing here is invented. Items marked **[YOU]** need Jaloliddin to
enter or confirm them in the submission system, and they cannot be filled from project files.

---

## Files to upload

| Slot | File | Status |
|---|---|---|
| Main article (first round: **PDF only**) | `paper/sdata_descriptor.pdf` | Built, 14 pp, figures embedded |
| Cover letter | `paper/cover_letter.md` → paste as text or export to PDF | Written |
| Figures | Embedded in the PDF (2 figures, limit is 8) | In place |
| Supplementary information | None | Not applicable |

At revision the journal requires `.docx` or `.tex` for the main article, **not** PDF. The
markdown source is `paper/sdata_descriptor.md`; converting it is a revision-stage task.

## Manuscript metadata

| Field | Value |
|---|---|
| Title (110-char limit) | A quality-controlled PM2.5 dataset with frozen cross-city evaluation splits for six Central Asian cities — **104 chars** |
| Article type | Data Descriptor |
| Abstract (170-word limit) | **150 words** — as in `paper/sdata_descriptor.pdf` |
| Subject terms | Environmental sciences; Atmospheric science; Computational science |
| Suggested keywords | PM2.5; air quality; Central Asia; benchmark dataset; spatial cross-validation; low-cost sensors; data quality control |

## Authors, in order

| # | Name | Affiliation | Role |
|---|---|---|---|
| 1 | Jaloliddin Musayev | International House Tashkent Academic Lyceum, Tashkent, Uzbekistan | **Corresponding**, ORCID 0009-0003-0210-3687 |
| 2 | Asadbek Abdivayitov | First Specialized Boarding School, Karshi, Uzbekistan | Co-author |
| 3 | Ozodbek Yo'ldashev | National University of Uzbekistan, Tashkent, Uzbekistan | Co-author |

Corresponding email: `jaloliddin2009applicant@gmail.com`

**[YOU]** Co-author ORCIDs. Two of the three are recorded: Jaloliddin Musayev
(0009-0003-0210-3687) and Asadbek Abdivayitov (0009-0006-3484-3438). Ozodbek Yo'ldashev's is
still outstanding. The system prompts per author, so either supply it or leave it blank if he
has none.

## Declarations (all already written into the manuscript)

| Declaration | Value |
|---|---|
| Competing interests | None declared |
| Funding | No specific grant; personal hardware; all sources free to access |
| Author contributions | Per CRediT, in the manuscript |
| Data availability | Zenodo `10.5281/zenodo.21930669`, CC BY 4.0; observations not redistributed, retrievable at source |
| Code availability | `github.com/jalencik/eco-pulse-benchmark`, MIT, archived in the same deposit |
| Ethics | Not applicable — no human or animal subjects |
| Generative AI | Disclosed in the manuscript |

## Open access / APC

| Item | Value |
|---|---|
| APC | £2150 / $2690 / €2390 |
| Discount | **50%** — Uzbekistan is named on Springer Nature's lower-middle-income discount list |
| Estimated payable | ~£1075 / ~$1345 / ~€1195 |
| Deadline | **Request at the point of submission.** Requests made during review or after acceptance "are unable to be considered" |
| Note | Springer Nature also runs a country-tiered APC pricing pilot that may supersede the discount; check what the form offers |

**[YOU]** Tick the waiver/discount request in the submission form. This is the one step that
cannot be undone later.

## [YOU] Items only you can do

1. Create or sign in to the Springer Nature submission account.
2. Request the 50% APC discount **in the form**.
3. Confirm the manuscript is not under consideration elsewhere (the cover letter states this).
4. Supply co-author ORCIDs if they have them.
5. Suggested / excluded reviewers, if the form asks and you want to name any.

## Verified before submission

- 584 tests pass
- Data Descriptor builds byte-identically across consecutive runs
- Title 104/110 chars, abstract 150/170 words, Background & Summary 648/700 words
- Section order matches the journal's required sequence
- 2 figures (limit 8), 4 tables (limit 10)
- `splits.sha256` unchanged — no scientific data altered
- No secrets, credentials or local paths in tracked files
- Zenodo v1.1.0 unchanged
