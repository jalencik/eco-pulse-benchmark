"""Assemble the daily feature table for Phase 5 modelling.

Resolution: DAILY, not hourly, and that is forced
-------------------------------------------------
Every satellite feature is a daily composite -- MAIAC, AAI, NO2, SO2, CO -- and CAMS is
extracted at one forecast step per day. The target is therefore the **local-calendar daily
mean PM2.5**, matching the exceedance metric already used in Phase 3.

This means the Phase 5 models are NOT directly comparable to the Phase 3 hourly ladder.
Reporting a daily RMSE beside an hourly one would flatter the daily model for free, because
averaging removes within-day variance the hourly task had to predict. The daily-resolution
baselines are therefore recomputed here rather than carried over.

Khujand is a pure zero-shot city
--------------------------------
Both Khujand stations begin 2023-11/2023-12, after the frozen train block closes on
2022-12-31, so Khujand contributes **zero training rows in every fold**. That is a genuine
property of the benchmark, not a defect: it makes Khujand a test of spatial transfer with no
local history whatsoever. `TrainingCoverage` reports it explicitly so no fold silently
assumes six training cities when it has five.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
INTERIM = ROOT / "data" / "interim"

CITY_TZ = {
    "Bishkek": "Asia/Bishkek",
    "Ashgabat": "Asia/Ashgabat",
    "Almaty": "Asia/Almaty",
    "Tashkent": "Asia/Tashkent",
    "Dushanbe": "Asia/Dushanbe",
    "Khujand": "Asia/Dushanbe",
}

#: Satellite sources: (parquet stem, value column).
SATELLITE_SOURCES = [
    ("maiac_aod", "aod_055"),
    ("s5p_aai", "absorbing_aerosol_index"),
    ("s5p_no2", "no2_tropospheric"),
    ("s5p_so2", "so2_column"),
    ("s5p_co", "co_column"),
]

STATIC_COLS = [
    "elevation",
    "ghsl_population_density",
    "viirs_nighttime_lights",
    "terrain_basin_index_25km",
    "terrain_basin_index_50km",
    "terrain_basin_index_100km",
    "distance_to_aralkum",
]


@dataclass
class TrainingCoverage:
    """Which stations actually have training-block rows, and which do not."""

    with_train: list[str] = field(default_factory=list)
    zero_shot: list[str] = field(default_factory=list)
    n_train_rows: dict[str, int] = field(default_factory=dict)

    def report(self) -> str:
        lines = [f"stations with training rows: {len(self.with_train)}"]
        if self.zero_shot:
            lines.append(
                f"ZERO-SHOT (no training rows at all): {self.zero_shot} -- these appear only "
                "in validation/test and contribute nothing to any fold's training set"
            )
        return "\n".join(lines)


def daily_target(panel: pd.DataFrame, city_of: dict[str, str], min_hours: int = 18) -> pd.DataFrame:
    """Local-calendar daily mean PM2.5, requiring `min_hours` observations.

    Local days, not UTC: a UTC boundary splits a Central Asian night in half, cutting the
    overnight inversion peak across two days and understating both.
    """
    rows = []
    for sid in panel.columns:
        s = panel[str(sid)].dropna()
        if s.empty:
            continue
        local = s.tz_convert(CITY_TZ[city_of[str(sid)]])
        ser = pd.Series(local.to_numpy(), index=local.index)
        grouped = ser.groupby(ser.index.date)
        agg = grouped.mean().where(grouped.count() >= min_hours).dropna()
        rows.append(
            pd.DataFrame(
                {
                    "station_id": str(sid),
                    "city": city_of[str(sid)],
                    "date": pd.to_datetime(list(agg.index)),
                    "pm25": agg.to_numpy(),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _load_satellite() -> pd.DataFrame:
    out: pd.DataFrame | None = None
    for stem, col in SATELLITE_SOURCES:
        path = INTERIM / f"{stem}.parquet"
        if not path.exists():
            continue
        d = pd.read_parquet(path)[["station_id", "date", col, "valid_pixels"]].copy()
        d = d.rename(columns={"valid_pixels": f"{col}_valid_px"})
        d["station_id"] = d["station_id"].astype(str)
        d["date"] = pd.to_datetime(d["date"])
        out = d if out is None else out.merge(d, on=["station_id", "date"], how="outer")
    return out if out is not None else pd.DataFrame()


def build_feature_table(splits: dict) -> tuple[pd.DataFrame, TrainingCoverage]:
    """Join target, satellite, CAMS, static and calendar features into one daily table."""
    city_of = {s["station_id"]: s["city"] for s in splits["stations"]}
    panel = pd.read_parquet(INTERIM / "benchmark_panel.parquet")
    panel.columns = [str(c) for c in panel.columns]

    df = daily_target(panel, city_of)
    sat = _load_satellite()
    if not sat.empty:
        df = df.merge(sat, on=["station_id", "date"], how="left")

    cams_path = INTERIM / "cams_pm25_forecast.parquet"
    if cams_path.exists():
        cams = pd.read_parquet(cams_path)[["station_id", "time", "cams_pm25_forecast"]].copy()
        cams["station_id"] = cams["station_id"].astype(str)
        cams["date"] = pd.to_datetime(cams["time"]).dt.normalize()
        df = df.merge(
            cams[["station_id", "date", "cams_pm25_forecast"]],
            on=["station_id", "date"],
            how="left",
        )

    static_path = INTERIM / "static_features.csv"
    if static_path.exists():
        st = pd.read_csv(static_path)
        st["station_id"] = st["station_id"].astype(str)
        keep = ["station_id"] + [c for c in STATIC_COLS if c in st.columns]
        df = df.merge(st[keep], on="station_id", how="left")

    # Calendar encodings. Cyclical so December and January are adjacent rather than 11 apart.
    doy = df["date"].dt.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    df["month"] = df["date"].dt.month
    df["dow"] = df["date"].dt.dayofweek
    df["is_heating_season"] = df["month"].isin([10, 11, 12, 1, 2, 3]).astype(int)

    train_end = pd.Timestamp(
        {b["name"]: b for b in splits["temporal_blocks"]}["train"]["end"]
    ).tz_localize(None)
    n_train = df[df.date <= train_end].groupby("station_id").size().to_dict()
    all_ids = sorted(df.station_id.unique())
    cov = TrainingCoverage(
        with_train=[s for s in all_ids if n_train.get(s, 0) > 0],
        zero_shot=[s for s in all_ids if n_train.get(s, 0) == 0],
        n_train_rows={s: int(n_train.get(s, 0)) for s in all_ids},
    )
    return df.sort_values(["station_id", "date"]).reset_index(drop=True), cov


def feature_columns(df: pd.DataFrame, tier: str) -> list[str]:
    """Columns for a named feature tier.

    `deployable` deliberately excludes MAIAC AOD and the OFFL S5P gases: their measured
    Earth Engine latencies (8 days and 72 h) exceed the 24 h horizon, so a model using them
    could not be served. Only AAI, CAMS forecast, static and calendar survive.
    """
    static = [c for c in STATIC_COLS if c in df.columns]
    calendar = ["doy_sin", "doy_cos", "month", "dow", "is_heating_season"]
    sat_all = (
        [c for c, _ in [(v, k) for k, v in SATELLITE_SOURCES]]
        if False
        else [col for _, col in SATELLITE_SOURCES if col in df.columns]
    )
    valid_px = [f"{c}_valid_px" for _, c in SATELLITE_SOURCES if f"{c}_valid_px" in df.columns]
    cams = ["cams_pm25_forecast"] if "cams_pm25_forecast" in df.columns else []

    if tier == "static_only":
        return static + calendar
    if tier == "deployable":
        aai = [c for c in sat_all if "absorbing" in c]
        aai_px = [c for c in valid_px if "absorbing" in c]
        return aai + aai_px + cams + static + calendar
    if tier == "retrospective":
        return sat_all + valid_px + cams + static + calendar
    raise ValueError(f"unknown tier {tier!r}")
