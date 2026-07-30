"""MAIAC extraction: chunking, and the informative-missingness contract.

Offline. The Earth Engine call is not exercised here -- `scripts/pull_maiac.py` does that
against live credentials -- but the chunking arithmetic and the missingness invariants are
checkable without a Google account, and they are where silent corruption would live.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ecopulse_ca.ingest.earthengine import ExtractionError
from ecopulse_ca.ingest.maiac import (
    BUFFER_M,
    GETINFO_LIMIT,
    SCALE_FACTOR,
    SCALE_M,
    month_chunks,
)

N_STATIONS = 8


class TestMonthChunking:
    def test_tiles_the_range_without_gaps_or_overlap(self):
        chunks = month_chunks("2018-11-27", "2024-12-31")
        assert chunks[0][0] == "2018-11-27"
        assert chunks[-1][1] == "2024-12-31"
        for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:], strict=False):
            assert pd.Timestamp(next_start) == pd.Timestamp(prev_end) + pd.Timedelta(days=1)

    def test_every_chunk_stays_under_the_getinfo_ceiling(self):
        """The bug this guards: the generic extractor computed elements as
        stations x days, but MCD19A2_GRANULES yields ~80-220 granules per day, so the
        real count was ~80x higher. Compositing to daily server-side restores the
        arithmetic -- these chunks are only legal because of that."""
        for lo, hi in month_chunks("2018-11-27", "2024-12-31"):
            days = (pd.Timestamp(hi) - pd.Timestamp(lo)).days + 1
            assert days * N_STATIONS <= GETINFO_LIMIT

    def test_chunks_are_months_not_maximal_blocks(self):
        """Monthly, not element-maximal: a 600-day chunk is within the element budget but
        times out because it still composites ~80 granules per day server-side."""
        chunks = month_chunks("2020-01-01", "2020-12-31")
        assert len(chunks) == 12
        for lo, hi in chunks:
            assert (pd.Timestamp(hi) - pd.Timestamp(lo)).days <= 30

    def test_partial_first_and_last_months_are_respected(self):
        chunks = month_chunks("2018-11-27", "2019-01-15")
        assert chunks[0] == ("2018-11-27", "2018-11-30")
        assert chunks[-1] == ("2019-01-01", "2019-01-15")

    def test_single_day_range(self):
        assert month_chunks("2024-03-05", "2024-03-05") == [("2024-03-05", "2024-03-05")]

    def test_rejects_reversed_dates(self):
        with pytest.raises(ExtractionError, match="after"):
            month_chunks("2024-12-31", "2024-01-01")


class TestConstants:
    def test_scale_factor_matches_the_maiac_product(self):
        """AOD is stored as scaled integers; omitting this inflates values 1000x."""
        assert SCALE_FACTOR == 0.001

    def test_reduction_scale_matches_native_resolution(self):
        assert SCALE_M == 1000

    def test_buffer_is_larger_than_one_pixel(self):
        """A sub-pixel buffer would just resample a single cell."""
        assert BUFFER_M > SCALE_M


class TestExtractedDataContract:
    """Invariants on the committed extraction output, if present."""

    @pytest.fixture(scope="class")
    def extracted(self):
        path = pd.io.common.get_handle  # noqa: F841 - keep import surface small
        import pathlib

        p = pathlib.Path("data/interim/maiac_aod.parquet")
        if not p.exists():
            pytest.skip("maiac_aod.parquet not present (run scripts/pull_maiac.py)")
        return pd.read_parquet(p)

    def test_null_rows_are_retained_not_dropped(self, extracted):
        """Risk R7. Measured: missing days are dirtier (median +5.3, mean +12.9 ug/m3,
        Mann-Whitney p=1.4e-35), and on the top PM2.5 decile retrieval falls to 45.2%
        against 64.7% overall. Dropping nulls removes the extreme tail."""
        assert extracted["aod_055"].isna().any(), "no null rows -- were they dropped?"

    def test_every_null_has_zero_valid_pixels(self, extracted):
        bad = extracted[(extracted.aod_055.isna()) & (extracted.valid_pixels > 0)]
        assert bad.empty, f"{len(bad)} null AOD rows claim valid pixels"

    def test_every_value_has_at_least_one_valid_pixel(self, extracted):
        bad = extracted[(extracted.aod_055.notna()) & (extracted.valid_pixels == 0)]
        assert bad.empty, f"{len(bad)} AOD values computed from zero pixels"

    def test_valid_pixel_counts_vary(self, extracted):
        """'Mean AOD over 1 pixel' and 'over 53' are different facts."""
        present = extracted.loc[extracted.aod_055.notna(), "valid_pixels"]
        assert present.min() < present.max()

    def test_aod_values_are_physically_plausible(self, extracted):
        v = extracted.aod_055.dropna()
        assert v.min() >= 0.0
        assert v.max() < 6.0, "AOD above ~5 suggests the scale factor was not applied"

    def test_missingness_is_seasonal(self, extracted):
        """The mechanism is winter cloud/snow, not bright-desert failure: retrieval runs
        34% in January against 94% in July."""
        rate = (
            extracted.assign(mo=extracted.date.dt.month)
            .groupby("mo")
            .aod_055.apply(lambda s: s.notna().mean())
        )
        assert rate.loc[1] < rate.loc[7], "January should retrieve worse than July"
        assert rate.loc[7] - rate.loc[1] > 0.3
