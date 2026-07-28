"""End-to-end QC pipeline: ordering, n-effects, and the DECISIONS.md block."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecopulse_ca.qc.pipeline import decisions_block, run_qc
from tests.conftest import synthetic_pm25


def _panel(n: int = 4) -> dict[str, pd.Series]:
    return {f"s{i}": synthetic_pm25(seed=i, base=40 + 4 * i) for i in range(n)}


class TestStationRejection:
    def test_unit_error_station_rejected(self):
        panel = _panel()
        panel["bad_units"] = synthetic_pm25(seed=9) / 1000.0
        out = run_qc(panel)
        assert "bad_units" in out.rejected
        assert "Q4" in out.rejected["bad_units"]
        assert "bad_units" not in out.kept

    def test_short_series_rejected_by_q7(self):
        panel = _panel()
        panel["too_short"] = synthetic_pm25("2025-06-01", "2025-12-31", seed=9)
        out = run_qc(panel)
        assert "too_short" in out.rejected
        assert "Q7" in out.rejected["too_short"]

    def test_healthy_stations_survive(self):
        out = run_qc(_panel())
        assert set(out.kept) == {"s0", "s1", "s2", "s3"}
        assert out.rejected == {}


class TestTimezoneStage:
    def test_shifted_station_rejected(self):
        panel = _panel()
        panel["shifted"] = synthetic_pm25(seed=9, shift_hours=4)
        out = run_qc(panel)
        assert "shifted" in out.rejected
        assert "Q6" in out.rejected["shifted"]

    def test_broken_station_does_not_drag_the_reference(self):
        """A station already rejected at stage 1 must not influence the Q6 reference.

        This is why unit/completeness rejection runs before the composite is built: a
        median over four good stations plus one wrong-unit series would still be fine, but
        a median over two good and two broken ones would not.
        """
        panel = _panel(4)
        panel["bad_units"] = synthetic_pm25(seed=9, shift_hours=6) / 1000.0
        out = run_qc(panel)
        assert "bad_units" in out.rejected
        # The four aligned stations must all survive -- the broken one had no vote.
        assert set(out.kept) == {"s0", "s1", "s2", "s3"}

    def test_q6_skipped_when_too_few_stations(self):
        # With a single station there is no region to compare against; the honest action
        # is to skip the check rather than compare a station to itself.
        out = run_qc({"only": synthetic_pm25(seed=0)})
        assert "only" in out.kept
        assert not any(f.rule == "Q6" for f in out.report.findings)


class TestRowMasking:
    def test_out_of_range_values_masked_not_dropped(self):
        panel = _panel()
        s = panel["s0"].copy()
        s.iloc[100] = -5.0
        panel["s0"] = s
        out = run_qc(panel)
        kept = out.kept["s0"]
        assert len(kept) == len(s)          # length preserved -- masked, not dropped
        assert np.isnan(kept.iloc[100])     # value removed

    def test_flatline_window_masked(self):
        panel = _panel()
        s = panel["s0"].copy()
        s.iloc[500:540] = 44.4
        panel["s0"] = s
        out = run_qc(panel)
        assert out.kept["s0"].iloc[500:540].isna().all()


class TestNEffect:
    def test_reports_station_and_observation_counts(self):
        panel = _panel()
        panel["bad"] = synthetic_pm25(seed=9) / 1000.0
        out = run_qc(panel)
        n = out.n_effect
        assert n["stations_in"] == 5
        assert n["stations_kept"] == 4
        assert n["stations_rejected"] == 1
        assert n["observations_after"] <= n["observations_before"]

    def test_summary_is_human_readable(self):
        out = run_qc(_panel())
        assert "stations" in out.summary()
        assert "observations" in out.summary()

    def test_decisions_block_carries_n_effect_and_bias_direction(self):
        block = decisions_block(run_qc(_panel()), "Q1 test")
        assert "Effect on n:" in block
        assert "Direction of bias if wrong:" in block
        assert "n_flagged" in block  # the findings table is embedded


class TestDuplicateStations:
    def test_census_duplicates_are_reported(self):
        census = pd.DataFrame([
            {"location_id": "s0", "latitude": 41.36, "longitude": 69.289},
            {"location_id": "s1", "latitude": 41.36, "longitude": 69.289},
        ])
        out = run_qc(_panel(2), census=census)
        assert any(f.rule == "Q5b" for f in out.report.findings)
