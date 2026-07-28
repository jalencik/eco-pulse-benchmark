"""The Makefile and the Windows shim must not drift.

The Makefile is canonical -- it is what a reviewer types and what the paper documents. But
`make` is not installed on the Windows dev machine, so `tasks.py` mirrors it. If the two
diverge, `make reproduce` and `python tasks.py reproduce` stop regenerating the same
numbers, and the reproducibility claim quietly becomes false.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def makefile_targets() -> set[str]:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    phony = re.search(r"^\.PHONY:\s*(.+)$", text, re.M)
    assert phony, "Makefile has no .PHONY line"
    return set(phony.group(1).split())


def shim_targets() -> set[str]:
    import ast

    tree = ast.parse((ROOT / "tasks.py").read_text(encoding="utf-8"))
    targets: set[str] = set()
    for node in ast.walk(tree):
        # TARGETS = {...} literal
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    targets.add(k.value)
        # TARGETS["reproduce"] = ...
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.slice, ast.Constant)
                    and isinstance(tgt.slice.value, str)
                ):
                    targets.add(tgt.slice.value)
    return targets


def test_every_shim_target_exists_in_makefile():
    missing = shim_targets() - makefile_targets()
    assert not missing, f"in tasks.py but not the Makefile: {sorted(missing)}"


def test_reproduce_exists_in_both():
    """`make reproduce` is a hard requirement of the project spec."""
    assert "reproduce" in makefile_targets()
    assert "reproduce" in shim_targets()


def test_reproduce_runs_tests_before_producing_numbers():
    """Order is load-bearing: splits are frozen and hash-verified before any model runs."""
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("reproduce:"))
    order = line.split(":", 1)[1].split()
    assert order.index("test") < order.index("splits") < order.index("baselines")


def test_gitignore_never_commits_env_but_does_commit_splits():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.env$", text, re.M), ".env must be gitignored"
    assert "!benchmark/splits/**" in text, "frozen splits are the deliverable and must commit"
