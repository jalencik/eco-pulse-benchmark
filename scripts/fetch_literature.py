"""Resolve the Phase 0 reading list through scholarly APIs instead of publisher pages.

Run:  python scripts/fetch_literature.py [--out research/sources.json]

Direct retrieval of ScienceDirect and MDPI article pages returned HTTP 403, which left
four high-priority sources at SNIPPET depth — including A9, whose split protocol determines
how the related-work section is written, and B2, the methodological critique this project
is built around. Citing a paper from a search-result summary is how wrong author lists and
invented findings get into a manuscript.

These APIs are the documented machine-readable route to the same records and do not block:

  OpenAlex     — coverage, abstracts (inverted index), OA locations
  Crossref     — authoritative DOI metadata: authors, journal, year
  Semantic Scholar — abstracts, TLDRs, open-access PDF links
  Europe PMC   — full text for anything with a PMC identifier

Depth is assigned by what was actually retrieved, never by what was hoped for:

  FULL      full text retrieved (Europe PMC / arXiv / OA PDF link resolved)
  ABSTRACT  publisher abstract obtained from a structured record
  SNIPPET   nothing better than a search summary

Nothing here fabricates a citation. A target that resolves to no record is written out with
depth=UNRESOLVED so the gap stays visible in the ledger.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "sources.json"

OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
S2 = "https://api.semanticscholar.org/graph/v1/paper/search"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# ref id -> search phrase. Ids match research/LITERATURE.md so the two can be reconciled.
TARGETS: dict[str, str] = {
    "A2": "Cities of Central Asia new hotspots of air pollution in the world",
    "A4": "Validation and comparison of high-resolution MAIAC aerosol products over Central Asia",
    "A5": "Dominant sources of PM2.5 in Kazakhstan urban cities PMF HYSPLIT",
    "A6": "PM2.5 source apportionment Dushanbe Tajikistan air quality Central Asian urban",
    "A7": "Impacts of the desiccation of the Aral Sea on the Central Asian dust life cycle",
    "A8": "Characteristics of salt dust aerosols and their transport implications Aral Sea",
    "A9": "Particulate matter PM2.5 prediction in Tashkent using machine learning",
    "B2": "A review of machine learning for modeling air quality overlooked but important issues",
    "B3": "Assessing validating machine learning unrefined particle air pollution mobile "
    "monitoring spatially spatiotemporally",
    "B4": "Distributional bias compromises leave-one-out cross-validation",
    "B5": "AirDelhi fine-grained spatio-temporal particulate matter dataset Delhi",
    "C3": "Explainable machine learning multi-pollutant forecasting African cities transfer learning",
    "C4": "Improved hybrid transfer learning based deep learning model PM2.5 concentration",
}

# Methodological sources the manuscript already leans on. These are known-item lookups by
# exact title, not topical browsing: a topic phrase returns whatever is most cited nearby,
# which is how "WHO air quality guidelines" resolved to a paper on antimicrobial resistance.
SWEEPS: dict[str, str] = {
    "M1": "Cross-validation strategies for data with temporal, spatial, hierarchical, "
    "or phylogenetic structure",
    "M2": "Importance of spatial predictor variable selection in machine learning "
    "applications of moving window kriging",
    "M3": "Comparing predictive accuracy",
    "M4": "Testing the equality of prediction mean squared errors",
    "M5": "A simple, positive semi-definite, heteroskedasticity and autocorrelation "
    "consistent covariance matrix",
    "M6": "Hyperparameters and tuning strategies for random forest",
    "M7": "Machine learning based estimation of ground-level PM2.5 concentrations",
    "M8": "Field evaluation of low-cost particulate matter sensors in high and low "
    "concentration environments",
    "M9": "The CAMS reanalysis of atmospheric composition",
    "M10": "LightGBM: a highly efficient gradient boosting decision tree",
    "M11": "A unified approach to interpreting model predictions",
    "M12": "Estimating ground-level PM2.5 using aerosol optical depth and "
    "meteorological parameters",
}

# A fuzzy search returns the most-cited nearby paper, not the requested one. Accepting
# results[0] unchecked produced a list in which A9 resolved to a COVID lockdown study and
# "conformal prediction" to a 1960s decision-theory essay. Any candidate whose title does
# not genuinely resemble the query is discarded as UNRESOLVED, because a wrong citation in
# the manuscript is worse than an acknowledged gap.
MATCH_THRESHOLD = 0.62

# Token-share alone is not sufficient when one word carries all the discriminative power.
# "PM2.5 prediction in Tashkent using machine learning" scored 0.71 against a paper on the
# *Brazilian Cerrado*: every generic term matched and only the place name did not. Where a
# target is defined by a proper noun, that noun is required outright.
REQUIRED: dict[str, set[str]] = {
    "A2": {"central", "asia"},
    "A4": {"maiac", "central", "asia"},
    "A5": {"kazakhstan"},
    "A6": {"dushanbe"},
    "A7": {"aral"},
    "A8": {"aral"},
    "A9": {"tashkent"},
    "B5": {"delhi"},
    "C3": {"african"},
    "M9": {"cams"},
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "of",
    "for",
    "in",
    "on",
    "to",
    "with",
    "using",
    "from",
    "its",
    "at",
    "by",
    "or",
    "as",
    "is",
    "are",
    "be",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 2}


def title_matches(query: str, title: str | None, ref: str = "") -> tuple[bool, float]:
    """Accept only if the returned title genuinely corresponds to what was asked for.

    Scored as the share of the query's content words present in the title. Recall-oriented
    on purpose: publishers routinely append or drop subtitles, so requiring a symmetric
    match would reject correct hits, while requiring most of the query's distinctive terms
    reliably rejects an unrelated paper.
    """
    if not title:
        return False, 0.0
    q, t = _tokens(query), _tokens(title)
    if not q:
        return False, 0.0
    required = REQUIRED.get(ref.removeprefix("S:"), set())
    if required and not required.issubset(t):
        return False, 0.0
    score = len(q & t) / len(q)
    return score >= MATCH_THRESHOLD, score


IDENTITY_THRESHOLD = 0.85


def same_work(a: str | None, b: str | None) -> bool:
    """Are these two titles the same paper? A stricter question than relevance.

    Reusing the retrieval threshold here merged the LightGBM paper with "A Novel Scheme for
    Mapping of MVT-Type Pb-Zn Prospectivity: LightGBM ... Gradient Boosting Decision Tree",
    which shares five of seven content words and so cleared 0.62 comfortably. Identity uses
    a *symmetric* Jaccard: a title that adds a whole other subject is not the same work,
    however much vocabulary it borrows.
    """
    if not a or not b:
        return False
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= IDENTITY_THRESHOLD


def _safe(text: str) -> str:
    """Console-safe rendering. The JSON keeps full Unicode; only stdout is narrowed.

    The Windows console here is cp1251, which cannot encode the non-breaking hyphens and
    typographic dashes publishers put in titles. Printing one raised UnicodeEncodeError and
    aborted a sweep that had already completed its network work.
    """
    enc = sys.stdout.encoding or "utf-8"
    return text.encode(enc, errors="replace").decode(enc, errors="replace")


def _get(client: httpx.Client, url: str, params: dict[str, Any]) -> Any | None:
    """One polite request. Any failure returns None -- a probe must not kill the sweep."""
    try:
        r = client.get(url, params=params, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return None


def _invert(index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as an inverted index; rebuild the text."""
    if not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, spots in index.items():
        positions.extend((s, word) for s in spots)
    return " ".join(w for _, w in sorted(positions)) or None


def from_openalex(client: httpx.Client, query: str) -> list[dict]:
    data = _get(client, OPENALEX, {"search": query, "per-page": 5})
    out: list[dict] = []
    for w in (data or {}).get("results") or []:
        oa = (w.get("best_oa_location") or {}) or {}
        out.append(
            {
                "title": w.get("title"),
                "year": w.get("publication_year"),
                "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
                "venue": ((w.get("primary_location") or {}).get("source") or {}).get(
                    "display_name"
                ),
                "authors": [
                    a["author"]["display_name"]
                    for a in (w.get("authorships") or [])[:8]
                    if a.get("author")
                ],
                "abstract": _invert(w.get("abstract_inverted_index")),
                "oa_pdf": oa.get("pdf_url"),
                "is_oa": bool(w.get("open_access", {}).get("is_oa")),
                "cited_by": w.get("cited_by_count"),
                "source_api": "openalex",
            }
        )
    return out


def from_crossref(client: httpx.Client, query: str) -> list[dict]:
    data = _get(client, CROSSREF, {"query.bibliographic": query, "rows": 5})
    out: list[dict] = []
    for it in ((data or {}).get("message") or {}).get("items") or []:
        abstract = it.get("abstract")
        if abstract:
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        out.append(
            {
                "title": (it.get("title") or [None])[0],
                "year": (it.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0],
                "doi": it.get("DOI"),
                "venue": (it.get("container-title") or [None])[0],
                "authors": [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in (it.get("author") or [])
                ][:8],
                "abstract": abstract,
                "source_api": "crossref",
            }
        )
    return out


def from_s2(client: httpx.Client, query: str) -> list[dict]:
    fields = "title,year,abstract,externalIds,openAccessPdf,venue,authors,tldr,citationCount"
    data = _get(client, S2, {"query": query, "limit": 5, "fields": fields})
    out: list[dict] = []
    for p in (data or {}).get("data") or []:
        out.append(
            {
                "title": p.get("title"),
                "year": p.get("year"),
                "doi": (p.get("externalIds") or {}).get("DOI"),
                "pmcid": (p.get("externalIds") or {}).get("PubMedCentral"),
                "arxiv": (p.get("externalIds") or {}).get("ArXiv"),
                "venue": p.get("venue"),
                "authors": [a["name"] for a in (p.get("authors") or [])][:8],
                "abstract": p.get("abstract"),
                "tldr": (p.get("tldr") or {}).get("text"),
                "oa_pdf": (p.get("openAccessPdf") or {}).get("url"),
                "cited_by": p.get("citationCount"),
                "source_api": "semanticscholar",
            }
        )
    return out


def epmc_fulltext(client: httpx.Client, doi: str | None, title: str | None) -> str | None:
    """Europe PMC serves full text for open-access records; returns the PMCID if present."""
    q = f'DOI:"{doi}"' if doi else f'TITLE:"{title}"'
    data = _get(client, EPMC, {"query": q, "format": "json", "pageSize": 1})
    results = ((data or {}).get("resultList") or {}).get("result") or []
    if not results:
        return None
    r = results[0]
    if r.get("isOpenAccess") == "Y" and r.get("pmcid"):
        return r["pmcid"]
    return None


def merge(*records: dict | None) -> dict:
    """Combine records that describe the *same work*, never fields from different ones.

    Field-wise "first non-empty value wins" is wrong across independent search APIs. Each
    one resolves the query separately, so a naive merge paired OpenAlex's title for the
    LightGBM paper with a Crossref DOI belonging to an unrelated Natural Resources Research
    article. The result looks impeccable and resolves to the wrong paper — worse than an
    obviously missing field, because nothing about it invites checking.

    So: the first record is the spine, and a later record may only contribute fields if it
    is plausibly the same work — matching DOI, or no DOI to contradict with and a matching
    title. Anything else is discarded and recorded in `merge_conflicts`.
    """
    spine: dict[str, Any] = {}
    contributors: list[str] = []
    conflicts: list[str] = []

    for rec in records:
        if not rec:
            continue
        if not spine:
            spine = {k: v for k, v in rec.items() if v not in (None, "", [])}
            contributors.append(rec["source_api"])
            continue

        same_doi = (
            rec.get("doi") and spine.get("doi") and rec["doi"].lower() == spine["doi"].lower()
        )
        no_conflict = not rec.get("doi") or not spine.get("doi")

        if not (same_doi or (no_conflict and same_work(spine.get("title"), rec.get("title")))):
            conflicts.append(f"{rec['source_api']}:{(rec.get('title') or '?')[:40]}")
            continue

        for k, v in rec.items():
            if v in (None, "", []) or k == "source_api":
                continue
            spine.setdefault(k, v)
        contributors.append(rec["source_api"])

    spine["apis"] = contributors
    if conflicts:
        spine["merge_conflicts"] = conflicts
    return spine


def depth_of(rec: dict) -> str:
    if rec.get("pmcid") or rec.get("arxiv") or rec.get("oa_pdf"):
        return "FULL"
    if rec.get("abstract"):
        return "ABSTRACT"
    if rec.get("title"):
        return "SNIPPET"
    return "UNRESOLVED"


def best(
    query: str, candidates: list[dict], ref: str = ""
) -> tuple[dict | None, float, str | None]:
    """Highest-scoring candidate that clears the gate, plus the best rejected title."""
    scored = sorted(
        ((c, title_matches(query, c.get("title"), ref)[1]) for c in candidates),
        key=lambda cs: cs[1],
        reverse=True,
    )
    if not scored:
        return None, 0.0, None
    top, score = scored[0]
    if score == 0.0 and candidates:
        return None, 0.0, candidates[0].get("title")
    if score >= MATCH_THRESHOLD:
        return top, score, None
    return None, score, top.get("title")


def resolve(client: httpx.Client, key: str, query: str) -> dict:
    pools = []
    for fetch in (from_openalex, from_s2, from_crossref):
        pools.append(fetch(client, query))
        time.sleep(0.4)

    picked, scores, rejected = [], [], []
    for pool in pools:
        hit, score, reject = best(query, pool, key)
        picked.append(hit)
        scores.append(score)
        if reject:
            rejected.append(reject)

    if not any(picked):
        # Recorded, not silently dropped: an acknowledged gap is auditable, a missing row
        # looks like the question was never asked.
        return {
            "ref": key,
            "query": query,
            "depth": "UNRESOLVED",
            "best_score": round(max(scores) if scores else 0.0, 2),
            "closest_rejected": rejected[0] if rejected else None,
        }

    rec = merge(*picked)
    rec["match_score"] = round(max(scores), 2)

    if not rec.get("pmcid"):
        pmcid = epmc_fulltext(client, rec.get("doi"), rec.get("title"))
        if pmcid:
            rec["pmcid"] = pmcid
        time.sleep(0.3)

    rec["ref"] = key
    rec["query"] = query
    rec["depth"] = depth_of(rec)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--skip-sweeps", action="store_true")
    args = ap.parse_args()

    records: list[dict] = []
    headers = {"User-Agent": "eco-pulse-ca/0.1 (academic benchmark; contact via repository)"}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        print(f"resolving {len(TARGETS)} known targets\n")
        for key, query in TARGETS.items():
            rec = resolve(client, key, query)
            records.append(rec)
            title = _safe((rec.get("title") or "unresolved")[:62])
            print(f"  {key:4s} {rec['depth']:10s} {title}")

        if not args.skip_sweeps:
            print(f"\ntopical sweeps ({len(SWEEPS)})\n")
            for key, query in SWEEPS.items():
                rec = resolve(client, f"S:{key}", query)
                records.append(rec)
                title = _safe((rec.get("title") or "unresolved")[:62])
                print(f"  {key:20s} {rec['depth']:10s} {title}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    by_depth: dict[str, int] = {}
    for r in records:
        by_depth[r["depth"]] = by_depth.get(r["depth"], 0) + 1
    print(f"\nwrote {out}")
    print("depth: " + ", ".join(f"{k}={v}" for k, v in sorted(by_depth.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
