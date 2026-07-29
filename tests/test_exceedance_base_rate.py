"""Exceedance F1 must never be reported without its base-rate reference.

Found on the live benchmark: 64.8% of test-block days exceed the WHO 15 µg/m³ guideline,
so a predictor that says "exceeded" every day scores F1 = 0.764 — and no model on the
credential-free ladder beats it. The best (IDW) reaches 0.762; ordinary kriging, which wins
on RMSE, scores 0.728.

A metric where the trivial answer wins is not measuring skill. These tests pin the
corrections that make the number interpretable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ecopulse_ca.eval.metrics import WHO_2021_PM25_24H, exceedance_metrics

TZ = "Asia/Tashkent"


def _hourly(daily_values: list[float]) -> pd.Series:
    """Build an hourly series whose local daily means are exactly `daily_values`."""
    idx = pd.date_range("2024-01-01", periods=24 * len(daily_values), freq="h", tz="UTC")
    vals = np.repeat(np.array(daily_values, dtype=float), 24)
    return pd.Series(vals, index=idx)


class TestTrivialPredictorReference:
    def test_always_exceed_scores_the_base_rate_f1(self):
        # 7 of 10 days exceed -> precision 0.7, recall 1.0 -> F1 = 2*.7/1.7
        obs = _hourly([50.0] * 7 + [5.0] * 3)
        pred = _hourly([1000.0] * 10)
        m = exceedance_metrics(obs, pred, WHO_2021_PM25_24H, TZ)
        assert m.recall == pytest.approx(1.0)
        assert m.precision == pytest.approx(m.base_rate)
        assert m.f1 == pytest.approx(m.f1_trivial_always)
        assert not m.beats_trivial

    def test_high_base_rate_makes_trivial_f1_look_excellent(self):
        """The Dushanbe case: 88% of days exceed, so saying yes always scores 0.94."""
        obs = _hourly([50.0] * 88 + [5.0] * 12)
        m = exceedance_metrics(obs, _hourly([1000.0] * 100), WHO_2021_PM25_24H, TZ)
        assert m.f1_trivial_always > 0.93
        assert m.peirce_skill == pytest.approx(0.0, abs=1e-9)

    def test_low_base_rate_makes_trivial_f1_look_poor(self):
        """The Bishkek case: 23% base rate, so the same trivial answer scores 0.38."""
        obs = _hourly([50.0] * 23 + [5.0] * 77)
        m = exceedance_metrics(obs, _hourly([1000.0] * 100), WHO_2021_PM25_24H, TZ)
        assert m.f1_trivial_always < 0.40
        # Same predictor, wildly different F1 -> pooling F1 across cities measures the
        # cities, not the model.


class TestPeirceSkill:
    def test_is_zero_for_any_constant_prediction(self):
        obs = _hourly([50.0] * 6 + [5.0] * 4)
        for constant in (1.0, 20.0, 1000.0):
            m = exceedance_metrics(obs, _hourly([constant] * 10), WHO_2021_PM25_24H, TZ)
            assert m.peirce_skill == pytest.approx(0.0, abs=1e-9), (
                f"constant {constant} should have zero skill"
            )

    def test_is_one_for_a_perfect_predictor(self):
        obs = _hourly([50.0] * 5 + [5.0] * 5)
        m = exceedance_metrics(obs, obs, WHO_2021_PM25_24H, TZ)
        assert m.peirce_skill == pytest.approx(1.0)

    def test_is_independent_of_base_rate(self):
        """The property F1 lacks: the same skill scores the same on clean and dirty cities."""
        # A predictor that is right on 80% of exceedances and 80% of non-exceedances.
        def build(n_exceed: int, n_clean: int):
            obs = _hourly([50.0] * n_exceed + [5.0] * n_clean)
            pred = (
                [50.0] * int(n_exceed * 0.8) + [5.0] * (n_exceed - int(n_exceed * 0.8))
                + [5.0] * int(n_clean * 0.8) + [50.0] * (n_clean - int(n_clean * 0.8))
            )
            return exceedance_metrics(obs, _hourly(pred), WHO_2021_PM25_24H, TZ)

        dirty = build(80, 20)
        clean = build(20, 80)
        assert dirty.peirce_skill == pytest.approx(clean.peirce_skill, abs=0.02)
        # F1, by contrast, differs sharply for the same skill.
        assert abs(dirty.f1 - clean.f1) > 0.2

    def test_is_negative_for_an_anti_correlated_predictor(self):
        obs = _hourly([50.0] * 5 + [5.0] * 5)
        inverted = _hourly([5.0] * 5 + [50.0] * 5)
        m = exceedance_metrics(obs, inverted, WHO_2021_PM25_24H, TZ)
        assert m.peirce_skill < 0


class TestReportingContract:
    def test_base_rate_is_always_carried_with_f1(self):
        obs = _hourly([50.0] * 6 + [5.0] * 4)
        d = exceedance_metrics(obs, obs, WHO_2021_PM25_24H, TZ).as_dict()
        for field in ("f1", "base_rate", "f1_trivial_always", "peirce_skill", "beats_trivial"):
            assert field in d, f"{field} must travel with the F1 number"

    def test_empty_input_returns_nan_not_zero(self):
        empty = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
        m = exceedance_metrics(empty, empty, WHO_2021_PM25_24H, TZ)
        assert m.n_days == 0
        assert np.isnan(m.f1)
