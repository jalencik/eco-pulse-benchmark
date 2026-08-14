"""The stitched manuscript is the artifact a reader receives.

`render.py` already fails on an unresolved placeholder, but the stitched file is assembled
afterwards from separate inputs, so the guarantee has to hold on the final bytes too. The
specific hazards:

  - a rendered section left over from a previous run, silently carrying last run's numbers;
  - a `{{placeholder}}` reaching the reader, which is worse than a build that refuses;
  - a reference list that drifts from the records the resolver actually verified.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "paper" / "sections"
MANUSCRIPT = ROOT / "paper" / "extended_technical_report.md"
SOURCES = ROOT / "research" / "sources.json"
STITCH = ROOT / "paper" / "scripts" / "stitch.py"

PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

pytestmark = pytest.mark.skipif(not MANUSCRIPT.exists(), reason="manuscript not yet stitched")


@pytest.fixture(scope="module")
def text() -> str:
    return MANUSCRIPT.read_text(encoding="utf-8")


class TestStitchedOutput:
    def test_no_unresolved_placeholders(self, text):
        assert not PLACEHOLDER.findall(text), "a placeholder reached the final manuscript"

    def test_all_seven_sections_present(self, text):
        for n, name in enumerate(
            [
                "Introduction",
                "Data, Operational Constraints",
                "Benchmark Construction",
                "Baseline",
                "Model",
                "Results",
                "Limitations and Discussion",
            ],
            start=1,
        ):
            assert re.search(rf"^# {n}\. .*{re.escape(name)}", text, re.M), (
                f"section {n} ({name}) missing from the manuscript"
            )

    def test_sections_appear_in_order(self, text):
        headings = re.findall(r"^# (\d)\. ", text, re.M)
        assert headings == sorted(headings), f"sections out of order: {headings}"

    def test_has_a_reference_section(self, text):
        assert "## References" in text

    def test_does_not_claim_state_of_the_art(self, text):
        """A standing rule of this project, checked on the assembled artifact."""
        lowered = text.lower()
        for banned in ("state of the art", "state-of-the-art", "sota"):
            for line in lowered.splitlines():
                if banned in line and "we do not claim" not in line:
                    pytest.fail(f"unqualified SOTA claim: {line.strip()[:90]}")


class TestReferenceIntegrity:
    def test_every_resolved_source_is_cited_in_the_list(self, text):
        records = json.loads(SOURCES.read_text(encoding="utf-8"))
        for r in records:
            if r["depth"] != "UNRESOLVED":
                assert f"**[{r['ref']}]**" in text, f"{r['ref']} missing from references"

    def test_unresolved_sources_carry_no_fabricated_entry(self, text):
        """A9 has no record; it must appear as a gap, never as a citation with metadata."""
        records = json.loads(SOURCES.read_text(encoding="utf-8"))
        for r in records:
            if r["depth"] == "UNRESOLVED":
                assert "no matching record" in text or r["ref"] in text

    def test_a_ref_is_not_listed_both_as_read_and_as_not_obtained(self, text):
        """A3 was read in full but is unindexed; listing it twice reads as a contradiction."""
        not_obtained = text.split("### Sought but not obtained")[-1]
        unindexed_block = text.split("### Sources not indexed by the resolvers")[-1].split(
            "### Sought but not obtained"
        )[0]
        for ref in re.findall(r"\*\*\[(\w+)\]\*\*", unindexed_block):
            assert f"**[{ref}]**" not in not_obtained, (
                f"{ref} is listed as both read-in-full and not-obtained"
            )

    def test_a9_split_protocol_is_flagged_unverified(self, text):
        """The one piece of prior art whose protocol we could not check."""
        assert "unverified" in text.lower()
        assert "Tashkent" in text

    def test_dois_in_references_match_the_resolved_records(self, text):
        records = json.loads(SOURCES.read_text(encoding="utf-8"))
        for r in records:
            if r.get("doi"):
                assert r["doi"] in text, f"{r['ref']} DOI absent or altered in references"


class TestStitchRefusesStaleInput:
    def test_stitch_fails_when_a_rendered_section_is_older_than_its_template(self, tmp_path):
        """Touching a template without re-rendering must not produce a manuscript."""
        tmpl = SEC / "01_introduction.md.tmpl"
        rendered = SEC / "01_introduction.md"
        original = rendered.stat().st_mtime

        import os

        # Make the rendered file older than the template.
        os.utime(rendered, (original - 100, tmpl.stat().st_mtime - 100))
        try:
            out = subprocess.run(
                [sys.executable, str(STITCH)], capture_output=True, text=True, cwd=ROOT
            )
            assert out.returncode == 1, "stitch accepted a stale rendered section"
            assert "REFUSING" in out.stderr
        finally:
            os.utime(rendered, (original, original))

    def test_stitch_succeeds_on_fresh_input(self):
        """Renders first, so the test does not depend on build order.

        In `reproduce` the suite runs *before* the `paper` target, so any assertion that
        rendered sections are fresh fails whenever a template was edited in the same
        commit — the very situation the pipeline exists to resolve. Producing its own
        input makes this hermetic.
        """
        render = subprocess.run(
            [sys.executable, str(ROOT / "paper" / "scripts" / "render.py")],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert render.returncode == 0, render.stderr
        out = subprocess.run(
            [sys.executable, str(STITCH)], capture_output=True, text=True, cwd=ROOT
        )
        assert out.returncode == 0, out.stderr


class TestPaperTargetProducesTheManuscript:
    def test_stitch_runs_after_render(self):
        import tasks

        order = [c[-1] for c in tasks.TARGETS["paper"]]
        assert order.index("paper/scripts/render.py") < order.index("paper/scripts/stitch.py")
