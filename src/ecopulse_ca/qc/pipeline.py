"""End-to-end QC: run every pre-registered rule over a station panel, emit the n-effects.

This is the module that makes rule 9 of the project spec operable -- "never delete or
silently impute data to make results better; every filtering decision goes in
data/DECISIONS.md with a reason and its effect on n".

Order matters and is not arbitrary:

1. **Station-level rejections first** (Q4 unit sanity, Q7 completeness, Q5 duplicates).
   A series in the wrong unit has no trustworthy subset, so masking individual rows in it
   would be wasted work and would report a misleading n-effect.
2. **Then the regional reference composite**, built only from surviving stations -- so a
   station already known to be broken cannot drag the reference it is judged against.
3. **Then Q6 timezone**, which is inherently comparative.
4. **Then row-level masks** (Q1, Q2, Q3) on what remains.

The pipeline never writes to DECISIONS.md itself. It returns the markdown; a human decides
what to record. Automating that would let a filtering decision enter the record without
anyone having read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ecopulse_ca.qc.rules import (
    FlatlinePolicy,
    QCFinding,
    QCReport,
    q1_physical_range,
    q2_flatline,
    q3_zero_run,
    q4_unit_sanity,
    q5_duplicate_stations,
    q7_completeness,
)
from ecopulse_ca.qc.timezone import diurnal_composite, q6_timezone, reference_composite


@dataclass
class QCOutcome:
    report: QCReport
    kept: dict[str, pd.Series] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)

    @property
    def n_effect(self) -> dict[str, int]:
        """Observation counts before and after QC -- the headline number for DECISIONS.md."""
        before = sum(f.n_total for f in self.report.findings if f.rule == "Q1")
        after = sum(int(s.notna().sum()) for s in self.kept.values())
        return {
            "stations_in": len(self.kept) + len(self.rejected),
            "stations_kept": len(self.kept),
            "stations_rejected": len(self.rejected),
            "observations_before": before,
            "observations_after": after,
        }

    def summary(self) -> str:
        n = self.n_effect
        pct = (
            100.0 * (n["observations_before"] - n["observations_after"]) / n["observations_before"]
            if n["observations_before"]
            else 0.0
        )
        return (
            f"stations {n['stations_in']} -> {n['stations_kept']} "
            f"({n['stations_rejected']} rejected); "
            f"observations {n['observations_before']} -> {n['observations_after']} "
            f"({pct:.2f}% removed)"
        )


def apply_flatline_policy(
    series: pd.Series,
    flatline_mask: pd.Series,
    station_id: str,
    policy: FlatlinePolicy,
) -> tuple[pd.Series, str | None]:
    """Decide what a detected flatline does to a station.

    Returns `(series, rejection_reason)`. A non-None reason drops the station entirely.

    Only MASK_WINDOW is implemented. The other two branches are deliberately left open
    because the choice is a scientific judgement, not a default:

    - REJECT_STATION: drop the series once flatlining exceeds some share of the record.
      Cleanest data, but it preferentially removes low-cost sensors -- and in this region
      that means removing whole cities, which tightens F3 (see research/GAP.md section 3).
      Needs a threshold: what share of a record being stuck makes the station untrustworthy?
    - KEEP_AND_FLAG: retain every value and expose the mask as a feature. Most information
      retained, but a downstream model can learn the artefact rather than the signal.

    See FlatlinePolicy in qc/rules.py for the full trade-off.
    """
    if policy is FlatlinePolicy.MASK_WINDOW:
        return series.mask(flatline_mask), None

    raise NotImplementedError(
        f"FlatlinePolicy.{policy.name} is not implemented. This is an open scientific "
        "decision, not an oversight -- see the docstring above before choosing."
    )


def run_qc(
    panel: dict[str, pd.Series],
    census: pd.DataFrame | None = None,
    *,
    timezones: dict[str, str] | None = None,
    flatline_policy: FlatlinePolicy = FlatlinePolicy.MASK_WINDOW,
) -> QCOutcome:
    """Run the full pre-registered QC suite over a panel of station series.

    `panel` maps station_id -> hourly PM2.5 series indexed by UTC timestamp.
    """
    report = QCReport()
    timezones = timezones or {}

    # -- stage 1: station-level rejection ----------------------------------------------
    if census is not None and not census.empty:
        report.add(q5_duplicate_stations(census))

    surviving: dict[str, pd.Series] = {}
    rejected: dict[str, str] = {}

    for sid, series in panel.items():
        station_findings: list[QCFinding] = [
            q4_unit_sanity(series, sid),
            q7_completeness(series, sid),
        ]
        report.add(*station_findings)
        fatal = next((f for f in station_findings if f.verdict == "reject"), None)
        if fatal is not None:
            rejected[sid] = f"{fatal.rule}: {fatal.detail}"
        else:
            surviving[sid] = series

    # Stations rejected by Q5a (one id at several coordinates) are dropped here too.
    for sid in list(surviving):
        if sid in report.rejected_stations and sid not in rejected:
            rejected[sid] = "Q5a: one location_id at multiple coordinates"
            surviving.pop(sid)

    # -- stage 2+3: reference composite from survivors, then timezone ------------------
    if len(surviving) >= 2:
        composites = {
            sid: diurnal_composite(s, timezones.get(sid)) for sid, s in surviving.items()
        }
        reference = reference_composite(composites)
        for sid, comp in composites.items():
            finding = q6_timezone(comp, reference, sid, int(surviving[sid].notna().sum()))
            report.add(finding)
            if finding.verdict == "reject":
                rejected[sid] = f"Q6: {finding.detail}"
        for sid in list(surviving):
            if sid in rejected:
                surviving.pop(sid)

    # -- stage 4: row-level masking ----------------------------------------------------
    kept: dict[str, pd.Series] = {}
    for sid, series in surviving.items():
        report.add(
            q1_physical_range(series, sid),
            q2_flatline(series, sid),
            q3_zero_run(series, sid),
        )
        masked, reason = apply_flatline_policy(
            series, report.row_mask(sid, series.index), sid, flatline_policy
        )
        if reason is not None:
            rejected[sid] = reason
        else:
            kept[sid] = masked

    return QCOutcome(report=report, kept=kept, rejected=rejected)


def decisions_block(outcome: QCOutcome, title: str) -> str:
    """Render a DECISIONS.md-ready entry. Paste it; do not auto-append it."""
    n = outcome.n_effect
    return "\n".join(
        [
            f"### {title}",
            f"- **Date:** {pd.Timestamp.utcnow():%Y-%m-%d}",
            "- **Decision:** applied pre-registered QC rules Q1-Q7",
            "- **Reason:** rules declared in data/DECISIONS.md before data inspection",
            f"- **Effect on n:** stations {n['stations_in']} -> {n['stations_kept']}, "
            f"observations {n['observations_before']} -> {n['observations_after']}",
            "- **Alternative considered:** see FlatlinePolicy in qc/rules.py",
            "- **Direction of bias if wrong:** rejecting whole stations preferentially "
            "removes low-cost sensors, and in this region that means removing whole "
            "cities -- which tightens F3.",
            "",
            outcome.report.to_markdown(),
        ]
    )
