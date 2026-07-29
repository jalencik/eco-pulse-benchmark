"""Credential readiness report — run this the moment a key lands in .env.

    python scripts/check_credentials.py

Reports which feature sets are unlocked, which remain blocked, and what each missing key
would buy. Never prints a key value.

Written before the keys arrive so that "did it take?" is a five-second check rather than a
failed pipeline run twenty minutes in.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from ecopulse_ca.features.catalogue import ALL_FEATURES, FEATURE_SETS  # noqa: E402
from ecopulse_ca.features.spec import unverified  # noqa: E402

OPTIONAL_PACKAGE = {
    "EE_PROJECT_ID": ("ee", "uv pip install earthengine-api"),
    "ADS_API_KEY": ("cdsapi", "uv pip install cdsapi"),
    "CDS_API_KEY": ("cdsapi", "uv pip install cdsapi"),
}


def _present(var: str) -> bool:
    return bool((os.getenv(var) or "").strip())


def _package_ready(var: str) -> tuple[bool, str]:
    entry = OPTIONAL_PACKAGE.get(var)
    if entry is None:
        return True, ""
    module, install = entry
    try:
        __import__(module)
    except ImportError:
        return False, install
    return True, ""


def main() -> int:
    print("credential status (values are never printed)\n")

    needed = sorted({f.credential for f in ALL_FEATURES if f.credential})
    for var in needed:
        has_key = _present(var)
        pkg_ok, install_hint = _package_ready(var)
        unlocks = sorted({f.name for f in ALL_FEATURES if f.credential == var})
        mark = "OK " if has_key else "-- "
        print(f"  {mark} {var:22s} {'set' if has_key else 'MISSING':8s} "
              f"unlocks {len(unlocks)} features")
        if has_key and not pkg_ok:
            print(f"       key present but package missing:  {install_hint}")
        if not has_key:
            print(f"       would unlock: {', '.join(unlocks[:4])}"
                  f"{' ...' if len(unlocks) > 4 else ''}")

    print("\nfeature sets:")
    for fset in FEATURE_SETS:
        missing = [c for c in fset.credentials_required() if not _present(c)]
        state = "READY" if not missing else f"blocked on {', '.join(missing)}"
        local = "local" if fset.locally_reproducible else "SERVER-SIDE ONLY"
        print(f"  {fset.name:24s} n={len(fset.features):2d}  {local:16s}  {state}")

    pending = unverified(ALL_FEATURES)
    print(f"\nunverified latency claims: {len(pending)}/{len(ALL_FEATURES)}")
    if pending:
        print("  " + ", ".join(f.name for f in pending))
        print("  Latency from memory and latency from documentation look identical in a")
        print("  table. The MAIAC claim was checked and proved wrong by ~32x; the rest")
        print("  are not assumed correct.")

    ready = [s.name for s in FEATURE_SETS
             if not [c for c in s.credentials_required() if not _present(c)]]
    print(f"\n{len(ready)}/{len(FEATURE_SETS)} feature sets ready: {ready or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
