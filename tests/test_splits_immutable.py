"""The splits are frozen. This test is what makes that true.

`benchmark/splits/splits.sha256` is compared against a fresh build. If they differ the
build fails -- **including when I am the one who changed something.** That is the entire
point: the failure mode this guards against is not malice, it is the very reasonable-looking
decision to adjust a split after seeing results, one small justified step at a time.

If a change to the splits is genuinely warranted, the procedure is:
  1. bump `BENCHMARK_VERSION`,
  2. record the reason in `data/DECISIONS.md`,
  3. regenerate and commit the new hash,
  4. **re-run every published number** -- old results are not comparable to new splits.
It is deliberately more work than editing a JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecopulse_ca.splits.builder import (
    SPLIT_DIR,
    build_leave_city_out,
    build_leave_station_out,
    canonical_json,
    digest,
)

SPLITS_JSON = SPLIT_DIR / "splits.json"
SPLITS_SHA = SPLIT_DIR / "splits.sha256"

pytestmark = pytest.mark.skipif(
    not SPLITS_JSON.exists(), reason="splits not frozen yet (run `make splits`)"
)


@pytest.fixture(scope="module")
def frozen() -> dict:
    return json.loads(SPLITS_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def committed_hash() -> str:
    return SPLITS_SHA.read_text(encoding="utf-8").split()[0]


class TestImmutability:
    def test_committed_file_matches_its_own_hash(self, frozen, committed_hash):
        """The headline check: splits.json has not been edited since it was frozen."""
        assert digest(frozen) == committed_hash, (
            "benchmark/splits/splits.json no longer matches splits.sha256.\n"
            "Splits are immutable. Do NOT regenerate the hash to make this pass -- see the "
            "module docstring for the amendment procedure."
        )

    def test_serialisation_is_deterministic(self, frozen):
        assert canonical_json(frozen) == canonical_json(json.loads(canonical_json(frozen)))

    def test_hash_verifies_against_the_RAW_FILE_BYTES(self, committed_hash):
        """The checksum must be verifiable with `sha256sum`, not only with our own code.

        Regression: `Path.write_text` translated newlines on Windows, so the bytes on disk
        differed from the canonical form that was hashed. The test still passed -- because
        it re-serialised the parsed payload -- while `sha256sum splits.json` failed. A
        published checksum that only this repo can verify is not a checksum.
        """
        import hashlib

        on_disk = hashlib.sha256(SPLITS_JSON.read_bytes()).hexdigest()
        assert on_disk == committed_hash, (
            "splits.sha256 does not match the raw bytes of splits.json. "
            "Check for newline translation on write."
        )

    def test_file_has_no_carriage_returns(self):
        assert b"\r\n" not in SPLITS_JSON.read_bytes(), (
            "CRLF in a hashed artifact makes the checksum platform-dependent"
        )

    def test_hash_file_records_the_version(self, frozen):
        text = SPLITS_SHA.read_text(encoding="utf-8")
        assert frozen["benchmark_version"] in text

    def test_hash_file_states_the_no_refreeze_rule(self):
        text = SPLITS_SHA.read_text(encoding="utf-8").lower()
        assert "immutable" in text
        assert "refreez" in text or "re-freez" in text


class TestLeaveCityOutIntegrity:
    def test_one_fold_per_city(self, frozen):
        cities = {s["city"] for s in frozen["stations"]}
        assert len(frozen["leave_city_out"]) == len(cities)

    def test_held_out_city_contributes_no_training_station(self, frozen):
        by_id = {s["station_id"]: s["city"] for s in frozen["stations"]}
        for fold in frozen["leave_city_out"]:
            train_cities = {by_id[s] for s in fold["train_stations"]}
            assert fold["held_out_city"] not in train_cities, (
                f"fold {fold['fold']} leaks {fold['held_out_city']} into training"
            )

    def test_held_out_and_train_stations_are_disjoint(self, frozen):
        for fold in frozen["leave_city_out"]:
            assert not set(fold["held_out_stations"]) & set(fold["train_stations"])

    def test_every_station_is_held_out_exactly_once(self, frozen):
        held = [s for f in frozen["leave_city_out"] for s in f["held_out_stations"]]
        assert sorted(held) == sorted(s["station_id"] for s in frozen["stations"])

    def test_each_fold_retains_enough_training_cities(self, frozen):
        # A nowcaster needs neighbours; a single training city cannot support IDW/kriging.
        for fold in frozen["leave_city_out"]:
            assert fold["n_train_cities"] >= 3, f"fold {fold['fold']} too thin"


class TestLeaveStationOutIntegrity:
    def test_held_out_station_never_in_train(self, frozen):
        for fold in frozen["leave_station_out"]["folds"]:
            assert fold["held_out_station"] not in fold["train_stations"]

    def test_folds_stay_within_one_city(self, frozen):
        by_id = {s["station_id"]: s["city"] for s in frozen["stations"]}
        for fold in frozen["leave_station_out"]["folds"]:
            cities = {by_id[s] for s in fold["train_stations"]} | {fold["city"]}
            assert len(cities) == 1

    def test_ineligible_cities_are_named_not_silently_absent(self, frozen):
        """Coverage gaps are a stated property of the benchmark."""
        ineligible = frozen["leave_station_out"]["ineligible_cities"]
        by_city: dict[str, int] = {}
        for s in frozen["stations"]:
            by_city[s["city"]] = by_city.get(s["city"], 0) + 1
        assert sorted(ineligible) == sorted(c for c, n in by_city.items() if n < 2)

    def test_builder_is_pure(self, frozen):
        """Rebuilding from the frozen station list reproduces the frozen folds."""
        assert build_leave_city_out(frozen["stations"]) == frozen["leave_city_out"]
        assert build_leave_station_out(frozen["stations"])[0] == frozen["leave_station_out"]


class TestReservedBlock:
    def test_reserved_period_is_declared_and_explained(self, frozen):
        names = [b["name"] for b in frozen["temporal_blocks"]]
        assert "reserved_post_test" in names
        assert any("reserved" in n.lower() for n in frozen["notes"])

    def test_reserved_starts_after_the_test_block(self, frozen):
        blocks = {b["name"]: b for b in frozen["temporal_blocks"]}
        assert blocks["reserved_post_test"]["start"] > blocks["test"]["end"]


class TestConfigIsRecorded:
    def test_purge_rule_is_stated_not_just_the_number(self, frozen):
        assert "max_lag_hours + max_horizon_hours" in frozen["config"]["purge_rule"]

    def test_seeds_are_frozen_with_the_splits(self, frozen):
        assert frozen["config"]["seeds"] == [0, 1, 2, 3, 4]

    def test_known_ground_truth_caveats_are_carried_in_the_artifact(self, frozen):
        """Bishkek's publisher disagreement must travel with the splits, not sit only in
        a markdown file a downstream user might never read."""
        notes = " ".join(frozen["notes"]).lower()
        assert "bishkek" in notes
        assert "11.1%" in " ".join(frozen["notes"])


def test_split_files_are_committed_to_git():
    """The frozen splits are the deliverable; .gitignore must not exclude them."""
    gitignore = (Path(SPLIT_DIR).parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "!benchmark/splits/**" in gitignore


class TestFreezeIsIdempotent:
    """Re-freezing identical splits must not modify a single committed byte.

    The freeze timestamp was previously re-stamped on every invocation, so `make reproduce`
    dirtied `splits.sha256` even when the benchmark had not moved. A reviewer running the
    pipeline then had to work out whether the splits had changed or only the clock had —
    on the one file whose stability the whole benchmark rests on. An idempotent
    reproduction is part of the claim, so it is tested rather than assumed.
    """

    def test_refreezing_preserves_the_original_timestamp(self, tmp_path):
        from ecopulse_ca.splits.builder import build, freeze

        payload = build()
        first = freeze(payload, out_dir=tmp_path)
        stamp_before = (tmp_path / "splits.sha256").read_text(encoding="utf-8")

        second = freeze(payload, out_dir=tmp_path)
        stamp_after = (tmp_path / "splits.sha256").read_text(encoding="utf-8")

        assert first == second
        assert stamp_before == stamp_after, "re-freezing rewrote the checksum file"

    def test_a_changed_payload_does_get_a_new_timestamp(self, tmp_path):
        """The preservation must be conditional on the hash, not unconditional."""
        from ecopulse_ca.splits.builder import build, freeze

        payload = build()
        freeze(payload, out_dir=tmp_path)
        before = (tmp_path / "splits.sha256").read_text(encoding="utf-8")

        altered = json.loads(json.dumps(payload))
        altered["benchmark_version"] = "9.9.9-test"
        freeze(altered, out_dir=tmp_path)
        after = (tmp_path / "splits.sha256").read_text(encoding="utf-8")

        assert before.split()[0] != after.split()[0], "hash did not change with the payload"
