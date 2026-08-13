"""Every published table must have a producer inside `make reproduce`.

WHY THIS TEST EXISTS
--------------------
Between 99b9a13 and 2026-08-13 the repository was in this state:

- `paper/scripts/extract_numbers.py` read `t4_01`, `t5_01`, `t5_02` and `t6_01`-`t6_05`;
- **no script in the repository wrote any of those names** -- the producers emitted
  `phase5_*.csv` / `phase6_*.csv`, which were renamed by hand;
- `reproduce` did not run the model layer at all, so it regenerated only the `t3_*` family
  and still exited 0.

The failure was therefore silent and total: `make reproduce` "succeeded" for months while
every headline table sat untouched on disk, and the manuscript claimed "No number in this
document is typed by hand."

A test that merely ran the pipeline would not have caught it -- the pipeline passed. What was
missing was an assertion that the *set of tables consumed* equals the *set of tables produced*.
That is what this file asserts, statically, without running anything.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLE_RE = re.compile(r"\b(t\d_\d{2}_[a-z0-9_]+\.csv)\b")


def _tracked_tables_in(path: pathlib.Path) -> set[str]:
    if not path.exists():
        return set()
    return set(TABLE_RE.findall(path.read_text(encoding="utf-8")))


def _reproduce_scripts() -> list[pathlib.Path]:
    """The .py files `reproduce` actually executes, read from tasks.py itself.

    Parsed rather than hardcoded: a duplicated list would drift from the real chain, which is
    the exact class of bug this test exists to prevent.
    """
    src = (ROOT / "tasks.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    targets: dict[str, list[list[str]]] = {}
    chain: tuple[str, ...] = ()
    for node in ast.walk(tree):
        # TARGETS carries a type annotation, so it parses as AnnAssign, not Assign. Handling
        # only Assign silently found nothing and made this test vacuously pass.
        if isinstance(node, ast.Assign | ast.AnnAssign):
            tgt = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
            name = getattr(tgt, "id", None)
            if node.value is None:
                continue
            if name == "TARGETS":
                for k, v in zip(node.value.keys, node.value.values, strict=True):
                    cmds = []
                    for cmd in v.elts:
                        parts = [e.value for e in cmd.elts if isinstance(e, ast.Constant)]
                        cmds.append(parts)
                    targets[k.value] = cmds
            elif name == "REPRODUCE_CHAIN":
                chain = tuple(e.value for e in node.value.elts)

    assert chain, "REPRODUCE_CHAIN not found in tasks.py"
    out: list[pathlib.Path] = []
    for target in chain:
        for cmd in targets.get(target, []):
            for part in cmd:
                if isinstance(part, str) and part.endswith(".py"):
                    out.append(ROOT / part)
    return out


def test_reproduce_chain_includes_the_model_layer():
    """Regression guard: the model layer was silently absent from `reproduce`."""
    src = (ROOT / "tasks.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    chain: tuple[str, ...] = ()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "REPRODUCE_CHAIN":
            chain = tuple(e.value for e in node.value.elts)
    assert chain, "REPRODUCE_CHAIN not found in tasks.py"
    assert "models" in chain, (
        "`models` is not in REPRODUCE_CHAIN -- the tuning and DM/SHAP layers would not run, "
        "and every t4/t5/t6 table would go stale while `reproduce` still exited 0"
    )
    # order matters: phase6_analysis.py reads t5_02, produced by train_phase5.py
    assert chain.index("models") < chain.index("paper")
    assert chain.index("baselines") < chain.index("models")


def test_every_consumed_table_has_a_producer_in_the_chain():
    consumed = _tracked_tables_in(ROOT / "paper" / "scripts" / "extract_numbers.py")
    assert consumed, "found no t*_*.csv reads in extract_numbers.py -- regex or path is wrong"

    produced: set[str] = set()
    for script in _reproduce_scripts():
        text = script.read_text(encoding="utf-8") if script.exists() else ""
        for name in TABLE_RE.findall(text):
            if "to_csv" in text and name in text:
                produced.add(name)

    orphans = sorted(consumed - produced)
    assert not orphans, (
        "these tables are read by the manuscript pipeline but produced by nothing in "
        f"REPRODUCE_CHAIN: {orphans}. A table with no producer cannot be regenerated, so the "
        "claim that every number is reproducible is false."
    )


@pytest.mark.parametrize(
    "script,expected",
    [
        ("scripts/train_gbdt.py", "t5_01_loco_untuned.csv"),
        ("scripts/train_phase5.py", "t5_02_loco_tuned.csv"),
        ("scripts/build_cams_variants.py", "t4_01_cams_baseline_variants.csv"),
    ],
)
def test_producers_write_the_tracked_filename(script: str, expected: str):
    """No producer may write a name that later needs renaming by hand.

    The rename step is where provenance was lost: train_phase5.py wrote `phase5_tuned.csv`,
    someone renamed it to `t5_02_loco_tuned.csv`, and phase6_analysis.py -- which read the old
    name -- could no longer run on any clone.
    """
    text = (ROOT / script).read_text(encoding="utf-8")
    assert expected in text, f"{script} does not write the tracked name {expected}"
    # Strip comments: the pre-rename name is legitimately discussed in explanatory comments,
    # and only executable references matter.
    code = "\n".join(line.split("#")[0] for line in text.splitlines())
    assert "phase5_tuned.csv" not in code, f"{script} still references the pre-rename filename"


def test_phase6_reads_the_tracked_phase5_output():
    text = (ROOT / "scripts" / "phase6_analysis.py").read_text(encoding="utf-8")
    assert "t5_02_loco_tuned.csv" in text
    assert "phase5_tuned.csv" not in text, (
        "phase6_analysis.py reads the pre-rename filename; this is exactly how the chain broke"
    )
