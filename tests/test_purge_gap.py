"""The purge gap must be derived from the models, not asserted as a constant.

If someone adds a model with a 30-day feature window and does not widen the purge, the
blocked-temporal split silently starts leaking: a training sample's feature window reaches
across the boundary into the validation or test block. These tests recompute the
requirement from the model definitions themselves, so that mistake fails the build instead
of quietly inflating scores.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ecopulse_ca.splits.builder import (
    MAX_HORIZON_HOURS,
    MAX_LAG_HOURS,
    PURGE_HOURS,
    build_temporal_blocks,
)
from tests.conftest import synthetic_pm25

HORIZONS = (24, 48, 72)


@pytest.fixture
def blocks():
    panel = pd.DataFrame({"a": synthetic_pm25("2019-01-01", "2026-06-30", seed=0)})
    return {b.name: b for b in build_temporal_blocks(panel)}


class TestPurgeIsDerived:
    def test_purge_equals_lag_plus_horizon(self):
        assert PURGE_HOURS == MAX_LAG_HOURS + MAX_HORIZON_HOURS

    def test_max_horizon_covers_every_declared_horizon(self):
        assert max(HORIZONS) <= MAX_HORIZON_HOURS

    def test_max_lag_covers_the_longest_feature_window(self):
        """SameHourMean(n_days=7) reaches back 7*24 = 168 h. Any longer window must
        widen MAX_LAG_HOURS, or the purge stops protecting the boundary."""
        from ecopulse_ca.models.persistence import SameHourMean

        longest_days = SameHourMean().n_days
        assert longest_days * 24 <= MAX_LAG_HOURS

    def test_climatology_uses_no_window_beyond_its_fold(self):
        # Climatology fits on whatever fit() receives, so it adds no lag requirement --
        # but only because fit() is never handed data outside the training block.
        from ecopulse_ca.models.climatology import Climatology

        assert not hasattr(Climatology(), "n_days")


class TestGapsAreWideEnough:
    def _gap_hours(self, earlier, later) -> float:
        return (pd.Timestamp(later.start) - pd.Timestamp(earlier.end)).total_seconds() / 3600

    def test_train_to_val_gap(self, blocks):
        assert self._gap_hours(blocks["train"], blocks["val"]) >= PURGE_HOURS

    def test_val_to_test_gap(self, blocks):
        assert self._gap_hours(blocks["val"], blocks["test"]) >= PURGE_HOURS

    def test_purge_blocks_are_exactly_the_declared_width(self, blocks):
        for name in ("purge_train_val", "purge_val_test"):
            width = blocks[name].hours() + 1  # inclusive bounds
            assert width == pytest.approx(PURGE_HOURS, abs=1), f"{name} is {width} h"

    def test_a_training_sample_cannot_reach_into_the_test_block(self, blocks):
        """The concrete failure the purge prevents."""
        train_end = pd.Timestamp(blocks["train"].end)
        test_start = pd.Timestamp(blocks["test"].start)
        furthest_reach = train_end + pd.Timedelta(MAX_HORIZON_HOURS, unit="h")
        assert furthest_reach < test_start

    def test_a_test_sample_feature_window_cannot_reach_into_val(self, blocks):
        test_start = pd.Timestamp(blocks["test"].start)
        val_end = pd.Timestamp(blocks["val"].end)
        earliest_feature = test_start - pd.Timedelta(MAX_LAG_HOURS, unit="h")
        assert earliest_feature > val_end


class TestBlockOrdering:
    def test_blocks_are_chronological_and_non_overlapping(self, blocks):
        order = ["train", "purge_train_val", "val", "purge_val_test", "test",
                 "reserved_post_test"]
        prev_end = None
        for name in order:
            b = blocks[name]
            start, end = pd.Timestamp(b.start), pd.Timestamp(b.end)
            assert start <= end, f"{name} start after end"
            if prev_end is not None:
                assert start > prev_end, f"{name} overlaps the previous block"
            prev_end = end

    def test_test_block_is_the_declared_year(self, blocks):
        assert pd.Timestamp(blocks["test"].start).year == 2024
        assert pd.Timestamp(blocks["test"].end).year == 2024

    def test_train_starts_at_real_data_not_the_index(self):
        """The panel index spans every station ever fetched, including rejected ones.

        Astana was rejected by Q7 but its 2018-07-27 start still sits in the index. Taking
        bounds from the index would declare a training block beginning four months before
        any retained station has an observation.
        """
        panel = pd.DataFrame({"a": synthetic_pm25("2020-06-01", "2026-01-01", seed=0)})
        panel.loc[panel.index[0]:panel.index[100], "a"] = float("nan")
        blocks = {b.name: b for b in build_temporal_blocks(panel)}
        first_real = panel["a"].first_valid_index()
        assert pd.Timestamp(blocks["train"].start) >= first_real.floor("h")
