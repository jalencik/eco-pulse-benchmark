"""Bank the test-block ablation behind the paper's showcase against-interest figure.

WHY THIS EXISTS
---------------
The manuscript reports, in three places, that excluding the satellite retrieval-count
features from Task N was frozen on a validation gain of 1.75 ug/m3 that "did not replicate,
delivering 0.045 ug/m3" on the test block. The 1.75 is checkable: t5_04_ablation_val.csv holds
the validation ablation. The 0.045 was not. No deposited table scored the with-features
configuration on the test block; the number came from a run whose per-fold outputs were never
banked. A reported-against-interest figure that a reader cannot check is worth less than one
they can, so this script produces the table.

WHAT IT DOES
------------
For every leave-city-out fold, fits the tuned Task N model twice with the hyperparameters
FROZEN in t5_02 (no re-tuning; the params column is identical across seeds within a fold):

    excluded   the deposited configuration, valid-pixel features removed
    included   the same configuration with the valid-pixel features retained

Same rows, same seeds, same log1p target and expm1 inversion, same clip at zero, scored on the
test block with the same metrics. The model constructor `mk` is read from train_phase5.py by
AST at runtime rather than copied, so the two scripts cannot build different models.

The test-block delta this table yields is what the manuscript now quotes, through a
placeholder. When this script was first run, the typed figure it replaced (0.045) did not
survive: the recomputed fold-mean delta was 0.25, and the sign varied by city. The
manuscript says so.

OUTPUT
------
paper/tables/t5_07_missingness_test.csv  one row per fold x config x seed
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
import lightgbm as lgb  # noqa: E402,F401  (mk() from train_phase5 refers to it by name)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ecopulse_ca.eval.metrics import regression_metrics  # noqa: E402
from ecopulse_ca.models.feature_table import build_feature_table, feature_columns  # noqa: E402
from ecopulse_ca.models.lag_features import SPATIAL_COLS, build_spatial_features  # noqa: E402

TABLES = ROOT / "paper" / "tables"
OUT = TABLES / "t5_07_missingness_test.csv"
SEEDS = [0, 1, 2, 3, 4]
TIER = "retrospective"


def _mk_from_train_phase5():
    """Return train_phase5.mk without importing the module (importing it trains everything)."""
    src = (ROOT / "scripts" / "train_phase5.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "mk")
    ns: dict = {"lgb": lgb}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "train_phase5.mk", "exec"), ns)
    return ns["mk"]


def main() -> int:
    mk = _mk_from_train_phase5()
    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
    B = {b["name"]: b for b in splits["temporal_blocks"]}
    tr_end = pd.Timestamp(B["train"]["end"]).tz_localize(None)
    va_lo, va_hi = (
        pd.Timestamp(B["val"]["start"]).tz_localize(None),
        pd.Timestamp(B["val"]["end"]).tz_localize(None),
    )
    te_lo, te_hi = (
        pd.Timestamp(B["test"]["start"]).tz_localize(None),
        pd.Timestamp(B["test"]["end"]).tz_localize(None),
    )
    coords = {s["station_id"]: (s["latitude"], s["longitude"]) for s in splits["stations"]}

    df, _cov = build_feature_table(splits)
    missingness_cols = [c for c in df.columns if "valid_px" in str(c)]
    base = feature_columns(df, TIER)
    feats = {
        "excluded": [c for c in base if c not in missingness_cols] + SPATIAL_COLS,
        "included": base + SPATIAL_COLS,
    }

    tuned = pd.read_csv(TABLES / "t5_02_loco_tuned.csv")
    tuned = tuned[(tuned.task == "N") & (tuned.tier == TIER) & (tuned.model == "lgbm_tuned")]
    params = {}
    for city, g in tuned.groupby("held_out_city"):
        assert (g.params == g.params.iloc[0]).all(), f"{city}: params differ across seeds"
        params[city] = ast.literal_eval(g.params.iloc[0])

    rows = []
    for fold in splits["leave_city_out"]:
        held = fold["held_out_city"]
        if held not in params:
            continue
        sp = build_spatial_features(df, coords, exclude_city=held)
        tr = sp[(sp.city != held) & (sp.date <= tr_end) & sp.pm25.notna()]
        va = sp[(sp.city != held) & (sp.date >= va_lo) & (sp.date <= va_hi) & sp.pm25.notna()]
        te = sp[(sp.city == held) & (sp.date >= te_lo) & (sp.date <= te_hi) & sp.pm25.notna()]
        if len(tr) < 200 or len(te) < 30 or len(va) < 50:
            continue
        fit = pd.concat([tr, va])
        for config, cols in feats.items():
            for seed in SEEDS:
                m = mk(seed, params[held]).fit(fit[cols], np.log1p(fit.pm25))
                pred = np.clip(np.expm1(m.predict(te[cols])), 0.0, None)
                r = regression_metrics(te.pm25, pd.Series(pred, index=te.index))
                rows.append(
                    {
                        "fold": held,
                        "config": config,
                        "n_features": len(cols),
                        "seed": seed,
                        "params": str(params[held]),
                        **r.as_dict(),
                    }
                )
        print(f"  {held:<10} done", flush=True)

    out = pd.DataFrame(rows).sort_values(["fold", "config", "seed"]).reset_index(drop=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    fm = out.groupby("config").rmse.mean()
    delta = float(fm["included"] - fm["excluded"])
    print(f"\nwrote {OUT}  ({len(out)} rows)")
    print(f"  fold-mean test RMSE  excluded={fm['excluded']:.4f}  included={fm['included']:.4f}")
    print(f"  excluding the features changed fold-mean test RMSE by {-delta:+.4f} ug/m3")
    print("  (the manuscript renders this figure from the table via freeze2_test_delta)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
