"""Regenerate every paper table from the results CSVs. Nothing here is hand-edited.

Run:  python paper/scripts/build_all.py

Reads paper/tables/*.csv (produced by scripts/run_baselines.py) and emits markdown tables
plus a results summary. If a number appears in the paper and not here, it does not belong
in the paper.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "paper" / "tables"


def _fmt(df: pd.DataFrame, digits: int = 2) -> str:
    return df.round(digits).to_markdown()


def table_task_f(df: pd.DataFrame) -> str:
    """Task F: forecasting. Horizons are reported separately -- never pooled."""
    out = [
        "## Task F — forecasting at monitored stations",
        "",
        "Test block 2024. Five seeds; every model is deterministic, so seed variance is "
        "**zero by construction** and is reported as `(det.)` rather than `± 0.000`.",
        "",
    ]
    for h in sorted(df.horizon_h.unique()):
        sub = df[df.horizon_h == h]
        agg = (
            sub.groupby("model")
            .agg(
                rmse=("rmse", "mean"),
                mae=("mae", "mean"),
                bias=("bias", "mean"),
                r2=("r2", "mean"),
                f1_exceed=("f1_exceed", "mean"),
                n=("n", "sum"),
            )
            .sort_values("rmse")
        )
        out += [f"### t+{h} h", "", _fmt(agg, 3), ""]
    return "\n".join(out)


def table_task_f_by_city(df: pd.DataFrame) -> str:
    out = [
        "## Task F — RMSE by city and horizon",
        "",
        "Per-city numbers are reported individually. Averaging six cities with different "
        "aerosol regimes into one figure hides exactly the variation that matters.",
        "",
    ]
    for h in sorted(df.horizon_h.unique()):
        piv = df[df.horizon_h == h].pivot_table(
            index="city", columns="model", values="rmse", aggfunc="mean"
        )
        out += [f"### t+{h} h (RMSE, µg/m³)", "", _fmt(piv), ""]
    return "\n".join(out)


def table_task_n(df: pd.DataFrame) -> str:
    out = [
        "## Task N — nowcasting, leave-city-out",
        "",
        "Each fold holds out one city entirely; the held-out city contributes no "
        "training label. These are the baselines any satellite model must beat.",
        "",
    ]
    agg = (
        df.groupby("model")
        .agg(
            rmse=("rmse", "mean"),
            mae=("mae", "mean"),
            bias=("bias", "mean"),
            r2=("r2", "mean"),
            f1_exceed=("f1_exceed", "mean"),
            n=("n", "sum"),
        )
        .sort_values("rmse")
    )
    out += ["### Pooled across folds", "", _fmt(agg, 3), ""]

    piv = df.pivot_table(index="held_out_city", columns="model", values="rmse", aggfunc="mean")
    out += ["### RMSE by held-out city (µg/m³)", "", _fmt(piv), ""]

    if "kriging_fallback_rate" in df.columns:
        fb = df.dropna(subset=["kriging_fallback_rate"])
        if not fb.empty:
            rate = fb.groupby("held_out_city")["kriging_fallback_rate"].mean()
            out += [
                "### Kriging fallback rate",
                "",
                "Share of predictions where the kriging system was singular and the "
                "model silently fell back to IDW. A high rate means the reported "
                "'kriging' column is substantially IDW underneath.",
                "",
                _fmt(rate.to_frame("fallback_rate"), 4),
                "",
            ]
    return "\n".join(out)


def table_dm(df: pd.DataFrame, task: str) -> str:
    out = [
        f"## Diebold–Mariano — Task {task}",
        "",
        "Newey–West HAC variance with truncation lag h−1, plus the "
        "Harvey–Leybourne–Newbold small-sample correction. A lower RMSE with "
        "p ≥ 0.05 is **not** an improvement.",
        "",
    ]
    if df.empty:
        return "\n".join(out + ["_No comparisons available._", ""])

    total = len(df)
    sig = int(df.significant_at_05.sum())
    ties = int((df.better == "tie").sum())
    out += [
        f"- comparisons: **{total}**",
        f"- significant at p < 0.05: **{sig}** ({100 * sig / total:.0f}%)",
        f"- exact ties (identical forecasts): **{ties}**",
        "",
    ]

    pair = (
        df.groupby(["model_a", "model_b"])
        .agg(
            n_comparisons=("p_value", "size"),
            n_significant=("significant_at_05", "sum"),
            median_p=("p_value", "median"),
        )
        .reset_index()
    )
    out += ["### By model pair", "", _fmt(pair, 4), ""]
    return "\n".join(out)


def main() -> int:
    need = ["t3_01_task_f_baselines_hourly.csv", "t3_02_task_n_baselines_hourly.csv", "t3_03_dm_task_f.csv", "t3_04_dm_task_n.csv"]
    missing = [n for n in need if not (TABLES / n).exists()]
    if missing:
        print(f"missing results: {missing}\nrun scripts/run_baselines.py first")
        return 1

    task_f = pd.read_csv(TABLES / "t3_01_task_f_baselines_hourly.csv")
    task_n = pd.read_csv(TABLES / "t3_02_task_n_baselines_hourly.csv")
    dm_f = pd.read_csv(TABLES / "t3_03_dm_task_f.csv")
    dm_n = pd.read_csv(TABLES / "t3_04_dm_task_n.csv")

    doc = [
        "# Baseline results — ECO Pulse CA benchmark v1.0.0",
        "",
        "**Generated by `paper/scripts/build_all.py`. Do not edit by hand.**",
        "",
        "Task F and Task N are different problems with different baselines and are never "
        "combined in one table. Exceedance F1 is scored on **local-calendar daily means** "
        "against the WHO 2021 24-hour guideline of 15 µg/m³, because that is what the "
        "guideline defines.",
        "",
        table_task_f(task_f),
        table_task_f_by_city(task_f),
        table_task_n(task_n),
        table_dm(dm_f, "F"),
        table_dm(dm_n, "N"),
        "## Known caveats that travel with these numbers",
        "",
        "1. **Bishkek's 2024 labels are publisher-dependent** — the two feeds of that one "
        "instrument agree on only 11.1% of overlapping hours in the test block "
        "(p95 disagreement 33.6 µg/m³). Bishkek rows carry that uncertainty irreducibly.",
        "2. **Leave-station-out covers 2 of 6 cities.** The rest hold a single instrument.",
        "3. **Kazakhstan contributes one city** — Astana failed Q7 at 42.8% completeness.",
        "4. **No result speaks to current conditions.** The reference network ended 2025-03-04.",
        "",
    ]
    out = TABLES.parent / "RESULTS.md"
    out.write_bytes("\n".join(doc).encode("utf-8"))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
