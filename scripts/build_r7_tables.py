"""Regenerate the Section 2 missingness tables from the extracted satellite parquets.

Run:  python scripts/build_r7_tables.py

Writes:
  paper/tables/t2_01_r7_missingness.csv
  paper/tables/t2_02_satellite_complementarity.csv

These two tables were originally computed ad hoc and their numbers hand-copied into the
manuscript, where they drifted (SO2 retrieval was written as 61.5% against an actual
60.62%). Every figure in Section 2 now comes from here, and `make reproduce` rebuilds it.

R7 is the risk that satellite retrieval failure is correlated with the target: retrievals
fail during dust, cloud and snow, which are the conditions carrying the highest
concentrations. The test is a Mann-Whitney U on observed PM2.5 split by whether the
retrieval succeeded that station-day -- rank-based, because PM2.5 is heavily right-skewed
and a t-test on the mean would be answering a different question.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from scipy.stats import mannwhitneyu

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
TABLES = ROOT / "paper" / "tables"

# band column -> (display name, parquet stem). AAI is the only one allowed negative values:
# the absorbing aerosol index is a ratio and is genuinely negative over bright scatterers.
FEATURES = [
    ("S5P SO2", "s5p_so2"),
    ("MAIAC AOD", "maiac_aod"),
    ("S5P NO2", "s5p_no2"),
    ("S5P CO", "s5p_co"),
    ("S5P AAI", "s5p_aai"),
]
WORST_DECILE_Q = 0.90


def daily_target() -> pd.DataFrame:
    """Local-calendar daily mean PM2.5 per station, long form.

    Reads benchmark_panel.parquet, not panel.parquet. The raw panel still carries the 11
    pre-merge feeds, including the duplicate embassy publications; the satellite grids key
    on the 8 merged entities ('Bishkek', 'Ashgabat' as merged labels). Joining the raw
    panel silently drops every Bishkek and Ashgabat day.
    """
    panel = pd.read_parquet(INTERIM / "benchmark_panel.parquet")
    flat = panel.reset_index(names="datetime")
    long = flat.melt(id_vars="datetime", var_name="station_id", value_name="pm25")
    long = long.dropna(subset=["pm25"])
    long["date"] = pd.to_datetime(long["datetime"], utc=True).dt.date
    return (
        long.groupby(["station_id", "date"], as_index=False)["pm25"]
        .mean()
        .astype({"station_id": str})
    )


def satellite_daily(stem: str) -> pd.DataFrame:
    """The station-day grid with the retrieved value, or NaN where retrieval failed.

    Each parquet is already a *complete* station x date grid over the extraction window --
    the daily compositor emits a fully-masked image for days with no usable granule rather
    than omitting the row. Retrieval failure is therefore a NaN inside an existing row, not
    an absent row, and the grid itself is the correct denominator. Treating absent rows as
    failures instead conflates 'never extracted' with 'retrieval failed' and drags the
    reported retrieval rate down by more than half.
    """
    df = pd.read_parquet(INTERIM / f"{stem}.parquet")
    ignore = {"station_id", "date", "datetime", "valid_pixels", "n_slices", "n_granules"}
    value_col = next(c for c in df.columns if c not in ignore)
    df = df.rename(columns={value_col: "value"})
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce").dt.date
    df["station_id"] = df["station_id"].astype(str)
    return df[["station_id", "date", "value"]]


def main() -> int:
    target = daily_target()
    rows = []
    presence: dict[str, pd.Series] = {}

    for display, stem in FEATURES:
        sat = satellite_daily(stem)
        # Inner join: the question is "given a station-day we both observed and attempted
        # to retrieve, does retrieval failure carry information about the target?" A
        # station-day with no ground observation cannot answer it either way.
        m = sat.merge(target, on=["station_id", "date"], how="inner")
        got = m["value"].notna()
        presence[stem] = got

        hi = m["pm25"] >= m["pm25"].quantile(WORST_DECILE_Q)
        month = pd.to_datetime(m["date"]).dt.month

        # Two-sided: we are testing whether the distributions differ, not asserting a
        # direction in advance. CO and AAI are expected to come back null.
        pm_missing, pm_present = m.loc[~got, "pm25"], m.loc[got, "pm25"]
        p = mannwhitneyu(pm_missing, pm_present, alternative="two-sided").pvalue

        # Negative retrievals sit below the instrument noise floor. Reported because
        # clipping them at zero would bias the tracer upward; only meaningful for the
        # column-density retrievals, not for AAI, whose index is legitimately negative
        # over bright scattering scenes. Denominator is *successful* retrievals -- a
        # negative value is a property of a retrieval that happened, so dividing by the
        # full grid would deflate it by the retrieval rate.
        neg = float((m.loc[got, "value"] < 0).mean() * 100) if stem != "s5p_aai" else float("nan")

        rows.append(
            {
                "feature": display,
                "key": stem,
                "retrieval_pct": got.mean() * 100,
                "delta_median_pm25": pm_missing.median() - pm_present.median(),
                "mannwhitney_p": p,
                "retrieval_worst_decile_pct": got[hi].mean() * 100,
                "retrieval_dec_pct": got[month == 12].mean() * 100,
                "retrieval_jul_pct": got[month == 7].mean() * 100,
                "negative_retrieval_pct": neg,
                "target_correlated": bool(p < 0.05),
            }
        )

    TABLES.mkdir(parents=True, exist_ok=True)
    out1 = pd.DataFrame(rows)
    out1.to_csv(TABLES / "t2_01_r7_missingness.csv", index=False)

    # Complementarity: does the clean feature (AAI) cover the days the contaminated one
    # (MAIAC) misses? If it did not, dropping MAIAC would simply cost us those rows.
    aod, aai = presence["maiac_aod"], presence["s5p_aai"]
    out2 = pd.DataFrame(
        [
            {
                "both_pct": (aod & aai).mean() * 100,
                "aai_only_pct": (~aod & aai).mean() * 100,
                "neither_pct": (~aod & ~aai).mean() * 100,
                "combined_pct": (aod | aai).mean() * 100,
            }
        ]
    )
    out2.to_csv(TABLES / "t2_02_satellite_complementarity.csv", index=False)

    print(out1.round(2).to_string(index=False))
    print()
    print(out2.round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
