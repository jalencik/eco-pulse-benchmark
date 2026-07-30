"""Phase 1c: pull hourly PM2.5 for every census-eligible station, then run QC.

Run:  python scripts/pull_panel.py

Writes:
  data/interim/panel.parquet          -- wide hourly panel, one column per station
  data/interim/panel_provenance.csv   -- what was actually retrieved, per station
  data/interim/qc_findings.csv        -- every QC finding with its n-effect
  data/interim/qc_decisions_block.md  -- paste-ready DECISIONS.md entry
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

from ecopulse_ca.config import SETTINGS
from ecopulse_ca.ingest.measurements import build_panel
from ecopulse_ca.ingest.openaq import OpenAQClient
from ecopulse_ca.qc.pipeline import decisions_block, run_qc

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"


def read_census(path: Path) -> pd.DataFrame:
    # keep_default_na=False: pandas would otherwise parse the literal string "N/A" -- which
    # OpenAQ really returns -- back into NaN, hiding exactly the fault D-004 documents.
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])
    for col in ("datetime_first", "datetime_last"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    df["q7_span_ok_upper_bound"] = (
        df["q7_span_ok_upper_bound"].astype(str).str.lower().isin({"true", "1"})
    )
    df["is_monitor"] = df["is_monitor"].astype(str).str.lower().isin({"true", "1"})
    for col in ("latitude", "longitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    if SETTINGS.use_fixtures:
        print("REFUSING: fixtures mode. Phase 1c needs live data -- set OPENAQ_API_KEY.")
        return 1

    census = read_census(INTERIM / "station_census.csv")
    eligible = census[census["q7_span_ok_upper_bound"]].copy()
    print(f"eligible feeds: {len(eligible)}  cities: {eligible['city'].nunique()}")

    with OpenAQClient(SETTINGS) as client:
        panel, provenance = build_panel(eligible, client)

    print(f"\nretrieved {len(panel)} station series")
    if not panel:
        print("nothing retrieved")
        return 1

    INTERIM.mkdir(parents=True, exist_ok=True)
    wide = pd.DataFrame(panel).sort_index()
    wide.to_parquet(INTERIM / "panel.parquet")
    provenance.to_csv(INTERIM / "panel_provenance.csv", index=False)
    print(provenance.to_string(index=False))

    # -- QC on the real series --------------------------------------------------------
    tz = dict(zip(eligible["location_id"].astype(str), eligible["timezone"], strict=False))
    outcome = run_qc(panel, census=eligible, timezones=tz)

    outcome.report.to_frame().to_csv(INTERIM / "qc_findings.csv", index=False)
    (INTERIM / "qc_decisions_block.md").write_text(
        decisions_block(outcome, "D-005 — QC applied to the live hourly panel"),
        encoding="utf-8",
    )

    print("\n=== QC ===")
    print(outcome.summary())
    if outcome.rejected:
        print("\nrejected:")
        for sid, why in sorted(outcome.rejected.items()):
            city = provenance.loc[provenance.location_id == sid, "city"]
            label = city.iloc[0] if len(city) else "?"
            print(f"  {sid} ({label}): {why}")

    survivors = eligible[eligible["location_id"].astype(str).isin(outcome.kept)]
    print(f"\nSURVIVING: {len(outcome.kept)} stations across {survivors['city'].nunique()} cities")
    print("cities: " + ", ".join(sorted(survivors["city"].dropna().unique())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
