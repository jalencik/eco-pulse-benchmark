"""No-dependency shim so `make` targets run on Windows, where make is absent.

Usage:  python tasks.py <target>
        python tasks.py help

The Makefile stays canonical — it is what a reviewer types, and it is the interface the
paper documents. This file exists only so the same targets work on the dev machine. The
two must not drift: `tests/test_makefile_shim_parity.py` asserts that every target defined
here also exists in the Makefile.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PY = sys.executable
PKG = "src/ecopulse_ca"

TARGETS: dict[str, list[list[str]]] = {
    "setup": [["uv", "venv", "--python", "3.12"], ["uv", "pip", "install", "-e", ".[dev]"]],
    "lint": [["ruff", "check", "."], ["ruff", "format", "--check", "."]],
    "typecheck": [["mypy", PKG]],
    "test": [[PY, "-m", "pytest"]],
    "test-fast": [[PY, "-m", "pytest", "-m", "not network and not slow"]],
    "splits": [[PY, "-m", "ecopulse_ca.splits.builder", "--freeze"]],
    "baselines": [
        [PY, "-m", "ecopulse_ca.tasks.forecasting", "--all-seeds"],
        [PY, "-m", "ecopulse_ca.tasks.nowcasting", "--all-seeds"],
    ],
    "paper": [[PY, "paper/scripts/build_all.py"]],
}

# Mirrors the Makefile's `reproduce` dependency chain. Splits are frozen and hash-verified
# before any model touches data — the order is load-bearing, not cosmetic.
TARGETS["reproduce"] = [
    cmd for t in ("lint", "typecheck", "test", "splits", "baselines", "paper") for cmd in TARGETS[t]
]


def run(target: str) -> int:
    if target in ("help", "-h", "--help"):
        print(__doc__)
        print("targets: " + ", ".join(sorted(TARGETS)))
        return 0
    if target not in TARGETS:
        print(f"unknown target {target!r}; try: python tasks.py help", file=sys.stderr)
        return 2

    for cmd in TARGETS[target]:
        if shutil.which(cmd[0]) is None and cmd[0] != PY:
            print(f"SKIP (not installed): {' '.join(cmd)}", file=sys.stderr)
            continue
        print(f"$ {' '.join(cmd)}", flush=True)
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1] if len(sys.argv) > 1 else "help"))
