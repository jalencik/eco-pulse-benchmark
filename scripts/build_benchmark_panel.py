"""Apply the three Phase-2 decisions and produce the final benchmark panel.

  1. Temporal test block = 2024 (last full year with complete reference coverage).
  2. Co-located feeds in Bishkek and Ashgabat merged into one series per city.
  3. Q6 rebuilt per city -- within-city agreement rejects; cross-city is informational.

Run:  python scripts/build_benchmark_panel.py

Writes data/interim/benchmark_panel.parquet, panel_sources.parquet, merge_report.md,
q6_percity_findings.csv, regime_summary.csv.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ecopulse_ca.qc.merge import choose_primary, merge_colocated
from ecopulse_ca.qc.rules import q5_duplicate_stations, q5c_value_identity_wide
from ecopulse_ca.qc.timezone_percity import regime_summary, run_q6_per_city

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
TEST_YEAR = 2024


def main() -> int:
    panel = pd.read_parquet(INTERIM / "panel.parquet")
    prov = pd.read_csv(INTERIM / "panel_provenance.csv")
    census = pd.read_csv(INTERIM / "station_census.csv", keep_default_na=False, na_values=[""])
    census["location_id"] = census["location_id"].astype(str)

    qc = pd.read_csv(INTERIM / "qc_findings.csv")
    rejected = set(qc.loc[qc.verdict == "reject", "station_id"].astype(str))
    keep = [c for c in panel.columns if str(c) not in rejected]
    panel = panel[keep]
    print(f"stations entering merge: {len(keep)} (excluded {sorted(rejected)})")

    city_of = dict(zip(prov.location_id.astype(str), prov.city, strict=False))
    tz_of = dict(zip(census.location_id, census.timezone, strict=False))
    coords = census.set_index("location_id")[["latitude", "longitude"]].astype(float)

    # -- decision 2: merge co-located feeds ------------------------------------------
    surviving = census[census.location_id.isin([str(c) for c in panel.columns])].copy()
    surviving[["latitude", "longitude"]] = surviving[["latitude", "longitude"]].astype(float)
    pairs = [f.station_id.split(",") for f in q5_duplicate_stations(surviving) if f.rule == "Q5b"]
    print(f"co-located pairs to merge (Q5b, distance): {len(pairs)}")

    # Q5c catches the inverse of Q5b: one instrument republished under coordinates that
    # DISAGREE, which distance can never see. Dushanbe 8684 (AirNow) / 9769 (StateAir) is the
    # same US-embassy republication D-003 caught in Bishkek and Ashgabat, but its two records
    # sit 6.06 km apart, so Q5b passed it -- and D-003 then cited that pair as its own safety
    # margin. 99.99% of the 33,462 overlapping hours are the identical reading (94.0% aligned,
    # and 99.9% of the rest identical at exactly the +5 h Dushanbe UTC offset).
    # These pairs merge under the SAME D-008 rule as Q5b: precedence and gap-fill, never
    # averaging. Evidence and thresholds: data/DECISIONS.md D-011 and D-012.
    seen = {frozenset(p) for p in pairs}
    for f in q5c_value_identity_wide(panel[[c for c in panel.columns]]):
        ids = f.station_id.split(",")
        if frozenset(ids) not in seen:
            pairs.append(ids)
            seen.add(frozenset(ids))
            print(f"  value-identity duplicate (Q5c): {f.station_id} -- {f.detail}")
    print(f"pairs to merge in total: {len(pairs)}")

    merged = panel.copy()
    sources = pd.DataFrame(index=panel.index)
    reports = []
    for ids in pairs:
        a, b = ids[0], ids[1]
        # A station can appear in at most one merge. Q5b and Q5c are independent detectors and
        # may name overlapping pairs; whichever fires first consumes the columns, so a later
        # pair referencing an already-merged feed is skipped rather than crashing on drop().
        if a not in merged.columns or b not in merged.columns:
            print(f"  skipping {a},{b}: already merged into another pair")
            continue
        city = city_of.get(a, a)
        p_id, s_id = choose_primary(panel[a], panel[b], a, b)
        vals, src, rep = merge_colocated(
            panel[p_id],
            panel[s_id],
            merged_id=city,
            primary_id=p_id,
            secondary_id=s_id,
        )
        merged = merged.drop(columns=[a, b])
        merged[city] = vals
        sources[city] = src
        reports.append(rep)
        city_of[city] = city
        tz_of[city] = tz_of.get(p_id)
        coords.loc[city] = coords.loc[p_id]
        print(
            f"  {city}: primary={p_id} secondary={s_id} -> {rep.n_merged:,} obs "
            f"({rep.pct_exact:.1f}% agreement)"
        )

    # Re-key CAMS onto the merged station ids in the SAME step that performs the merge.
    # CAMS is extracted at station coordinates, and a merged station inherits its primary's
    # coordinates (above), so the primary's CAMS series is by construction the forecast for
    # the merged station. Keeping this here means a merge can never again leave a benchmark
    # station with no CAMS key.
    #
    # It has to be here because it already went wrong once: merging Dushanbe produced a
    # station keyed "Dushanbe" while the CAMS parquet still held "8684"/"9769", so every
    # downstream join on (station_id, date) silently returned zero rows and the Dushanbe fold
    # vanished from Section 6 without any error. A dropped city is not a result; it is a bug
    # that looks like a result.
    cams_path = INTERIM / "cams_pm25_forecast.parquet"
    if reports and cams_path.exists():
        cams = pd.read_parquet(cams_path)
        cams["station_id"] = cams.station_id.astype(str)
        alias = {r.primary_id: r.merged_id for r in reports}
        drop_ids = {r.secondary_id for r in reports}
        if set(alias) & set(cams.station_id):
            keep = cams[~cams.station_id.isin(drop_ids)].copy()
            keep["station_id"] = keep.station_id.replace(alias)
            keep = keep.drop_duplicates(subset=["station_id", "time"])
            keep.to_parquet(cams_path, index=False)
            print(
                f"  re-keyed CAMS for merged stations: "
                f"{ {k: v for k, v in alias.items() if k in set(cams.station_id)} }"
            )

    for c in merged.columns:
        c = str(c)
        if c not in city_of:
            city_of[c] = city_of.get(c, c)

    # -- decision 3: per-city Q6 -------------------------------------------------------
    findings = run_q6_per_city(merged, city_of, tz_of)
    fdf = pd.DataFrame(
        [
            {
                "rule": f.rule,
                "station_id": f.station_id,
                "verdict": f.verdict,
                "n_flagged": f.n_flagged,
                "detail": f.detail,
            }
            for f in findings
        ]
    )
    fdf.to_csv(INTERIM / "q6_percity_findings.csv", index=False)
    q6_rejects = set(fdf.loc[fdf.verdict == "reject", "station_id"])
    print(
        f"\nQ6 per-city: {len(q6_rejects)} rejections "
        f"({int((fdf.rule == 'Q6a').sum())} stations checked)"
    )
    for _, r in fdf[fdf.verdict == "reject"].iterrows():
        print(f"  REJECT {r.station_id}: {r.detail}")

    final = merged.drop(columns=[c for c in merged.columns if str(c) in q6_rejects])

    # -- report -----------------------------------------------------------------------
    final.to_parquet(INTERIM / "benchmark_panel.parquet")
    if not sources.empty:
        sources.to_parquet(INTERIM / "panel_sources.parquet")
    regime_summary(final, city_of, tz_of).to_csv(INTERIM / "regime_summary.csv", index=False)
    (INTERIM / "merge_report.md").write_text(
        "# Co-located feed merges\n\n" + "\n\n".join(r.to_markdown() for r in reports),
        encoding="utf-8",
    )

    test = final[final.index.year == TEST_YEAR]
    print("\n" + "=" * 74)
    print("FINAL BENCHMARK PANEL")
    print("=" * 74)
    summary = pd.DataFrame(
        {
            "city": [city_of.get(str(c), str(c)) for c in final.columns],
            "n_obs": [int(final[c].notna().sum()) for c in final.columns],
            "first": [final[c].first_valid_index() for c in final.columns],
            "last": [final[c].last_valid_index() for c in final.columns],
            f"obs_in_{TEST_YEAR}": [int(test[c].notna().sum()) for c in final.columns],
            f"complete_{TEST_YEAR}": [
                round(float(test[c].notna().mean()), 3) for c in final.columns
            ],
        },
        index=[str(c) for c in final.columns],
    )
    print(summary.to_string())

    cities = sorted({city_of.get(str(c), str(c)) for c in final.columns})
    with_test = [c for c in final.columns if test[c].notna().sum() > 0]
    print(f"\nstations   : {len(final.columns)}")
    print(f"cities     : {len(cities)} -> {cities}")
    print(f"observations: {int(final.notna().sum().sum()):,}")
    print(
        f"\nTEST BLOCK {TEST_YEAR}: {len(with_test)} stations with data, "
        f"{len({city_of.get(str(c), str(c)) for c in with_test})} cities"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
