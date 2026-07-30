"""Standing rule 1, enforced mechanically: no random splits, ever.

This is a **static scan of `src/`**, not a runtime assertion, and that is deliberate. A
runtime check only fires on code paths a test happens to exercise; by the time a random
split reaches a results table it has usually already been run. Scanning the source means
the forbidden construct cannot be committed at all.

Air quality data is autocorrelated in space and time. A random shuffle places observations
from the same station -- often the same hour -- on both sides of the split, which inflates
scores dramatically. It is the single most common flaw in this literature: the closest
environmental analogue to this study (Jin et al., PeerJ 2022, Xinjiang) validates with
10-fold CV and no spatial stratification, and reports R2 of 0.73-0.81 as a result. See
research/LITERATURE.md section C.

If you genuinely need one of these constructs, the answer is not to add an exemption. It
is to use GroupKFold / TimeSeriesSplit / a leave-city-out iterator instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

#: (regex, why it is forbidden, what to use instead)
FORBIDDEN: list[tuple[str, str, str]] = [
    (
        r"\btrain_test_split\s*\(",
        "sklearn's train_test_split shuffles by default",
        "use the frozen splits in benchmark/splits/",
    ),
    (
        r"\bshuffle\s*=\s*True\b",
        "shuffling destroys temporal order and leaks autocorrelated neighbours",
        "keep temporal order; use a blocked split with a purge gap",
    ),
    (
        r"(?<![A-Za-z_])KFold\s*\(",
        "plain KFold splits randomly across stations and time",
        "use GroupKFold (by city/station) or TimeSeriesSplit",
    ),
    (
        r"(?<![A-Za-z_])ShuffleSplit\s*\(",
        "ShuffleSplit is a random split by construction",
        "use a blocked temporal or leave-city-out iterator",
    ),
    (
        r"\.sample\s*\(\s*frac\s*=",
        "random subsampling of an autocorrelated series leaks between folds",
        "subsample by whole blocks (station or time block), not by row",
    ),
]

# StratifiedGroupKFold / GroupKFold legitimately contain "KFold"; the negative lookbehind
# above already excludes them, but they are named here so the intent is explicit.
ALLOWED_SUBSTRINGS = ("GroupKFold", "StratifiedGroupKFold", "TimeSeriesSplit")


def _python_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def test_src_tree_is_non_empty():
    """Guard against the scan trivially passing because it found nothing to scan."""
    assert _python_files(), f"no python files found under {SRC}"


@pytest.mark.parametrize("pattern,reason,remedy", FORBIDDEN)
def test_no_forbidden_split_constructs(pattern: str, reason: str, remedy: str):
    rx = re.compile(pattern)
    violations: list[str] = []

    for path in _python_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if any(a in code for a in ALLOWED_SUBSTRINGS):
                continue
            if rx.search(code):
                violations.append(
                    f"  {path.relative_to(SRC.parent.parent)}:{lineno}: {line.strip()}"
                )

    assert not violations, (
        f"\nForbidden random-split construct: /{pattern}/\n"
        f"Why: {reason}\nInstead: {remedy}\n\nFound at:\n" + "\n".join(violations)
    )


def test_pyproject_declares_random_splits_disallowed():
    """The prohibition is also declared in config, so tooling can read it."""
    text = (SRC.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "random_splits_allowed = false" in text
