"""Every mapped Earth Engine collection must span the frozen test block.

This test exists because of a specific near-miss. `NOAA/VIIRS/001/VNP14A1` was mapped for
`viirs_active_fire_count` with a claimed 4-hour latency. Measurement (2026-07-29) showed:

- latency **774 days** -- wrong by ~4,600x; and
- final asset **2024-06-16**, which is dead centre of the frozen 2024 test block:
  **161 images in Jan-Jun 2024, zero in Jul-Dec 2024.**

A latency check catches the first. Only a coverage check against the *frozen* test block
catches the second, and the second is far more dangerous: fire signal present for half the
test year and structurally absent for the other half produces a spurious regime change on
1 July that invites a meteorological explanation for a data artefact.

Earth Engine also reported v001 as deprecated. A deprecated collection is frozen, so it
stops covering recent periods silently -- mapping one is therefore a build failure, not a
warning.

Runs offline against measured values recorded in `COLLECTION_COVERAGE`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ecopulse_ca.ingest.earthengine import (
    COLLECTION_COVERAGE,
    COLLECTION_FOR_FEATURE,
    COVERAGE_EXEMPT,
    DEPRECATED_COLLECTIONS,
)

SPLITS = Path(__file__).resolve().parents[1] / "benchmark" / "splits" / "splits.json"


@pytest.fixture(scope="module")
def blocks() -> dict:
    payload = json.loads(SPLITS.read_text(encoding="utf-8"))
    return {b["name"]: b for b in payload["temporal_blocks"]}


def _mapped_time_varying() -> list[tuple[str, str]]:
    return [
        (feature, collection)
        for feature, collection in sorted(COLLECTION_FOR_FEATURE.items())
        if collection not in COVERAGE_EXEMPT
    ]


class TestNoDeprecatedCollections:
    def test_no_mapped_collection_is_deprecated(self):
        used = set(COLLECTION_FOR_FEATURE.values())
        bad = used & DEPRECATED_COLLECTIONS
        assert not bad, (
            f"deprecated collections mapped: {sorted(bad)}. A deprecated collection is "
            "frozen and silently stops covering recent periods."
        )

    def test_the_known_bad_collection_is_recorded_as_deprecated(self):
        """Guards the guard: if this entry vanished, the check above would pass vacuously."""
        assert "NOAA/VIIRS/001/VNP14A1" in DEPRECATED_COLLECTIONS

    def test_viirs_fire_uses_v002(self):
        assert COLLECTION_FOR_FEATURE["viirs_active_fire_count"] == "NASA/VIIRS/002/VNP14A1"


class TestCoverageSpansTheTestBlock:
    @pytest.mark.parametrize("feature,collection", _mapped_time_varying())
    def test_collection_covers_the_frozen_test_block(self, feature, collection, blocks):
        assert collection in COLLECTION_COVERAGE, (
            f"{collection} has no measured coverage recorded. Measure it before mapping -- "
            "an unmeasured collection may die inside the test block."
        )
        first, last, _measured = COLLECTION_COVERAGE[collection]
        test_start = pd.Timestamp(blocks["test"]["start"]).tz_localize(None)
        test_end = pd.Timestamp(blocks["test"]["end"]).tz_localize(None)

        assert pd.Timestamp(first) <= test_start, (
            f"{feature}: {collection} starts {first}, after the test block opens "
            f"{test_start.date()}"
        )
        assert pd.Timestamp(last) >= test_end, (
            f"{feature}: {collection} ends {last}, BEFORE the test block closes "
            f"{test_end.date()}. Coverage stopping mid-block creates structured "
            "missingness that mimics a physical regime change."
        )

    @pytest.mark.parametrize("feature,collection", _mapped_time_varying())
    def test_collection_also_covers_the_training_block(self, feature, collection, blocks):
        """A collection that cannot reach the train block cannot be trained on.

        This is why the 22 h LANCE NRT fire collections are NOT used for the benchmark:
        they begin 2023-09/2023-10, well after the train block opens in 2018.
        """
        first, _last, _ = COLLECTION_COVERAGE[collection]
        train_start = pd.Timestamp(blocks["train"]["start"]).tz_localize(None)
        assert pd.Timestamp(first) <= train_start, (
            f"{feature}: {collection} starts {first}, after the train block opens "
            f"{train_start.date()} -- unusable for training"
        )


class TestTheV001Regression:
    """The specific failure, asserted so it cannot silently return."""

    def test_v001_would_fail_the_test_block_check(self, blocks):
        v001_last = pd.Timestamp("2024-06-16")
        test_end = pd.Timestamp(blocks["test"]["end"]).tz_localize(None)
        assert v001_last < test_end, (
            "v001's final asset must be shown to fall inside the test block, otherwise "
            "this regression test proves nothing"
        )

    def test_v002_passes_where_v001_failed(self, blocks):
        _first, last, _ = COLLECTION_COVERAGE["NASA/VIIRS/002/VNP14A1"]
        test_end = pd.Timestamp(blocks["test"]["end"]).tz_localize(None)
        assert pd.Timestamp(last) >= test_end


class TestCoverageBookkeeping:
    def test_every_mapped_collection_has_measured_coverage(self):
        missing = [
            c for c in set(COLLECTION_FOR_FEATURE.values())
            if c not in COLLECTION_COVERAGE
        ]
        assert not missing, f"collections mapped without measured coverage: {missing}"

    def test_exemptions_are_justified_not_just_listed(self):
        for collection, reason in COVERAGE_EXEMPT.items():
            assert len(reason) > 20, f"{collection} exemption lacks a reason"

    def test_coverage_entries_record_when_they_were_measured(self):
        for collection, (first, last, measured) in COLLECTION_COVERAGE.items():
            for label, value in (("first", first), ("last", last), ("measured", measured)):
                assert pd.Timestamp(value), f"{collection}: bad {label} date {value!r}"
            assert pd.Timestamp(measured) >= pd.Timestamp(last), (
                f"{collection}: measured {measured} precedes last asset {last}"
            )
