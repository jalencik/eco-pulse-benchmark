"""R10: does OpenAQ's `datetimeFirst` mean deployment, or ingestion?

Run:  python scripts/verify_r10.py [--sample N]

Writes:  data/interim/r10_probe.csv
         paper/tables/t2_04_r10_span_provenance.csv

Why this matters. 306 of 317 candidate stations were excluded for a span shorter than two
years, and almost all of them are AirGradient/Clarity low-cost units with a median span of
0.59 y. That exclusion rests entirely on `datetimeFirst`. If that field records when
OpenAQ *started ingesting* a feed rather than when the instrument was *deployed*, the true
spans are longer, the exclusions were too aggressive, and the benchmark is smaller than it
needed to be.

The test is direct rather than documentary: ask the API for measurements in a window
strictly *before* each station's reported `datetimeFirst`. Provider documentation can be
wrong or ambiguous; the archive either holds earlier rows or it does not.

  - rows returned before datetimeFirst  -> the field is an ingestion marker, exclusions
                                           were too aggressive, R10 is REAL
  - no rows for any probed station      -> the field reflects the archive's true start,
                                           exclusions were correct, R10 is CLOSED

Note on interpretation: a null result closes R10 *for the archive we are entitled to use*.
A sensor could have run earlier and had that history never reach OpenAQ. That is not a
recoverable benchmark row either way, so it does not change the split.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from ecopulse_ca.config import SETTINGS
from ecopulse_ca.ingest.measurements import DATETIME_FROM, DATETIME_TO
from ecopulse_ca.ingest.openaq import OpenAQClient

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
TABLES = ROOT / "paper" / "tables"

LOOKBACK_YEARS = 3
# One hour of margin, so a station whose first record sits exactly on the boundary is not
# counted as "earlier" by a rounding artefact.
MARGIN = pd.Timedelta(hours=1)


def probe_station(client: OpenAQClient, sensor_id: int, first: pd.Timestamp) -> dict:
    """Ask for hours strictly before `first`. Returns what came back."""
    lo = first - pd.DateOffset(years=LOOKBACK_YEARS)
    hi = first - MARGIN
    params = {
        DATETIME_FROM: lo.strftime("%Y-%m-%dT%H:%M:%SZ"),
        DATETIME_TO: hi.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 1000,
    }
    try:
        payload = client.get(f"/sensors/{sensor_id}/hours", params)
    except Exception as exc:  # noqa: BLE001 - a probe failure must not kill the sweep
        return {"error": type(exc).__name__, "n_before": None, "earliest_found": None}

    records = payload.get("results", []) if isinstance(payload, dict) else []
    stamps = []
    for r in records:
        period = (r.get("period") or {}).get("datetimeFrom") or {}
        utc = period.get("utc")
        if utc:
            stamps.append(pd.Timestamp(utc))

    # Guard against the failure mode this project has already hit: OpenAQ silently ignores
    # unknown query parameters, so a typo'd window returns the whole record and every
    # station looks like it has earlier data. Any stamp at or after `first` means the
    # window was not honoured, and the probe is uninterpretable rather than positive.
    honoured = all(s < first for s in stamps) if stamps else True
    return {
        "error": None,
        "n_before": len(stamps) if honoured else None,
        "earliest_found": min(stamps).isoformat() if stamps and honoured else None,
        "window_honoured": honoured,
    }


def positive_control(client: OpenAQClient, census: pd.DataFrame) -> tuple[bool, str]:
    """Prove the probe can detect data before declaring that it detected none.

    A sweep that returns "no earlier data" for every station is indistinguishable from a
    sweep that cannot see data at all -- wrong endpoint, silently-ignored parameters, an
    auth failure swallowed by the caller. OpenAQ *does* silently ignore unknown query
    parameters, and this project has already shipped two full pipeline runs against a
    window that was never applied.

    So: take an eligible station and ask for a window deep inside its known record. Rows
    must come back. If they do not, the negative result below means nothing.
    """
    eligible = census[census["q7_span_ok_upper_bound"]].dropna(subset=["datetime_first"])
    for _, st in eligible.iterrows():
        sensors = [s for s in str(st.pm25_sensor_ids).split(";") if s.strip().isdigit()]
        last = pd.to_datetime(st.datetime_last, utc=True, errors="coerce")
        if not sensors or pd.isna(last):
            continue
        # A week starting 30 days after the reported start: unambiguously inside the record.
        lo = st.datetime_first + pd.Timedelta(days=30)
        hi = lo + pd.Timedelta(days=7)
        if hi >= last:
            continue
        payload = client.get(
            f"/sensors/{int(sensors[0])}/hours",
            {
                DATETIME_FROM: lo.strftime("%Y-%m-%dT%H:%M:%SZ"),
                DATETIME_TO: hi.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": 1000,
            },
        )
        n = len(payload.get("results", []) if isinstance(payload, dict) else [])
        if n:
            return True, f"station {st.location_id}: {n} hours in a known-good 7-day window"
        return False, f"station {st.location_id}: 0 hours inside its own record"
    return False, "no eligible station suitable for a control"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40, help="stations to probe (0 = all)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if SETTINGS.use_fixtures:
        print("REFUSING: fixtures mode. R10 needs the live API -- set OPENAQ_API_KEY.")
        return 1

    census = pd.read_csv(INTERIM / "station_census.csv", keep_default_na=False, na_values=[""])
    census["datetime_first"] = pd.to_datetime(census["datetime_first"], utc=True, errors="coerce")
    census["q7_span_ok_upper_bound"] = (
        census["q7_span_ok_upper_bound"].astype(str).str.lower().isin({"true", "1"})
    )

    excluded = census[~census["q7_span_ok_upper_bound"]].dropna(subset=["datetime_first"]).copy()
    print(f"excluded stations: {len(excluded)}  (median span {excluded.span_years.median():.2f} y)")
    print(f"providers: {excluded.provider.value_counts().head(5).to_dict()}\n")

    # Stratify by provider so the answer is not dominated by whichever network is largest.
    if args.sample and args.sample < len(excluded):
        per = max(1, args.sample // max(1, excluded.provider.nunique()))
        picked = excluded.groupby("provider", group_keys=False).head(per).head(args.sample)
    else:
        picked = excluded
    print(f"probing {len(picked)} stations for measurements before their reported start\n")

    rows = []
    with OpenAQClient(SETTINGS) as client:
        ok_control, detail = positive_control(client, census)
        print(f"positive control: {'PASS' if ok_control else 'FAIL'} -- {detail}\n")
        if not ok_control:
            print("ABORTING: the probe cannot detect data that is known to exist, so a")
            print("negative result would be meaningless. R10 stays unverified.")
            return 1

        for _, st in picked.iterrows():
            sensors = [s for s in str(st.pm25_sensor_ids).split(";") if s.strip().isdigit()]
            if not sensors:
                continue
            res = probe_station(client, int(sensors[0]), st.datetime_first)
            rows.append(
                {
                    "location_id": st.location_id,
                    "city": st.city,
                    "provider": st.provider,
                    "sensor_id": int(sensors[0]),
                    "reported_first": st.datetime_first.isoformat(),
                    "span_years": st.span_years,
                    **res,
                }
            )
            flag = (
                "ERROR"
                if res["error"]
                else ("EARLIER DATA" if (res["n_before"] or 0) > 0 else "none")
            )
            print(f"  {st.location_id:>9}  {str(st.provider)[:18]:18s}  {flag}")

    out = pd.DataFrame(rows)
    INTERIM.mkdir(parents=True, exist_ok=True)
    out.to_csv(INTERIM / "r10_probe.csv", index=False)

    ok = out[out.error.isna()]
    with_earlier = ok[(ok.n_before.fillna(0) > 0)]
    unusable = out[out.error.notna() | out.n_before.isna()]

    verdict = "REAL" if len(with_earlier) else ("INCONCLUSIVE" if ok.empty else "CLOSED")
    summary = pd.DataFrame(
        [
            {
                "n_excluded_total": len(excluded),
                "n_probed": len(out),
                "n_interpretable": len(ok),
                "n_unusable": len(unusable),
                "n_with_earlier_data": len(with_earlier),
                "pct_with_earlier_data": 100 * len(with_earlier) / len(ok)
                if len(ok)
                else float("nan"),
                "lookback_years": LOOKBACK_YEARS,
                "positive_control": "pass",
                "verdict": verdict,
            }
        ]
    )
    TABLES.mkdir(parents=True, exist_ok=True)
    summary.to_csv(TABLES / "t2_04_r10_span_provenance.csv", index=False)

    print(f"\n{'=' * 62}")
    print(summary.to_string(index=False))
    print(f"{'=' * 62}")
    if verdict == "REAL":
        print("R10 REAL: datetimeFirst understates deployment. Exclusions were too")
        print("aggressive and the eligible station pool should be recomputed.")
    elif verdict == "CLOSED":
        print("R10 CLOSED: no station has archived measurements before its reported")
        print("start. datetimeFirst reflects the archive, and the exclusions stand.")
    else:
        print("R10 INCONCLUSIVE: no interpretable probe. Do not update the ledger.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
