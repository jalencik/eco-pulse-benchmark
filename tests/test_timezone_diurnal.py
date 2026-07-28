"""Q6 -- timezone validated against diurnal shape, not metadata.

Includes the Kazakhstan case (risk R3): an offset that changes partway through a record.
A whole-series check can miss that entirely, because the two halves partially cancel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecopulse_ca.qc.timezone import (
    best_lag,
    detect_offset_change,
    diurnal_composite,
    q6_timezone,
    reference_composite,
)
from tests.conftest import synthetic_pm25


def _reference(n: int = 4) -> pd.Series:
    return reference_composite(
        {f"s{i}": diurnal_composite(synthetic_pm25(seed=i, base=40 + 3 * i)) for i in range(n)}
    )


class TestDiurnalComposite:
    def test_is_zscored_and_24_long(self, clean_series):
        comp = diurnal_composite(clean_series)
        assert len(comp) == 24
        assert abs(float(comp.mean())) < 1e-9
        assert abs(float(comp.std(ddof=0)) - 1.0) < 0.05

    def test_recovers_the_expected_bimodal_shape(self, clean_series):
        comp = diurnal_composite(clean_series)
        # Evening peak (hour 20) should exceed the afternoon trough (hour ~14).
        assert comp[20] > comp[14]

    def test_too_sparse_returns_all_nan(self):
        idx = pd.date_range("2021-01-01", periods=20, freq="h", tz="UTC")
        assert diurnal_composite(pd.Series(np.arange(20.0), index=idx)).isna().all()


class TestBestLag:
    def test_aligned_series_has_zero_lag(self):
        ref = _reference()
        lag, corr = best_lag(diurnal_composite(synthetic_pm25(seed=99)), ref)
        assert lag == 0
        assert corr > 0.9

    def test_recovers_a_known_shift(self):
        ref = _reference()
        for shift in (1, 2, 3, 5):
            comp = diurnal_composite(synthetic_pm25(seed=99, shift_hours=shift))
            lag, corr = best_lag(comp, ref)
            assert lag == shift, f"expected lag {shift}, got {lag}"
            assert corr > 0.9

    def test_lag_is_signed_within_plus_minus_12(self):
        ref = _reference()
        comp = diurnal_composite(synthetic_pm25(seed=99, shift_hours=23))
        lag, _ = best_lag(comp, ref)
        assert lag == -1  # 23h forward == 1h back


class TestQ6:
    def test_aligned_station_passes(self):
        ref = _reference()
        s = synthetic_pm25(seed=99)
        assert q6_timezone(diurnal_composite(s), ref, "s1", len(s)).verdict == "pass"

    def test_one_hour_tolerated(self):
        # The region genuinely spans UTC+5 to UTC+6; 1h is not evidence of a fault.
        ref = _reference()
        s = synthetic_pm25(seed=99, shift_hours=1)
        assert q6_timezone(diurnal_composite(s), ref, "s1", len(s)).verdict == "pass"

    def test_three_hour_shift_rejected(self):
        ref = _reference()
        s = synthetic_pm25(seed=99, shift_hours=3)
        f = q6_timezone(diurnal_composite(s), ref, "s1", len(s))
        assert f.verdict == "reject"
        assert "+3h" in f.detail

    def test_station_is_flagged_never_silently_corrected(self):
        # Auto-rotating timestamps would manufacture agreement and destroy the evidence
        # that the source is wrong. The finding must surface.
        ref = _reference()
        s = synthetic_pm25(seed=99, shift_hours=4)
        f = q6_timezone(diurnal_composite(s), ref, "s1", len(s))
        assert f.verdict in {"reject", "flag"}
        assert f.n_flagged > 0


class TestOffsetChangeDetection:
    def test_detects_mid_record_offset_change(self):
        """The Kazakhstan case: UTC+6 until early 2024, UTC+5 after."""
        before = synthetic_pm25("2022-01-01", "2023-12-31", seed=5, shift_hours=0)
        after = synthetic_pm25("2024-01-01", "2025-12-31", seed=5, shift_hours=2)
        series = pd.concat([before, after])

        out = detect_offset_change(series, _reference(), freq="YE")
        assert not out.empty
        assert out.attrs.get("suspected_change") is True
        assert (out["shift_from_previous"].abs() > 1).any()

    def test_stable_series_reports_no_change(self):
        out = detect_offset_change(synthetic_pm25("2022-01-01", "2025-12-31", seed=5), _reference())
        assert out.attrs.get("suspected_change") is False

    def test_short_periods_are_skipped_not_guessed(self):
        # Fewer than ~2 weeks cannot form a stable composite; inventing a lag from noise
        # would be worse than reporting nothing.
        out = detect_offset_change(synthetic_pm25("2022-01-01", "2022-01-05"), _reference())
        assert out.empty
