"""Q6 -- validate timezones against the diurnal cycle rather than against metadata.

Timezone errors are the classic silent bug in multi-source air quality work: nothing
raises, nothing looks wrong, and every temporal feature is quietly shifted. Metadata
offsets are frequently incorrect, and a mislabelled offset is indistinguishable from
correct data unless you check against something physical.

The physical check used here is the **diurnal composite**: mean concentration by
hour-of-day. Urban PM2.5 has a robust local signature -- morning and evening peaks around
traffic and heating, with an afternoon minimum when the boundary layer is deepest. Rather
than hard-coding what time those peaks "should" occur (which varies by city, season and
source mix), each station is compared to a **regional reference composite** by circular
cross-correlation. A station whose best alignment is at a non-zero lag is shifted relative
to its neighbours, which is what a timezone error looks like.

This also catches the case that motivated the check: **Kazakhstan is understood to have
unified onto a single UTC+5 offset in early 2024**, having previously spanned UTC+5 and
UTC+6. For any multi-year Astana record that means the offset changes *mid-series*.
`detect_offset_change` looks for exactly that by compositing period-by-period, so the fault
surfaces as a finding instead of silently degrading every temporal feature.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecopulse_ca.qc.rules import QCFinding

MIN_HOURS_PER_BIN = 5  # minimum observations per hour-of-day bin for a usable composite


def diurnal_composite(s: pd.Series, tz: str | None = None) -> pd.Series:
    """Mean value by local hour-of-day, z-scored. Index 0..23.

    Z-scoring removes level and amplitude, leaving only the *shape* -- which is what the
    alignment check is about. A clean station and a badly-calibrated one with the same
    timing should compare as aligned.
    """
    if s.empty:
        return pd.Series(dtype=float)

    idx = pd.DatetimeIndex(s.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    if tz:
        idx = idx.tz_convert(tz)

    tmp = pd.DataFrame({"value": s.to_numpy()}, index=idx)
    grouped = tmp.groupby(tmp.index.hour)["value"]
    comp = grouped.mean()
    counts = grouped.count()

    comp = comp.reindex(range(24))
    comp[counts.reindex(range(24)).fillna(0) < MIN_HOURS_PER_BIN] = np.nan
    if comp.notna().sum() < 12:  # too gappy to judge
        return pd.Series(np.nan, index=range(24), dtype=float)

    comp = comp.interpolate(limit_direction="both")
    sd = comp.std()
    return (comp - comp.mean()) / sd if sd and np.isfinite(sd) and sd > 0 else comp * 0.0


def reference_composite(composites: dict[str, pd.Series]) -> pd.Series:
    """Regional reference: median across stations, hour by hour.

    Median rather than mean so that a handful of misaligned stations cannot drag the
    reference toward their own error.
    """
    usable = [c for c in composites.values() if c.notna().any()]
    if not usable:
        return pd.Series(np.nan, index=range(24), dtype=float)
    return pd.concat(usable, axis=1).median(axis=1)


def best_lag(composite: pd.Series, reference: pd.Series) -> tuple[int, float]:
    """Circular cross-correlation. Returns (lag_hours, correlation) at best alignment.

    Lag is expressed in [-12, +11]: a lag of +2 means the station's cycle occurs two hours
    later than the reference, i.e. its timestamps are behind by two hours.
    """
    if composite.isna().all() or reference.isna().all():
        return 0, float("nan")

    a = composite.to_numpy(dtype=float)
    b = reference.to_numpy(dtype=float)
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        return 0, float("nan")
    if a.std() == 0 or b.std() == 0:
        return 0, float("nan")

    best = (0, -np.inf)
    for lag in range(24):
        corr = float(np.corrcoef(a, np.roll(b, lag))[0, 1])
        if np.isfinite(corr) and corr > best[1]:
            best = (lag, corr)

    lag = best[0]
    return (lag - 24 if lag > 12 else lag), best[1]


def lag_identifiability(reference: pd.Series, lag: int) -> float:
    """How much the reference resembles *itself* rotated by `lag` hours.

    A high value means the reference cannot distinguish that lag from zero, so a station
    "matching better" at that lag is not evidence of anything.

    This is not hypothetical. Central Asian urban PM2.5 is bimodal -- a morning traffic
    peak and an evening traffic/heating peak roughly 12 hours apart -- so the observed
    regional reference self-correlates at **r = +0.69 under a 12-hour rotation**. Whole-
    shape correlation simply cannot separate a 12-hour offset from no offset here.
    """
    a = reference.to_numpy(dtype=float)
    if not np.isfinite(a).all() or a.std() == 0:
        return 1.0  # treat as maximally ambiguous rather than silently confident
    return float(np.corrcoef(a, np.roll(a, lag))[0, 1])


def peak_alignment(composite: pd.Series, reference: pd.Series) -> tuple[int, int]:
    """Hour offsets of the daily minimum and maximum relative to the reference.

    A physically anchored cross-check on the correlation result. The afternoon minimum
    (deepest boundary layer) and the evening maximum are concrete features; if both sit
    within an hour or two of the reference, a claimed 12-hour shift is not credible
    whatever the correlation says.

    Offsets are returned wrapped into [-12, +11].
    """

    def wrap(x: int) -> int:
        return x - 24 if x > 12 else x

    dmin = wrap(int(composite.to_numpy().argmin()) - int(reference.to_numpy().argmin()))
    dmax = wrap(int(composite.to_numpy().argmax()) - int(reference.to_numpy().argmax()))
    return dmin, dmax


def q6_timezone(
    composite: pd.Series,
    reference: pd.Series,
    station_id: str,
    n_obs: int,
    max_lag: int = 1,
    min_corr: float = 0.5,
    max_ambiguity: float = 0.5,
) -> QCFinding:
    """Flag a station whose diurnal cycle is shifted relative to the region.

    `max_lag=1` tolerates a one-hour difference, which is genuine in a region genuinely
    spanning UTC+5 to UTC+6 and is not worth flagging. Two hours or more is a fault.

    A station is **flagged, never silently corrected.** Auto-rotating timestamps to force
    alignment would destroy the evidence that something is wrong with the source, and would
    quietly manufacture agreement where none exists.
    """
    lag, corr = best_lag(composite, reference)

    if not np.isfinite(corr):
        return QCFinding(
            "Q6",
            "station",
            station_id,
            n_obs,
            0,
            "flag",
            "diurnal composite unusable (too few observations per hour bin)",
        )
    if corr < min_corr:
        return QCFinding(
            "Q6",
            "station",
            station_id,
            n_obs,
            0,
            "flag",
            f"diurnal shape does not match the region (r={corr:.2f} at lag {lag:+d}h); "
            "could be a genuinely different source regime rather than a timezone error "
            "-- inspect before deciding",
        )
    if abs(lag) > max_lag:
        # Before rejecting, ask whether this lag is even identifiable. If the reference
        # resembles itself at this rotation, "matches better at lag L" is an artifact of a
        # near-symmetric signal, not evidence of a shifted clock.
        ambiguity = lag_identifiability(reference, lag)
        dmin, dmax = peak_alignment(composite, reference)

        if ambiguity > max_ambiguity:
            return QCFinding(
                "Q6",
                "station",
                station_id,
                n_obs,
                0,
                "flag",
                f"apparent {lag:+d}h shift (r={corr:.2f}) is NOT IDENTIFIABLE: the regional "
                f"reference self-correlates at r={ambiguity:.2f} under the same rotation, "
                f"because the diurnal cycle is bimodal. Physical features disagree with the "
                f"shift (min offset {dmin:+d}h, max offset {dmax:+d}h). Flagged for "
                f"inspection, NOT rejected -- see data/DECISIONS.md D-006.",
            )

        if abs(dmin) <= max_lag and abs(dmax) <= max_lag:
            return QCFinding(
                "Q6",
                "station",
                station_id,
                n_obs,
                0,
                "flag",
                f"correlation suggests {lag:+d}h but the daily minimum and maximum are "
                f"aligned ({dmin:+d}h / {dmax:+d}h). Contradictory evidence -- flagged, "
                f"not rejected.",
            )

        return QCFinding(
            "Q6",
            "station",
            station_id,
            n_obs,
            n_obs,
            "reject",
            f"diurnal cycle shifted {lag:+d}h vs regional reference (r={corr:.2f}, "
            f"ambiguity={ambiguity:.2f}, min {dmin:+d}h, max {dmax:+d}h) "
            "-- probable timezone error",
        )
    return QCFinding(
        "Q6",
        "station",
        station_id,
        n_obs,
        0,
        "pass",
        f"aligned within {max_lag}h (lag {lag:+d}h, r={corr:.2f})",
    )


def detect_offset_change(
    s: pd.Series,
    reference: pd.Series,
    tz: str | None = None,
    freq: str = "YE",
    max_lag: int = 1,
) -> pd.DataFrame:
    """Look for a timezone offset that changes mid-record.

    Motivated by Kazakhstan's reported 2024 move to a single UTC+5 offset: a station whose
    offset changes partway through has a *correct* overall composite in neither half, and a
    whole-series check can miss it entirely because the two halves partially cancel.

    Returns one row per period with its estimated lag. A change in `lag` between
    consecutive periods is the signal; the caller decides whether to split the series.
    """
    if s.empty:
        return pd.DataFrame(columns=["period", "n", "lag_hours", "corr", "shift_from_previous"])

    idx = pd.DatetimeIndex(s.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    s = pd.Series(s.to_numpy(), index=idx)

    rows = []
    for period, chunk in s.groupby(pd.Grouper(freq=freq)):
        if chunk.notna().sum() < 24 * 14:  # need ~2 weeks to form a stable composite
            continue
        lag, corr = best_lag(diurnal_composite(chunk, tz), reference)
        rows.append(
            {
                "period": period,
                "n": int(chunk.notna().sum()),
                "lag_hours": lag,
                "corr": round(corr, 3) if np.isfinite(corr) else np.nan,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["shift_from_previous"] = out["lag_hours"].diff().fillna(0).astype(int)
    out.attrs["suspected_change"] = bool((out["shift_from_previous"].abs() > max_lag).any())
    return out
