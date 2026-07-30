"""Pull daily MAIAC AOD for the 8 benchmark stations, 2018-11-27 .. 2024-12-31.

    python scripts/pull_maiac.py

Writes data/interim/maiac_aod.parquet plus a provenance JSON.

Every station-day is retained, including days with no retrieval (aod null,
valid_pixels 0). Risk R7: MAIAC fails during dust, snow and heavy cloud -- the extreme
episodes -- so dropping those rows would condition the benchmark on "retrieval succeeded".
Chunk completeness is asserted, not assumed: a short chunk means silent data loss.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import os  # noqa: E402

from ecopulse_ca.ingest.earthengine import StationPoint  # noqa: E402
from ecopulse_ca.ingest.maiac import (  # noqa: E402
    BUFFER_M,
    COLLECTION,
    SCALE_M,
    _retry,
    extract_maiac_chunk,
    month_chunks,
)

INTERIM = ROOT / "data" / "interim"
START, END = "2018-11-27", "2024-12-31"


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    import ee

    project = (os.getenv("EE_PROJECT_ID") or "").strip()
    if not project:
        print("EE_PROJECT_ID not set")
        return 1
    _retry(lambda: ee.Initialize(project=project))

    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text(encoding="utf-8"))
    stations = [
        StationPoint(s["station_id"], s["latitude"], s["longitude"], s["city"])
        for s in splits["stations"]
    ]
    chunks = month_chunks(START, END)
    print(f"MAIAC AOD | {len(stations)} stations | {START}..{END} | {len(chunks)} chunks")
    print(f"collection {COLLECTION}, buffer {BUFFER_M} m, scale {SCALE_M} m\n", flush=True)

    frames, incomplete, failed = [], [], []
    t0 = time.time()
    for i, (lo, hi) in enumerate(chunks, 1):
        try:
            res = extract_maiac_chunk(ee, stations, lo, hi)
        except Exception as exc:  # noqa: BLE001 - record and continue; never silently skip
            failed.append({"chunk": f"{lo}..{hi}", "error": str(exc)[:200]})
            print(f"  [{i:2d}/{len(chunks)}] {lo[:7]}  FAILED: {type(exc).__name__}", flush=True)
            continue
        if not res.complete:
            incomplete.append(
                {"chunk": f"{lo}..{hi}", "expected": res.n_expected, "returned": res.n_returned}
            )
        frames.append(res.frame)
        if i % 12 == 0 or i == len(chunks):
            done = sum(len(f) for f in frames)
            print(
                f"  [{i:2d}/{len(chunks)}] {lo[:7]}  rows so far {done:,}  "
                f"elapsed {(time.time() - t0) / 60:.1f} min",
                flush=True,
            )

    if not frames:
        print("nothing retrieved")
        return 1

    df = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["station_id", "date"])
        .reset_index(drop=True)
    )
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM / "maiac_aod.parquet")

    city_of = {s["station_id"]: s["city"] for s in splits["stations"]}
    expected_days = (pd.Timestamp(END) - pd.Timestamp(START)).days + 1
    provenance = {
        "collection": COLLECTION,
        "band": "Optical_Depth_055",
        "scale_factor": 0.001,
        "buffer_m": BUFFER_M,
        "reduce_scale_m": SCALE_M,
        "period": f"{START}..{END}",
        "n_stations": len(stations),
        "expected_station_days": len(stations) * expected_days,
        "returned_rows": int(len(df)),
        "null_aod_rows": int(df["aod_055"].isna().sum()),
        "chunks": len(chunks),
        "chunks_failed": failed,
        "chunks_incomplete": incomplete,
        "note": "Daily composite of ~100 granules/day computed server-side BEFORE "
        "reduction; reducing per-granule would weight days by overpass count. "
        "Null rows retained deliberately (risk R7).",
    }
    (INTERIM / "maiac_aod_provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )

    print(f"\nrows {len(df):,} / expected {len(stations) * expected_days:,}")
    print(f"null AOD {df['aod_055'].isna().sum():,} ({100 * df['aod_055'].isna().mean():.1f}%)")
    if failed:
        print(f"FAILED chunks: {len(failed)} -- see provenance JSON")
    if incomplete:
        print(f"INCOMPLETE chunks: {len(incomplete)} -- see provenance JSON")

    df["city"] = df["station_id"].map(city_of)
    print("\nretrieval rate by city:")
    by_city = df.groupby("city").agg(
        station_days=("aod_055", "size"),
        retrieved=("aod_055", lambda s: int(s.notna().sum())),
    )
    by_city["pct"] = (100 * by_city.retrieved / by_city.station_days).round(1)
    print(by_city.to_string())

    print("\nretrieval rate by month (informative missingness -- expect a winter minimum):")
    m = (
        df.assign(month=df["date"].dt.month)
        .groupby("month")
        .agg(pct_retrieved=("aod_055", lambda s: round(100 * s.notna().mean(), 1)))
    )
    print(m.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
