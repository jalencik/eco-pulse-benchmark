"""OpenAQ v3 client, and the station census that settles falsifier F3.

The census is deliberately built from `/v3/locations` alone. That endpoint carries
`datetimeFirst` / `datetimeLast` per location, so the record span of every station in the
region can be established **without downloading a single measurement**. F3 -- "are there
enough cities to support leave-city-out at all?" -- is the question that decides whether
the headline result exists, so it should be answered with one cheap call, not after
building a pipeline around stations that may not qualify.

Two response fields matter more than they look:

- `isMonitor` separates reference-grade instruments from low-cost sensors. In a region
  where most signals are low-cost, this is the difference between a calibration anchor and
  a device that needs one. It becomes the benchmark's quality tier.
- `isMobile` marks sensors that move. A moving sensor has no fixed location, so it cannot
  participate in leave-city-out or leave-station-out at all, and is excluded rather than
  silently averaged into a city.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ecopulse_ca.config import SETTINGS, Settings
from ecopulse_ca.ingest.base import HttpSource

log = logging.getLogger(__name__)

PM25 = "pm25"


class OpenAQClient(HttpSource):
    base_url = "https://api.openaq.org/v3"
    page_limit = 1000

    def __init__(self, settings: Settings = SETTINGS) -> None:
        super().__init__(use_fixtures=settings.use_fixtures, cache_dir=settings.cache_dir)
        self.settings = settings

    def auth_headers(self) -> dict[str, str]:
        key = self.settings.openaq_api_key
        return {"X-API-Key": key} if key else {}

    def fixture_name(self, path: str, params: dict[str, Any] | None) -> str:
        params = params or {}
        if path == "/locations":
            return f"openaq_locations_{str(params.get('iso', 'ALL')).upper()}"
        if "/hours" in path:
            return "openaq_sensor_hours"
        return "openaq_" + path.strip("/").replace("/", "_")

    # -- endpoints ----------------------------------------------------------------------
    def locations(self, iso: str) -> list[dict]:
        """All monitoring locations for one ISO-3166 alpha-2 country code."""
        return self.paginate("/locations", {"iso": iso})

    def sensor_hours(self, sensor_id: int, date_from: str, date_to: str) -> list[dict]:
        """Hourly aggregates for one sensor.

        The `/hours` endpoint returns a `coverage` block (expectedCount, observedCount,
        percentComplete) alongside each value. That is exactly the quantity QC rule Q7
        needs, reported by the provider rather than inferred by us.
        """
        return self.paginate(
            f"/sensors/{sensor_id}/hours",
            {"date_from": date_from, "date_to": date_to},
        )


# -- census ---------------------------------------------------------------------------


def _pm25_sensors(location: dict) -> list[int]:
    return [
        s["id"]
        for s in (location.get("sensors") or [])
        if (s.get("parameter") or {}).get("name") == PM25
    ]


def _dt(node: Any) -> str | None:
    """OpenAQ returns datetimes as {'utc': ..., 'local': ...}; keep UTC for arithmetic."""
    if isinstance(node, dict):
        return node.get("utc")
    return node if isinstance(node, str) else None


def census_frame(locations: list[dict], country: str) -> pd.DataFrame:
    rows = []
    for loc in locations:
        sensors = _pm25_sensors(loc)
        coords = loc.get("coordinates") or {}
        rows.append(
            {
                "location_id": loc.get("id"),
                "name": loc.get("name"),
                "locality": loc.get("locality"),
                "country": (loc.get("country") or {}).get("code") or country,
                "latitude": coords.get("latitude"),
                "longitude": coords.get("longitude"),
                "timezone": loc.get("timezone"),
                "is_monitor": loc.get("isMonitor"),
                "is_mobile": loc.get("isMobile"),
                "provider": (loc.get("provider") or {}).get("name"),
                "n_pm25_sensors": len(sensors),
                "pm25_sensor_ids": ",".join(str(s) for s in sensors),
                "datetime_first": _dt(loc.get("datetimeFirst")),
                "datetime_last": _dt(loc.get("datetimeLast")),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    for col in ("datetime_first", "datetime_last"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    df["span_days"] = (df["datetime_last"] - df["datetime_first"]).dt.total_seconds() / 86400
    df["span_years"] = df["span_days"] / 365.25

    # Preliminary eligibility only. Q7 also requires >=60% hourly completeness, which needs
    # the /hours coverage block -- so this flag is an upper bound on the qualifying set,
    # never a final verdict. Named to make that impossible to forget.
    df["q7_span_ok_upper_bound"] = (
        (df["n_pm25_sensors"] > 0) & (~df["is_mobile"].fillna(False)) & (df["span_years"] >= 2.0)
    )
    return df


def run_census(settings: Settings = SETTINGS) -> pd.DataFrame:
    """Station census across all in-scope countries. Answers F3."""
    frames = []
    with OpenAQClient(settings) as client:
        for iso in settings.countries:
            try:
                locs = client.locations(iso)
            except Exception as exc:  # noqa: BLE001 - one country failing must not kill the census
                log.warning("census failed for %s: %s", iso, exc)
                continue
            log.info("%s: %d locations", iso, len(locs))
            frames.append(census_frame(locs, iso))

    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(
        ["country", "locality", "name"], na_position="last"
    )


def summarise_census(df: pd.DataFrame) -> pd.DataFrame:
    """Per-country rollup -- the table that decides whether leave-city-out is viable."""
    if df.empty:
        return pd.DataFrame()
    eligible = df[df["q7_span_ok_upper_bound"]]
    return (
        df.groupby("country")
        .agg(
            locations=("location_id", "count"),
            with_pm25=("n_pm25_sensors", lambda s: int((s > 0).sum())),
            reference_monitors=("is_monitor", lambda s: int(s.fillna(False).sum())),
            mobile=("is_mobile", lambda s: int(s.fillna(False).sum())),
            max_span_years=("span_years", "max"),
        )
        .join(
            eligible.groupby("country").agg(
                span_eligible=("location_id", "count"),
                distinct_localities=("locality", "nunique"),
            )
        )
        .fillna({"span_eligible": 0, "distinct_localities": 0})
        .astype({"span_eligible": int, "distinct_localities": int})
        .reset_index()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAQ station census (settles F3)")
    parser.add_argument("--out", type=Path, default=Path("data/interim/station_census.csv"))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    mode = "FIXTURES (no API key)" if SETTINGS.use_fixtures else "LIVE API"
    print(f"census mode: {mode}   countries: {', '.join(SETTINGS.countries)}")

    df = run_census()
    if df.empty:
        print("no locations returned")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    summary = summarise_census(df)
    print(f"\n{len(df)} locations -> {args.out}\n")
    print(summary.to_string(index=False))

    cities = df.loc[df["q7_span_ok_upper_bound"], "locality"].dropna().nunique()
    print(f"\nF3 check: {cities} distinct localities pass the >=2yr span pre-filter.")
    print("  (upper bound -- Q7 completeness not yet applied)")
    if SETTINGS.use_fixtures:
        print("  FIXTURE DATA -- not a finding. Paste OPENAQ_API_KEY into .env for real counts.")
    elif cities < 4:
        print("  *** F3 TRIGGERED: leave-city-out is not viable. Degrade to leave-station-out")
        print("      and narrow the claim, per research/GAP.md section 3. ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
