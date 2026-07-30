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

from ecopulse_ca.ingest.base import IngestError
from ecopulse_ca.ingest.openaq import OpenAQClient

log = logging.getLogger(__name__)

#: The ONLY query-parameter names OpenAQ v3 honours for time filtering.
#:
#: This is a named constant rather than an inline string because getting it wrong is
#: silent and catastrophic. OpenAQ returns HTTP 200 and well-formed records for an
#: unrecognised parameter, simply ignoring the filter -- so every request "succeeds" while
#: returning data from the start of the sensor's record. Two complete pipeline runs passed
#: with `date_from`/`date_to` before an arithmetic check (10,000 records inside an
#: 8,760-hour year) exposed it. `tests/test_ingest_openaq.py` pins these names.
DATETIME_FROM = "datetime_from"
DATETIME_TO = "datetime_to"


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
) -> tuple[pd.Series, pd.Series, list[int]]:
    """Hourly series for one sensor, pulled year by year.

    Returns `(values, coverage, partial_years)`.

    Two properties exist because of a bug that destroyed data in proportion to record
    length -- deep pagination is what times out, so the longest and most valuable series
    failed hardest:

    - **A year that fetches incompletely contributes what it retrieved.** It is never
      dropped wholesale, and it is reported in `partial_years` so the gap is recorded
      rather than mistaken for a station that simply had no data.
    - **Pagination is bounded by the expected record count.** An hourly endpoint over H
      hours needs at most ceil(H/limit) pages; requesting one page past the end is what
      produced the 408s. A small margin is allowed for duplicate or overlapping records.
    """
    values, coverage, partial_years = [], [], []

    for year in range(date_from.year, date_to.year + 1):
        lo = max(date_from, pd.Timestamp(f"{year}-01-01", tz="UTC"))
        hi = min(date_to, pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC"))
        if lo > hi:
            continue

        expected_hours = int((hi - lo).total_seconds() // 3600) + 1
        max_pages = max(1, -(-expected_hours // client.page_limit) + 1)  # ceil + margin

        try:
            records = client.paginate(
                f"/sensors/{sensor_id}/hours",
                {
                    # MUST be datetime_from / datetime_to. OpenAQ v3 silently IGNORES
                    # unknown query parameters rather than returning 400, so the wrong
                    # name yields HTTP 200 with well-formed records from the start of the
                    # sensor's history. Verified empirically against the live API:
                    # date_from/date_to and dateFrom/dateTo are both ignored.
                    DATETIME_FROM: lo.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    DATETIME_TO: hi.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                max_pages=max_pages,
            )
        except Exception as exc:  # noqa: BLE001 - one bad year must not lose the others
            log.warning("sensor %s year %s failed outright: %s", sensor_id, year, exc)
            partial_years.append(year)
            continue

        # Arithmetic impossibility check. A window of H hours cannot contain more than H
        # hourly records; materially more means the time filter was not applied and the
        # response is data from elsewhere in the record. This catches an ignored filter
        # from ANY cause -- a renamed parameter, an API change, a typo -- rather than only
        # the specific mistake already made. It raises rather than warns, because the
        # alternative is a plausible-looking series built from the wrong period.
        if len(records) > expected_hours * 1.05 + 1:
            raise IngestError(
                f"sensor {sensor_id} {year}: got {len(records)} records for a window of "
                f"{expected_hours} hours. The time filter was not applied -- check that "
                f"the query parameters are still {DATETIME_FROM}/{DATETIME_TO}. OpenAQ "
                f"silently ignores unrecognised parameters and returns HTTP 200."
            )

        if client.last_pagination_partial:
            partial_years.append(year)

        v, c = records_to_series(records)
        log.info(
            "sensor %s %s: %d records%s",
            sensor_id,
            year,
            len(v),
            " (PARTIAL)" if client.last_pagination_partial else "",
        )
        if not v.empty:
            values.append(v)
            coverage.append(c)

    if not values:
        empty_idx = pd.DatetimeIndex([], tz="UTC")
        return (
            pd.Series(dtype=float, index=empty_idx),
            pd.Series(dtype=float, index=empty_idx),
            partial_years,
        )

    vals = pd.concat(values).sort_index()
    cov = pd.concat(coverage).sort_index()
    vals = vals[~vals.index.duplicated(keep="first")]
    cov = cov[~cov.index.duplicated(keep="first")]
    return reindex_hourly(vals), cov, partial_years


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
            int(s)
            for s in str(row.get("pm25_sensor_ids", "")).split(",")
            if str(s).strip().isdigit()
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
        best_partial: list[int] = []
        for sensor_id in sensor_ids:
            series, _cov, partial = fetch_sensor_series(client, sensor_id, lo, hi)
            if best is None or series.notna().sum() > best.notna().sum():
                best, best_sensor, best_partial = series, sensor_id, partial

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
                # Years whose fetch was incomplete. A completeness figure for a station
                # with partial years understates the station, not the sensor -- the
                # distinction must survive into the manifest.
                "partial_fetch_years": ",".join(str(y) for y in best_partial),
                "fetch_complete": not best_partial,
            }
        )

    return panel, pd.DataFrame(rows)
