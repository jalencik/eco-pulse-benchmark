# 9. Declarations

## 9.1 Data availability

The benchmark definition — station set, temporal blocks, leave-city-out and
leave-station-out folds — is archived in Zenodo at **https://doi.org/10.5281/zenodo.21930669**
(version 1.1.0, CC BY 4.0), together with the SHA-256 checksum that fixes
it. The working repository is `https://github.com/jalencik/eco-pulse-benchmark`; cite the
Zenodo version DOI rather than the branch head, so a reported score is attributable to one
frozen split definition. All analysis code, the baseline ladder, and the
scripts that regenerate every table and figure in this manuscript are in the same
repository. A single command (`make reproduce`) regenerates every reported number from the
frozen splits.

Ground observations derive from the OpenAQ API (US diplomatic-post reference monitors and
national networks). The derived hourly panel is **not** redistributed here because the
per-feed licence terms are heterogeneous and four of the ten source feeds carry no licence
record at all; depositing the merged panel under a single licence would assert a uniform
permission the evidence does not support. Per-location licence records were retrieved on
2026-08-14 and are tabulated in full in `data/MANIFEST.md`, which also records provenance per
source, and `README.md` gives the three commands that rebuild the panel from the API with an
OpenAQ key, together with the two further accounts the predictor layer needs. Satellite products are public: MAIAC AOD (MCD19A2.061) and Sentinel-5P
(OFFL/NRTI) via Google Earth Engine; CAMS forecasts and ERA5 via the Copernicus
Atmosphere Data Store and Climate Data Store respectively.

**Note on permanence.** The StateAir publication channel closed on 2025-03-04. Five of the
ten contributing source feeds stop there — every StateAir feed, plus Bishkek's AirNow feed —
and at benchmark-station level, after co-published feeds are merged,
**2 of 7 stations
(8881, Bishkek) end there**; the others survive through their longer-lived
feed. The closure was not uniform and this statement has been corrected twice: an earlier
version said "six of the eight", which was wrong in both terms, and a later one said the
programme itself had terminated, which overstates what the evidence supports. Three
diplomatic-post monitors continued or resumed publication through AirNow after that date. The record curated here is finite and partly withdrawn
at source, which is a reason to archive this benchmark rather than an argument against it.
Authors intending to cite it should reference the frozen checksum, not the branch head.

## 9.2 Declaration of generative AI in the writing process

During the preparation of this work the corresponding author, Jaloliddin Musayev, used Anthropic Claude (Claude Code) to
assist with software implementation, data-pipeline construction, statistical tooling, and
drafting and editing of the manuscript text. The authors reviewed and edited all output,
verified every reported number against the regenerated result tables, and take full
responsibility for the content of the publication. Generative AI is not listed as an author
and no AI system holds authorship or accountability for this work.

## 9.3 CRediT author contributions

**Jaloliddin Musayev:** Conceptualisation; Methodology; Software; Validation; Formal
analysis; Investigation; Data curation; Writing — original draft; Writing — review and
editing; Visualisation; Project administration.

**Asadbek Abdivayitov:** Data curation; Investigation.

**Ozodbek Yo'ldashev:** Supervision; Writing — review and editing.

All authors read and approved the submitted manuscript.

## 9.4 Funding

This research received no specific grant from any funding agency in the public, commercial,
or not-for-profit sectors. All computation was performed on the authors' personal hardware,
and every data source used is publicly accessible at no cost.

## 9.5 Competing interests

The authors declare no competing financial or non-financial interests.

## 9.6 Ethics

This study used publicly available environmental measurements and involved no human
subjects, animal subjects, or personally identifiable data. Ethical approval was not
required.

## 9.7 Acknowledgements

The authors thank the National University of Uzbekistan and International House Tashkent
Academic Lyceum for institutional support. The author
further thanks OpenAQ for maintaining the aggregation layer that made the regional census
possible, and notes that the US diplomatic-post monitoring programme supplied the only
consistent multi-country reference in Central Asia for the period studied.
