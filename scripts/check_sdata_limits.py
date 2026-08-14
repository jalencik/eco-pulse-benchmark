"""Guard the Scientific Data submission limits on the Data Descriptor templates.

Run:  python scripts/check_sdata_limits.py

Scientific Data enforces a 170-word abstract, a 700-word Background and Summary, and a
110-character title. The editorial system queries a non-conforming manuscript rather than
truncating it, and a query costs weeks -- which is the entire reason this venue was chosen
over a journal with a first-review round measured in months.

The abstract currently sits one word under its limit. A single added clause breaks it
silently, exactly as a one-word edit breaks the Elsevier highlights guarded by
`check_highlights.py`. This script exists for the same reason and is its sibling.

Counting is done on the *rendered* text: placeholders are substituted from numbers.json
first, because `{{n_stations}}` is one token but the `8` it becomes is also one, while
`{{train_start}}` becomes a date that a reader counts as one word and a naive splitter
might not. Counting the template rather than the render would measure the wrong document.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDATA = ROOT / "paper" / "sdata"
NUMBERS = ROOT / "paper" / "numbers.json"

PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

# (template, heading the section starts at, word limit)
LIMITS: list[tuple[str, str, int]] = [
    ("00_title_abstract.md.tmpl", "## Abstract", 170),
    ("01_background_summary.md.tmpl", "## Background and Summary", 700),
]

TITLE_LIMIT = 110


def render(text: str, nums: dict[str, str]) -> tuple[str, list[str]]:
    missing = sorted({k for k in PLACEHOLDER.findall(text) if k not in nums})
    return PLACEHOLDER.sub(lambda m: nums.get(m.group(1), m.group(1)), text), missing


def main() -> int:
    if not SDATA.is_dir():
        print(f"FAILED: {SDATA} does not exist", file=sys.stderr)
        return 1

    nums = json.loads(NUMBERS.read_text(encoding="utf-8"))
    failures: list[str] = []

    # Title: first ATX heading of the first template, measured in characters including
    # spaces, which is how the submission form counts it.
    first = SDATA / LIMITS[0][0]
    rendered_first, _ = render(first.read_text(encoding="utf-8"), nums)
    title_line = next(
        (ln[2:].strip() for ln in rendered_first.splitlines() if ln.startswith("# ")), ""
    )
    if not title_line:
        failures.append(f"{first.name}: no title heading found")
    else:
        n = len(title_line)
        status = "OK" if n <= TITLE_LIMIT else f"OVER by {n - TITLE_LIMIT}"
        print(f"  title{'':26} {n:4d} / {TITLE_LIMIT:4d} chars  {status}")
        if n > TITLE_LIMIT:
            failures.append(f"title is {n} characters, limit {TITLE_LIMIT}")

    for name, heading, limit in LIMITS:
        path = SDATA / name
        if not path.exists():
            failures.append(f"{name}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        rendered, missing = render(text, nums)
        if missing:
            failures.append(f"{name}: unresolved placeholders {missing}")
            continue
        if heading not in rendered:
            failures.append(f"{name}: heading {heading!r} not found")
            continue
        words = len(rendered.split(heading, 1)[1].split())
        status = "OK" if words <= limit else f"OVER by {words - limit}"
        print(f"  {heading:30} {words:4d} / {limit:4d} words  {status}")
        if words > limit:
            failures.append(f"{heading} is {words} words, limit {limit}")

    if failures:
        print("\nFAILED -- Scientific Data limits not met:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print("\nall Scientific Data submission limits satisfied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
