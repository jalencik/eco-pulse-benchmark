"""Fetch hourly PM2.5 series for the census-eligible sensors.

Design choices that matter for reproducibility:

- **Requests are chunked by calendar year.** A six-year hourly range is ~52k records, or
  ~52 pages at the API's 1000-record limit. Chunking means each cached response is small
  and stable, an interrupted pull resumes at year granularity rather than restarting, and
  the manifest can checksum year-sized units.

- **The provider's own `coverage` block is preserved.** `/v3/sensors/{id}/hours` reports
  `expectedCount` / `observedCount` / `percentComplete` per hour. Q7 completeness should be
  measured against what the provider says it expected, not against a count we infer.

- **Series are reindexed onto a complete hourly grid.** A gap must be an explicit NaN, not
  an absent row. If gaps are merely missing rows, every downstream completeness figure is
  computed against the rows that happen to exist and comes out near 100% -- the exact
  failure `q7_completeness` is written to avoid.
"""

from __future__ import annotations

import logging

import pandas as pd

from ecopulse_ca.ingest.openaq import OpenAQClient

log = logging.getLogger(__name__)


def _period_start(record: dict) -> str | None:
    period = record.get("period") or {}
    dt_from = period.get("datetimeFrom") or {}
    if isinstance(dt_from, dict):
        return dt_from.get("utc")
    return dt_from if isinstance(dt_from, str) else None


def records_to_series(records: list[dict]) -> tuple[pd.Series, pd.Series]:
    """Convert `/hours` records into (values, percent_complete), indexed by UTC hour."""
    rows = []
    for r in records:
        ts = _period_start(r)
        if ts is None:
            continue
        cov = r.get("coverage") or {}
        rows.append(
            {
                "ts": ts,
                "value": r.get("value"),
                "percent_complete": cov.get("percentComplete"),
            }
        )
    if not rows:
        empty_idx = pd.DatetimeIndex([], tz="UTC")
        return pd.Series(dtype=float, index=empty_idx), pd.Series(dtype=float, index=empty_idx)

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).drop_duplicates(subset="ts", keep="first").set_index("ts")
    df = df.sort_index()
    return df["value"].astype(float), df["percent_complete"].astype(float)


def reindex_hourly(series: pd.Series) -> pd.Series:
    """Put the series on a gap-free hourly grid so missing hours become explicit NaN."""
    if series.empty:
        return series
    full = pd.date_range(series.index.min(), series.index.max(), freq="h", tz="UTC")
    return series.reindex(full)


def fetch_sensor_series(
    client: OpenAQClient,
    sensor_id: int,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> tuple[pd.Series, pd.Series]:
    """Hourly series for one sensor, pulled year by year."""
    values, coverage = [], []
    for year in range(date_from.year, date_to.year + 1):
        lo = max(date_from, pd.Timestamp(f"{year}-01-01", tz="UTC"))
        hi = min(date_to, pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC"))
        if lo > hi:
            continue
        try:
            records = client.paginate(
                f"/sensors/{sensor_id}/hours",
                {
                    "date_from": lo.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "date_to": hi.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
        except Exception as exc:  # noqa: BLE001 - one bad year must not lose the others
            log.warning("sensor %s year %s failed: %s", sensor_id, year, exc)
            continue
        v, c = records_to_series(records)
        log.info("sensor %s %s: %d records", sensor_id, year, len(v))
        values.append(v)
        coverage.append(c)

    if not values:
        empty_idx = pd.DatetimeIndex([], tz="UTC")
        return pd.Series(dtype=float, index=empty_idx), pd.Series(dtype=float, index=empty_idx)

    vals = pd.concat(values).sort_index()
    cov = pd.concat(coverage).sort_index()
    vals = vals[~vals.index.duplicated(keep="first")]
    cov = cov[~cov.index.duplicated(keep="first")]
    return reindex_hourly(vals), cov


def build_panel(
    census: pd.DataFrame,
    client: OpenAQClient,
    *,
    station_key: str = "location_id",
) -> tuple[dict[str, pd.Series], pd.DataFrame]:
    """Fetch every eligible station's series.

    Returns `(panel, provenance)`. `provenance` records, per station, what was actually
    retrieved -- so the manifest reflects the pull rather than the request.
    """
    panel: dict[str, pd.Series] = {}
    rows = []

    for _, row in census.iterrows():
        sensor_ids = [
            int(s) for s in str(row.get("pm25_sensor_ids", "")).split(",") if str(s).strip().isdigit()
        ]
        if not sensor_ids:
            continue
        sid = str(row[station_key])
        lo = pd.Timestamp(row["datetime_first"])
        hi = pd.Timestamp(row["datetime_last"])

        # A location can expose several PM2.5 sensors (e.g. an instrument swap). Take the
        # one with the most observations rather than blending them: different instruments
        # have different calibration, and averaging across a swap manufactures a series
        # that no device ever measured.
        best: pd.Series | None = None
        best_sensor = None
        for sensor_id in sensor_ids:
            series, _cov = fetch_sensor_series(client, sensor_id, lo, hi)
            if best is None or series.notna().sum() > best.notna().sum():
                best, best_sensor = series, sensor_id

        if best is None or best.empty:
            log.warning("no data for station %s", sid)
            continue

        panel[sid] = best
        rows.append(
            {
                "location_id": sid,
                "city": row.get("city"),
                "country": row.get("country"),
                "provider": row.get("provider"),
                "is_monitor": row.get("is_monitor"),
                "sensor_id_used": best_sensor,
                "n_sensors_available": len(sensor_ids),
                "first_obs": best.index.min(),
                "last_obs": best.index.max(),
                "n_hours_in_span": len(best),
                "n_observed": int(best.notna().sum()),
                "completeness": round(float(best.notna().mean()), 4),
            }
        )

    return panel, pd.DataFrame(rows)
