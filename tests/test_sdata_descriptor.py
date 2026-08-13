"""The Scientific Data Data Descriptor must stay conformant and consistent.

Scientific Data queries a non-conforming manuscript rather than truncating it, and a query
costs weeks — which is the reason this venue was chosen over a journal with a ~48-week first
review round. These tests make the format constraints fail at build time instead.

They also enforce the property that matters most once two documents exist: the Data Descriptor
and the research-article manuscript are rendered from the SAME `numbers.json`, so they cannot
disagree about a figure. A second document is a second place for a number to go stale.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDATA = ROOT / "paper" / "sdata"
DOC = ROOT / "paper" / "sdata_descriptor.md"
NUMBERS = ROOT / "paper" / "numbers.json"
PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

# Required by the Scientific Data submission guidelines, in order.
REQUIRED = [
    "Abstract",
    "Background and Summary",
    "Methods",
    "Data Records",
    "Technical Validation",
    "Usage Notes",
    "Data Availability",
    "Code Availability",
]

pytestmark = pytest.mark.skipif(not DOC.exists(), reason="descriptor not built yet")


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_every_required_section_is_present(doc):
    missing = [h for h in REQUIRED if f"## {h}" not in doc]
    assert not missing, f"Data Descriptor is missing required sections: {missing}"


def test_sections_appear_in_the_prescribed_order(doc):
    positions = [(h, doc.index(f"## {h}")) for h in REQUIRED if f"## {h}" in doc]
    ordered = [h for h, _ in sorted(positions, key=lambda kv: kv[1])]
    assert ordered == [h for h in REQUIRED if f"## {h}" in doc], (
        f"sections are out of order: {ordered}"
    )


def test_no_conclusion_section(doc):
    """The Data Descriptor format has no Conclusion; including one invites a desk query."""
    assert not re.search(r"^#+\s*(\d+\.\s*)?Conclusion", doc, re.MULTILINE), (
        "the Data Descriptor format has no Conclusion section"
    )


def test_no_unresolved_placeholders(doc):
    leftover = sorted(set(PLACEHOLDER.findall(doc)))
    assert not leftover, f"unresolved placeholders reached the descriptor: {leftover}"


def test_title_within_110_characters(doc):
    title = next(line for line in doc.splitlines() if line.startswith("# "))
    text = title[2:].strip()
    assert len(text) <= 110, f"title is {len(text)} chars, limit 110"


def test_abstract_within_170_words(doc):
    body = doc.split("## Abstract", 1)[1].split("##", 1)[0]
    assert len(body.split()) <= 170, f"abstract is {len(body.split())} words, limit 170"


def test_background_and_summary_within_700_words(doc):
    body = doc.split("## Background and Summary", 1)[1].split("\n## ", 1)[0]
    assert len(body.split()) <= 700, f"Background and Summary is {len(body.split())} words"


def test_data_availability_does_not_assert_an_unminted_doi(doc):
    """A DOI that does not resolve is worse than an honest placeholder.

    Scientific Data requires deposition in a repository with a persistent identifier. Until
    the deposit exists the manuscript must say so rather than print a plausible-looking
    identifier that a reviewer will try to resolve.
    """
    section = doc.split("## Data Availability", 1)[1].split("\n## ", 1)[0]
    minted = re.findall(r"10\.\d{4,9}/[^\s)\]]+", section)
    if minted:
        assert "PENDING" in section.upper(), (
            f"an unverified DOI is asserted in Data Availability: {minted}"
        )
    assert "PENDING DEPOSIT" in section.upper() or minted, (
        "Data Availability must either cite a real DOI or state that deposition is pending"
    )


def test_descriptor_and_manuscript_agree_on_shared_figures(doc):
    """Both documents render from one numbers.json, so shared keys must match in the text."""
    nums = json.loads(NUMBERS.read_text(encoding="utf-8"))
    manuscript = (ROOT / "paper" / "final_manuscript.md").read_text(encoding="utf-8")
    for key in (
        "n_stations",
        "n_cities",
        "taskn_retrospective_rmse",
        "daily_constant_rmse",
        "sig_primary_t_p",
        "benchmark_version",
    ):
        value = nums[key]
        if value in manuscript:
            assert value in doc, (
                f"{key} = {value} appears in the manuscript but not in the Data Descriptor; "
                "the two documents would disagree"
            )


def test_every_template_is_in_the_build_order():
    """A template on disk that the builder does not know about would be silently dropped."""
    build = (ROOT / "scripts" / "build_sdata.py").read_text(encoding="utf-8")
    order = set(re.findall(r'"(\d\d_[a-z_]+)"', build))
    on_disk = {p.name.replace(".md.tmpl", "") for p in SDATA.glob("*.md.tmpl")}
    assert on_disk <= order, f"templates not in build order: {sorted(on_disk - order)}"
