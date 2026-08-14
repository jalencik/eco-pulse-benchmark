"""Build and freeze the benchmark splits.

Once frozen, these files are the benchmark. `tests/test_splits_immutable.py` compares the
live build against the committed `splits.sha256` and fails if anything moves -- including
if *I* move it. That test is the point of this module.

The purge gap is derived, not chosen
------------------------------------
A training sample at time ``t`` reads features from ``[t - max_lag, t]`` and predicts
``t + h``. A test sample at ``t'`` reads features from ``[t' - max_lag, t']``. For no
training sample's feature window or target to touch the test block:

    purge >= max_lag + max_horizon = 168 + 72 = 240 hours

168 h is the longest feature window on the ladder (`SameHourMean(n_days=7)`); 72 h is the
longest forecast horizon. If either grows, the purge must grow with it, and
`tests/test_purge_gap.py` recomputes the requirement from the model definitions rather than
trusting the constant below.

Why post-2024 data is reserved and unused
-----------------------------------------
Only four stations report after the US embassy programme ended (2025-03-04). That period
cannot be training data -- training on 2025 while testing on 2024 is lookahead -- and it
cannot be test data either, since coverage would be uneven across cities. It is therefore
labelled ``reserved`` and excluded from every split, rather than quietly dropped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
INTERIM = ROOT / "data" / "interim"
SPLIT_DIR = ROOT / "benchmark" / "splits"

# 1.1.0 (2026-08-13) -- Dushanbe 8684/9769 were one US-embassy instrument republished under
# two location_ids with coordinates 6.06 km apart, so the 150 m Q5b distance rule could not
# see it. 99.99% of their 33,462 overlapping hours are the identical reading. They are now
# merged under the D-008 rule (precedence + gap-fill, never averaging), exactly as the
# Bishkek and Ashgabat republications already were. Stations 8 -> 7; cities unchanged at 6;
# leave-station-out loses its two Dushanbe folds. See data/DECISIONS.md D-011 and D-012.
# Every published number was regenerated against this version -- v1.0.0 results are not
# comparable.
BENCHMARK_VERSION = "1.1.0"
MAX_LAG_HOURS = 168  # longest feature window on the ladder (SameHourMean, 7 days)
MAX_HORIZON_HOURS = 72  # longest forecast horizon (t+72h)
PURGE_HOURS = MAX_LAG_HOURS + MAX_HORIZON_HOURS  # 240 h -- derived, not chosen
TEST_YEAR = 2024


@dataclass(frozen=True)
class Block:
    name: str
    start: str
    end: str

    def hours(self) -> float:
        return (pd.Timestamp(self.end) - pd.Timestamp(self.start)).total_seconds() / 3600


HOUR = pd.Timedelta(1, unit="h")


def build_temporal_blocks(panel: pd.DataFrame) -> list[Block]:
    """Blocked-temporal split with a purge gap either side of the validation block.

    Bounds come from the first and last hour that any *surviving* station actually reports,
    not from the panel index. The index is the union over every station ever fetched, so it
    still begins at Astana's 2018-07-27 even though Astana was rejected by Q7 -- using it
    would declare a training block that starts 4 months before any retained station has a
    single observation.
    """
    observed = panel.notna().any(axis=1)
    first_obs = pd.DatetimeIndex(panel.index[observed]).min().floor("h")
    last_obs = pd.DatetimeIndex(panel.index[observed]).max().floor("h")

    purge = pd.Timedelta(PURGE_HOURS, unit="h")
    test_start = pd.Timestamp(f"{TEST_YEAR}-01-01", tz="UTC")
    test_end = pd.Timestamp(f"{TEST_YEAR}-12-31 23:00", tz="UTC")

    purge2_start = test_start - purge
    val_end = purge2_start - HOUR
    purge1_start = pd.Timestamp(f"{TEST_YEAR - 1}-01-01", tz="UTC")
    val_start = purge1_start + purge
    train_end = purge1_start - HOUR

    def iso(t: pd.Timestamp) -> str:
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    return [
        Block("train", iso(first_obs), iso(train_end)),
        Block("purge_train_val", iso(purge1_start), iso(val_start - HOUR)),
        Block("val", iso(val_start), iso(val_end)),
        Block("purge_val_test", iso(purge2_start), iso(test_start - HOUR)),
        Block("test", iso(test_start), iso(test_end)),
        Block("reserved_post_test", iso(test_end + HOUR), iso(last_obs)),
    ]


def build_leave_city_out(stations: list[dict]) -> list[dict]:
    """One fold per city; the held-out city contributes **no** training stations."""
    cities = sorted({s["city"] for s in stations})
    folds = []
    for i, city in enumerate(cities):
        held = sorted(s["station_id"] for s in stations if s["city"] == city)
        train = sorted(s["station_id"] for s in stations if s["city"] != city)
        folds.append(
            {
                "fold": i,
                "held_out_city": city,
                "held_out_stations": held,
                "train_stations": train,
                "n_train_cities": len({s["city"] for s in stations if s["city"] != city}),
            }
        )
    return folds


def build_leave_station_out(stations: list[dict]) -> list[dict]:
    """Within-city station holdout. Only possible where a city has >= 2 instruments.

    On this panel that is Dushanbe and Khujand only -- 2 of 6 cities. Cities with a single
    instrument are listed explicitly under ``ineligible_cities`` so the coverage gap is a
    stated property of the benchmark rather than an unexplained absence.
    """
    by_city: dict[str, list[str]] = {}
    for s in stations:
        by_city.setdefault(s["city"], []).append(s["station_id"])

    folds: list[dict[str, Any]] = []
    ineligible: list[str] = []
    for city, ids in sorted(by_city.items()):
        ids = sorted(ids)
        if len(ids) < 2:
            ineligible.append(city)
            continue
        for sid in ids:
            folds.append(
                {
                    "fold": len(folds),
                    "city": city,
                    "held_out_station": sid,
                    "train_stations": sorted(i for i in ids if i != sid),
                }
            )
    return [{"folds": folds, "ineligible_cities": ineligible}]


def canonical_json(payload: dict) -> str:
    """Deterministic serialisation -- byte-identical across runs and platforms."""
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def digest(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


REQUIRED_INPUTS = ("benchmark_panel.parquet", "panel_provenance.csv", "station_census.csv")


def _require_inputs(panel_path: Path) -> None:
    """Fail with instructions rather than a bare FileNotFoundError.

    These three files are derived from the OpenAQ archive and are gitignored, so a fresh
    clone does not have them. A reviewer running `make reproduce` first would otherwise get
    `FileNotFoundError: data\\interim\\benchmark_panel.parquet` and no indication of whether
    the repository was broken or a step was missing. The splits themselves *are* committed,
    so verifying the benchmark needs no rebuild — only regenerating it from source does.
    """
    missing = [panel_path] if not panel_path.exists() else []
    missing += [INTERIM / n for n in REQUIRED_INPUTS[1:] if not (INTERIM / n).exists()]
    if not missing:
        return
    names = "\n".join(f"    {m}" for m in missing)
    raise FileNotFoundError(
        "cannot rebuild the splits: the derived ground-truth panel is absent.\n\n"
        f"missing:\n{names}\n\n"
        "These are produced from the OpenAQ archive and are not committed (see\n"
        "data/MANIFEST.md for provenance and licence status). To regenerate them you need\n"
        "an OPENAQ_API_KEY in .env, then:\n\n"
        "    python -m ecopulse_ca.ingest.openaq --census\n"
        "    python scripts/pull_panel.py\n\n"
        "To *verify* the frozen benchmark instead, no rebuild is needed. The splits are\n"
        "committed and self-verifying:\n\n"
        "    cd benchmark/splits && sha256sum -c splits.sha256"
    )


def build(panel_path: Path = INTERIM / "benchmark_panel.parquet") -> dict:
    _require_inputs(panel_path)
    panel = pd.read_parquet(panel_path)
    prov = pd.read_csv(INTERIM / "panel_provenance.csv")
    census = pd.read_csv(INTERIM / "station_census.csv", keep_default_na=False, na_values=[""])
    census["location_id"] = census["location_id"].astype(str)
    coords = census.set_index("location_id")[["latitude", "longitude"]]

    city_of = dict(zip(prov.location_id.astype(str), prov.city, strict=False))
    id_of_city = {v: k for k, v in city_of.items()}

    stations = []
    for col in panel.columns:
        sid = str(col)
        city = city_of.get(sid, sid)  # merged columns are named by city
        lookup = sid if sid in coords.index else id_of_city.get(city, sid)
        lat = float(coords.loc[lookup, "latitude"]) if lookup in coords.index else float("nan")
        lon = float(coords.loc[lookup, "longitude"]) if lookup in coords.index else float("nan")
        stations.append(
            {
                "station_id": sid,
                "city": city,
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "n_observations": int(panel[col].notna().sum()),
            }
        )
    stations.sort(key=lambda s: (s["city"], s["station_id"]))

    blocks = build_temporal_blocks(panel)
    lco = build_leave_city_out(stations)
    lso = build_leave_station_out(stations)

    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "config": {
            "max_lag_hours": MAX_LAG_HOURS,
            "max_horizon_hours": MAX_HORIZON_HOURS,
            "purge_hours": PURGE_HOURS,
            "purge_rule": "purge_hours == max_lag_hours + max_horizon_hours",
            "test_year": TEST_YEAR,
            "seeds": [0, 1, 2, 3, 4],
        },
        "stations": stations,
        "temporal_blocks": [asdict(b) for b in blocks],
        "leave_city_out": lco,
        "leave_station_out": lso[0],
        "combined_headline": {
            "description": "unseen city x unseen period: leave_city_out folds evaluated "
            "only on the test block",
            "spatial": "leave_city_out",
            "temporal": "test",
        },
        "notes": [
            "Post-test data is reserved and unused: it cannot train (lookahead vs the 2024 "
            "test block) and cannot test (only 4 stations report after 2025-03-04).",
            "leave_station_out covers 2 of 6 cities; the rest hold a single instrument.",
            "Bishkek and Ashgabat are merged feeds -- see data/DECISIONS.md D-008. Bishkek's "
            "two publishers agree on only 11.1% of overlapping hours in the 2024 test block.",
        ],
    }
    return payload


def _write_exact(path: Path, text: str) -> None:
    """Write bytes exactly as given -- no platform newline translation.

    `Path.write_text` translates "\\n" to "\\r\\n" on Windows, which makes the file on disk
    differ from the canonical serialisation that was hashed. The published checksum would
    then fail `sha256sum splits.json` -- the obvious way a third party verifies it -- and
    look like tampering. The checksum must be verifiable with standard tools, not only with
    this repo's own code.
    """
    path.write_bytes(text.encode("utf-8"))


def freeze(payload: dict, out_dir: Path = SPLIT_DIR) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_exact(out_dir / "splits.json", canonical_json(payload))

    for name in ("temporal_blocks", "leave_city_out", "leave_station_out"):
        _write_exact(out_dir / f"{name}.json", canonical_json({name: payload[name]}))

    sha = digest(payload)

    # The freeze timestamp records when the benchmark was frozen, not when this command
    # last ran. Re-stamping it on every invocation made `make reproduce` mutate a committed
    # file even when the splits were byte-identical, so a reviewer who ran the pipeline got
    # a dirty working tree from a no-op and had to decide whether the benchmark had moved.
    # An idempotent reproduction is part of the claim, so the original stamp is preserved
    # whenever the hash is unchanged.
    frozen_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = out_dir / "splits.sha256"
    if existing.exists():
        text = existing.read_text(encoding="utf-8")
        if text.startswith(f"{sha}  splits.json"):
            for line in text.splitlines():
                if line.startswith("# frozen "):
                    frozen_at = line.removeprefix("# frozen ").strip()
                    break

    _write_exact(
        out_dir / "splits.sha256",
        f"{sha}  splits.json\n"
        f"# benchmark_version {payload['benchmark_version']}\n"
        f"# frozen {frozen_at}\n"
        f"# IMMUTABLE. If this hash changes, tests/test_splits_immutable.py fails.\n"
        f"# Poor predictor coverage in a frozen city is REPORTED, never fixed by refreezing.\n"
        f"# Verify with:  sha256sum -c splits.sha256\n",
    )
    return sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build/freeze benchmark splits")
    ap.add_argument("--freeze", action="store_true", help="write the split files")
    args = ap.parse_args(argv)

    payload = build()
    sha = digest(payload)

    print(f"benchmark v{payload['benchmark_version']}")
    print(f"stations : {len(payload['stations'])}")
    print(f"cities   : {len({s['city'] for s in payload['stations']})}")
    print(f"purge    : {PURGE_HOURS} h  ({MAX_LAG_HOURS} lag + {MAX_HORIZON_HOURS} horizon)")
    print("\ntemporal blocks:")
    for b in payload["temporal_blocks"]:
        print(f"  {b['name']:20s} {b['start']}  ->  {b['end']}")
    print(f"\nleave-city-out folds     : {len(payload['leave_city_out'])}")
    print(
        f"leave-station-out folds  : {len(payload['leave_station_out']['folds'])}"
        f"  (ineligible: {payload['leave_station_out']['ineligible_cities']})"
    )
    print(f"\nsha256: {sha}")

    if args.freeze:
        freeze(payload)
        print(f"frozen -> {SPLIT_DIR}")
    else:
        print("(dry run -- pass --freeze to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
