"""Figures for the Data Descriptor: coverage and error structure.

A Data Descriptor is read by someone deciding whether the data suit their problem. The two
things they need to see first are *what is actually in the record* -- which stations report,
when, and how completely -- and *where the data are hard*. Neither is answerable from prose.

Both figures are generated from the frozen artefacts, so they cannot drift from the tables.
"""

from __future__ import annotations

import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIG = ROOT / "paper" / "figures"
T = ROOT / "paper" / "tables"


def coverage_figure() -> None:
    """Monthly data completeness per station, with the evaluation blocks marked."""
    splits = json.loads((ROOT / "benchmark/splits/splits.json").read_text())
    blocks = {b["name"]: b for b in splits["temporal_blocks"]}
    city_of = {str(s["station_id"]): s["city"] for s in splits["stations"]}

    panel = pd.read_parquet(ROOT / "data/interim/benchmark_panel.parquet")
    panel.columns = [str(c) for c in panel.columns]
    idx = pd.DatetimeIndex(panel.index)

    order = sorted(panel.columns, key=lambda c: (city_of.get(c, ""), c))
    monthly = []
    for col in order:
        s = panel[col]
        got = s.groupby([idx.year, idx.month]).apply(lambda x: x.notna().mean())
        monthly.append(got)
    M = pd.DataFrame(monthly, index=[f"{city_of.get(c, '?')} ({c})" for c in order])
    M.columns = [pd.Timestamp(year=y, month=m, day=1) for y, m in M.columns]
    M = M.reindex(sorted(M.columns), axis=1)

    fig, ax = plt.subplots(figsize=(11, 3.6))
    im = ax.imshow(M.to_numpy(dtype=float), aspect="auto", cmap="viridis",
                   vmin=0, vmax=1, interpolation="nearest")
    ax.set_yticks(range(len(M)))
    ax.set_yticklabels(M.index, fontsize=8)
    step = max(1, len(M.columns) // 14)
    ax.set_xticks(range(0, len(M.columns), step))
    ax.set_xticklabels([d.strftime("%Y-%m") for d in M.columns[::step]], rotation=45,
                       ha="right", fontsize=7)

    # Shade the evaluation blocks rather than drawing bare lines: a reader needs to see the
    # SPAN each block covers, and white text on a pale colormap is unreadable.
    ymax = len(M) - 0.5
    for name, colour, label in (("val", "#ffffff", "validation"), ("test", "#e8000b", "test")):
        lo = pd.Timestamp(blocks[name]["start"]).tz_localize(None)
        hi = pd.Timestamp(blocks[name]["end"]).tz_localize(None)
        x0 = float(np.searchsorted(M.columns, lo)) - 0.5
        x1 = float(np.searchsorted(M.columns, hi)) - 0.5
        ax.add_patch(
            plt.Rectangle((x0, -0.5), x1 - x0, ymax + 0.5, fill=False,
                          edgecolor=colour, lw=2.0, ls="--", zorder=5, clip_on=False)
        )
        ax.text((x0 + x1) / 2, -1.15, label, color=colour, ha="center", va="bottom",
                fontsize=8, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.15", fc="black", ec="none", alpha=0.55))

    cb = fig.colorbar(im, ax=ax, pad=0.01, fraction=0.025)
    cb.set_label("hourly completeness", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    ax.set_title("Monthly data completeness per station", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "figS1_coverage.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote figS1_coverage.png")


def error_structure_figure() -> None:
    """Fold error against city mean concentration -- the dataset's dominant error structure."""
    pred = pd.read_csv(T / "t6_01_predictions_task_n.csv", dtype={"station_id": str})
    per = pd.read_csv(T / "t7_01_error_analysis_by_fold.csv")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    ax = axes[0]
    ax.scatter(per.obs_mean, per.rmse, s=70, c="#31688e", zorder=3)
    for _, r in per.iterrows():
        ax.annotate(r.fold, (r.obs_mean, r.rmse), textcoords="offset points",
                    xytext=(6, 4), fontsize=8)
    ax.set_xlabel("observed mean PM2.5 in held-out city (µg m$^{-3}$)")
    ax.set_ylabel("fold RMSE (µg m$^{-3}$)")
    ax.set_title("Error grows with city concentration", fontsize=10)
    ax.grid(alpha=0.3, zorder=0)

    ax = axes[1]
    ax.scatter(per.obs_mean, per.bias, s=70, c="#35b779", zorder=3)
    ax.axhline(0, color="k", lw=1, ls="--", zorder=2)
    for _, r in per.iterrows():
        ax.annotate(r.fold, (r.obs_mean, r.bias), textcoords="offset points",
                    xytext=(6, 4), fontsize=8)
    ax.set_xlabel("observed mean PM2.5 in held-out city (µg m$^{-3}$)")
    ax.set_ylabel("mean bias (µg m$^{-3}$)")
    ax.set_title("Clean cities over-predicted, polluted under-predicted", fontsize=10)
    ax.grid(alpha=0.3, zorder=0)

    fig.tight_layout()
    fig.savefig(FIG / "figS2_error_structure.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote figS2_error_structure.png")


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    coverage_figure()
    error_structure_figure()
