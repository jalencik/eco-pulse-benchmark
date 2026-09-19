"""Render and stitch the submission manuscript from paper/sdata/*.md.tmpl.

Why this is a separate document from `paper/extended_technical_report.md`
---------------------------------------------------------------
The manuscript was reshaped into a standard research article on 2026-09-19, because the
venue is unknown and may be a local journal. It previously required Background and
Summary, Methods, Data Records, Technical Validation, Usage Notes and Code Availability, with
a 170-word abstract and a 700-word Background and Summary, and it has no Conclusion section.
The research-article manuscript is retained because the preprint and the fallback venues in
JOURNAL_STRATEGY.md use it; this script builds the venue-specific document from the same
verified `numbers.json`, so the two cannot disagree about a number.

The same two refusals as `paper/scripts/render.py` apply, for the same reasons: an unresolved
`{{placeholder}}` is a hard failure, and the check is repeated on the final stitched bytes
because that is what a reader receives.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDATA = ROOT / "paper" / "sdata"
OUT = ROOT / "paper" / "sdata_descriptor.md"
PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

# The section order. A section present in the directory but missing here is a
# build failure, not a silent omission -- the whole point is that the document conforms.
# Repositories cited as data rather than as literature. journals expect datasets to
# carry their own citation; a bare prose mention does not satisfy that.
DATA_SOURCES = {
    "OpenAQ": (
        "OpenAQ Inc. (2025). *OpenAQ air quality data platform*, API v3. "
        "Accessed 2026-07-29. https://openaq.org"
    ),
}

ORDER = [
    "00_title_abstract",
    "01_background_summary",
    "02_methods",
    "03_data_records",
    "04_technical_validation",
    "05_usage_notes",
    "05b_conclusions",
    "06_availability",
    "07_declarations",
]


def main() -> int:
    nums = json.loads((ROOT / "paper" / "numbers.json").read_text(encoding="utf-8"))
    present = {p.name.replace(".md.tmpl", ""): p for p in SDATA.glob("*.md.tmpl")}

    unknown = sorted(set(present) - set(ORDER))
    if unknown:
        print(f"FAILED: template(s) not in the section order: {unknown}")
        return 1

    missing_sections = [s for s in ORDER if s not in present]

    parts, unresolved = [], []
    for stem in ORDER:
        tmpl = present.get(stem)
        if tmpl is None:
            continue
        text = tmpl.read_text(encoding="utf-8")
        missing = sorted({k for k in PLACEHOLDER.findall(text) if k not in nums})
        if missing:
            unresolved.append((tmpl.name, missing))
            continue
        parts.append(PLACEHOLDER.sub(lambda m: nums[m.group(1)], text).rstrip() + "\n")

    if unresolved:
        print("FAILED: unresolved placeholders (no matching key in numbers.json):")
        for name, keys in unresolved:
            print(f"  {name}: {', '.join(keys)}")
        return 1

    # References. Every journal requires a reference list, and this manuscript
    # cites works in-text; a citing document with no reference list fails editorial
    # screening outright. Built from research/sources.json -- the same resolver-verified
    # records the research-article manuscript uses -- and restricted to works this document
    # actually cites, so it is not padded with the longer article's bibliography.
    body = "\n\n".join(parts)
    # Match both citation forms, "(Jin et al., 2022)" and "Jin et al. (2022)", on a
    # whitespace-collapsed body: the templates are hard-wrapped, and a citation split across
    # a line ("Papagiannis et" at a line end, "al., 2024" on the next) silently dropped out of the list before this.
    # Lowercase particles ("van Donkelaar") are allowed; the record's surname is the last token.
    _flat = re.sub(r"\s+", " ", body)
    _who = r"((?:[a-z]+ )?[A-Z][\w'’-]+(?: et al\.| and (?:[a-z]+ )?[A-Z][\w'’-]+)?)"

    def _first_surname(who: str) -> str:
        return re.split(r" et al\.| and ", who)[0].split()[-1]

    cited = {
        (_first_surname(w), y) for w, y in re.findall(rf"\({_who}, ((?:19|20)\d{{2}})\)", _flat)
    }
    cited |= {
        (_first_surname(w), y)
        for w, y in re.findall(rf"(?<!\w){_who} \(((?:19|20)\d{{2}})\)", _flat)
    }
    records = json.loads((ROOT / "research" / "sources.json").read_text(encoding="utf-8"))

    def _surname(rec: dict) -> str:
        a = (rec.get("authors") or [""])[0]
        return a.split()[-1] if a else ""

    used, seen = [], set()
    for surname, year in sorted(cited):
        for rec in records:
            if rec.get("title") and _surname(rec) == surname and str(rec.get("year")) == year:
                if rec.get("doi") not in seen:
                    used.append(rec)
                    seen.add(rec.get("doi"))
                break

    def _fmt(rec: dict) -> str:
        au = rec.get("authors") or []
        if len(au) == 1:
            who = au[0]
        elif len(au) <= 3:
            who = ", ".join(au[:-1]) + f" and {au[-1]}"
        else:
            who = f"{au[0]} et al."
        out = f"{who} ({rec.get('year')}). *{rec.get('title')}*."
        if rec.get("venue"):
            out += f" {rec['venue']}."
        if rec.get("doi"):
            out += f" https://doi.org/{rec['doi']}"
        return out

    refs = ["## References", ""]
    for i, rec in enumerate(
        sorted(used, key=lambda r: (_surname(r).lower(), r.get("year") or 0)), 1
    ):
        refs.append(f"{i}. {_fmt(rec)}")

    # Data citations. Datasets are cited in their own right rather
    # than mentioned in prose. These are repositories, not literature, so they resolve against
    # DATA_SOURCES instead of sources.json.
    data_cited = sorted({k for k, _ in cited} & set(DATA_SOURCES))
    if data_cited:
        refs += ["", "### Data Citations", ""]
        for i, key in enumerate(data_cited, 1):
            refs.append(f"D{i}. {DATA_SOURCES[key]}")

    unmatched = sorted(
        {(s, y) for s, y in cited if s not in DATA_SOURCES}
        - {(_surname(r), str(r.get("year"))) for r in used}
    )
    if unmatched:
        print(f"  WARNING: unmatched in-text citations: {unmatched}")

    # The section order places
    # References directly after Code Availability and *before* Author Contributions, not at
    # the end of the document. Insert rather than append, so the declarations keep trailing.
    rendered = [s for s in ORDER if s in present]
    refs_pos = rendered.index("07_declarations") if "07_declarations" in rendered else len(parts)
    parts.insert(refs_pos, "\n".join(refs) + "\n")

    doc = "\n\n".join(parts)
    leftover = sorted(set(PLACEHOLDER.findall(doc)))
    if leftover:
        print(f"FAILED: placeholders survived into the stitched document: {leftover}")
        return 1

    OUT.write_text(doc, encoding="utf-8")
    words = len(doc.split())
    print(f"wrote {OUT}")
    print(f"  {len(parts) - 1} of {len(ORDER)} required sections + References, {words:,} words")

    if missing_sections:
        print("\n  NOT YET WRITTEN (required by the article format):")
        for s in missing_sections:
            print(f"    - {s}")
        print("\n  The document is INCOMPLETE and must not be submitted in this state.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
