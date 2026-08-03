# 9. Declarations

> **AUTHOR ACTION REQUIRED.** Fields marked [TO COMPLETE] must be completed before submission. They
> are institution- and journal-specific and cannot be filled in from the repository.

## 9.1 Data availability

The benchmark definition — station set, temporal blocks, leave-city-out and
leave-station-out folds — is openly available at
`https://github.com/jalencik/eco-pulse-ca-benchmark` under `benchmark/splits/`, together
with the SHA-256 checksum that fixes it. All analysis code, the baseline ladder, and the
scripts that regenerate every table and figure in this manuscript are in the same
repository. A single command (`make reproduce`) regenerates every reported number from the
frozen splits.

Ground observations derive from the OpenAQ API (US diplomatic-post reference monitors and
national networks). The derived hourly panel is **not** redistributed here because the
per-station licence terms have not been transcribed; `data/MANIFEST.md` records provenance
per source, and `README.md` gives the two commands that rebuild the panel from the API with
an OpenAQ key. Satellite products are public: MAIAC AOD (MCD19A2.061) and Sentinel-5P
(OFFL/NRTI) via Google Earth Engine; CAMS forecasts and ERA5 via the Copernicus
Atmosphere Data Store and Climate Data Store respectively.

**Note on permanence.** The US State Department terminated its global diplomatic-post air
quality programme in March 2025 and six of the eight stations end on 2025-03-04. The record
curated here is finite and partly withdrawn at source, which is a reason to archive this
benchmark rather than an argument against it. Authors intending to cite it should reference
the frozen checksum, not the branch head.

## 9.2 Declaration of generative AI in the writing process

During the preparation of this work the author used Anthropic Claude (Claude Code) to
assist with software implementation, data-pipeline construction, statistical tooling, and
drafting and editing of the manuscript text. The author reviewed and edited all output,
verified every reported number against the regenerated result tables, and takes full
responsibility for the content of the publication. Generative AI is not listed as an author
and no AI system holds authorship or accountability for this work.

**[TO COMPLETE:** Adjust wording to the target journal's required template. Elsevier requires this
statement immediately above the reference list; IEEE additionally requires the system to be
named, the affected sections identified, and the level of use described. Routine grammar and
spelling correction does not, under any of these policies, require declaration.**]**

## 9.3 CRediT author contributions

**[TO COMPLETE: Author name]:** Conceptualisation; Methodology; Software; Validation; Formal analysis;
Investigation; Data curation; Writing — original draft; Writing — review and editing;
Visualisation; Project administration.

**[TO COMPLETE:** If the mentor or any collaborator contributed to supervision, methodology or review, add
them here with the appropriate CRediT terms. Omitting a genuine contributor is a more
serious problem than any question of AI assistance.**]**

## 9.4 Funding

**[TO COMPLETE:** State the funding source, or the following if none:**]** This research received no specific
grant from any funding agency in the public, commercial, or not-for-profit sectors.

## 9.5 Competing interests

The author declares no competing financial or non-financial interests.

## 9.6 Ethics

This study used publicly available environmental measurements and involved no human
subjects, animal subjects, or personally identifiable data. Ethical approval was not
required.

## 9.7 Acknowledgements

**[TO COMPLETE:** Acknowledge your mentor, institution, and any data providers here.**]** The author thanks
OpenAQ for maintaining the aggregation layer that made the regional census possible, and
notes that the US diplomatic-post monitoring programme supplied the only consistent
multi-country reference in Central Asia for the period studied.
