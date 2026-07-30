"""Bank the co-located feed divergence statistics used in Section 7.

Run:  python scripts/build_merge_divergence.py

Writes:  paper/tables/t2_03_feed_divergence.csv

The embassy monitors are published twice, by StateAir and by AirNow, under distinct
identifiers. Where the two feeds of one physical instrument disagree, the *label* is
provider-dependent and every metric computed on those rows inherits that uncertainty.
Ashgabat's pair is a clean duplicate; Bishkek's is not, and the divergence is concentrated
in the frozen test year. These numbers appear in the limitations section and are therefore
generated rather than transcribed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
TABLES = ROOT / "paper" / "tables"

# city -> (primary feed id, secondary feed id), from data/DECISIONS.md D-006.
PAIRS = {"Bishkek": ("8225", "8827"), "Ashgabat": ("8870", "8170")}
AGREE_TOL = 0.1  # ug/m3; the feeds are published at 0.1 resolution
TEST_YEAR = 2024


def main() -> int:
    panel = pd.read_parquet(INTERIM / "panel.parquet")
    rows = []

    for city, (primary, secondary) in PAIRS.items():
        missing = [c for c in (primary, secondary) if c not in panel.columns]
        if missing:
            print(f"{city}: missing feeds {missing} -- skipped")
            continue

        pair = panel[[primary, secondary]].dropna()
        diff = (pair[primary] - pair[secondary]).abs()
        year = pair.index.year
        in_test = year == TEST_YEAR

        rows.append(
            {
                "city": city,
                "primary": primary,
                "secondary": secondary,
                "overlap_hours": int(len(pair)),
                "agreement_pct": float((diff <= AGREE_TOL).mean() * 100),
                "p95_abs_diff": float(diff.quantile(0.95)),
                "max_abs_diff": float(diff.max()),
                "overlap_hours_test": int(in_test.sum()),
                # The test-block figures are the ones that matter: they bound the label
                # uncertainty carried by every number reported in Section 6.
                "agreement_pct_test": float((diff[in_test] <= AGREE_TOL).mean() * 100),
                "p95_abs_diff_test": float(diff[in_test].quantile(0.95)),
            }
        )

    TABLES.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "t2_03_feed_divergence.csv", index=False)
    print(out.round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
