#!/usr/bin/env python3
"""온산 급행 before/after 집계 — v11 정정본과 동일 기준.

before = sandan_accessibility_0800_by_stop.csv (08:00 R5 출력)
매칭 = solutions_corridors 대표정류장명 → 정류장 id 전체, id inner join, demand>0 수요가중.
(run_r5_scenario.compare_results와 동일 로직, before만 v11 기준 파일로 고정)
"""
import pandas as pd
from pathlib import Path

OUT = Path(__file__).resolve().parent

before = pd.read_csv(OUT / "sandan_accessibility_0800_by_stop.csv")
corr = pd.read_csv(OUT / "solutions_corridors.csv", encoding="utf-8-sig")
row = corr[corr["corridor_id"] == "onsan_1"].iloc[0]
reps = [n.strip() for n in str(row["representative_stops"]).split("·") if n.strip()]
origin_ids = before.loc[before["name"].isin(reps), "id"].tolist()
dest = row["destination_sandan_id"]

rows = []
for speed in (25, 30, 35):
    after = pd.read_csv(OUT / f"onsan_express_accessibility_{speed}kph_by_stop.csv")
    joined = (
        before[before["id"].isin(origin_ids)][["id", "name", "demand", dest]]
        .rename(columns={dest: "before"})
        .merge(
            after[after["id"].isin(origin_ids)][["id", dest]].rename(columns={dest: "after"}),
            on="id", how="inner",
        )
    )
    valid = joined.dropna(subset=["before", "after"])
    valid = valid[valid["demand"] > 0]
    w = valid["demand"]
    b = (valid["before"] * w).sum() / w.sum()
    a = (valid["after"] * w).sum() / w.sum()
    rows.append({
        "corridor_id": "onsan_1",
        "origin_area": row["origin_area"],
        "destination_sandan_id": dest,
        "destination_sandan": row["destination_sandan"],
        "representative_stop_count": len(reps),
        "valid_origin_stop_count": int(len(valid)),
        "weighted_demand": int(w.sum()),
        "before_access_min": round(b, 1),
        "after_access_min": round(a, 1),
        "saved_min": round(b - a, 1),
        "improved_origin_stops": int((valid["after"] < valid["before"]).sum()),
        "speed_kmph": speed,
    })

res = pd.DataFrame(rows)
res.to_csv(OUT / "onsan_express_comparison.csv", index=False)
print(res.to_string(index=False))

meta = pd.read_csv(OUT / "onsan_express_virtual_routes_35kph.csv")
print("\n--- 가상노선 메타(35kph) ---")
for m in meta.itertuples(index=False):
    print(f"middle_stops={m.middle_stops}")
    print(f"middle_stop_count={m.middle_stop_count} additional_cover={m.additional_cover_boardings_07_09}")
    print(f"seq={m.stop_sequence}")
