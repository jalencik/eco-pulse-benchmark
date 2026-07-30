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
    "baselines": [
        [PY, "-m", "ecopulse_ca.tasks.forecasting", "--all-seeds"],
        [PY, "-m", "ecopulse_ca.tasks.nowcasting", "--all-seeds"],
    ],
    "paper": [
        [PY, "scripts/build_r7_tables.py"],
        [PY, "scripts/build_merge_divergence.py"],
        [PY, "paper/scripts/build_all.py"],
        [PY, "paper/scripts/extract_numbers.py"],
        [PY, "paper/scripts/render.py"],
    ],
}

# Mirrors the Makefile's `reproduce` dependency chain. Splits are frozen and hash-verified
# before any model touches data — the order is load-bearing, not cosmetic.
REPRODUCE_CHAIN = ("lint", "typecheck", "test", "splits", "baselines", "paper")
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
