"""Extract every figure the manuscript quotes, straight from the banked CSVs.

The manuscript is written with {{placeholders}} and rendered by substituting this mapping.
A number therefore CANNOT drift from its source: there is no hand-typed figure in the text,
and a placeholder with no matching key fails the render rather than silently printing itself.
"""
from __future__ import annotations
import json, pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
T = ROOT / "paper" / "tables"
N: dict[str, str] = {}

def put(k: str, v, dp: int = 2) -> None:
    N[k] = f"{v:.{dp}f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)

# ---- benchmark shape (from the frozen splits, not retyped) ----
sp = json.loads((ROOT/"benchmark/splits/splits.json").read_text())
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
for nm in ("train","val","test"):
    put(f"{nm}_start", blocks[nm]["start"][:10]); put(f"{nm}_end", blocks[nm]["end"][:10])

# ---- Phase 6 DM ----
dm = pd.read_csv(T/"t6_02_dm_lgbm_vs_cams.csv")
pool = dm[dm.fold=="POOLED"].iloc[0]
put("dm_pooled_stat", pool.dm); put("dm_pooled_n", pool.n, 0)
put("dm_pooled_p", "< 0.0001" if pool.p < 1e-4 else f"{pool.p:.4f}")
put("rmse_lgbm_pooled", pool.rmse_lgbm); put("rmse_cams_pooled", pool.rmse_cams)
folds = dm[dm.fold!="POOLED"]
put("dm_n_sig", int(folds.sig.sum()), 0); put("dm_n_folds", len(folds), 0)
put("dm_fold_favouring_cams", ", ".join(folds[folds.better=="b"].fold))
for _, r in folds.iterrows():
    f = r.fold.lower()
    put(f"dm_{f}_p", r.p, 4); put(f"dm_{f}_stat", r.dm)
    put(f"rmse_lgbm_{f}", r.rmse_lgbm); put(f"rmse_cams_{f}", r.rmse_cams)

ls = pd.read_csv(T/"t6_03_dm_lag_sensitivity_daily.csv")
put("dm_lag_min_p", ls.p_value.max(), 4)
put("dm_lag_all_sig", "yes" if ls.significant_at_05.all() else "no")
put("dm_lag_range", f"{int(ls.truncation_lag_h.min())} to {int(ls.truncation_lag_h.max())}")

# ---- SHAP ----
fam = pd.read_csv(T/"t6_05_shap_by_family.csv", index_col=0).iloc[:,0]
tot = fam.sum()
for k, v in fam.items():
    put(f"shap_{k}_pct", 100*v/tot, 1)
feat = pd.read_csv(T/"t6_04_shap_by_feature.csv").groupby("feature").mean_abs_shap.mean()
put("shap_top_feature", feat.idxmax()); put("shap_top_value", feat.max())
put("shap_second_feature", feat.sort_values(ascending=False).index[1])
put("shap_second_value", feat.sort_values(ascending=False).iloc[1])

# ---- Phase 5 tuned ladder ----
t5 = pd.read_csv(T/"t5_02_loco_tuned.csv")
n5 = t5[(t5.task=="N")&(t5.model=="lgbm_tuned")]
for tier, g in n5.groupby("tier"):
    put(f"taskn_{tier}_rmse", g.rmse.mean()); put(f"taskn_{tier}_r2", g.r2.mean())
    put(f"taskn_{tier}_mae", g.mae.mean()); put(f"taskn_{tier}_sd", g.rmse.std())
c5 = t5[(t5.task=="N")&(t5.model=="cams_debiased_pooled")]
put("taskn_cams_rmse", c5.rmse.mean()); put("taskn_cams_r2", c5.r2.mean())
put("taskn_cams_mae", c5.mae.mean())
f5 = t5[t5.task=="F"]
for tier, g in f5.groupby("tier"):
    put(f"taskf_{tier}_rmse", g.rmse.mean()); put(f"taskf_{tier}_r2", g.r2.mean())
put("taskf_seed_sd_max", f5.groupby("tier").rmse.std().max(), 2)
put("taskn_seed_sd_max", n5.groupby(["tier","held_out_city"]).rmse.std().max(), 2)

# ---- untuned comparison ----
t5u = pd.read_csv(T/"t5_01_loco_untuned.csv")
u = t5u[t5u.model=="lightgbm"]
for tier, g in u.groupby("tier"):
    put(f"untuned_{tier}_rmse", g.rmse.mean()); put(f"untuned_{tier}_r2", g.r2.mean())

# ---- CAMS bias ----
cb = pd.read_csv(T/"t4_01_cams_baseline_variants.csv")
for v, g in cb.groupby("variant"):
    put(f"cams_{v}_rmse", g.rmse.mean()); put(f"cams_{v}_r2", g.r2.mean())
    put(f"cams_{v}_bias", g.bias.mean())

out = ROOT/"paper"/"numbers.json"
out.write_text(json.dumps(dict(sorted(N.items())), indent=2), encoding="utf-8")
print(f"extracted {len(N)} verified figures -> {out}")
for k in list(sorted(N))[:8]: print(f"  {k} = {N[k]}")
