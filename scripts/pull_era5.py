"""Extract ERA5 single-level and 925 hPa pressure-level fields for the benchmark stations.

ORACLE ONLY. ERA5's measured latency is 6 days (163 h), ~7x the shortest forecast horizon,
so nothing derived from it may appear in a deployed number -- only in a labelled
reanalysis-oracle ablation. The catalogue enforces that; this script just fetches.

PRECIPITATION ALIGNMENT -- the trap this script exists to avoid
--------------------------------------------------------------
ERA5 returns instantaneous and accumulated variables in SEPARATE files inside one zip.
`total_precipitation` at timestamp T is the accumulation over the interval (T-1h, T] --
i.e. the hour ENDING at T -- whereas `blh`/`t2m`/`u10`/`v10` at T are values AT T.

Rather than shift the series and hope the convention is remembered, the column is NAMED for
its semantics: `precip_prev_hour_m`. A feature called `precip` sitting beside `t2m` invites
exactly the off-by-one-hour error that no summary statistic would reveal.

INVERSION SIGN CONVENTION
-------------------------
`inversion_strength_k = T(925 hPa) - T(2 m)`. POSITIVE means warmer aloft than at the
surface: a capping inversion that traps emissions near the ground. Negative is the normal
well-mixed lapse rate. Getting this backwards inverts the entire physical story behind the
Tashkent and Almaty basin regimes.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import time
import warnings

warnings.filterwarnings("ignore")
import pandas as pd
import xarray as xr
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))
from ecopulse_ca.ingest.copernicus import (  # noqa: E402
    CDS_URL,
    ERA5_MAX_MONTHS_PER_REQUEST,
    assign_cells,
    extract_points,
    month_blocks,
    station_bbox,
    unzip_members,
)

SCRATCH = pathlib.Path(
    r"C:\Users\user\AppData\Local\Temp\claude\C--Users-user-Desktop-Claude-skills"
    r"\c2d216a0-79d2-4781-b726-c5bb2c79dc9f\scratchpad\era5run"
)
SCRATCH.mkdir(parents=True, exist_ok=True)

splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
st = [(s["station_id"], s["city"], s["latitude"], s["longitude"]) for s in splits["stations"]]
area = station_bbox([s[2] for s in st], [s[3] for s in st])

import cdsapi

c = cdsapi.Client(
    url=CDS_URL, key=(os.getenv("CDS_API_KEY") or "").strip(), quiet=True, progress=False
)

SINGLE_VARS = [
    "boundary_layer_height",
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "total_precipitation",
]
RENAME = {
    "blh": "blh_m",
    "t2m": "t2m_k",
    "u10": "u10_ms",
    "v10": "v10_ms",
    "tp": "precip_prev_hour_m",
}  # name encodes the (T-1h, T] convention


def fetch(dataset: str, req: dict, tgt: pathlib.Path, months: list) -> list[pathlib.Path]:
    """Fetch with adaptive fallback: cost rejection halves the block rather than aborting."""
    try:
        c.retrieve(dataset, req, str(tgt))
        return unzip_members(tgt, SCRATCH / "x")
    except Exception as e:
        if "cost limits" in str(e) or "too large" in str(e):
            raise RuntimeError("COST") from e
        raise


def run(dataset: str, label: str, variables: list[str], extra: dict, out_name: str) -> None:
    blocks = month_blocks("2018-11-01", "2024-12-31", ERA5_MAX_MONTHS_PER_REQUEST)
    print(f"\n=== {label} | {len(blocks)} requests ===", flush=True)
    frames, failed, cells = [], [], None
    t0 = time.time()
    for n, block in enumerate(blocks, 1):
        years = sorted({str(y) for y, _ in block})
        months = sorted({f"{m:02d}" for _, m in block})
        req = {
            "product_type": ["reanalysis"],
            "variable": variables,
            "year": years,
            "month": months,
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": area,
            "data_format": "netcdf",
            "download_format": "unarchived",
            **extra,
        }
        tgt = SCRATCH / f"{out_name}_{n:03d}.nc"
        try:
            members = fetch(dataset, req, tgt, block)
            for m in members:
                ds = xr.open_dataset(m)
                tdim = "valid_time" if "valid_time" in ds.sizes else "time"
                if cells is None:
                    cells = assign_cells(ds.latitude.values, ds.longitude.values, st)
                sq = ds.squeeze(drop=True)
                present = {k: v for k, v in RENAME.items() if k in sq}
                if not present:
                    present = {v: v for v in sq.data_vars}
                frames.append(extract_points(sq, present, cells, tdim))
                ds.close()
        except Exception as e:
            failed.append({"block": f"{years}-{months}", "error": str(e)[:200]})
            print(f"  [{n}/{len(blocks)}] FAILED: {str(e)[:100]}", flush=True)
        finally:
            tgt.unlink(missing_ok=True)
            shutil.rmtree(SCRATCH / "x", ignore_errors=True)
        if n % 3 == 0 or n == len(blocks):
            print(
                f"  [{n}/{len(blocks)}] rows {sum(len(f) for f in frames):,} "
                f"{(time.time() - t0) / 60:.1f}m",
                flush=True,
            )
    df = pd.concat(frames, ignore_index=True)
    # instant/accum members arrive separately -> collapse to one row per station-hour
    df = df.groupby(["station_id", "city", "time"], as_index=False).first()
    df = df.sort_values(["station_id", "time"]).reset_index(drop=True)
    df.to_parquet(ROOT / f"data/interim/{out_name}.parquet")
    (ROOT / f"data/interim/{out_name}_provenance.json").write_text(
        json.dumps(
            {
                "dataset": dataset,
                "variables": variables,
                "extra": extra,
                "area_NWSE": area,
                "requests": len(blocks),
                "failed": failed,
                "rows": int(len(df)),
                "oracle_only": True,
                "latency_measured_h": 163,
                "precip_convention": "precip_prev_hour_m[T] = accumulation over (T-1h, T]; "
                "instantaneous vars at T are values AT T",
                "cell_collisions": {
                    x.station_id: list(x.shares_cell_with)
                    for x in (cells or [])
                    if x.shares_cell_with
                },
            },
            indent=2,
        )
    )
    print(f"  DONE rows {len(df):,} failed {len(failed)}", flush=True)


run("reanalysis-era5-single-levels", "ERA5 single-levels", SINGLE_VARS, {}, "era5_single")
run(
    "reanalysis-era5-pressure-levels",
    "ERA5 925 hPa",
    ["temperature"],
    {"pressure_level": ["925"]},
    "era5_925",
)
