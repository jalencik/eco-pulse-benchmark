"""Generate the manuscript figures from the banked result tables.

Run:  python scripts/build_figures.py

Writes paper/figures/fig{1..5}_*.png at 300 dpi.

Every figure is produced from `paper/tables/*.csv` — the same CSVs the text draws its
numbers from — so a figure cannot disagree with the prose. This is the zero-drift rule
extended to plots: a chart drawn once from a notebook and pasted in is exactly as prone to
silent staleness as a hand-typed number.

Design constraints, all of them requirements of the target venues rather than taste:

* **Legible in greyscale.** Reviewers print. Series are separated by hatch pattern and
  marker shape, never by colour alone, and the palette is a grey ramp.
* **Every axis labelled with units.** µg/m³ throughout; no bare numbers.
* **No chartjunk.** No gridlines competing with data, no 3-D, no decorative colour.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "paper" / "tables"
FIGS = ROOT / "paper" / "figures"
SPLITS = ROOT / "benchmark" / "splits" / "splits.json"

DPI = 300
GREY = ["#2b2b2b", "#6e6e6e", "#a5a5a5", "#cccccc"]
HATCH = ["", "///", "...", "xxx"]

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.constrained_layout.use": True,
    }
)

PRETTY = {
    "training_pool_mean": "Training pool mean",
    "nearest_monitor": "Nearest monitor",
    "idw_k5_p2": "IDW (k=5, p=2)",
    "ordinary_kriging": "Ordinary kriging",
    "cams_debiased_pooled": "CAMS (debiased)",
    "lgbm_tuned": "LightGBM (tuned)",
    "lgbm_tuned_lags": "LightGBM (+lags)",
    "spatial_neighbour": "Spatial neighbour",
    "static_geography": "Static geography",
    "calendar": "Calendar",
    "satellite": "Satellite",
    "cams_forecast": "CAMS forecast",
    "satellite_missingness": "Satellite missingness",
}


LOW_COST_CITIES = {"Khujand"}


def fig1_study_area() -> str:
    """Station geography. Reviewers ask 'where is this?' before anything else."""
    splits = json.loads(SPLITS.read_bytes())
    st = pd.DataFrame(splits["stations"])
    # Instrument grade is a function of city: both Khujand instruments are Clarity low-cost
    # optical sensors and every other benchmark station is a US diplomatic-post BAM/FEM
    # monitor (data/MANIFEST.md, per-instrument grade table; DECISIONS.md D-012). The caption
    # promises the two are drawn with different markers, so they are.
    low_cost = st.city.isin(LOW_COST_CITIES)
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    for mask, marker, lab in (
        (~low_cost, "o", "Reference monitor (area $\\propto$ n observations)"),
        (low_cost, "^", "Low-cost sensor (Clarity)"),
    ):
        sub = st[mask]
        ax.scatter(
            sub.longitude,
            sub.latitude,
            s=sub.n_observations / 900,
            c=GREY[0],
            marker=marker,
            edgecolor="white",
            zorder=3,
            label=lab,
        )
    seen: set[str] = set()
    for _, r in st.iterrows():
        if r.city in seen:
            continue
        seen.add(r.city)
        ax.annotate(
            r.city,
            (r.longitude, r.latitude),
            textcoords="offset points",
            xytext=(7, 4),
            fontsize=8.5,
        )
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")
    ax.set_title("Figure 1. Benchmark stations across Central Asia", loc="left", fontsize=10)
    ax.grid(alpha=0.25, linewidth=0.5, zorder=0)
    ax.legend(frameon=False, loc="lower left", fontsize=8)
    out = FIGS / "fig1_study_area.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out.name


def fig2_baseline_ladder() -> str:
    """Task N ladder. The central honesty claim of the paper, in one panel."""
    # Daily ladder, legal rungs only. The hourly table (t3_02) was plotted here until it was
    # noticed that the two model bars are daily, which put hourly and daily RMSE on one axis,
    # the comparison Section 4.3 forbids. The oracle constant is excluded: it is not a rung.
    base = pd.read_csv(TABLES / "t3_06_task_n_baselines_daily.csv")
    base = base[base.legal.astype(str).str.lower() == "true"]
    tuned = pd.read_csv(TABLES / "t5_02_loco_tuned.csv")
    rows = base.groupby("model").rmse.mean().to_dict()
    n = tuned[(tuned.task == "N") & (tuned.tier == "retrospective")]
    for m, g in n.groupby("model"):
        rows[m] = g.rmse.mean()

    s = pd.Series(rows).sort_values(ascending=True)
    labels = [PRETTY.get(k, k) for k in s.index]
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    bars = ax.barh(labels, s.values, color=GREY[2], edgecolor="black", linewidth=0.7)
    # Highlight the headline model without relying on colour alone.
    for bar, key in zip(bars, s.index, strict=False):
        if key == "lgbm_tuned":
            bar.set_color(GREY[0])
            bar.set_hatch("///")
    for bar, v in zip(bars, s.values, strict=False):
        ax.text(v + 0.3, bar.get_y() + bar.get_height() / 2, f"{v:.1f}", va="center", fontsize=8)
    ax.set_xlabel("Leave-city-out RMSE, daily means (µg/m³)")
    ax.set_title("Figure 2. Task N baseline ladder", loc="left", fontsize=10)
    ax.set_xlim(0, max(s.values) * 1.15)
    out = FIGS / "fig2_baseline_ladder.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out.name


def fig3_per_city() -> str:
    """Per-city LightGBM vs CAMS. Pooling six aerosol regimes hides the story."""
    t = pd.read_csv(TABLES / "t5_02_loco_tuned.csv")
    t = t[(t.task == "N") & (t.tier == "retrospective") & (t.held_out_city != "ALL")]
    piv = t.pivot_table(index="held_out_city", columns="model", values="rmse", aggfunc="mean")
    keep = [c for c in ("lgbm_tuned", "cams_debiased_pooled") if c in piv.columns]
    piv = piv[keep].sort_values(keep[0])

    x = range(len(piv))
    w = 0.38
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for i, col in enumerate(keep):
        ax.bar(
            [p + i * w for p in x],
            piv[col],
            width=w,
            label=PRETTY.get(col, col),
            color=GREY[i * 2],
            edgecolor="black",
            linewidth=0.7,
            hatch=HATCH[i],
        )
    ax.set_xticks([p + w / 2 for p in x])
    ax.set_xticklabels(piv.index, rotation=20, ha="right")
    ax.set_ylabel("RMSE (µg/m³)")
    ax.set_title(
        "Figure 3. Held-out city error: tuned model vs debiased CAMS", loc="left", fontsize=10
    )
    ax.legend(frameon=False, fontsize=8)
    out = FIGS / "fig3_per_city_rmse.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out.name


def fig4_shap() -> str:
    """Attribution by family — the result the paper reports against its own interest."""
    s = pd.read_csv(TABLES / "t6_05_shap_by_family.csv")
    s = s.set_index("family").iloc[:, 0].sort_values()
    pct = 100 * s / s.sum()
    labels = [PRETTY.get(k, k) for k in pct.index]
    fig, ax = plt.subplots(figsize=(6.0, 3.2))
    bars = ax.barh(labels, pct.values, color=GREY[2], edgecolor="black", linewidth=0.7)
    for bar, key in zip(bars, pct.index, strict=False):
        if "satellite" in key:
            bar.set_hatch("...")
            bar.set_color(GREY[1])
    for bar, v in zip(bars, pct.values, strict=False):
        ax.text(v + 0.4, bar.get_y() + bar.get_height() / 2, f"{v:.1f}%", va="center", fontsize=8)
    ax.set_xlabel("Share of total mean |SHAP| (%)")
    ax.set_title("Figure 4. Feature attribution by family", loc="left", fontsize=10)
    ax.set_xlim(0, max(pct.values) * 1.18)
    out = FIGS / "fig4_shap_by_family.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out.name


def fig5_obs_pred() -> str:
    """Observed vs predicted with the 1:1 line. Shows compression toward the mean."""
    d = pd.read_csv(TABLES / "t6_01_predictions_task_n.csv").dropna(subset=["pm25", "lgbm"])
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.scatter(d.pm25, d.lgbm, s=7, alpha=0.30, c=GREY[1], edgecolor="none")
    hi = float(max(d.pm25.max(), d.lgbm.max())) * 1.03
    ax.plot([0, hi], [0, hi], "k--", linewidth=0.9, label="1:1")
    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_xlabel("Observed daily PM2.5 (µg/m³)")
    ax.set_ylabel("Predicted daily PM2.5 (µg/m³)")
    ax.set_title("Figure 5. Observed vs predicted, leave-city-out", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    out = FIGS / "fig5_obs_vs_pred.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return out.name


def main() -> int:
    FIGS.mkdir(parents=True, exist_ok=True)
    made = []
    for fn in (fig1_study_area, fig2_baseline_ladder, fig3_per_city, fig4_shap, fig5_obs_pred):
        try:
            made.append(fn())
        except Exception as exc:  # noqa: BLE001 - one bad figure must not kill the set
            print(f"  FAILED {fn.__name__}: {type(exc).__name__}: {exc}", file=sys.stderr)
    for name in made:
        kb = (FIGS / name).stat().st_size / 1024
        print(f"  {name:32s} {kb:6.0f} KB")
    print(f"\nwrote {len(made)}/5 figures to {FIGS}")
    return 0 if len(made) == 5 else 1


if __name__ == "__main__":
    sys.exit(main())
