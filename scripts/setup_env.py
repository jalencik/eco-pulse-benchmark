"""Create the pinned virtual environment on any OS, with or without `uv`.

Run:  python scripts/setup_env.py [--force] [--no-uv]

The original setup step was `uv venv --python 3.12 && uv pip install -e ".[dev]"`, which
assumes `uv` is installed. On a reviewer's machine it may not be, and on the Windows dev
machine it was not: `uv` had created a managed CPython, then disappeared from PATH, leaving
an environment that could be *run* but not *rebuilt*.

Interpreter discovery here executes every candidate rather than trusting a registry. This
is not defensive style for its own sake -- the Windows `py` launcher listed a 3.12 runtime
that failed to launch with 0x80070003 (ERROR_PATH_NOT_FOUND). A discovery routine that
believed `py --list` would have selected a broken interpreter and failed later, during
install, with a confusing error. Probing costs one subprocess per candidate and turns that
into a clean skip.

Exit codes:  0 success, 1 no suitable interpreter found, 2 venv creation or install failed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
TARGET = (3, 12)  # pyproject pins >=3.12,<3.13
PROBE = "import sys;print('%d.%d.%d' % sys.version_info[:3])"


def venv_python(venv: Path = VENV) -> Path:
    """Interpreter path inside a venv. Windows uses Scripts/, POSIX uses bin/."""
    return (
        venv
        / ("Scripts" if os.name == "nt" else "bin")
        / ("python.exe" if os.name == "nt" else "python")
    )


def probe(cmd: list[str]) -> tuple[int, int, int] | None:
    """Execute a candidate and return its version, or None if it cannot run.

    Any failure is a rejection: missing binary, non-zero exit, unparseable output, or a
    launcher that resolves to a path Windows cannot open.
    """
    try:
        out = subprocess.run(
            [*cmd, "-c", PROBE], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        parts = tuple(int(p) for p in out.stdout.strip().split("."))
    except ValueError:
        return None
    return parts if len(parts) == 3 else None  # type: ignore[return-value]


def candidates() -> list[list[str]]:
    """Every plausible route to a 3.12 interpreter, cheapest and most explicit first."""
    out: list[list[str]] = []

    # Explicit minor-version names, which is what a correctly configured machine offers.
    for name in ("python3.12", "python3", "python"):
        found = shutil.which(name)
        if found:
            out.append([found])

    # Windows launcher. Both selector spellings are tried; on this machine both listed a
    # runtime that would not start, which the probe catches.
    if os.name == "nt" and shutil.which("py"):
        out.append(["py", "-3.12"])
        out.append(["py", "-V:3.12"])

    # An existing venv's base interpreter. This is the case that rescued the dev machine:
    # the venv still ran, so its base_prefix pointed at a working CPython that nothing
    # else on the system could find.
    existing = venv_python()
    if existing.exists():
        got = subprocess.run(
            [str(existing), "-c", "import sys;print(sys.base_prefix)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if got.returncode == 0:
            base = Path(got.stdout.strip())
            for exe in (base / "python.exe", base / "bin" / "python3", base / "bin" / "python"):
                if exe.exists():
                    out.append([str(exe)])

    # uv-managed interpreters, reachable even when uv itself is off PATH.
    roots = [
        Path(os.environ.get("APPDATA", "~")).expanduser() / "uv" / "python",
        Path.home() / ".local" / "share" / "uv" / "python",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.glob("cpython-3.12.*")):
            for exe in (d / "python.exe", d / "bin" / "python3", d / "bin" / "python"):
                if exe.exists():
                    out.append([str(exe)])

    # Last resort: whatever is running this script.
    out.append([sys.executable])

    seen, unique = set(), []
    for c in out:
        key = tuple(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def find_interpreter() -> list[str] | None:
    for cmd in candidates():
        version = probe(cmd)
        if version is None:
            print(f"  skip  {' '.join(cmd)}  (will not run)")
            continue
        label = ".".join(str(v) for v in version)
        if version[:2] == TARGET:
            print(f"  USE   {' '.join(cmd)}  ({label})")
            return cmd
        print(f"  skip  {' '.join(cmd)}  ({label}, need 3.12)")
    return None


def run(cmd: list[str], **kw) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT, **kw).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="recreate .venv even if usable")
    ap.add_argument("--no-uv", action="store_true", help="ignore uv even if installed")
    args = ap.parse_args()

    uv = None if args.no_uv else shutil.which("uv")

    # Reuse a healthy environment rather than deleting it. Recreating costs a reviewer
    # several minutes of downloads and can only lose information.
    if VENV.exists() and not args.force:
        current = probe([str(venv_python())])
        if current and current[:2] == TARGET:
            print(f".venv already present at {'.'.join(map(str, current))} -- installing into it")
            return install(uv)
        print(f".venv present but unusable ({current}); use --force to recreate")
        return 2

    if VENV.exists():
        print(f"removing {VENV}")
        shutil.rmtree(VENV)

    # uv can download a 3.12 if none is installed, so it is tried first when available.
    if uv and run([uv, "venv", "--python", "3.12", str(VENV)]) == 0:
        return install(uv)

    print("locating a Python 3.12 interpreter:")
    interp = find_interpreter()
    if interp is None:
        print(
            "\nno Python 3.12 found. Install one, then re-run:\n"
            "  uv:      uv python install 3.12 && python scripts/setup_env.py\n"
            "  Windows: py install 3.12\n"
            "  macOS:   brew install python@3.12\n"
            "  Linux:   apt install python3.12 python3.12-venv",
            file=sys.stderr,
        )
        return 1

    if run([*interp, "-m", "venv", str(VENV)]) != 0:
        print("venv creation failed", file=sys.stderr)
        return 2
    return install(uv)


def install(uv: str | None) -> int:
    py = str(venv_python())
    if uv:
        # VIRTUAL_ENV tells uv which environment to install into.
        env = {**os.environ, "VIRTUAL_ENV": str(VENV)}
        if run([uv, "pip", "install", "-e", ".[dev]"], env=env) == 0:
            return verify(py)
        print("uv install failed; falling back to pip", file=sys.stderr)

    if run([py, "-m", "pip", "install", "--upgrade", "pip"]) != 0:
        return 2
    if run([py, "-m", "pip", "install", "-e", ".[dev]"]) != 0:
        return 2
    return verify(py)


def verify(py: str) -> int:
    """A setup step that reports success without a working import is worse than failing."""
    version = probe([py])
    if not version or version[:2] != TARGET:
        print(f"FAILED: .venv is {version}, expected 3.12.x", file=sys.stderr)
        return 2
    check = subprocess.run(
        [py, "-c", "import ecopulse_ca, pandas, lightgbm, pytest, ruff"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        print(f"FAILED: environment does not import cleanly\n{check.stderr}", file=sys.stderr)
        return 2
    print(f"\nOK  .venv at Python {'.'.join(map(str, version))}, all core imports resolve")
    print(f"    activate: {VENV}/{'Scripts' if os.name == 'nt' else 'bin'}/activate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
