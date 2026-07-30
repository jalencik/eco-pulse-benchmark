"""The reference list must not contain a citation nobody verified.

A wrong citation is the one manuscript defect a reviewer can confirm in seconds and that
destroys trust in everything around it. Two near-misses in this project make the risk
concrete, and both produced output that looked entirely reasonable:

  - "PM2.5 prediction in Tashkent" resolved to a study of the Brazilian Cerrado, because
    every generic term matched and only the place name did not;
  - the LightGBM paper was merged with a Crossref DOI belonging to an unrelated Natural
    Resources Research article, yielding a correct title pointing at the wrong paper.

These tests run offline against the banked records; they never touch the network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "research" / "sources.json"
TABLE = ROOT / "research" / "SOURCES_TABLE.md"
REVIEW = ROOT / "research" / "LITERATURE.md"

pytestmark = pytest.mark.skipif(not SOURCES.exists(), reason="literature not yet resolved")


@pytest.fixture(scope="module")
def records() -> list[dict]:
    return json.loads(SOURCES.read_text(encoding="utf-8"))


class TestResolvedRecords:
    def test_every_record_has_a_ref_and_a_depth(self, records):
        for r in records:
            assert r.get("ref"), f"record without a ref: {r}"
            assert r["depth"] in {"FULL", "ABSTRACT", "SNIPPET", "UNRESOLVED"}

    def test_resolved_records_carry_a_title(self, records):
        for r in records:
            if r["depth"] != "UNRESOLVED":
                assert r.get("title"), f"{r['ref']} resolved but has no title"

    def test_unresolved_records_carry_no_bibliographic_data(self, records):
        """An unresolved target must stay visibly empty, never half-filled with a guess."""
        for r in records:
            if r["depth"] == "UNRESOLVED":
                assert not r.get("doi") and not r.get("authors"), (
                    f"{r['ref']} is UNRESOLVED but carries metadata"
                )

    def test_dois_are_well_formed(self, records):
        for r in records:
            doi = r.get("doi")
            if doi:
                assert re.match(r"^10\.\d{4,9}/\S+$", doi), f"{r['ref']} has malformed DOI {doi!r}"

    def test_no_duplicate_dois_across_refs(self, records):
        """Two refs sharing a DOI means one of them resolved to the wrong paper."""
        seen: dict[str, str] = {}
        for r in records:
            doi = (r.get("doi") or "").lower()
            if not doi:
                continue
            assert doi not in seen, f"{r['ref']} and {seen[doi]} share DOI {doi}"
            seen[doi] = r["ref"]

    def test_match_scores_clear_the_gate(self, records):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import fetch_literature as fl

        for r in records:
            if r["depth"] == "UNRESOLVED":
                continue
            assert r.get("match_score", 0) >= fl.MATCH_THRESHOLD, (
                f"{r['ref']} banked below the match threshold"
            )

    def test_required_tokens_are_present_in_resolved_titles(self, records):
        """The Tashkent/Cerrado failure: a proper noun that must appear, and did not."""
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import fetch_literature as fl

        for r in records:
            if r["depth"] == "UNRESOLVED":
                continue
            required = fl.REQUIRED.get(r["ref"].removeprefix("S:"), set())
            if required:
                title_tokens = fl._tokens(r["title"])
                assert required.issubset(title_tokens), (
                    f"{r['ref']} title {r['title']!r} is missing required {required}"
                )


class TestMergeSafety:
    def test_merge_rejects_a_different_work(self):
        """Field-wise merging across APIs is what produced the LightGBM/Pb-Zn citation."""
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import fetch_literature as fl

        spine = {
            "title": "LightGBM: A Highly Efficient Gradient Boosting Decision Tree",
            "doi": None,
            "source_api": "openalex",
        }
        other = {
            "title": "A Novel Scheme for Mapping of MVT-Type Pb-Zn Prospectivity: "
            "LightGBM, a Gradient Boosting Decision Tree",
            "doi": "10.1007/s11053-023-10249-6",
            "source_api": "crossref",
        }
        merged = fl.merge(spine, other)
        assert merged.get("doi") is None, "merge absorbed a DOI from a different paper"
        assert merged.get("merge_conflicts"), "the rejection was not recorded"

    def test_merge_accepts_the_same_work(self):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import fetch_literature as fl

        a = {
            "title": "The CAMS reanalysis of atmospheric composition",
            "doi": "10.5194/acp-19-3515-2019",
            "source_api": "openalex",
        }
        b = {
            "title": "The CAMS reanalysis of atmospheric composition",
            "doi": "10.5194/acp-19-3515-2019",
            "abstract": "text",
            "source_api": "crossref",
        }
        merged = fl.merge(a, b)
        assert merged.get("abstract") == "text"
        assert not merged.get("merge_conflicts")

    def test_identity_is_stricter_than_relevance(self):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import fetch_literature as fl

        assert fl.IDENTITY_THRESHOLD > fl.MATCH_THRESHOLD


class TestGeneratedTableIsInSync:
    def test_table_exists_and_is_generated(self):
        assert TABLE.exists(), "run scripts/build_literature_table.py"
        assert "GENERATED by" in TABLE.read_text(encoding="utf-8").splitlines()[0]

    def test_every_resolved_doi_appears_in_the_table(self, records):
        text = TABLE.read_text(encoding="utf-8")
        for r in records:
            if r.get("doi"):
                assert r["doi"] in text, f"{r['ref']} DOI missing from the generated table"

    def test_a2_is_attributed_to_the_right_authors(self):
        """A2 was recorded as 'Kulkarni et al. (?)'; the real first author is Tursumbayeva.

        Scoped to the citation row, not the whole document: the gaps section legitimately
        names the old attribution while explaining the correction, and a document-wide
        substring check would flag that prose as a regression.
        """
        rows = [
            ln for ln in REVIEW.read_text(encoding="utf-8").splitlines() if ln.startswith("| A2 |")
        ]
        assert rows, "A2 row not found in the review"
        assert "Tursumbayeva" in rows[0]
        assert "Kulkarni" not in rows[0], "the corrected A2 attribution has regressed"
