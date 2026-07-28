"""Pre-registered QC rules Q1-Q7, as declared in data/DECISIONS.md before seeing data.

Every rule returns a `QCFinding` carrying **n_total and n_flagged**. That is not
bookkeeping: the master spec forbids dropping data without recording the effect on n, and
a rule that cannot report its own n-effect cannot satisfy that. `QCReport.to_markdown()`
emits the block that goes straight into data/DECISIONS.md.

Rules are split into two kinds, and the distinction matters:

- **Row-level** (Q1, Q2, Q3) mask individual observations.
- **Station-level** (Q4, Q5, Q7) accept or reject a whole series.

Masking and rejecting have different bias directions, so they are never conflated. See
`FlatlinePolicy` for the one place where that choice is genuinely open.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import numpy as np
import pandas as pd

Verdict = Literal["pass", "flag", "reject"]

# Q1 physical plausibility bounds, ug/m3.
PM25_MIN, PM25_MAX = 0.0, 1000.0
# Q4 station-median sanity bounds, ug/m3. Catches mg/m3 reported as ug/m3 (x1000) and AQI
# values reported as concentrations.
MEDIAN_MIN, MEDIAN_MAX = 1.0, 500.0
# Q2 / Q3 run lengths, in hourly samples.
FLATLINE_RUN = 24
ZERO_RUN = 6
# Q7 inclusion thresholds.
MIN_YEARS, MIN_COMPLETENESS = 2.0, 0.60


class FlatlinePolicy(Enum):
    """What to do with a detected flatline.

    The three options push results in different directions, which is why this is explicit
    rather than buried:

    - MASK_WINDOW  -- drop only the stuck run. Keeps the station. Risk: a sensor that
      sticks repeatedly stays in the benchmark with its good periods intact, so the
      station's *apparent* reliability is inflated.
    - REJECT_STATION -- drop the whole series once flatlining exceeds a share of the
      record. Safest for data quality, but preferentially removes cheap sensors, which in
      Central Asia means preferentially removing whole cities -- and F3 is already tight.
    - KEEP_AND_FLAG -- retain everything, expose the mask as a feature. Maximum
      information, maximum risk that a downstream model learns the artefact.

    Default is MASK_WINDOW: it is the least destructive option that still removes values
    known to be wrong, and given how few stations the region has, discarding a station
    outright needs stronger evidence than one stuck run.
    """

    MASK_WINDOW = "mask_window"
    REJECT_STATION = "reject_station"
    KEEP_AND_FLAG = "keep_and_flag"


@dataclass
class QCFinding:
    rule: str
    scope: Literal["row", "station"]
    station_id: str
    n_total: int
    n_flagged: int
    verdict: Verdict
    detail: str = ""
    mask: pd.Series | None = field(default=None, repr=False)

    @property
    def pct_flagged(self) -> float:
        return 100.0 * self.n_flagged / self.n_total if self.n_total else 0.0


def _runs(flags: pd.Series) -> pd.Series:
    """Label maximal runs of equal values, so run lengths can be measured."""
    return (flags != flags.shift()).cumsum()


def q1_physical_range(s: pd.Series, station_id: str) -> QCFinding:
    """Negative mass is impossible; >1000 ug/m3 is near-universally a sensor fault."""
    bad = (s < PM25_MIN) | (s > PM25_MAX)
    bad = bad.fillna(False)
    return QCFinding(
        rule="Q1",
        scope="row",
        station_id=station_id,
        n_total=len(s),
        n_flagged=int(bad.sum()),
        verdict="flag" if bad.any() else "pass",
        detail=f"outside [{PM25_MIN}, {PM25_MAX}] ug/m3",
        mask=bad,
    )


def q2_flatline(s: pd.Series, station_id: str, run_length: int = FLATLINE_RUN) -> QCFinding:
    """>= `run_length` consecutive identical non-zero values.

    A real ambient signal is never bit-identical for a full day. Zeros are excluded here
    and handled by Q3, because a reported zero usually means "no data" rather than "stuck".
    """
    nonzero = s.notna() & (s != 0)
    grp = _runs(s.where(nonzero))
    sizes = s.groupby(grp).transform("size")
    stuck = (sizes >= run_length) & nonzero
    stuck = stuck.fillna(False)
    return QCFinding(
        rule="Q2",
        scope="row",
        station_id=station_id,
        n_total=len(s),
        n_flagged=int(stuck.sum()),
        verdict="flag" if stuck.any() else "pass",
        detail=f">={run_length} consecutive identical non-zero values",
        mask=stuck,
    )


def q3_zero_run(s: pd.Series, station_id: str, run_length: int = ZERO_RUN) -> QCFinding:
    """>= `run_length` consecutive exact zeros -- almost always missing-data-as-zero."""
    is_zero = (s == 0).fillna(False)
    grp = _runs(is_zero)
    sizes = is_zero.groupby(grp).transform("size")
    bad = is_zero & (sizes >= run_length)
    return QCFinding(
        rule="Q3",
        scope="row",
        station_id=station_id,
        n_total=len(s),
        n_flagged=int(bad.sum()),
        verdict="flag" if bad.any() else "pass",
        detail=f">={run_length} consecutive exact zeros",
        mask=bad,
    )


def q4_unit_sanity(s: pd.Series, station_id: str) -> QCFinding:
    """Reject a series whose median implies the wrong unit.

    A median below 1 suggests mg/m3 mislabelled as ug/m3; above 500 suggests an AQI value
    reported as a concentration. Both are whole-series faults, so the verdict is rejection
    rather than masking -- there is no subset of the series that is trustworthy.
    """
    med = float(s.median()) if s.notna().any() else float("nan")
    bad = not np.isfinite(med) or med < MEDIAN_MIN or med > MEDIAN_MAX
    return QCFinding(
        rule="Q4",
        scope="station",
        station_id=station_id,
        n_total=len(s),
        n_flagged=len(s) if bad else 0,
        verdict="reject" if bad else "pass",
        detail=f"median={med:.2f} ug/m3, expected [{MEDIAN_MIN}, {MEDIAN_MAX}]",
    )


#: Two feeds closer than this are treated as the same physical instrument.
#: Set from observed data, not guessed: in the live Central Asia census the StateAir and
#: AirNow feeds of the US Embassy monitors sit 57 m apart (Bishkek) and 40 m apart
#: (Ashgabat) -- the same device published by two programmes. Exact-coordinate matching
#: misses both. Meanwhile the two genuinely distinct Dushanbe sites are 6.06 km apart, so
#: there is a wide margin between "same instrument" and "different site".
COLOCATION_METRES = 150.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def q5_duplicate_stations(
    census: pd.DataFrame, colocation_m: float = COLOCATION_METRES
) -> list[QCFinding]:
    """Detect ID/coordinate inconsistencies that silently corrupt spatial splits.

    Two distinct failures, both present in the live OpenAQ data for this region:

    (a) one ``location_id`` at more than one coordinate -- a moved or re-used station;
    (b) several ``location_id``s at effectively the same place -- co-located duplicates
        that leak between train and test under leave-station-out.

    Case (b) is distance-based, not exact-match. The failure this exists to catch is the
    US Embassy instruments republished under both StateAir and AirNow: two ``location_id``s,
    two providers, coordinates differing in the fourth decimal place, one physical device.
    Holding one out while training on the other is not a spatial split at all.
    """
    out: list[QCFinding] = []
    if census.empty or not {"latitude", "longitude"}.issubset(census.columns):
        return out

    for loc_id, grp in census.groupby("location_id"):
        pts = grp[["latitude", "longitude"]].dropna().drop_duplicates()
        if len(pts) > 1:
            spread = max(
                haversine_m(*pts.iloc[i], *pts.iloc[j])
                for i in range(len(pts))
                for j in range(i + 1, len(pts))
            )
            if spread > colocation_m:
                out.append(
                    QCFinding(
                        rule="Q5a", scope="station", station_id=str(loc_id),
                        n_total=len(grp), n_flagged=len(grp), verdict="reject",
                        detail=f"one location_id spans {spread:.0f} m across "
                               f"{len(pts)} coordinates",
                    )
                )

    # Single-link clustering over the colocation radius: A~B and B~C puts all three in one
    # cluster, which is what "same site" means physically.
    pts = census.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    parent = list(range(len(pts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    lats = pts["latitude"].to_numpy(dtype=float)
    lons = pts["longitude"].to_numpy(dtype=float)
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if haversine_m(lats[i], lons[i], lats[j], lons[j]) <= colocation_m:
                parent[find(i)] = find(j)

    for _, idxs in pd.Series(range(len(pts))).groupby([find(i) for i in range(len(pts))]):
        grp = pts.loc[list(idxs)]
        ids = sorted({str(i) for i in grp["location_id"]})
        if len(ids) > 1:
            providers = sorted({str(p) for p in grp.get("provider", pd.Series(dtype=str))})
            out.append(
                QCFinding(
                    rule="Q5b", scope="station", station_id=",".join(ids),
                    n_total=len(grp), n_flagged=len(grp), verdict="flag",
                    detail=f"{len(ids)} location_ids within {colocation_m:.0f} m "
                           f"-- probably one instrument"
                           + (f", providers: {', '.join(providers)}" if providers else ""),
                )
            )
    return out


def q7_completeness(
    s: pd.Series,
    station_id: str,
    min_years: float = MIN_YEARS,
    min_completeness: float = MIN_COMPLETENESS,
) -> QCFinding:
    """Require >= `min_years` of record at >= `min_completeness` hourly coverage.

    Needed so a blocked-temporal split with a purge gap has enough on both sides of every
    boundary. Completeness is measured against the *expected* hourly count over the span,
    not against the number of rows present -- otherwise a series with huge gaps scores 100%.
    """
    if s.empty or s.notna().sum() == 0:
        return QCFinding("Q7", "station", station_id, len(s), len(s), "reject", "empty series")

    idx = pd.DatetimeIndex(s.index)
    span_hours = (idx.max() - idx.min()).total_seconds() / 3600 + 1
    years = span_hours / (365.25 * 24)
    completeness = float(s.notna().sum()) / span_hours if span_hours > 0 else 0.0
    ok = years >= min_years and completeness >= min_completeness
    return QCFinding(
        rule="Q7",
        scope="station",
        station_id=station_id,
        n_total=len(s),
        n_flagged=0 if ok else len(s),
        verdict="pass" if ok else "reject",
        detail=f"span={years:.2f}y (need {min_years}), completeness={completeness:.1%} "
        f"(need {min_completeness:.0%})",
    )


@dataclass
class QCReport:
    findings: list[QCFinding] = field(default_factory=list)

    def add(self, *f: QCFinding | list[QCFinding]) -> QCReport:
        for item in f:
            self.findings.extend(item if isinstance(item, list) else [item])
        return self

    @property
    def rejected_stations(self) -> set[str]:
        return {f.station_id for f in self.findings if f.verdict == "reject"}

    def row_mask(self, station_id: str, index: pd.Index) -> pd.Series:
        """Union of all row-level masks for a station: True == drop this observation."""
        mask = pd.Series(False, index=index)
        for f in self.findings:
            if f.scope == "row" and f.station_id == station_id and f.mask is not None:
                mask |= f.mask.reindex(index, fill_value=False)
        return mask

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "rule": f.rule,
                    "scope": f.scope,
                    "station_id": f.station_id,
                    "verdict": f.verdict,
                    "n_total": f.n_total,
                    "n_flagged": f.n_flagged,
                    "pct_flagged": round(f.pct_flagged, 3),
                    "detail": f.detail,
                }
                for f in self.findings
            ]
        )

    def to_markdown(self) -> str:
        """Emit a DECISIONS.md-ready block. Every line carries its n-effect."""
        df = self.to_frame()
        if df.empty:
            return "_No QC findings._"
        lines = [
            "| rule | scope | station | verdict | n_total | n_flagged | % | detail |",
            "|---|---|---|---|---:|---:|---:|---|",
        ]
        for _, r in df.iterrows():
            lines.append(
                f"| {r['rule']} | {r['scope']} | `{r['station_id']}` | **{r['verdict']}** | "
                f"{r['n_total']} | {r['n_flagged']} | {r['pct_flagged']:.2f} | {r['detail']} |"
            )
        n_rej = len(self.rejected_stations)
        lines.append("")
        lines.append(f"**Stations rejected: {n_rej}** -- {sorted(self.rejected_stations)}")
        return "\n".join(lines)
