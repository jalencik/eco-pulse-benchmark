"""Merge co-located feeds that Q5b identified as one physical instrument.

Why this is not a simple average
--------------------------------
The US Embassy monitors are published twice, under StateAir and under AirNow, as separate
`location_id`s a few tens of metres apart. They are **one instrument**, so averaging the
two feeds would not reduce noise -- there is only one measurement -- and where the feeds
disagree it would fabricate a third value that no device ever produced.

So the merge is strictly **precedence + gap-fill**: every retained hour comes from exactly
one publisher, and which publisher is recorded per hour.

The disagreement is real and time-structured
--------------------------------------------
Measured on the live panel (2026-07-29), share of overlapping hours agreeing to 0.1 ug/m3:

    year   Bishkek   Ashgabat
    2019    100.0%     100.0%
    2020    100.0%     100.0%
    2021     28.4%     100.0%
    2022     50.1%     100.0%
    2023     61.2%      93.8%
    2024     11.1%     100.0%
    2025      6.2%     100.0%

Ashgabat is a clean duplicate throughout. **Bishkek is identical only through 2020 and then
diverges**, with 2024 the worst year (p95 disagreement 33.6 ug/m3, max 479). Since 2024 is
the benchmark's temporal test block, Bishkek's test labels depend on the publisher chosen.
`merge_report` surfaces that so it can never be discovered late, and the per-hour `source`
series lets the error analysis split Bishkek results by publisher.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Two feeds agreeing to within this (ug/m3) are treated as reporting the same value.
EXACT_TOL = 0.1


@dataclass
class MergeReport:
    """Everything a reader needs to judge whether a merge was legitimate."""

    merged_id: str
    primary_id: str
    secondary_id: str
    n_primary: int
    n_secondary: int
    n_overlap: int
    n_filled_from_secondary: int
    n_merged: int
    pct_exact: float
    median_abs_diff: float
    p95_abs_diff: float
    max_abs_diff: float
    per_year_pct_exact: dict[int, float]

    @property
    def is_clean_duplicate(self) -> bool:
        """True when the feeds are effectively identical wherever both report."""
        return self.pct_exact >= 95.0

    def to_markdown(self) -> str:
        verdict = "clean duplicate" if self.is_clean_duplicate else "**DIVERGENT — see below**"
        lines = [
            f"**{self.merged_id}** — primary `{self.primary_id}`, secondary `{self.secondary_id}`",
            "",
            f"- overlap: {self.n_overlap:,} h; agreement to {EXACT_TOL} ug/m3: "
            f"**{self.pct_exact:.1f}%** ({verdict})",
            f"- median |diff| {self.median_abs_diff:.2f}, p95 {self.p95_abs_diff:.2f}, "
            f"max {self.max_abs_diff:.0f} ug/m3",
            f"- observations: primary {self.n_primary:,} + {self.n_filled_from_secondary:,} "
            f"gap-filled = **{self.n_merged:,}**",
            "- agreement by year: "
            + ", ".join(f"{y} {p:.0f}%" for y, p in sorted(self.per_year_pct_exact.items())),
        ]
        return "\n".join(lines)


def merge_colocated(
    primary: pd.Series,
    secondary: pd.Series,
    *,
    merged_id: str,
    primary_id: str,
    secondary_id: str,
) -> tuple[pd.Series, pd.Series, MergeReport]:
    """Combine two feeds of one instrument.

    Returns `(values, source, report)` where `source` records, per hour, which
    `location_id` supplied the value -- so a later analysis can split results by publisher
    rather than having to trust that the merge was neutral.

    Precedence is `primary` wherever it reports; `secondary` fills only the gaps. No hour
    is ever an average of the two.
    """
    idx = primary.index.union(secondary.index)
    p = primary.reindex(idx)
    s = secondary.reindex(idx)

    both = pd.concat([p, s], axis=1).dropna()
    if both.empty:
        diff = pd.Series(dtype=float)
    else:
        diff = (both.iloc[:, 0] - both.iloc[:, 1]).abs()

    values = p.where(p.notna(), s)
    source = pd.Series(np.where(p.notna(), primary_id, np.where(s.notna(), secondary_id, "")),
                       index=idx)
    source[values.isna()] = ""

    per_year: dict[int, float] = {}
    if not both.empty:
        years = pd.DatetimeIndex(both.index).year
        for y in sorted(set(years)):
            d = diff[years == y]
            per_year[int(y)] = float(100.0 * (d < EXACT_TOL).mean())

    report = MergeReport(
        merged_id=merged_id,
        primary_id=primary_id,
        secondary_id=secondary_id,
        n_primary=int(primary.notna().sum()),
        n_secondary=int(secondary.notna().sum()),
        n_overlap=len(both),
        n_filled_from_secondary=int((p.isna() & s.notna()).sum()),
        n_merged=int(values.notna().sum()),
        pct_exact=float(100.0 * (diff < EXACT_TOL).mean()) if len(diff) else 100.0,
        median_abs_diff=float(diff.median()) if len(diff) else 0.0,
        p95_abs_diff=float(diff.quantile(0.95)) if len(diff) else 0.0,
        max_abs_diff=float(diff.max()) if len(diff) else 0.0,
        per_year_pct_exact=per_year,
    )
    return values, source, report


def choose_primary(a: pd.Series, b: pd.Series, a_id: str, b_id: str) -> tuple[str, str]:
    """Primary is the feed with more observations; ties break on the lexically smaller id.

    A data-driven rule rather than a preference for one publisher, so it is reproducible
    from the manifest and does not encode an unstated belief about which programme is more
    trustworthy. Where the feeds are identical the choice is immaterial; where they are
    not -- Bishkek -- the choice is recorded and its consequences reported.
    """
    na, nb = int(a.notna().sum()), int(b.notna().sum())
    if na > nb or (na == nb and a_id <= b_id):
        return a_id, b_id
    return b_id, a_id
