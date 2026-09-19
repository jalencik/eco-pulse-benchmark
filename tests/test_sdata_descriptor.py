"""The submission manuscript must stay conformant and consistent.

A journal queries a non-conforming manuscript instead of truncating it, and a query costs
weeks. These tests make the format constraints fail at build time instead.

They also enforce the property that matters most once two documents exist: the submission
manuscript and the longer technical report are rendered from the SAME `numbers.json`, so they
cannot disagree about a figure. A second document is a second place for a number to go stale.
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

# Zenodo VERSION DOI for v1.1.0 (not the concept DOI). Reserved 2026-08-14.
RESERVED_DOI = "10.5281/zenodo.21930669"

# The research-article section order.
REQUIRED = [
    "Abstract",
    "1. Introduction",
    "2. Materials and methods",
    "3. The released benchmark",
    "4. Results",
    "5. Discussion",
    "6. Conclusions",
    "Data availability",
    "Code availability",
]

pytestmark = pytest.mark.skipif(not DOC.exists(), reason="descriptor not built yet")


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_every_required_section_is_present(doc):
    missing = [h for h in REQUIRED if f"## {h}" not in doc]
    assert not missing, f"manuscript is missing required sections: {missing}"


def test_sections_appear_in_the_prescribed_order(doc):
    positions = [(h, doc.index(f"## {h}")) for h in REQUIRED if f"## {h}" in doc]
    ordered = [h for h, _ in sorted(positions, key=lambda kv: kv[1])]
    assert ordered == [h for h in REQUIRED if f"## {h}" in doc], (
        f"sections are out of order: {ordered}"
    )


def test_conclusions_section_exists(doc):
    """The venue is not yet chosen and may be a local journal, so the manuscript is shaped as
    a standard research article. Every such template expects a Conclusions section, and its
    absence is the first thing a desk editor notices. (Under the earlier Data Descriptor
    shape this guard ran in the opposite direction, because that format forbids one.)
    """
    assert re.search(r"^#+\s*(\d+\.\s*)?Conclusions?\b", doc, re.MULTILINE), (
        "a research article needs a Conclusions section"
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
    body = doc.split("## 1. Introduction", 1)[1].split("\n## ", 1)[0]
    assert len(body.split()) <= 700, f"Introduction is {len(body.split())} words"


def test_data_availability_does_not_assert_an_unminted_doi(doc):
    """Data Availability must cite the reserved DOI, and only that one.

    A DOI that does not resolve is worse than an honest placeholder, so while the deposit was
    pending this test required an explicit PENDING marker. The DOI has since been reserved on
    Zenodo, so the guard now checks the opposite direction: the section must carry exactly the
    reserved identifier, carry no leftover placeholder, and not introduce any other DOI that
    has not been verified.

    RESERVED_DOI is the *version* DOI for v1.1.0, not the concept DOI: a reported score must
    be attributable to one frozen split definition.
    """
    section = doc.split("## Data availability", 1)[1].split("\n## ", 1)[0]
    assert RESERVED_DOI in section, (
        f"Data availability does not cite the reserved DOI {RESERVED_DOI}"
    )
    assert "PENDING" not in section.upper(), (
        "a placeholder survives in Data availability alongside a real DOI"
    )
    others = {d.rstrip(".,)") for d in re.findall(r"10\.\d{4,9}/[^\s)\]*]+", section)}
    others.discard(RESERVED_DOI)
    assert not others, f"unverified DOI(s) asserted in Data Availability: {sorted(others)}"


def test_no_doi_placeholder_survives_anywhere(doc):
    """The placeholder must be gone from the whole document, not just Data Availability."""
    assert "DOI PENDING DEPOSIT" not in doc


def test_descriptor_and_manuscript_agree_on_shared_figures(doc):
    """Both documents render from one numbers.json, so shared keys must match in the text."""
    nums = json.loads(NUMBERS.read_text(encoding="utf-8"))
    manuscript = (ROOT / "paper" / "extended_technical_report.md").read_text(encoding="utf-8")
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
                f"{key} = {value} appears in the technical report but not in the manuscript; "
                "the two documents would disagree"
            )


def test_every_template_is_in_the_build_order():
    """A template on disk that the builder does not know about would be silently dropped."""
    build = (ROOT / "scripts" / "build_sdata.py").read_text(encoding="utf-8")
    order = set(re.findall(r'"(\d\d[a-z]?_[a-z_]+)"', build))
    on_disk = {p.name.replace(".md.tmpl", "") for p in SDATA.glob("*.md.tmpl")}
    assert on_disk <= order, f"templates not in build order: {sorted(on_disk - order)}"
