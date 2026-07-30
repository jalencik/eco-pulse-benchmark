"""The Makefile and the Windows shim must not drift.

The Makefile is what a reviewer types and what the paper documents, but `make` is not
installed on the Windows dev machine, so `tasks.py` mirrors it. If the two diverge,
`make reproduce` and `python tasks.py reproduce` stop regenerating the same numbers and the
reproducibility claim quietly becomes false.

An earlier version of this file compared target *names* only. That is exactly why the drift
it existed to prevent went unnoticed: the Makefile's `paper` target gained two producer
scripts that were never added to the shim, and every test still passed. The Makefile now
delegates to the shim, so the commands cannot differ, and these tests assert the delegation
rather than trusting it.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"

# Targets that legitimately do not delegate: help prints, reproduce is a dependency chain
# resolved by make itself, clean is a filesystem operation with no shim equivalent.
NON_DELEGATING = {"help", "reproduce", "clean"}


def makefile_targets() -> set[str]:
    phony = re.search(r"^\.PHONY:\s*(.+)$", MAKEFILE.read_text(encoding="utf-8"), re.M)
    assert phony, "Makefile has no .PHONY line"
    return set(phony.group(1).split())


def makefile_recipes() -> dict[str, list[str]]:
    """target -> recipe lines (tab-indented), comments and blanks removed."""
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("\t"):
            if current:
                recipes.setdefault(current, []).append(line.strip())
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+):", line)
        current = m.group(1) if m else None
    return recipes


def shim_targets() -> set[str]:
    """Target names declared in tasks.py.

    Must handle ast.AnnAssign as well as ast.Assign. `TARGETS: dict[...] = {...}` is an
    *annotated* assignment, and an earlier version of this helper matched only ast.Assign
    — so it returned a single target and the parity comparison was vacuous.
    """
    tree = ast.parse((ROOT / "tasks.py").read_text(encoding="utf-8"))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    targets.add(k.value)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.slice, ast.Constant)
                    and isinstance(tgt.slice.value, str)
                ):
                    targets.add(tgt.slice.value)
    return targets


class TestParity:
    def test_target_sets_match_exactly(self):
        """Both directions. A target in one and not the other is drift either way."""
        assert shim_targets() - NON_DELEGATING == makefile_targets() - NON_DELEGATING

    def test_every_makefile_target_delegates_to_the_shim(self):
        """Delegation is what makes command-level drift impossible."""
        recipes = makefile_recipes()
        for target in makefile_targets() - NON_DELEGATING:
            assert target in recipes, f"{target} declared .PHONY but has no recipe"
            assert recipes[target] == [f"$(PY) tasks.py {target}"], (
                f"{target} does not delegate; it runs {recipes[target]}"
            )

    def test_reproduce_exists_in_both(self):
        assert "reproduce" in makefile_targets()
        assert "reproduce" in shim_targets()

    def test_reproduce_runs_tests_before_producing_numbers(self):
        """Order is load-bearing: splits are frozen and hash-verified before any model runs."""
        line = next(
            ln
            for ln in MAKEFILE.read_text(encoding="utf-8").splitlines()
            if ln.startswith("reproduce:")
        )
        order = line.split(":", 1)[1].split()
        assert order.index("test") < order.index("splits") < order.index("baselines")

    def test_shim_reproduce_chain_matches_makefile(self):
        """The shim's chain and the Makefile's prerequisites must be the same sequence."""
        import tasks

        line = next(
            ln
            for ln in MAKEFILE.read_text(encoding="utf-8").splitlines()
            if ln.startswith("reproduce:")
        )
        assert list(tasks.REPRODUCE_CHAIN) == line.split(":", 1)[1].split()


class TestShimFailsLoudly:
    """`reproduce` once exited 0 on a machine with no ruff, having run nothing."""

    def test_missing_executable_is_a_failure_not_a_skip(self, monkeypatch):
        import tasks

        monkeypatch.setitem(
            tasks.TARGETS, "_probe", [["definitely-not-a-real-binary-xyz", "--version"]]
        )
        assert tasks.run("_probe") == 127

    def test_nonzero_exit_stops_the_chain(self, monkeypatch):
        import tasks

        monkeypatch.setitem(
            tasks.TARGETS,
            "_probe",
            [[sys.executable, "-c", "raise SystemExit(3)"], [sys.executable, "-c", "pass"]],
        )
        assert tasks.run("_probe") == 3

    def test_run_loop_has_no_continue_branch(self):
        """Structural guard: the skip was a bare `continue` in the command loop.

        Checked on the AST rather than the source text, so the docstring explaining the bug
        does not trip the test that guards against it.
        """
        tree = ast.parse((ROOT / "tasks.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run")
        assert not [n for n in ast.walk(fn) if isinstance(n, ast.Continue)], (
            "tasks.run() skips a command instead of failing"
        )

    def test_unknown_target_is_rejected(self):
        import tasks

        assert tasks.run("no-such-target") == 2


class TestPaperTargetRegeneratesTheManuscript:
    def test_paper_renders_and_not_just_builds_tables(self):
        """`paper` stopped at build_all.py, so sections were never re-rendered."""
        import tasks

        scripts = {cmd[-1] for cmd in tasks.TARGETS["paper"]}
        for required in (
            "scripts/build_r7_tables.py",
            "scripts/build_merge_divergence.py",
            "paper/scripts/extract_numbers.py",
            "paper/scripts/render.py",
        ):
            assert required in scripts, f"`paper` does not run {required}"

    def test_extraction_precedes_rendering(self):
        import tasks

        order = [cmd[-1] for cmd in tasks.TARGETS["paper"]]
        assert order.index("paper/scripts/extract_numbers.py") < order.index(
            "paper/scripts/render.py"
        ), "render must consume freshly extracted numbers"


class TestEnvironmentSetupIsPortable:
    def test_setup_does_not_require_uv(self):
        """uv was absent on the dev machine; setup must not hard-depend on it."""
        import tasks

        flat = " ".join(" ".join(c) for c in tasks.TARGETS["setup"])
        assert "uv " not in flat, "setup must not invoke uv directly"
        assert "scripts/setup_env.py" in flat

    def test_setup_runs_under_the_launching_interpreter(self):
        """The venv may not exist yet, so setup cannot be run by the venv python."""
        import tasks

        assert tasks.TARGETS["setup"][0][0] == sys.executable

    def test_setup_script_is_executable_and_self_documenting(self):
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts/setup_env.py"), "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert out.returncode == 0
        assert "--force" in out.stdout


class TestGitHygiene:
    def test_gitignore_never_commits_env_but_does_commit_splits(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert re.search(r"^\.env$", text, re.M), ".env must be gitignored"
        assert "!benchmark/splits/**" in text, "frozen splits are the deliverable and must commit"


@pytest.mark.parametrize("target", ["lint", "typecheck", "test", "splits", "baselines", "paper"])
def test_no_target_invokes_a_bare_tool_name(target):
    """Bare `ruff`/`mypy` depend on PATH. `python -m ruff` depends on the venv, correctly."""
    import tasks

    for cmd in tasks.TARGETS[target]:
        assert Path(cmd[0]).exists() or cmd[0] == sys.executable, (
            f"{target} invokes {cmd[0]!r} by bare name; use `python -m` instead"
        )
