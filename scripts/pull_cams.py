"""Extract CAMS global forecast PM2.5 (leadtime 24h) for the benchmark stations.

CAMS first, ERA5 second: CAMS is both the deployable met feature AND the mandated
"beat raw CAMS" baseline, so it is the load-bearing half. ERA5 can only ever produce a
labelled oracle ablation.
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
    ADS_URL,
    CAMS_MAX_MONTHS_PER_REQUEST,
    DEPLOYABLE_LEADTIME_H,
    KG_M3_TO_UG_M3,
    assign_cells,
    extract_points,
    month_blocks,
    station_bbox,
    unzip_members,
)

SCRATCH = pathlib.Path(
    r"C:\Users\user\AppData\Local\Temp\claude\C--Users-user-Desktop-Claude-skills"
    r"\c2d216a0-79d2-4781-b726-c5bb2c79dc9f\scratchpad\cams"
)
SCRATCH.mkdir(parents=True, exist_ok=True)

splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
st = [(s["station_id"], s["city"], s["latitude"], s["longitude"]) for s in splits["stations"]]
area = station_bbox([s[2] for s in st], [s[3] for s in st])
blocks = month_blocks("2018-11-01", "2024-12-31", CAMS_MAX_MONTHS_PER_REQUEST)
print(
    f"CAMS PM2.5 | leadtime {DEPLOYABLE_LEADTIME_H}h | {len(blocks)} requests | area {area}",
    flush=True,
)

import cdsapi

c = cdsapi.Client(
    url=ADS_URL, key=(os.getenv("ADS_API_KEY") or "").strip(), quiet=True, progress=False
)
frames, failed, cells = [], [], None
t0 = time.time()
for n, block in enumerate(blocks, 1):
    lo = f"{block[0][0]}-{block[0][1]:02d}-01"
    last = pd.Timestamp(f"{block[-1][0]}-{block[-1][1]:02d}-01") + pd.offsets.MonthEnd(0)
    hi = min(last, pd.Timestamp("2024-12-31")).strftime("%Y-%m-%d")
    tgt = SCRATCH / f"cams_{lo}_{hi}.nc"
    req = {
        "variable": ["particulate_matter_2.5um"],
        "date": [f"{lo}/{hi}"],
        "time": ["00:00"],
        "leadtime_hour": [str(DEPLOYABLE_LEADTIME_H)],
        "type": ["forecast"],
        "area": area,
        "data_format": "netcdf",
    }
    try:
        c.retrieve("cams-global-atmospheric-composition-forecasts", req, str(tgt))
        members = unzip_members(tgt, SCRATCH / "x")
        for m in members:
            ds = xr.open_dataset(m)
            tdim = "forecast_reference_time" if "forecast_reference_time" in ds.sizes else "time"
            if cells is None:
                cells = assign_cells(ds.latitude.values, ds.longitude.values, st)
            sq = ds.squeeze(drop=True)
            frames.append(
                extract_points(
                    sq,
                    {"pm2p5": "cams_pm25_forecast"},
                    cells,
                    tdim,
                    scale={"cams_pm25_forecast": KG_M3_TO_UG_M3},
                )
            )
            ds.close()
    except Exception as e:
        failed.append({"block": f"{lo}..{hi}", "error": str(e)[:200]})
        print(f"  [{n}/{len(blocks)}] FAILED {lo}..{hi}: {str(e)[:90]}", flush=True)
    finally:
        tgt.unlink(missing_ok=True)  # delete immediately: 8.2 GB budget
        shutil.rmtree(SCRATCH / "x", ignore_errors=True)
    if n % 5 == 0 or n == len(blocks):
        print(
            f"  [{n}/{len(blocks)}] rows {sum(len(f) for f in frames):,} "
            f"{(time.time() - t0) / 60:.1f}m",
            flush=True,
        )

df = pd.concat(frames, ignore_index=True).sort_values(["station_id", "time"]).reset_index(drop=True)
df.to_parquet(ROOT / "data/interim/cams_pm25_forecast.parquet")
prov = {
    "dataset": "cams-global-atmospheric-composition-forecasts",
    "leadtime_hour": DEPLOYABLE_LEADTIME_H,
    "leadtime_rationale": "step 0 is effectively analysis and would be lookahead; 24h "
    "is the forecast a live service holds, consistent with the "
    "12h ADS latency",
    "units": "ug/m^3 (converted from kg/m^3 by x1e9)",
    "area_NWSE": area,
    "requests": len(blocks),
    "failed": failed,
    "rows": int(len(df)),
    "null_share": round(float(df.cams_pm25_forecast.isna().mean()), 4),
    "cell_collisions": {
        c.station_id: list(c.shares_cell_with) for c in (cells or []) if c.shares_cell_with
    },
}
(ROOT / "data/interim/cams_pm25_forecast_provenance.json").write_text(json.dumps(prov, indent=2))
print(
    f"\nrows {len(df):,}  failed {len(failed)}  "
    f"null {100 * df.cams_pm25_forecast.isna().mean():.2f}%"
)
