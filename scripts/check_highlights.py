"""Verify paper/HIGHLIGHTS.md against Elsevier's submission constraints.

Run:  python scripts/check_highlights.py

Elsevier requires three to five bullets, each at most 85 characters including spaces, with
no jargon, acronyms or abbreviations. The editorial system rejects a non-conforming file
rather than truncating it, and the limit is trivially broken by a one-word edit — so it is
checked rather than trusted, like every other constraint in this repository.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "paper" / "HIGHLIGHTS.md"

MAX_CHARS = 85
MIN_BULLETS, MAX_BULLETS = 3, 5

# Acronyms Elsevier's guidance asks authors to avoid in Highlights. PM2.5 is retained
# deliberately: it is the field's standard term and a keyword readers search for, not an
# abbreviation that obscures meaning.
DISCOURAGED = ["RMSE", "MAE", "SHAP", "CAMS", "LOCO", "LSO", "AOD", "DM test", "R²"]


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1

    bullets = [
        ln[2:].strip() for ln in SRC.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")
    ]

    problems: list[str] = []
    if not MIN_BULLETS <= len(bullets) <= MAX_BULLETS:
        problems.append(f"{len(bullets)} bullets; Elsevier allows {MIN_BULLETS}-{MAX_BULLETS}")

    for i, b in enumerate(bullets, 1):
        n = len(b)
        flag = "OK " if n <= MAX_CHARS else "OVER"
        print(f"  {flag} {n:>3}/{MAX_CHARS}  {b}")
        if n > MAX_CHARS:
            problems.append(f"bullet {i} is {n - MAX_CHARS} characters over")
        for acr in DISCOURAGED:
            if re.search(rf"\b{re.escape(acr)}\b", b):
                problems.append(f"bullet {i} contains the acronym {acr!r}")

    print()
    if problems:
        print("FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(f"{len(bullets)} highlights, all within {MAX_CHARS} characters, no acronyms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
