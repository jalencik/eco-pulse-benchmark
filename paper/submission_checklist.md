# Submission checklist

The venue is not chosen, so this checklist is written to hold for any of them. Where a
journal's own form says otherwise, its form wins. Items marked **[YOU]** need the
corresponding author to enter or confirm them in the submission system, and cannot be filled
from project files.

---

## Files to upload

| Slot | File | Status |
|---|---|---|
| Main article | `paper/sdata_descriptor.pdf` | Built, 13 pp, figures embedded. Rename before upload, e.g. `Musayev_PM25_Central_Asia.pdf` |
| Cover letter | `paper/cover_letter.md`, pasted as text or exported to PDF | Written. **[YOU]** fill `[JOURNAL]`; keep the closing APC paragraph only if the venue charges a fee |
| Highlights | `paper/highlights.md` | 5 bullets, each within 85 characters. Only some journals ask for it |
| Figures | Embedded in the PDF, 3 figures | In place |
| Supplementary information | None | Not applicable |

The file name says `sdata_descriptor` for build-path reasons. The document inside is a
standard research article. Many journals want an editable format (`.docx` or `.tex`) at
revision rather than at first submission; the markdown source is `paper/sdata_descriptor.md`,
and converting it is a revision-stage task.

## Manuscript metadata

| Field | Value |
|---|---|
| Title | A quality-controlled PM2.5 dataset with frozen cross-city evaluation splits for six Central Asian cities — **104 characters** |
| Article type | Research article |
| Abstract | **165 words** |
| Sections | Abstract; 1. Introduction; 2. Materials and methods; 3. The released benchmark; 4. Results; 5. Discussion; 6. Conclusions; declarations; references |
| Suggested keywords | PM2.5; air quality; Central Asia; benchmark dataset; spatial cross-validation; low-cost sensors; data quality control |
| Suggested subject terms | Environmental sciences; Atmospheric science; Computational science |

## Authors, in order

| # | Name | Affiliation | Role |
|---|---|---|---|
| 1 | Jaloliddin Musayev | International House Tashkent Academic Lyceum, Tashkent, Uzbekistan | **Corresponding**, ORCID 0009-0003-0210-3687 |
| 2 | Asadbek Abdivayitov | First Specialized Boarding School, Karshi, Uzbekistan | Co-author, ORCID 0009-0006-3484-3438 |

Corresponding email: `jaloliddin2009applicant@gmail.com`

**[YOU]** The corresponding author's ORCID record registers the surname as "Musaev" while
every manuscript artefact uses "Musayev". Correct the ORCID record before submitting, or the
publication will not attach to the right profile.

## Declarations (all already written into the manuscript)

| Declaration | Value |
|---|---|
| Competing interests | None declared |
| Funding | No specific grant; personal hardware; all sources free to access |
| Author contributions | Per CRediT, in the manuscript |
| Data availability | Zenodo `10.5281/zenodo.21930669`, CC BY 4.0; observations not redistributed, retrievable at source |
| Code availability | `github.com/jalencik/eco-pulse-benchmark`, MIT, archived in the same deposit |
| Ethics | Not applicable, no human or animal subjects |
| Generative AI | Disclosed in the manuscript, above the reference list |

Some journals place the generative-AI statement immediately above the references and others
in the declarations block. The manuscript satisfies both: the statement sits in the
declarations, which follow the references.

## Article-processing charges

Only some venues charge one, so treat this section as conditional.

| Item | Value |
|---|---|
| Whether payable | **[YOU]** Check the venue's own page. Many regional and society journals charge nothing |
| Discount | Uzbekistan appears on most publishers' lower-middle-income waiver or discount lists |
| Deadline | **Request at the point of submission.** Most publishers will not consider a request made during review or after acceptance |

**[YOU]** If the venue charges a fee, tick the waiver or discount request in the form. It is
the one step that cannot be undone later.

## [YOU] Items only you can do

1. Choose the venue and put its name in the cover letter.
2. Create or sign in to the submission account.
3. Request a fee waiver or discount in the form, if the venue charges one.
4. Confirm the manuscript is not under consideration elsewhere; the cover letter states this.
5. Suggested or excluded reviewers, if the form asks and you want to name any.
6. Correct the ORCID surname.

## Verified before submission

- 592 tests pass; `ruff check` and `ruff format --check` clean
- The manuscript builds byte-identically across consecutive runs
- Title 104/110 characters, abstract 165/170 words, introduction 684/700 words
- 3 figures, 12 result tables listed, 21 references, no unresolved placeholders
- Every in-text citation resolves to a reference entry
- `splits.sha256` unchanged, so no scientific data was altered
- No secrets, credentials or local paths in tracked files
- Zenodo v1.1.0 unchanged; the manuscript discloses that two later tables post-date it

The title, abstract and introduction limits above are portability floors rather than one
venue's rule: they sit inside the limits of every candidate considered, including the
strictest, so passing them keeps every option open.
