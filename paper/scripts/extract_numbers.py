"""Extract every figure the manuscript quotes, straight from the banked CSVs.

The manuscript is written with {{placeholders}} and rendered by substituting this mapping.
A number therefore CANNOT drift from its source: there is no hand-typed figure in the text,
and a placeholder with no matching key fails the render rather than silently printing itself.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
T = ROOT / "paper" / "tables"
N: dict[str, str] = {}


def put(k: str, v, dp: int = 2) -> None:
    N[k] = f"{v:.{dp}f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


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
put("dm_fold_favouring_cams", ", ".join(folds[folds.better == "b"].fold))
for _, r in folds.iterrows():
    f = r.fold.lower()
    put(f"dm_{f}_p", r.p, 4)
    put(f"dm_{f}_stat", r.dm)
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

out = ROOT / "paper" / "numbers.json"
out.write_text(json.dumps(dict(sorted(N.items())), indent=2), encoding="utf-8")
print(f"extracted {len(N)} verified figures -> {out}")
for k in list(sorted(N))[:8]:
    print(f"  {k} = {N[k]}")
