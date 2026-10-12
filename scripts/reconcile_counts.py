"""Reconcile every observation count and missing-data percentage quoted in this repository.

Run:  python scripts/reconcile_counts.py            # print the chain
      python scripts/reconcile_counts.py --check    # exit 1 if a documented figure drifts

The repository quotes several different "n"s for what looks like one dataset: 450,817,
341,321, 340,439 and 247,075 hourly figures, and 34.5%, 34.8% and 36.1% for AOD missingness.
They are not rival estimates. Each one counts a different thing at a different stage, and this
script derives all of them from the stored parquet files so that none has to be taken on trust.
The README section "Why the numbers differ" quotes this script's output.

Needs the licensed hourly panel (`data/interim/panel.parquet`), which is not redistributed;
without it the script says so and exits 0, the same way the panel-dependent tests skip.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
SPLITS = ROOT / "benchmark" / "splits"
sys.path.insert(0, str(ROOT / "src"))

from ecopulse_ca.qc.pipeline import apply_flatline_policy  # noqa: E402
from ecopulse_ca.qc.rules import (  # noqa: E402
    FlatlinePolicy,
    QCReport,
    q1_physical_range,
    q2_flatline,
    q3_zero_run,
)

# The figures the README and DECISIONS.md quote. --check fails when the data stops agreeing.
EXPECTED = {
    "hours_in_span_10_feeds": 450_817,
    "observed_10_feeds": 341_321,
    "after_row_masks_10_feeds": 340_439,
    "benchmark_panel_observed": 247_075,
    "masked_hours_still_in_panel": 882,
    "benchmark_window_observed": 206_966,
    "aod_null_extraction_grid": 6_148,
    "aod_extraction_grid_station_days": 17_816,
}


def _load_r7():
    spec = importlib.util.spec_from_file_location(
        "build_r7_tables", ROOT / "scripts" / "build_r7_tables.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hourly_chain() -> dict[str, int]:
    panel = pd.read_parquet(INTERIM / "panel.parquet")
    panel.columns = [str(c) for c in panel.columns]
    prov = pd.read_csv(INTERIM / "panel_provenance.csv")
    prov["location_id"] = prov["location_id"].astype(str)
    qc = pd.read_csv(INTERIM / "qc_findings.csv")
    rejected = set(qc.loc[qc.verdict == "reject", "station_id"].astype(str))
    keep = [c for c in panel.columns if c not in rejected]

    # Row-level masks, exactly as run_qc's last stage applies them (D-002: MASK_WINDOW).
    masked_hours = {}
    for sid in keep:
        s = panel[sid]
        rep = QCReport()
        rep.add(q1_physical_range(s, sid), q2_flatline(s, sid), q3_zero_run(s, sid))
        m, _ = apply_flatline_policy(s, rep.row_mask(sid, s.index), sid, FlatlinePolicy.MASK_WINDOW)
        masked_hours[sid] = s.notna() & m.isna()

    bench = pd.read_parquet(INTERIM / "benchmark_panel.parquet")
    src = pd.read_parquet(INTERIM / "panel_sources.parquet")
    pairs = {
        "Bishkek": ("8225", "8827"),
        "Ashgabat": ("8870", "8170"),
        "Dushanbe": ("8684", "9769"),
    }
    still_in = 0
    for city, ids in pairs.items():
        for fid in ids:
            still_in += int((masked_hours[fid] & bench[city].notna() & (src[city] == fid)).sum())
    for fid in keep:  # feeds that were never merged
        if fid in bench.columns:
            still_in += int((masked_hours[fid] & bench[fid].notna()).sum())

    blocks = json.loads((SPLITS / "temporal_blocks.json").read_text(encoding="utf-8"))[
        "temporal_blocks"
    ]
    by_block = {}
    for b in blocks:
        lo, hi = pd.Timestamp(b["start"]), pd.Timestamp(b["end"])
        by_block[b["name"]] = int(
            bench[(bench.index >= lo) & (bench.index <= hi)].notna().sum().sum()
        )
    window = pd.Timestamp("2018-11-27", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")
    in_window = int(
        bench[(bench.index >= window[0]) & (bench.index < window[1])].notna().sum().sum()
    )

    splits = json.loads((SPLITS / "splits.json").read_text(encoding="utf-8"))
    return {
        "hours_in_span_10_feeds": int(prov[prov.location_id.isin(keep)].n_hours_in_span.sum()),
        "observed_10_feeds": int(panel[keep].notna().sum().sum()),
        "after_row_masks_10_feeds": int(
            sum((panel[k].notna() & ~masked_hours[k]).sum() for k in keep)
        ),
        "benchmark_panel_observed": int(bench.notna().sum().sum()),
        "splits_json_n_observations": sum(int(x["n_observations"]) for x in splits["stations"]),
        "masked_hours_still_in_panel": still_in,
        "benchmark_window_observed": in_window,
        **{f"block_{k}": v for k, v in by_block.items()},
    }


def aod_missingness() -> dict[str, float]:
    r7 = _load_r7()
    raw = pd.read_parquet(INTERIM / "maiac_aod.parquet")
    out = {
        "aod_extraction_grid_station_days": len(raw),
        "aod_null_extraction_grid": int(raw["aod_055"].isna().sum()),
    }
    out["aod_null_pct_extraction_grid"] = 100 * out["aod_null_extraction_grid"] / len(raw)

    grid = r7.satellite_daily("maiac_aod")  # Dushanbe re-keyed to its primary, secondary dropped
    out["aod_grid_7_instruments_station_days"] = len(grid)
    out["aod_null_pct_7_instruments"] = 100 * grid["value"].isna().mean()

    joined = grid.merge(r7.daily_target(), on=["station_id", "date"], how="inner")
    out["aod_ground_truth_station_days"] = len(joined)
    out["aod_null_pct_ground_truth_days"] = 100 * joined["value"].isna().mean()
    return out


def main(argv: list[str]) -> int:
    if not (INTERIM / "panel.parquet").exists():
        print("reconcile_counts: data/interim/panel.parquet is not present (licensed panel, not")
        print("redistributed); nothing to reconcile on this clone.")
        return 0

    chain, aod = hourly_chain(), aod_missingness()
    print("HOURLY OBSERVATIONS")
    for k, v in chain.items():
        print(f"  {k:34s} {v:>10,}")
    print("\nAOD MISSINGNESS")
    for k, v in aod.items():
        print(f"  {k:34s} {v:>12,.2f}" if isinstance(v, float) else f"  {k:34s} {v:>12,}")

    if "--check" in argv:
        got = {**chain, **aod}
        bad = {k: (want, got.get(k)) for k, want in EXPECTED.items() if got.get(k) != want}
        if chain["benchmark_panel_observed"] != chain["splits_json_n_observations"]:
            bad["splits_json_n_observations"] = (
                chain["benchmark_panel_observed"],
                chain["splits_json_n_observations"],
            )
        if bad:
            print("\nDRIFT:", file=sys.stderr)
            for k, (want, have) in bad.items():
                print(f"  {k}: documented {want!r}, derived {have!r}", file=sys.stderr)
            return 1
        print("\nOK: every documented figure reproduces from the stored data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
