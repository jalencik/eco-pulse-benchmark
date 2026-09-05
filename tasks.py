"""No-dependency shim so the Makefile targets run on Windows, where make is absent.

Usage:  python tasks.py <target>
        python tasks.py help

This file is the single definition of what each target runs; the Makefile delegates to it
rather than repeating the commands. The two had already drifted once — the Makefile's
`paper` target gained producer scripts that were never added here, and the parity test
missed it because it compared target *names* only, not the commands behind them.

Three behaviours are deliberate and load-bearing:

1. **A missing tool is a failure, not a skip.** An earlier version printed
   `SKIP (not installed)` and continued, so `reproduce` exited 0 on a machine without ruff
   or mypy — reporting that every number had been regenerated when nothing had run. A
   reproducibility harness that passes without doing the work is worse than no harness.

2. **Targets run under the project venv, not the launching interpreter.** The dev machine's
   `python` is a 3.14 Store shim while the project pins 3.12; `python tasks.py test` with
   that shim would test an interpreter the project does not support.

3. **`paper` regenerates the manuscript, not only the tables.** It previously stopped at
   `build_all.py`, so the rendered sections were never rebuilt from the CSVs that
   `reproduce` had just regenerated.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PKG = "src/ecopulse_ca"


def _project_python() -> str:
    """The venv interpreter if present, else whatever is running us."""
    exe = (
        ROOT
        / ".venv"
        / ("Scripts" if os.name == "nt" else "bin")
        / ("python.exe" if os.name == "nt" else "python")
    )
    return str(exe) if exe.exists() else sys.executable


PY = _project_python()

# Dev tools are invoked as `python -m <tool>` rather than by bare name: they are declared
# dependencies installed inside the venv, so this resolves them without needing a PATH
# entry, and makes "tool missing" mean "the environment is broken" — which is the truth.
TARGETS: dict[str, list[list[str]]] = {
    # setup runs under the *launching* interpreter: the venv may not exist yet.
    "setup": [[sys.executable, "scripts/setup_env.py"]],
    "lint": [[PY, "-m", "ruff", "check", "."], [PY, "-m", "ruff", "format", "--check", "."]],
    "typecheck": [[PY, "-m", "mypy", PKG]],
    "test": [[PY, "-m", "pytest"]],
    "test-fast": [[PY, "-m", "pytest", "-m", "not network and not slow"]],
    "splits": [[PY, "-m", "ecopulse_ca.splits.builder", "--freeze"]],
    # One script runs Task F and Task N across all five seeds. The target previously named
    # `ecopulse_ca.tasks.forecasting` and `.nowcasting`, which have never existed — the
    # package holds only __init__.py. `reproduce` therefore could not have run to
    # completion, and the error surfaced the first time it was executed end to end.
    "baselines": [[PY, "scripts/run_baselines.py"]],
    # The model layer was ABSENT from `reproduce` until 2026-08-13. Its four producers wrote
    # phase5_*/phase6_* filenames that were renamed by hand to t4_*/t5_*/t6_* in 99b9a13, so
    # `reproduce` regenerated only the t3_* family and still exited 0 -- mtimes showed t4/t5/t6
    # frozen at Jul 30 while the command ran on Aug 3 and Aug 13. Every producer now writes the
    # tracked filename directly, and the chain runs them. Order is a real dependency:
    # phase6_analysis.py reads t5_02, so train_phase5.py must precede it.
    "models": [
        [PY, "scripts/train_gbdt.py"],
        [PY, "scripts/train_phase5.py"],
        # Re-scores the Task N model on the test block with and without the retrieval-count
        # features, at the hyperparameters train_phase5 froze in t5_02. The manuscript quoted
        # this outcome from a run whose outputs were never deposited; now it is a table.
        [PY, "scripts/build_missingness_test.py"],
        [PY, "scripts/build_cams_variants.py"],
        [PY, "scripts/phase6_analysis.py"],
        # Both read t6_01, so they must follow phase6_analysis.py.
        # build_daily_baselines re-scores the Task N ladder at DAILY resolution on the models'
        # own evaluation rows; the hourly table is not comparable to daily model scores.
        # build_significance computes the primary (city-level) and sensitivity inference.
        [PY, "scripts/build_daily_baselines.py"],
        [PY, "scripts/build_significance.py"],
        # Khujand is the only two-station city, so it carries 26.7% of every row-level
        # statistic while being the one city the manuscript calls incomparable in kind.
        # This recomputes the primary inference without it, so the pooled claims are
        # measured against that objection rather than left exposed to it.
        [PY, "scripts/build_khujand_sensitivity.py"],
        # Reporting analyses on the FROZEN predictions -- error decomposition by fold,
        # concentration regime and season, the feature audit, and whether the ladder ranking
        # survives removing one city. None of these change the configuration.
        [PY, "scripts/build_error_analysis.py"],
        [PY, "scripts/build_feature_audit.py"],
        [PY, "scripts/build_robustness.py"],
    ],
    "paper": [
        [PY, "scripts/build_r7_tables.py"],
        [PY, "scripts/build_merge_divergence.py"],
        # Reads the committed research/sources.json; deterministic and offline. The
        # resolver that *populates* that file (scripts/fetch_literature.py) is network
        # bound and deliberately stays out of `reproduce`, which must run without a
        # network and give the same answer every time.
        [PY, "scripts/build_literature_table.py"],
        [PY, "paper/scripts/build_all.py"],
        # Figures are drawn from the same banked CSVs as the prose, so they regenerate with
        # the tables. A chart pasted in once drifts from its source exactly as a hand-typed
        # number does. (The PDF build is deliberately NOT here: it is a submission
        # deliverable, not part of reproducing the numbers.)
        [PY, "scripts/build_figures.py"],
        [PY, "scripts/build_sdata_figures.py"],
        [PY, "paper/scripts/extract_numbers.py"],
        [PY, "paper/scripts/render.py"],
        [PY, "paper/scripts/stitch.py"],
        # Guards an Elsevier submission constraint (5 bullets, <=85 chars each). The
        # editorial system rejects a non-conforming file rather than truncating it, and
        # a one-word edit breaks the limit silently.
        [PY, "scripts/check_highlights.py"],
        # The Scientific Data Data Descriptor is built from the SAME numbers.json as the
        # research-article manuscript, so the two documents cannot disagree about a figure.
        # build_sdata.py exits non-zero if a required section is missing or a placeholder
        # survives; check_sdata_limits.py guards the 170/700/110 submission limits.
        [PY, "scripts/build_sdata.py"],
        [PY, "scripts/check_sdata_limits.py"],
    ],
    # Scientific Data wants a single PDF of the main article in the first review round. It is
    # a submission deliverable rather than a number, which is why it sits outside `reproduce`
    # -- but it stays a script so the submitted artefact is never the one file in the project
    # that nothing can rebuild. Run after `paper`.
    "pdf": [[PY, "paper/scripts/build_pdf.py"]],
}

# Mirrors the Makefile's `reproduce` dependency chain. Splits are frozen and hash-verified
# before any model touches data — the order is load-bearing, not cosmetic.
REPRODUCE_CHAIN = ("lint", "typecheck", "test", "splits", "baselines", "models", "paper")
TARGETS["reproduce"] = [cmd for t in REPRODUCE_CHAIN for cmd in TARGETS[t]]


def _base_is_invisible(home: str) -> bool:
    """True when this process cannot see the venv's base interpreter.

    Detected by looking, not by matching path names. Windows Store Python runs in an
    AppContainer whose view of %APPDATA%\\Roaming is virtualised, so a uv-managed
    interpreter there is unreachable -- CreateProcess returns ERROR_FILE_NOT_FOUND for a
    file that plainly exists and runs when invoked from any other parent.

    A name-based check is not reliable: `sys.executable` under the Store alias reports the
    alias *target* (AppData\\Local\\Python\\pythoncore-*), not the WindowsApps path, so the
    obvious heuristic silently misses the case it exists for.
    """
    base = Path(home)
    return not any((base / n).exists() for n in ("python.exe", "bin/python3", "bin/python"))


def _venv_home() -> str | None:
    """The base interpreter a venv delegates to, from pyvenv.cfg."""
    cfg = ROOT / ".venv" / "pyvenv.cfg"
    if not cfg.exists():
        return None
    for line in cfg.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "home":
            return value.strip()
    return None


def diagnose() -> str | None:
    """Return an actionable message if the environment cannot run, else None.

    Probing once here converts a cryptic failure repeated per command into a single
    explanation. On this machine the raw symptom was exit 103 and
    `No Python at '"C:\\...\\python.exe'` -- for a path that exists and runs fine when
    invoked directly.
    """
    if not Path(PY).exists():
        return f"no environment at {ROOT / '.venv'}\nrun: python tasks.py setup"

    probe = subprocess.run(
        [PY, "-c", "import sys;print(sys.version_info[:2])"], capture_output=True, text=True
    )
    if probe.returncode == 0:
        return None

    lines = [
        f"the project environment at {ROOT / '.venv'} will not start.",
        f"  launcher: {sys.executable}",
        f"  venv:     {PY}",
    ]
    home = _venv_home()
    if home:
        lines.append(f"  base:     {home}")
    if probe.stderr.strip():
        lines.append(f"  error:    {probe.stderr.strip().splitlines()[0]}")

    if home and _base_is_invisible(home):
        lines += [
            "",
            "Cause: the launching interpreter cannot see the venv's base interpreter, which",
            "exists and runs fine from any other parent. This is Windows Store Python: it",
            "runs in a sandbox whose view of %APPDATA%\\Roaming is virtualised, so a",
            "uv-managed interpreter there is unreachable. The venv is not corrupt -- the",
            "launcher cannot reach through to it.",
            "",
            "Fix, any one of:",
            "  1. run through the venv directly:",
            "       .venv\\Scripts\\python.exe tasks.py <target>",
            "  2. install a non-Store Python 3.12 (python.org or `py install 3.12`),",
            "     then: python scripts/setup_env.py --force",
            "  3. disable the Store aliases: Settings > Apps > Advanced app settings >",
            "     App execution aliases > turn off python.exe / python3.exe",
        ]
    else:
        lines += ["", "Try rebuilding it:  python scripts/setup_env.py --force"]
    return "\n".join(lines)


def run(target: str) -> int:
    if target in ("help", "-h", "--help"):
        print(__doc__)
        print("targets: " + ", ".join(sorted(TARGETS)))
        return 0
    if target not in TARGETS:
        print(f"unknown target {target!r}; try: python tasks.py help", file=sys.stderr)
        return 2

    if target != "setup":
        problem = diagnose()
        if problem:
            print(problem, file=sys.stderr)
            return 2

    for cmd in TARGETS[target]:
        print(f"$ {' '.join(cmd)}", flush=True)
        try:
            result = subprocess.run(cmd, cwd=ROOT)
        except FileNotFoundError:
            print(
                f"\nFAILED: {cmd[0]} not found — the environment is incomplete.\n"
                f"run: python tasks.py setup",
                file=sys.stderr,
            )
            return 127
        if result.returncode != 0:
            print(f"\nFAILED ({result.returncode}): {' '.join(cmd)}", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1] if len(sys.argv) > 1 else "help"))
