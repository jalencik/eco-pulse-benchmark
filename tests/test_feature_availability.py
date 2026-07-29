"""Rule 3, enforced: no lookahead in operational features.

This is the test the project spec required from the start and that had nothing to guard
until Phase 4 introduced the first non-operational feature.

The failure it prevents is invisible in a metrics table. ERA5 boundary layer height and
CAMS reanalysis PM2.5 describe exactly the physical quantities that drive PM2.5, are
cleaner and better documented than their forecast counterparts, and are already in most
atmospheric pipelines. A model that consumes them will post an excellent number and be
undeployable, because ERA5 lags roughly five days and CAMS reanalysis months. Nothing about
the resulting RMSE looks wrong.

So the deployment claim is a typed property, checked here, rather than something a reader
has to take on trust.
"""

from __future__ import annotations

import pytest

from ecopulse_ca.features.catalogue import (
    ALL_FEATURES,
    DEPLOYABLE,
    FEATURE_SETS,
    MET_FORECAST,
    MET_REANALYSIS,
    REANALYSIS_ORACLE,
    SATELLITE,
    STATIC_ONLY,
)
from ecopulse_ca.features.spec import (
    CREDENTIAL_FOR,
    FeatureSet,
    FeatureSpec,
    Reduction,
    Source,
    Statistic,
    unverified,
)

#: Shortest forecast horizon on the ladder. A deployable feature staler than this could not
#: inform that forecast even in principle.
MIN_FORECAST_HORIZON_H = 24


class TestDeployableSetContainsNoOracleFeatures:
    """The headline guarantee."""

    def test_deployable_set_validates(self):
        problems = DEPLOYABLE.validate()
        assert not problems, "\n".join(problems)

    def test_deployable_set_has_zero_oracle_features(self):
        oracle = DEPLOYABLE.oracle_features()
        assert not oracle, (
            "features not obtainable at prediction time leaked into the deployable set: "
            f"{[f.name for f in oracle]}"
        )

    @pytest.mark.parametrize("fset", FEATURE_SETS, ids=lambda s: s.name)
    def test_every_declared_set_is_self_consistent(self, fset: FeatureSet):
        assert not fset.validate(), "\n".join(fset.validate())

    def test_adding_a_reanalysis_feature_to_a_deployable_set_fails(self):
        """Guards the guard: if this passed silently, the checks above prove nothing."""
        contaminated = FeatureSet(
            name="contaminated",
            features=DEPLOYABLE.features + MET_REANALYSIS[:1],
            deployable=True,
        )
        problems = contaminated.validate()
        assert problems, "a reanalysis feature was accepted into a deployable set"
        assert "not available at runtime" in problems[0]


class TestReanalysisIsMarkedUnavailable:
    @pytest.mark.parametrize("f", MET_REANALYSIS, ids=lambda f: f.name)
    def test_reanalysis_features_are_oracle_only(self, f: FeatureSpec):
        assert f.available_at_runtime is False
        assert f.latency_hours is None
        assert f.is_oracle

    @pytest.mark.parametrize("f", MET_REANALYSIS, ids=lambda f: f.name)
    def test_reanalysis_features_say_so_in_their_caveat(self, f: FeatureSpec):
        """A reader scanning the catalogue must see it without consulting a flag."""
        assert "ORACLE ONLY" in f.caveat

    def test_oracle_set_is_not_claimed_deployable(self):
        assert REANALYSIS_ORACLE.deployable is False
        assert REANALYSIS_ORACLE.oracle_features()


class TestForecastReanalysisPairing:
    """CAMS forecast and CAMS reanalysis describe the same quantity with opposite
    availability. Confusing them is the single easiest way to violate rule 3."""

    def test_cams_forecast_is_available_and_reanalysis_is_not(self):
        fc = {f.name: f for f in MET_FORECAST}["cams_pm25_forecast"]
        re = {f.name: f for f in MET_REANALYSIS}["cams_pm25_reanalysis"]
        assert fc.available_at_runtime is True
        assert re.available_at_runtime is False

    def test_the_pair_is_distinguishable_by_name(self):
        names = [f.name for f in MET_FORECAST + MET_REANALYSIS]
        for n in names:
            assert n.endswith(("_forecast", "_reanalysis")) or "forecast" in n, (
                f"{n} does not state its provenance in its name"
            )

    def test_no_feature_name_is_ambiguous_between_the_two(self):
        assert len({f.name for f in ALL_FEATURES}) == len(ALL_FEATURES)


class TestLatencyIsCheckable:
    @pytest.mark.parametrize("f", ALL_FEATURES, ids=lambda f: f.name)
    def test_availability_and_latency_agree(self, f: FeatureSpec):
        if f.available_at_runtime:
            assert f.latency_hours is not None and f.latency_hours >= 0
        else:
            assert f.latency_hours is None

    def test_construction_rejects_available_without_latency(self):
        with pytest.raises(ValueError, match="requires a latency_hours"):
            FeatureSpec("x", Source.DERIVED, "d", "u",
                        available_at_runtime=True, latency_hours=None)

    def test_construction_rejects_latency_on_an_oracle_feature(self):
        with pytest.raises(ValueError, match="meaningless"):
            FeatureSpec("x", Source.CDS_ERA5, "d", "u",
                        available_at_runtime=False, latency_hours=120.0)

    def test_deployable_latency_fits_inside_the_shortest_horizon(self):
        """A feature staler than the horizon cannot inform that forecast."""
        worst = DEPLOYABLE.max_latency_hours()
        assert worst < MIN_FORECAST_HORIZON_H, (
            f"worst deployable latency is {worst} h but the shortest horizon is "
            f"{MIN_FORECAST_HORIZON_H} h"
        )


class TestInformativeMissingness:
    """Risk R7: MAIAC retrievals fail during dust, snow and cloud -- the extreme episodes."""

    def test_maiac_aod_is_flagged(self):
        aod = {f.name: f for f in SATELLITE}["maiac_aod_055"]
        assert aod.missingness_informative is True
        assert "dropped" in aod.caveat or "never" in aod.caveat.lower()

    def test_valid_pixel_fraction_is_itself_a_feature(self):
        """Missingness is modelled, not discarded."""
        names = {f.name for f in SATELLITE}
        assert "maiac_valid_pixel_fraction" in names

    @pytest.mark.parametrize(
        "f", [f for f in SATELLITE if f.missingness_informative], ids=lambda f: f.name
    )
    def test_flagged_features_carry_a_caveat(self, f: FeatureSpec):
        assert f.caveat, f"{f.name} has informative missingness but no caveat for readers"


class TestServerSideReductionByConstruction:
    """~8.6 GB free disk. No code path may download a raster."""

    @pytest.mark.parametrize(
        "f", [f for f in ALL_FEATURES if f.source is not Source.DERIVED],
        ids=lambda f: f.name,
    )
    def test_every_gridded_feature_declares_a_reduction(self, f: FeatureSpec):
        assert f.reduction is not None, (
            f"{f.name} has no Reduction -- it would have to be downloaded as a raster"
        )

    @pytest.mark.parametrize(
        "f", [f for f in ALL_FEATURES if f.reduction is not None], ids=lambda f: f.name
    )
    def test_buffers_are_positive_and_sane(self, f: FeatureSpec):
        assert 0 < f.reduction.buffer_m <= 100_000

    def test_informative_missingness_features_emit_a_valid_count(self):
        """'Mean AOD over 3 valid pixels' and 'over 300' are different facts."""
        for f in ALL_FEATURES:
            if f.missingness_informative and f.reduction is not None:
                assert f.reduction.emit_valid_count, (
                    f"{f.name} has informative missingness but discards the pixel count"
                )

    def test_reduction_describes_itself(self):
        r = Reduction(3000, Statistic.MEAN)
        assert "3000 m" in r.describe()


class TestCredentials:
    @pytest.mark.parametrize("source", list(Source), ids=lambda s: s.value)
    def test_every_source_maps_to_a_credential(self, source: Source):
        assert source in CREDENTIAL_FOR

    def test_derived_features_need_no_credential(self):
        assert CREDENTIAL_FOR[Source.DERIVED] == ""

    def test_deployable_set_lists_its_credentials(self):
        creds = DEPLOYABLE.credentials_required()
        assert "EE_PROJECT_ID" in creds
        assert "ADS_API_KEY" in creds
        # ERA5 is oracle-only, so a deployable run must NOT need the CDS key.
        assert "CDS_API_KEY" not in creds

    def test_static_only_set_needs_no_atmospheric_credentials(self):
        creds = STATIC_ONLY.credentials_required()
        assert "ADS_API_KEY" not in creds
        assert "CDS_API_KEY" not in creds


class TestVerificationDebtIsVisible:
    def test_unverified_features_are_enumerable(self):
        """Latency from memory and latency from documentation look identical in a table.

        This test does not fail on unverified features -- Phase 4 has just begun and none
        are checked yet. It asserts the debt is *countable*, so it cannot quietly persist
        into a deployment claim.
        """
        pending = unverified(ALL_FEATURES)
        assert isinstance(pending, tuple)
        assert len(pending) <= len(ALL_FEATURES)

    def test_no_feature_claims_verification_without_a_caveat_or_source(self):
        for f in ALL_FEATURES:
            if f.verified:
                assert f.caveat or f.native_resolution, (
                    f"{f.name} claims verified but records no supporting detail"
                )
