"""Extract every figure the manuscript quotes, straight from the banked CSVs.

The manuscript is written with {{placeholders}} and rendered by substituting this mapping.
A number therefore CANNOT drift from its source: there is no hand-typed figure in the text,
and a placeholder with no matching key fails the render rather than silently printing itself.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys as _sys

import pandas as pd

_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from ecopulse_ca.qc.rules import MIN_YEARS

ROOT = pathlib.Path(__file__).resolve().parents[2]
T = ROOT / "paper" / "tables"
N: dict[str, str] = {}


def put(k: str, v, dp: int = 2) -> None:
    N[k] = f"{v:.{dp}f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def _and_list(items) -> str:
    """Join names the way the sentence around them needs: "A", "A and B", "A, B and C".

    These lists are substituted mid-sentence, so a bare ", ".join() renders as
    "Ashgabat, Bishkek the sign is reversed".
    """
    xs = [str(x) for x in items]
    if len(xs) < 2:
        return "".join(xs)
    return f"{', '.join(xs[:-1])} and {xs[-1]}"


# ---- benchmark shape (from the frozen splits, not retyped) ----
sp = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
put("n_stations", len(sp["stations"]), 0)
put("n_cities", len({s["city"] for s in sp["stations"]}), 0)
put("n_loco_folds", len(sp["leave_city_out"]), 0)
put("purge_hours", sp["config"]["purge_hours"], 0)
put("max_lag_hours", sp["config"]["max_lag_hours"], 0)
put("max_horizon_hours", sp["config"]["max_horizon_hours"], 0)
put("test_year", sp["config"]["test_year"], 0)
put("n_lso_folds", len(sp["leave_station_out"]["folds"]), 0)

# Instrument grade, read from the OpenAQ census rather than asserted. The manuscript
# previously called all instruments "reference"; Khujand's two are Clarity low-cost units
# (is_monitor = false), which is the distinction the exclusion of 306 low-cost stations
# turns on. Deriving it here means the count cannot drift from the data.
_census = pd.read_csv(
    ROOT / "data/interim/station_census.csv",
    dtype={"location_id": str},
    keep_default_na=False,
    na_values=[""],
)
_bench_ids = {str(s["station_id"]) for s in sp["stations"]}
_merged = {s["city"] for s in sp["stations"] if not str(s["station_id"]).isdigit()}
# Merged feeds are keyed by city name in the splits; resolve them back to their source rows.
_rows = _census[
    _census.location_id.isin(_bench_ids) | (_census.city.isin(_merged) & _census.is_monitor)
]
_ref_cities = {r.city for r in _rows.itertuples() if str(r.is_monitor) == "True"}
_low_cities = {
    s["city"]
    for s in sp["stations"]
    if str(s["station_id"])
    in set(_census.loc[~_census.is_monitor.astype(str).eq("True"), "location_id"])
}
_n_low = sum(
    1
    for s in sp["stations"]
    if str(s["station_id"])
    in set(_census.loc[~_census.is_monitor.astype(str).eq("True"), "location_id"])
)
put("n_reference_instruments", len(sp["stations"]) - _n_low, 0)
put("n_lowcost_instruments", _n_low, 0)
put("lowcost_cities", ", ".join(sorted(_low_cities)))
put("q7_min_years", MIN_YEARS, 0)

# Khujand's span INSIDE the benchmark window. The pre-registered Q7 rule is satisfied for
# these two only by counting data after the record ends, which is reserved and never used.
_test_end = pd.Timestamp([b for b in sp["temporal_blocks"] if b["name"] == "test"][0]["end"])
_k = _census[_census.city == "Khujand"].sort_values("location_id")
_spans = [
    (min(pd.Timestamp(r.datetime_last), _test_end) - pd.Timestamp(r.datetime_first)).days / 365.25
    for r in _k.itertuples()
]
if len(_spans) >= 2:
    put("khujand_a_span_in_window", _spans[0])
    put("khujand_b_span_in_window", _spans[1])
put("lso_ineligible", ", ".join(sp["leave_station_out"]["ineligible_cities"]))
blocks = {b["name"]: b for b in sp["temporal_blocks"]}
for nm in ("train", "val", "test"):
    put(f"{nm}_start", blocks[nm]["start"][:10])
    put(f"{nm}_end", blocks[nm]["end"][:10])

# ---- Phase 6 DM ----
dm = pd.read_csv(T / "t6_02_dm_lgbm_vs_cams.csv")
pool = dm[dm.fold == "POOLED"].iloc[0]
put("dm_pooled_stat", pool.dm)
put("dm_pooled_n", pool.n, 0)
put("dm_pooled_p", "< 0.0001" if pool.p < 1e-4 else f"{pool.p:.4f}")
put("rmse_lgbm_pooled", pool.rmse_lgbm)
put("rmse_cams_pooled", pool.rmse_cams)
folds = dm[dm.fold != "POOLED"]
put("dm_n_sig", int(folds.sig.sum()), 0)
put("dm_n_folds", len(folds), 0)
put("dm_fold_favouring_cams", _and_list(folds[folds.better == "b"].fold))
for _, r in folds.iterrows():
    f = r.fold.lower()
    put(f"dm_{f}_p", r.p, 4)
    put(f"dm_{f}_stat", r.dm)
    put(f"dm_{f}_n", int(r.n), 0)
    put(f"rmse_lgbm_{f}", r.rmse_lgbm)
    put(f"rmse_cams_{f}", r.rmse_cams)

ls = pd.read_csv(T / "t6_03_dm_lag_sensitivity_daily.csv")
put("dm_lag_min_p", ls.p_value.max(), 4)
put("dm_lag_all_sig", "yes" if ls.significant_at_05.all() else "no")
put("dm_lag_range", f"{int(ls.truncation_lag_h.min())} to {int(ls.truncation_lag_h.max())}")

# ---- SHAP ----
fam = pd.read_csv(T / "t6_05_shap_by_family.csv", index_col=0).iloc[:, 0]
tot = fam.sum()
for k, v in fam.items():
    put(f"shap_{k}_pct", 100 * v / tot, 1)
feat = pd.read_csv(T / "t6_04_shap_by_feature.csv").groupby("feature").mean_abs_shap.mean()
put("shap_top_feature", feat.idxmax())
put("shap_top_value", feat.max())
put("shap_second_feature", feat.sort_values(ascending=False).index[1])
put("shap_second_value", feat.sort_values(ascending=False).iloc[1])

# ---- Phase 5 tuned ladder ----
t5 = pd.read_csv(T / "t5_02_loco_tuned.csv")
n5 = t5[(t5.task == "N") & (t5.model == "lgbm_tuned")]
for tier, g in n5.groupby("tier"):
    put(f"taskn_{tier}_rmse", g.rmse.mean())
    put(f"taskn_{tier}_r2", g.r2.mean())
    put(f"taskn_{tier}_mae", g.mae.mean())
    put(f"taskn_{tier}_sd", g.rmse.std())
c5 = t5[(t5.task == "N") & (t5.model == "cams_debiased_pooled")]
put("taskn_cams_rmse", c5.rmse.mean())
put("taskn_cams_r2", c5.r2.mean())
put("taskn_cams_mae", c5.mae.mean())
f5 = t5[t5.task == "F"]
for tier, g in f5.groupby("tier"):
    put(f"taskf_{tier}_rmse", g.rmse.mean())
    put(f"taskf_{tier}_r2", g.r2.mean())
put("taskf_seed_sd_max", f5.groupby("tier").rmse.std().max(), 2)
put("taskn_seed_sd_max", n5.groupby(["tier", "held_out_city"]).rmse.std().max(), 2)

# ---- untuned comparison ----
t5u = pd.read_csv(T / "t5_01_loco_untuned.csv")
u = t5u[t5u.model == "lightgbm"]
for tier, g in u.groupby("tier"):
    put(f"untuned_{tier}_rmse", g.rmse.mean())
    put(f"untuned_{tier}_r2", g.r2.mean())

# ---- CAMS bias ----
cb = pd.read_csv(T / "t4_01_cams_baseline_variants.csv")
for v, g in cb.groupby("variant"):
    put(f"cams_{v}_rmse", g.rmse.mean())
    put(f"cams_{v}_r2", g.r2.mean())
    put(f"cams_{v}_bias", g.bias.mean())

# ---- Phase 3 baseline ladder (Section 4) ----
# Task F and Task N are never pooled: different problems, different admissible features.
tf3 = pd.read_csv(T / "t3_01_task_f_baselines_hourly.csv")
for mdl, g in tf3.groupby("model"):
    put(f"p3f_{mdl}_rmse", g.rmse.mean())
    put(f"p3f_{mdl}_r2", g.r2.mean())
for (mdl, h), g in tf3.groupby(["model", "horizon_h"]):
    put(f"p3f_{mdl}_rmse_h{h}", g.rmse.mean())
put("p3f_horizons", ", ".join(f"t+{h} h" for h in sorted(tf3.horizon_h.unique())))

tn3 = pd.read_csv(T / "t3_02_task_n_baselines_hourly.csv")
for mdl, g in tn3.groupby("model"):
    put(f"p3n_{mdl}_rmse", g.rmse.mean())
    put(f"p3n_{mdl}_r2", g.r2.mean())
    put(f"p3n_{mdl}_f1", g.f1_exceed.mean(), 3)
    put(f"p3n_{mdl}_pss", g.peirce_skill.mean(), 3)
put("p3_trivial_f1", tn3.f1_trivial_always.mean(), 3)
put("p3_base_rate", 100 * tn3.base_rate.mean(), 1)
put("p3n_any_beats_trivial", "yes" if bool(tn3.beats_trivial.any()) else "no")
put("p3n_best_rmse_model", tn3.groupby("model").rmse.mean().idxmin())
put("p3n_best_f1_model", tn3.groupby("model").f1_exceed.mean().idxmax())
# How far the best nowcaster actually clears the trivial always-exceed floor. The
# manuscript asserted in four places that nothing cleared it at all, which this margin
# contradicts; emitting it keeps the corrected sentence tied to the table.
put(
    "p3n_best_f1_margin",
    tn3.groupby("model").f1_exceed.mean().max() - tn3.f1_trivial_always.mean(),
    3,
)

# ---- R7 informative missingness (Section 2) ----
r7 = pd.read_csv(T / "t2_01_r7_missingness.csv")
for _, r in r7.iterrows():
    k = r.key.replace("s5p_", "").replace("maiac_", "")
    put(f"r7_{k}_retrieval", r.retrieval_pct, 1)
    # Signed: CO's delta is genuinely negative. A hardcoded '+' in the template would
    # turn a null result into a fabricated positive one.
    put(f"r7_{k}_delta", f"{r.delta_median_pm25:+.1f}")
    put(f"r7_{k}_worst", r.retrieval_worst_decile_pct, 1)
    put(f"r7_{k}_dec", r.retrieval_dec_pct, 1)
    put(f"r7_{k}_jul", r.retrieval_jul_pct, 1)
    # Underflow to exactly 0.0 is a float64 limit, not a p-value. Report it as a bound.
    put(f"r7_{k}_p", "< 1e-300" if r.mannwhitney_p == 0 else f"{r.mannwhitney_p:.2g}")
put("r7_so2_negative", r7.set_index("key").loc["s5p_so2", "negative_retrieval_pct"], 1)

# ---- co-located feed divergence (Section 7) ----
fd = pd.read_csv(T / "t2_03_feed_divergence.csv").set_index("city")
for city in fd.index:
    c = city.lower()
    put(f"feed_{c}_agree", fd.loc[city, "agreement_pct"], 1)
    put(f"feed_{c}_agree_test", fd.loc[city, "agreement_pct_test"], 1)
    put(f"feed_{c}_p95_test", fd.loc[city, "p95_abs_diff_test"], 1)
    put(f"feed_{c}_overlap_test", int(fd.loc[city, "overlap_hours_test"]))

comp = pd.read_csv(T / "t2_02_satellite_complementarity.csv").iloc[0]
put("comp_both", comp.both_pct, 1)
put("comp_aai_only", comp.aai_only_pct, 1)
put("comp_neither", comp.neither_pct, 1)
put("comp_combined", comp.combined_pct, 1)

# --------------------------------------------------------------------------------------
# Corrected result framing: pooled vs per-fold R2, the daily (comparable) baseline ladder,
# and the primary/sensitivity inference. Every figure below is derived here rather than
# written into the prose, because these are precisely the numbers the paper previously got
# wrong by quoting one aggregation while describing another.
# --------------------------------------------------------------------------------------
_pred = pd.read_csv(T / "t6_01_predictions_task_n.csv", dtype={"station_id": str})

# Pooled R^2: variance explained against the GLOBAL mean. This is what a reader hears in
# "explains X% of the variance". The headline 0.07 is the mean of per-fold R^2, each against
# its own city's mean -- a different and much harder quantity.
_ss_res = float(((_pred.pm25 - _pred.lgbm) ** 2).sum())
_ss_tot = float(((_pred.pm25 - _pred.pm25.mean()) ** 2).sum())
put("r2_pooled_global", 1.0 - _ss_res / _ss_tot)

_per_fold = {}
for _c, _g in _pred.groupby("fold"):
    _r = 1.0 - float(((_g.pm25 - _g.lgbm) ** 2).sum()) / float(
        ((_g.pm25 - _g.pm25.mean()) ** 2).sum()
    )
    _per_fold[_c] = _r
put("r2_fold_min", min(_per_fold.values()))
put("r2_fold_max", max(_per_fold.values()))
put("n_folds_negative_r2", sum(1 for v in _per_fold.values() if v < 0), 0)
put(
    "per_fold_r2_rows",
    "\n".join(f"| {c} | {v:+.3f} |" for c, v in sorted(_per_fold.items(), key=lambda kv: kv[1])),
)

_acf1 = float(
    pd.Series((_pred.pm25 - _pred.lgbm) ** 2 - (_pred.pm25 - _pred.pooled) ** 2)
    .groupby(_pred.station_id)
    .apply(lambda s: s.autocorr(1))
    .mean()
)
put("acf_lag1", _acf1)

_daily_f = T / "t3_06_task_n_baselines_daily.csv"
if _daily_f.exists():
    _d = pd.read_csv(_daily_f)
    _fm = _d.groupby("model").apply(
        lambda g: g.groupby("fold").rmse.mean().mean(), include_groups=False
    )
    _tuned_rmse = N.get("taskn_retrospective_rmse")
    _rows = [f"| {m} | {v:.2f} |" for m, v in _fm.sort_values(ascending=False).items()]
    _rows.append(f"| **LightGBM, retrospective** | **{_tuned_rmse}** |")
    put("daily_ladder_rows", "\n".join(_rows))
    # Split the ladder by legality. `oracle_city_constant` uses the held-out city's own
    # test-block mean and is NOT achievable at prediction time; it is reported as a diagnostic
    # floor, never as a baseline the model is compared against.
    _legal = _d[_d.legal] if "legal" in _d.columns else _d
    _fml = _legal.groupby("model").apply(
        lambda g: g.groupby("fold").rmse.mean().mean(), include_groups=False
    )
    put("best_legal_baseline", _fml.idxmin())
    put("best_legal_baseline_rmse", float(_fml.min()))
    put("legal_baseline_margin", float(_fml.min()) - float(_tuned_rmse))
    put("n_legal_baselines_beaten", int((_fml > float(_tuned_rmse)).sum()), 0)
    put("n_legal_baselines", len(_fml), 0)
    _rows_l = [f"| {m} | {v:.2f} |" for m, v in _fml.sort_values(ascending=False).items()]
    _rows_l.append(f"| **LightGBM, retrospective (log target)** | **{_tuned_rmse}** |")
    put("daily_ladder_rows", "\n".join(_rows_l))
    if "oracle_city_constant" in _fm.index:
        _c = float(_fm["oracle_city_constant"])
        put("daily_constant_rmse", _c)
        # Signed, and named for what it is. This constant is an ORACLE (it uses the held-out
        # city's own test-block mean) so it is a diagnostic floor, not a baseline the model is
        # required to beat. Both the signed margin and its absolute size are emitted so the
        # prose cannot read as a win regardless of sign -- an earlier framing did exactly that.
        put("oracle_margin", _c - float(_tuned_rmse))
        put("oracle_gap_abs", abs(float(_tuned_rmse) - _c))
        put("daily_constant_margin", _c - float(_tuned_rmse))
        put("daily_constant_deficit", abs(float(_tuned_rmse) - _c))
        _per_fold_const = _d[_d.model == "oracle_city_constant"].groupby("fold").rmse.mean()
        _per_fold_tuned = (
            pd.read_csv(T / "t5_02_loco_tuned.csv")
            .query("task == 'N' and tier == 'retrospective' and model == 'lgbm_tuned'")
            .groupby("held_out_city")
            .rmse.mean()
        )
        _beat = int(sum(_per_fold_tuned[c] < _per_fold_const[c] for c in _per_fold_const.index))
        put("n_folds_beat_constant", _beat, 0)
        put("n_folds_beat_oracle", _beat, 0)

# Ranking robustness against the strongest legal rival. A fold-mean over 6 cities can lead
# while being statistically indistinguishable and while flipping on removal of one city; all
# three facts are surfaced so the prose cannot state only the first.
_rob_f = T / "t7_05_ranking_robustness.csv"
if _rob_f.exists():
    _rob = pd.read_csv(_rob_f).sort_values("rival_rmse")
    _r0 = _rob.iloc[0]
    put("n_folds_beat_idw", int(_r0.folds_model_better), 0)
    put("idw_paired_p", float(_r0.paired_p), 3)
    put("idw_loco_leads", int(_r0.loco_subsets_model_leads), 0)
    put("idw_margin_seed_sd", float(_r0.margin_over_seed_sd), 1)
    _lad2 = pd.read_csv(T / "t3_06_task_n_baselines_daily.csv")
    _t5b = pd.read_csv(T / "t5_02_loco_tuned.csv")
    _mb = (
        _t5b.query("task == 'N' and tier == 'retrospective' and model == 'lgbm_tuned'")
        .groupby("held_out_city")
        .rmse.mean()
    )
    _ref = [c for c in _mb.index if c not in set(_low_cities)]
    put("model_rmse_ref_only", float(_mb[_ref].mean()))
    _idw2 = _lad2[_lad2.model == "idw_k5_p2"].groupby("fold").rmse.mean()
    put("idw_rmse_ref_only", float(_idw2[[c for c in _ref if c in _idw2.index]].mean()))

# Error structure. These three tables were the only result tables whose figures reached the
# prose by hand-typing rather than substitution, and all seven of them had drifted from
# source by the time it was checked - one of them across the 100 boundary. Emitting them here
# puts them under the same render-time guarantee as every other number in the manuscript.
_fold_f = T / "t7_01_error_analysis_by_fold.csv"
if _fold_f.exists():
    _fold = pd.read_csv(_fold_f)
    for _r in _fold.itertuples():
        put(f"bias_{str(_r.fold).lower()}", float(_r.bias), 1)
        put(f"median_bias_{str(_r.fold).lower()}", float(_r.median_bias), 1)
    _hi = _fold.loc[_fold.bias.idxmax()]
    _lo = _fold.loc[_fold.bias.idxmin()]
    put("bias_fold_max_city", _hi.fold)
    put("bias_fold_max", float(_hi.bias), 1)
    put("bias_fold_min_city", _lo.fold)
    put("bias_fold_min", float(_lo.bias), 1)
    put("n_folds_positive_r2", int((_fold.r2 > 0).sum()), 0)

    # Red-team of the error-structure claim. RMSE scales with the target's own variability,
    # so "error grows with a city's mean" is partly a scale effect and partly a finding. Both
    # coefficients are emitted, plus the normalised one that separates them, because the raw
    # correlation alone overstates what the data show. Spearman on 6 folds, computed here
    # rather than retyped.
    def _spearman(a, b):
        ra = pd.Series(a).rank()
        rb = pd.Series(b).rank()
        return float(ra.corr(rb))

    put("rho_mean_rmse", _spearman(_fold.obs_mean, _fold.rmse), 2)
    put("rho_mean_rmse_norm", _spearman(_fold.obs_mean, _fold.rmse / _fold.obs_sd), 2)
    put("rho_mean_bias", _spearman(_fold.obs_mean, _fold.bias), 2)

_conc_f = T / "t7_02_error_by_concentration.csv"
if _conc_f.exists():
    _conc = pd.read_csv(_conc_f).set_index("band")
    _clean = _conc.loc[[b for b in _conc.index if b.startswith("clean")][0]]
    _ext = _conc.loc[[b for b in _conc.index if b.startswith("extreme")][0]]
    put("bias_clean_band", float(_clean.bias), 1)
    put("bias_extreme_band", float(_ext.bias), 1)
    put("rmse_extreme_band", float(_ext.rmse), 1)
    put("share_extreme_band", 100 * float(_ext.share_of_rows), 1)

    # Two universal statements in the prose were true of a majority, not of every city.
    # Emitting the counts keeps the corrected wording tied to the tables.
    _maj = _fold[_fold.exceed_rate > 0.5]
    put("n_cities_exceed_most_days", len(_maj), 0)
    put("exceed_rate_max", 100 * float(_fold.exceed_rate.max()), 0)
    put("exceed_rate_min", 100 * float(_fold.exceed_rate.min()), 0)
    put("exceed_city_max", _fold.loc[_fold.exceed_rate.idxmax()].fold)
    put("exceed_city_min", _fold.loc[_fold.exceed_rate.idxmin()].fold)

_seas_f = T / "t7_03_error_by_season.csv"
if _seas_f.exists():
    _seas = pd.read_csv(_seas_f).set_index("season")
    put("rmse_djf", float(_seas.loc["DJF"].rmse), 1)
    put("rmse_jja", float(_seas.loc["JJA"].rmse), 1)
    put("r2_djf", float(_seas.loc["DJF"].r2), 2)
    put("r2_jja", float(_seas.loc["JJA"].r2), 2)

# Per-city debiasing of CAMS helps in most cities and hurts in one. The Introduction stated it
# as universal; these keys let it state the exception instead.
_cams_f = T / "t4_01_cams_baseline_variants.csv"
if _cams_f.exists():
    _cv = pd.read_csv(_cams_f).pivot_table(
        index="city", columns="variant", values="rmse", aggfunc="mean"
    )
    if {"raw", "debiased_local"} <= set(_cv.columns):
        _better = _cv.debiased_local < _cv.raw
        put("n_cities_debias_helps", int(_better.sum()), 0)
        put("n_cities_debias_total", int(len(_cv)), 0)
        _worst = (_cv.debiased_local - _cv.raw).idxmax()
        put("debias_worst_city", _worst)
        put("debias_worst_raw", float(_cv.raw[_worst]))
        put("debias_worst_local", float(_cv.debiased_local[_worst]))

# Leave-Khujand-out sensitivity. Khujand is the only two-station city and the only
# low-cost one, so it dominates row-level statistics while being declared incomparable in
# kind. These keys let the manuscript state the sensitivity result rather than assert
# robustness.
_kho_f = T / "t7_06_leave_khujand_out.csv"
if _kho_f.exists():
    _kho = pd.read_csv(_kho_f).set_index("set")
    _all, _ex = _kho.loc["all_cities"], _kho.loc["excluding_Khujand"]
    put("khujand_row_share", 100 * float(_all.excluded_city_row_share), 1)
    put("kho_verdict", str(_all.verdict))
    put("kho_n_rows_excl", int(_ex.n_rows), 0)
    put("kho_rmse_model_excl", float(_ex.rmse_model))
    put("kho_rmse_cams_excl", float(_ex.rmse_cams))
    put("kho_p_t_excl", float(_ex.p_paired_t), 4)
    put("kho_p_perm_excl", float(_ex.p_permutation), 4)
    put("kho_perm_floor_excl", float(_ex.permutation_floor), 4)
    put("kho_mean_d_all", float(_all.mean_loss_differential), 1)
    put("kho_mean_d_excl", float(_ex.mean_loss_differential), 1)

# Section 6 scores the five-seed ENSEMBLE mean prediction, while Section 5 reports means of
# single-seed runs. The two differ, the ensemble is the better estimator, and the manuscript
# printed one as the centre of a spread computed from the other. Emitting the ensemble figure
# lets the text state which is which instead of eliding it.
_ens_f = T / "t6_01_predictions_task_n.csv"
if _ens_f.exists():
    _ep = pd.read_csv(_ens_f)
    _per_fold_ens = _ep.groupby("fold").apply(
        lambda g: float(((g.pm25 - g.lgbm) ** 2).mean() ** 0.5), include_groups=False
    )
    put("taskn_ensemble_rmse", float(_per_fold_ens.mean()))
    put("n_seeds_ensembled", int(len([c for c in _ep.columns if c.startswith("lgbm_seed")])), 0)

# Daily-resolution Task N ladder, per model. Table 6.1 and Figure 2 had been placing hourly
# baseline RMSEs (t3_02) beside daily model RMSEs, which is the resolution mixing the paper
# itself forbids in Section 4.3. Legal rungs only; the oracle constant is excluded here.
_dl_f = T / "t3_06_task_n_baselines_daily.csv"
if _dl_f.exists():
    _dl = pd.read_csv(_dl_f)
    _dl = _dl[_dl.legal.astype(str).str.lower() == "true"]
    for _m, _g in _dl.groupby("model"):
        put(f"p3n_daily_{_m}_rmse", float(_g.rmse.mean()))
        put(f"p3n_daily_{_m}_r2", float(_g.r2.mean()))
    _dbest = _dl.groupby("model").rmse.mean().idxmin()
    put("p3n_daily_best_rmse_model", _dbest)
    put("p3n_daily_best_rmse", float(_dl.groupby("model").rmse.mean().min()))

# Why the bias relation is monotone. The held-out-city predictions barely vary between
# cities, so bias = predicted mean - observed mean is a decreasing function of observed mean
# almost by construction. The spread of the two is what the reader needs to see.
_pm_f = T / "t6_01_predictions_task_n.csv"
if _pm_f.exists():
    _pm = pd.read_csv(_pm_f).groupby("fold").agg(obs=("pm25", "mean"), pred=("lgbm", "mean"))
    put("pred_city_mean_min", float(_pm.pred.min()))
    put("pred_city_mean_max", float(_pm.pred.max()))
    put("pred_city_mean_range", float(_pm.pred.max() - _pm.pred.min()))
    put("obs_city_mean_min", float(_pm.obs.min()))
    put("obs_city_mean_max", float(_pm.obs.max()))
    put("obs_city_mean_range", float(_pm.obs.max() - _pm.obs.min()))

# How many hypothesis tests the deposited tables contain, so the manuscript can say which
# family is corrected and admit that the rest are descriptive.
_n_p = 0
for _tp in sorted(T.glob("t*_*.csv")):
    _tdf = pd.read_csv(_tp)
    for _c in _tdf.columns:
        if _c == "p" or _c.endswith("_p") or _c in ("p_value", "mannwhitney_p", "paired_p"):
            _n_p += int(_tdf[_c].notna().sum())
put("n_p_values_in_tables", _n_p, 0)

# Per-city RMSE difference, tuned model minus IDW, on the same basis build_robustness.py uses
# (seed-mean model RMSE per held-out city from t5_02; daily IDW RMSE per fold from t3_06).
# Section 6.1 quoted this range as two typed literals that had drifted from both tables.
_idw_t5 = T / "t5_02_loco_tuned.csv"
_idw_t3 = T / "t3_06_task_n_baselines_daily.csv"
if _idw_t5.exists() and _idw_t3.exists():
    _mdl = (
        pd.read_csv(_idw_t5)
        .query("task == 'N' and tier == 'retrospective' and model == 'lgbm_tuned'")
        .groupby("held_out_city")
        .rmse.mean()
    )
    _idw = pd.read_csv(_idw_t3).query("model == 'idw_k5_p2'").groupby("fold").rmse.mean()
    _dd = (_mdl - _idw).dropna()
    put("idw_fold_diff_min", float(_dd.min()))
    put("idw_fold_diff_max", float(_dd.max()))

_sig_f = T / "t6_06_significance.csv"
if _sig_f.exists():
    _s = pd.read_csv(_sig_f)

    def _p(sub: str) -> float:
        m = _s[_s.test.str.contains(sub, regex=False)]
        return float(m.p.iloc[0]) if len(m) else float("nan")

    put("sig_primary_t_p", _p("paired t-test on city means"), 4)
    put("sig_primary_perm_p", _p("exact sign-flip permutation"), 4)
    put("sig_naive_p", f"{_p('independence assumed'):.1e}")
    put("sig_hac60_p", _p("lag 60 d"), 4)
    put("sig_boot_p", _p("cluster bootstrap"), 4)
    _n_cities = len({s["city"] for s in sp["stations"]})
    put("sig_primary_df", _n_cities - 1, 0)
    put("sig_perm_floor", 2 / (2**_n_cities), 5)

    # The primary analysis reported p-values and no effect. These carry the estimand itself
    # and its interval, both already present in t6_06, so the tables can show what the study
    # actually estimated rather than only whether it cleared a threshold.
    def _row(sub: str):
        return _s[_s.test.str.contains(sub, regex=False)].iloc[0]

    def _ci(sub: str, dp: int = 1) -> str:
        r = _row(sub)
        if pd.isna(r.ci_lo) or pd.isna(r.ci_hi):
            return "not defined"
        return f"{float(r.ci_lo):+.{dp}f}, {float(r.ci_hi):+.{dp}f}"

    # The city-level effect is the mean of the 6 city differentials, carried verbatim as the
    # permutation row's statistic. The station-day effect is the centre of its symmetric t
    # interval; the naive and HAC rows agree there to machine precision.
    _naive = _row("independence assumed")
    put("sig_mean_d_city", float(_row("exact sign-flip permutation").statistic), 1)
    put("sig_mean_d_stationday", (float(_naive.ci_lo) + float(_naive.ci_hi)) / 2, 1)
    put("sig_ci_t", _ci("paired t-test on city means"))
    put("sig_ci_naive", _ci("independence assumed"))
    put("sig_ci_hac60", _ci("lag 60 d"))
    put("sig_ci_boot", _ci("cluster bootstrap"))

# Task F comparability: the Section 3 baselines are hourly and horizon-resolved; the learned
# Task F model is daily and single-horizon. Both counts are surfaced so the incomparability is
# stated with numbers rather than asserted.
_t3f = pd.read_csv(T / "t3_01_task_f_baselines_hourly.csv")
put("taskf_baseline_n_obs", f"{int(_t3f[_t3f.model == 'same_hour_mean_7d'].n.sum()):,}")
_t5f = pd.read_csv(T / "t5_02_loco_tuned.csv")
put("taskf_model_n", f"{int(_t5f[_t5f.task == 'F'].n.iloc[0]):,}")

# --------------------------------------------------------------------------------------
# Seed dispersion. Section 3.6 rule 5 requires every submission to this benchmark to report
# variability across seeds, and Section 5.4 states results are given as mean +/- SD -- but no
# results table carried an error bar. Deriving the SDs here closes that: the paper must obey
# the rule it imposes on others.
# --------------------------------------------------------------------------------------
_t5 = pd.read_csv(T / "t5_02_loco_tuned.csv")
_n5 = _t5[(_t5.task == "N") & (_t5.model == "lgbm_tuned")]
for _tier in ("static_only", "deployable", "retrospective"):
    _g = _n5[_n5.tier == _tier]
    if _g.empty:
        continue
    # SD of the fold-mean RMSE across seeds: resample the whole protocol per seed, which is
    # the quantity the headline number is an instance of.
    _per_seed = _g.groupby("seed").apply(
        lambda x: x.groupby("held_out_city").rmse.mean().mean(), include_groups=False
    )
    put(f"taskn_{_tier}_rmse_sd", float(_per_seed.std(ddof=1)))
_ret = _n5[_n5.tier == "retrospective"]
_fold_sd = _ret.groupby("held_out_city").rmse.std(ddof=1)
for _city, _v in _fold_sd.items():
    put(f"rmse_lgbm_{_city.lower()}_sd", float(_v))
put("taskn_seed_sd_max_folds", float(_fold_sd.max()))
put("n_seeds", int(_n5.seed.nunique()), 0)

# Tuning grid size, read from the script rather than typed, so it cannot drift.
_gridsrc = (ROOT / "scripts" / "train_phase5.py").read_text(encoding="utf-8")
_gm = re.search(r"GRID\s*=\s*list\(itertools\.product\((.+?)\)\)", _gridsrc)
if _gm:
    _dims = [len(eval(x)) for x in re.findall(r"\[[^\]]*\]", _gm.group(1))]
    _size = 1
    for _d in _dims:
        _size *= _d
    put("tuning_grid_size", _size, 0)

put("n_generated_tables", len(list(T.glob("t*_*.csv"))), 0)

# Astana's completeness, parsed from the QC findings rather than typed into the prose. It was
# the last hand-written scientific figure in the manuscript.
_qc = pd.read_csv(ROOT / "data/interim/qc_findings.csv")
_ast = _qc[(_qc.station_id.astype(str) == "7094") & (_qc.rule == "Q7")]
if len(_ast):
    _m = re.search(r"completeness=([\d.]+)%", str(_ast.detail.iloc[0]))
    if _m:
        put("astana_completeness_pct", float(_m.group(1)), 1)
    _m2 = re.search(r"need (\d+)%", str(_ast.detail.iloc[0]))
    if _m2:
        put("q7_min_completeness_pct", int(_m2.group(1)), 0)

_holm_f = T / "t6_07_per_fold_holm.csv"
if _holm_f.exists():
    put("n_sig_holm", int(pd.read_csv(_holm_f).sig_holm_05.sum()), 0)

# --------------------------------------------------------------------------------------
# Figures used only by the data-descriptor sections (Data Records, Technical Validation,
# Usage Notes, Availability). Derived here for the same reason as everything else: a Data
# Records table that describes the deposit from memory will drift from the deposit.
# --------------------------------------------------------------------------------------
put("benchmark_version", sp["benchmark_version"])
put("seeds_list", ", ".join(str(s) for s in sp["config"]["seeds"]))
_sd = ROOT / "benchmark" / "splits"
for _key, _fn in [
    ("size_splits_json", "splits.json"),
    ("size_temporal_blocks", "temporal_blocks.json"),
    ("size_leave_city_out", "leave_city_out.json"),
    ("size_leave_station_out", "leave_station_out.json"),
    ("size_splits_sha", "splits.sha256"),
]:
    _p = _sd / _fn
    put(_key, f"{_p.stat().st_size:,}" if _p.exists() else "n/a")
for _t in (
    "t3_01_task_f_baselines_hourly",
    "t3_02_task_n_baselines_hourly",
    "t3_06_task_n_baselines_daily",
    "t4_01_cams_baseline_variants",
    "t5_01_loco_untuned",
    "t5_02_loco_tuned",
    "t6_01_predictions_task_n",
    "t6_02_dm_lgbm_vs_cams",
    "t6_06_significance",
    "t6_07_per_fold_holm",
    "t7_06_leave_khujand_out",
):
    _p = T / f"{_t}.csv"
    put(f"rows_{_t[:5]}", f"{len(pd.read_csv(_p)):,}" if _p.exists() else "n/a")

# Cities holding more than one instrument -- the only ones a within-city timing check covers.
_percity = {}
for _s in sp["stations"]:
    _percity[_s["city"]] = _percity.get(_s["city"], 0) + 1
put("n_cities_multi_station", sum(1 for v in _percity.values() if v > 1), 0)

# How many BENCHMARK stations actually end at the diplomatic-post shutdown. The manuscript
# said "six of the eight"; at source-feed level it is 5 of the 10 feeds that survive Q7
# (D-005), and at benchmark-station level -- after merging, which is the level the sentence
# is about -- it is fewer still, because a merged station survives as long as its
# longest-lived feed.
_SHUTDOWN = pd.Timestamp("2025-03-05", tz="UTC")
_panel_p_pre = ROOT / "data/interim/benchmark_panel.parquet"
if _panel_p_pre.exists():
    _pp = pd.read_parquet(_panel_p_pre)
    _pp.columns = [str(c) for c in _pp.columns]
    _ends = {c: _pp[c].dropna().index.max() for c in _pp.columns}
    _n_end = sum(1 for v in _ends.values() if pd.notna(v) and v < _SHUTDOWN)
    put("n_stations_ending_at_shutdown", _n_end, 0)
    put(
        "stations_ending_at_shutdown",
        ", ".join(sorted(c for c, v in _ends.items() if pd.notna(v) and v < _SHUTDOWN)),
    )

# Duplicate-detection evidence, recomputed from the hourly panel rather than quoted.
_panel_p = ROOT / "data/interim/benchmark_panel.parquet"
if _panel_p.exists():
    _pan = pd.read_parquet(_panel_p)
    _pan.columns = [str(c) for c in _pan.columns]

    def _identical_pct(a: str, b: str) -> tuple[float, int]:
        if a not in _pan.columns or b not in _pan.columns:
            return (float("nan"), 0)
        _ov = _pan[[a, b]].dropna()
        if _ov.empty:
            return (float("nan"), 0)
        return (100.0 * (_ov[a] - _ov[b]).abs().lt(1e-9).mean(), len(_ov))

    _kp, _kn = _identical_pct("1894632", "1924313")
    put("khujand_identical_pct", _kp, 1)
    # Post-merge the Dushanbe pair no longer exists in the panel, so these are the values
    # measured before the merge and recorded in data/DECISIONS.md D-012. They are stated as
    # constants HERE, in one place, rather than retyped into prose.
    put("dushanbe_overlap_hours", "33,462")
    put("dushanbe_identical_pct", "94.0")
    put("dushanbe_lag5_pct", "99.9")
    put("dushanbe_explained_pct", "99.99")
    put("identity_coincidence_pct", "2.6")

# Test count, collected rather than typed. pytest is already a project dependency and
# --collect-only is cheap; a typed count would be stale the moment a test is added.
try:
    import subprocess as _sub

    _r = _sub.run(
        [_sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "not network"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    _m = re.search(r"(\d+)\s+tests? collected", _r.stdout)
    put("n_tests", _m.group(1) if _m else "n/a")
except Exception:
    put("n_tests", "n/a")

out = ROOT / "paper" / "numbers.json"
out.write_text(json.dumps(dict(sorted(N.items())), indent=2), encoding="utf-8")
print(f"extracted {len(N)} verified figures -> {out}")
for k in list(sorted(N))[:8]:
    print(f"  {k} = {N[k]}")
