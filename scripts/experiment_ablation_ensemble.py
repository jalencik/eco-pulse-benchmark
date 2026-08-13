"""Feature ablation, ensembling, calibration and temporal CV -- VALIDATION ONLY.

THE TEST BLOCK IS NEVER READ BY THIS SCRIPT.
-------------------------------------------
Everything here is model *selection*, so it is scored on the validation block with
leave-city-out over the training cities. Any configuration that wins here would then have to
be frozen and evaluated once on test, exactly as the log1p transform was. Nothing is chosen
because it wins on test, because test is not available to this code.

FOUR QUESTIONS
--------------
1. **Ablation** -- which feature families actually carry the model? SHAP attributes a fitted
   model's behaviour; it does not answer what happens if a family is removed and the model
   refitted. Only ablation answers that, and the two can disagree sharply.
2. **Ensembling** -- LightGBM and random forest make different errors on this data. If the
   errors are partly independent, a simple average should beat either.
3. **Calibration** -- the model may carry a systematic level bias in a held-out city that a
   single training-fitted scalar could remove.
4. **Temporal CV** -- the reported protocol trains on 2018-2023 and tests on 2024. A
   rolling-origin check asks whether skill is stable across years or an artefact of one.
"""

from __future__ import annotations

import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecopulse_ca.models.feature_table import build_feature_table, feature_columns
from ecopulse_ca.models.lag_features import SPATIAL_COLS, build_spatial_features

OUT_ABL = ROOT / "paper" / "tables" / "t5_04_ablation_val.csv"
OUT_ENS = ROOT / "paper" / "tables" / "t5_05_ensemble_calibration_val.csv"
OUT_TCV = ROOT / "paper" / "tables" / "t5_06_temporal_cv_val.csv"
SEEDS = [0, 1, 2]
TIER = "retrospective"


def family(f: str) -> str:
    """Identical to the SHAP grouping in phase6_analysis.py, so the two are comparable."""
    if f in SPATIAL_COLS:
        return "spatial_neighbour"
    if "valid_px" in f:
        return "satellite_missingness"
    if any(k in f for k in ("aod", "aerosol", "no2", "so2", "co_col")):
        return "satellite"
    if "cams" in f:
        return "cams_forecast"
    if any(k in f for k in ("doy", "month", "dow", "heating")):
        return "calendar"
    return "static_geography"


def rmse(y, p) -> float:
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def fit_predict(model, X_tr, y_tr, X_va):
    """Always the frozen log1p objective, inverted to ug/m3."""
    model.fit(X_tr, np.log1p(y_tr))
    return np.clip(np.expm1(model.predict(X_va)), 0.0, None)


def lgbm(seed):
    return lgb.LGBMRegressor(
        n_estimators=800, learning_rate=0.03, num_leaves=31, min_child_samples=20,
        colsample_bytree=0.7, subsample=0.8, subsample_freq=1, random_state=seed, verbose=-1)


def main() -> int:
    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
    B = {b["name"]: b for b in splits["temporal_blocks"]}
    tr_end = pd.Timestamp(B["train"]["end"]).tz_localize(None)
    va_lo = pd.Timestamp(B["val"]["start"]).tz_localize(None)
    va_hi = pd.Timestamp(B["val"]["end"]).tz_localize(None)
    coords = {s["station_id"]: (s["latitude"], s["longitude"]) for s in splits["stations"]}
    df, _ = build_feature_table(splits)
    cities = sorted({s["city"] for s in splits["stations"]})

    abl, ens, tcv = [], [], []

    for held in cities:
        sp = build_spatial_features(df, coords, exclude_city=held)
        feats = feature_columns(df, TIER) + SPATIAL_COLS
        fams = sorted({family(f) for f in feats})
        tr = sp[(sp.city != held) & (sp.date <= tr_end) & sp.pm25.notna()]
        va = sp[(sp.city == held) & (sp.date >= va_lo) & (sp.date <= va_hi) & sp.pm25.notna()]
        if len(tr) < 200 or len(va) < 30:
            print(f"  {held}: skipped (train {len(tr)}, val {len(va)})", flush=True)
            continue
        y_tr, y_va = tr.pm25.to_numpy(float), va.pm25.to_numpy(float)
        med = tr[feats].astype(float).median()

        def X(frame, cols):
            return frame[cols].astype(float).fillna(med[cols])

        # ---- 1. ABLATION -------------------------------------------------------------
        for label, cols in (
            [("all", feats)]
            + [(f"only_{f}", [c for c in feats if family(c) == f]) for f in fams]
            + [(f"drop_{f}", [c for c in feats if family(c) != f]) for f in fams]
        ):
            if not cols:
                continue
            for seed in SEEDS:
                p = fit_predict(lgbm(seed), X(tr, cols), y_tr, X(va, cols))
                abl.append({"fold": held, "config": label, "n_features": len(cols),
                            "seed": seed, "rmse": rmse(y_va, p)})

        # ---- 2. ENSEMBLE + 3. CALIBRATION --------------------------------------------
        pl = np.mean([fit_predict(lgbm(s), X(tr, feats), y_tr, X(va, feats)) for s in SEEDS], 0)
        pr = np.mean([
            fit_predict(RandomForestRegressor(n_estimators=300, min_samples_leaf=5,
                                              n_jobs=-1, random_state=s),
                        X(tr, feats), y_tr, X(va, feats)) for s in SEEDS], 0)
        # In-sample training predictions give a TRAINING-ONLY calibration scalar. Fitting it
        # on validation would make the validation score self-referential.
        pl_tr = np.mean([fit_predict(lgbm(s), X(tr, feats), y_tr, X(tr, feats)) for s in SEEDS], 0)
        scale = float(y_tr.mean() / max(pl_tr.mean(), 1e-9))
        offset = float(y_tr.mean() - pl_tr.mean())
        for label, pred in (
            ("lgbm", pl), ("rf", pr),
            ("ens_mean", 0.5 * pl + 0.5 * pr),
            ("ens_70_30", 0.7 * pl + 0.3 * pr),
            ("lgbm_scaled", np.clip(pl * scale, 0, None)),
            ("lgbm_offset", np.clip(pl + offset, 0, None)),
        ):
            ens.append({"fold": held, "config": label, "rmse": rmse(y_va, pred),
                        "bias": float(np.mean(pred - y_va))})

        # ---- 4. TEMPORAL CV (rolling origin, still validation-scored) -----------------
        for cut in ("2020-12-31", "2021-12-31", "2022-12-31"):
            c = pd.Timestamp(cut)
            tsub = tr[tr.date <= c]
            if len(tsub) < 200:
                continue
            p = fit_predict(lgbm(0), X(tsub, feats), tsub.pm25.to_numpy(float), X(va, feats))
            tcv.append({"fold": held, "train_through": cut, "n_train": len(tsub),
                        "rmse": rmse(y_va, p)})
        print(f"  {held}: done", flush=True)

    for frame, path, name in ((abl, OUT_ABL, "ablation"), (ens, OUT_ENS, "ensemble/calibration"),
                              (tcv, OUT_TCV, "temporal CV")):
        pd.DataFrame(frame).to_csv(path, index=False)
        print(f"wrote {path.name} ({len(frame)} rows)")

    a = pd.DataFrame(abl)
    print("\n=== ABLATION (validation fold-mean RMSE) ===")
    for k, v in (a.groupby("config").apply(
            lambda g: g.groupby("fold").rmse.mean().mean(), include_groups=False)
            .sort_values().items()):
        print(f"  {k:<32} {v:8.3f}")
    e = pd.DataFrame(ens)
    print("\n=== ENSEMBLE / CALIBRATION (validation fold-mean RMSE) ===")
    for k, v in (e.groupby("config").apply(
            lambda g: g.groupby("fold").rmse.mean().mean(), include_groups=False)
            .sort_values().items()):
        print(f"  {k:<32} {v:8.3f}")
    t = pd.DataFrame(tcv)
    if len(t):
        print("\n=== TEMPORAL CV (validation fold-mean RMSE by training cut-off) ===")
        for k, v in t.groupby("train_through").rmse.mean().items():
            print(f"  train through {k}   {v:8.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
