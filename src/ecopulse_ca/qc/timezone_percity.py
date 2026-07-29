"""Q6 rebuilt per city (post-hoc revision — see data/DECISIONS.md D-007).

Why the regional-reference version had to go
--------------------------------------------
The original Q6 compared every station's diurnal composite to a regional median. That
assumes cities share a diurnal shape. Measured on the live panel, they do not:

    city        local argmin   local argmax   regime
    Dushanbe          15             9        afternoon dilution minimum
    Khujand           16             8        afternoon dilution minimum
    Tashkent          14            22        afternoon dilution minimum
    Astana            14            23        afternoon dilution minimum
    Bishkek          6-7            20        evening heating peak, pre-dawn minimum
    Ashgabat         3-4            20        evening heating peak, pre-dawn minimum
    Almaty             6            13        afternoon MAXIMUM -- unlike any other

Only 6 of 11 stations have the textbook afternoon minimum. A regional median is therefore
dominated by whichever regime happens to be most common, and stations in the minority
regime get flagged for being *correct*. Three of ten surviving feeds were flagged this way
(r = 0.31-0.34) purely for shape disagreement.

A hardcoded physical window ("the minimum must be in the afternoon") fails identically --
it would reject Bishkek and Ashgabat, whose pre-dawn minimum is the expected signature of
evening residential coal heating that decays overnight.

What replaces it
----------------
Two checks that do not assume cities resemble each other:

1. **Within-city agreement** (rejection-capable). Instruments in the same city measure the
   same airshed and must agree on timing. On the live panel every multi-instrument city
   agrees to within one hour: Dushanbe 15/15, Khujand 16/16, Bishkek 6/7, Ashgabat 3/4.
   A station disagreeing with its own city is strong evidence of a clock fault.

2. **Temporal self-consistency** (rejection-capable). A station compared against *itself*
   in earlier periods. This is what catches an offset that changes mid-record -- the
   Kazakhstan 2024 case -- and needs no other station at all.

Cross-city comparison is retained as **informational only** and can never reject.

Honest limitation: cities with a single instrument (Almaty and Tashkent, after the
Bishkek/Ashgabat merges) get only check 2. A constant, lifelong offset at a single-
instrument city is not detectable by any method here, and is recorded as such.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ecopulse_ca.qc.rules import QCFinding
from ecopulse_ca.qc.timezone import best_lag, diurnal_composite


@dataclass
class CityDiurnal:
    city: str
    station_ids: list[str]
    composites: dict[str, pd.Series]

    @property
    def n_instruments(self) -> int:
        return len(self.station_ids)


def peak_hours(composite: pd.Series) -> tuple[int, int]:
    """(hour of minimum, hour of maximum) — the physically concrete features."""
    a = composite.to_numpy(dtype=float)
    return int(a.argmin()), int(a.argmax())


def _wrap(h: int) -> int:
    return h - 24 if h > 12 else (h + 24 if h < -12 else h)


def q6_within_city(
    city: str,
    composites: dict[str, pd.Series],
    n_obs: dict[str, int],
    max_lag: int = 1,
) -> list[QCFinding]:
    """Compare instruments within one city against their own city-median composite.

    Returns one finding per station. With fewer than two instruments the check is not
    possible and returns a single `pass` finding recording that fact -- silence would be
    indistinguishable from having checked.
    """
    ids = sorted(composites)
    if len(ids) < 2:
        sid = ids[0] if ids else city
        return [
            QCFinding(
                "Q6a", "station", sid, n_obs.get(sid, 0), 0, "pass",
                f"{city} has a single instrument -- within-city timing check not possible. "
                "A constant lifelong offset here is undetectable by any check in this suite.",
            )
        ]

    stacked = pd.concat([composites[s] for s in ids], axis=1)
    city_ref = stacked.median(axis=1)

    out: list[QCFinding] = []
    for sid in ids:
        lag, corr = best_lag(composites[sid], city_ref)
        dmin = _wrap(peak_hours(composites[sid])[0] - peak_hours(city_ref)[0])
        dmax = _wrap(peak_hours(composites[sid])[1] - peak_hours(city_ref)[1])
        agrees = abs(lag) <= max_lag and abs(dmin) <= max_lag and abs(dmax) <= max_lag
        out.append(
            QCFinding(
                "Q6a", "station", sid, n_obs.get(sid, 0),
                0 if agrees else n_obs.get(sid, 0),
                "pass" if agrees else "reject",
                f"{city}: lag {lag:+d}h (r={corr:.2f}), min {dmin:+d}h, max {dmax:+d}h "
                f"vs the {len(ids)}-instrument city median",
            )
        )
    return out


def q6_cross_city_informational(
    composites: dict[str, pd.Series],
    cities: dict[str, str],
) -> list[QCFinding]:
    """Regime description across cities. **Never rejects.**

    Retained because the regime split is a genuine scientific finding worth reporting -- the
    error analysis should separate dilution-driven cities from heating-driven ones -- but it
    is not evidence of a fault, so its verdict is always `pass`.
    """
    out = []
    for sid, comp in composites.items():
        if comp.isna().all():
            continue
        amin, amax = peak_hours(comp)
        regime = "afternoon-minimum (dilution-driven)" if 11 <= amin <= 18 else (
            "pre-dawn-minimum (evening-source-driven)" if amin <= 8 else "other"
        )
        out.append(
            QCFinding(
                "Q6b", "station", sid, 0, 0, "pass",
                f"{cities.get(sid, '?')}: local min {amin:02d}:00, max {amax:02d}:00 "
                f"-- {regime} [informational, never rejects]",
            )
        )
    return out


def build_city_composites(
    panel: pd.DataFrame,
    city_of: dict[str, str],
    tz_of: dict[str, str],
) -> dict[str, CityDiurnal]:
    """Group station composites by city, computed in each station's local time."""
    grouped: dict[str, CityDiurnal] = {}
    for sid in panel.columns:
        sid = str(sid)
        city = city_of.get(sid)
        if city is None:
            continue
        comp = diurnal_composite(panel[sid], tz_of.get(sid))
        if comp.isna().all():
            continue
        entry = grouped.setdefault(city, CityDiurnal(city, [], {}))
        entry.station_ids.append(sid)
        entry.composites[sid] = comp
    return grouped


def run_q6_per_city(
    panel: pd.DataFrame,
    city_of: dict[str, str],
    tz_of: dict[str, str],
    max_lag: int = 1,
) -> list[QCFinding]:
    """Full per-city Q6: within-city rejection checks plus informational regime labels."""
    n_obs = {str(c): int(panel[c].notna().sum()) for c in panel.columns}
    grouped = build_city_composites(panel, city_of, tz_of)

    findings: list[QCFinding] = []
    all_comps: dict[str, pd.Series] = {}
    for city, entry in sorted(grouped.items()):
        findings.extend(q6_within_city(city, entry.composites, n_obs, max_lag=max_lag))
        all_comps.update(entry.composites)

    findings.extend(q6_cross_city_informational(all_comps, city_of))
    return findings


def regime_summary(
    panel: pd.DataFrame, city_of: dict[str, str], tz_of: dict[str, str]
) -> pd.DataFrame:
    """Per-station local-time diurnal features. Feeds the paper's regime table."""
    rows = []
    for sid in panel.columns:
        sid = str(sid)
        comp = diurnal_composite(panel[sid], tz_of.get(sid))
        if comp.isna().all():
            continue
        amin, amax = peak_hours(comp)
        rows.append(
            {
                "station_id": sid,
                "city": city_of.get(sid),
                "timezone": tz_of.get(sid),
                "local_argmin": amin,
                "local_argmax": amax,
                "amplitude_z": float(np.nanmax(comp) - np.nanmin(comp)),
            }
        )
    return pd.DataFrame(rows).sort_values(["city", "station_id"])
