#!/usr/bin/env python3
"""Build and evaluate the v10 sandan express-commuter GTFS scenario."""
from __future__ import annotations

import csv
import json
import math
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments" / "sandan"
GTFS_DIR = ROOT / "gtfs"
SCENARIO_DIR = OUT / "gtfs_scenario"
SCENARIO_ZIP = OUT / "gtfs_sandan_scenario.zip"
SCENARIO_CFG = ROOT / "config" / "ulsan_sandan_scenario.yaml"
EXPRESS_ACCESS = OUT / "express_accessibility_by_stop.csv"

TOP_CORRIDORS = ["ulsan_mipo_1", "gilcheon_1", "sin_free_trade_1"]
SPEED_KMPH = 35.0
DWELL_SECONDS = 30
BUFFER_KM = 1.5
COMMUTE_HOURS = {7, 8}
MID_STOP_TARGET = {"ulsan_mipo_1": 3, "gilcheon_1": 5, "sin_free_trade_1": 3}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def seconds_to_time(seconds: int) -> str:
    hh, rem = divmod(seconds, 3600)
    mm, ss = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def read_destinations() -> dict[str, dict]:
    cfg = yaml.safe_load((ROOT / "config" / "ulsan_sandan.yaml").read_text(encoding="utf-8"))
    return {d["id"]: d for d in cfg["destinations"]}


def nearest_stop(stops: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    d = (stops["stop_lat"] - lat).pow(2) + (
        (stops["stop_lon"] - lon) * math.cos(math.radians(lat))
    ).pow(2)
    return stops.loc[d.idxmin()]


def point_to_segment_km(
    lat: float,
    lon: float,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> tuple[float, float]:
    """Approximate distance and along-line position using a local tangent plane."""
    lat0 = math.radians((start_lat + end_lat) / 2)
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(lat0)
    sx, sy = start_lon * km_per_deg_lon, start_lat * km_per_deg_lat
    ex, ey = end_lon * km_per_deg_lon, end_lat * km_per_deg_lat
    px, py = lon * km_per_deg_lon, lat * km_per_deg_lat
    vx, vy = ex - sx, ey - sy
    wx, wy = px - sx, py - sy
    denom = vx * vx + vy * vy
    if denom == 0:
        return math.hypot(px - sx, py - sy), 0.0
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
    proj_x, proj_y = sx + t * vx, sy + t * vy
    return math.hypot(px - proj_x, py - proj_y), t


def commute_boardings_by_stop_name() -> pd.Series:
    hourly = pd.read_csv(ROOT / "dataset" / "demand_hourly.csv")
    hourly["hour"] = pd.to_numeric(hourly["hour"], errors="coerce")
    hourly["boardings"] = pd.to_numeric(hourly["boardings"], errors="coerce").fillna(0)
    commute = hourly[hourly["hour"].isin(COMMUTE_HOURS)]
    return commute.groupby("stop_name")["boardings"].sum()


def select_middle_stop_ids(
    row: pd.Series,
    stops: pd.DataFrame,
    destination: dict,
    origin_stop_ids: list[str],
    boardings: pd.Series,
) -> list[dict]:
    target = MID_STOP_TARGET.get(row["corridor_id"], 4)
    used = set(origin_stop_ids)
    candidates = []
    for stop in stops.itertuples(index=False):
        sid = str(stop.stop_id)
        if sid in used:
            continue
        demand = int(boardings.get(stop.stop_name, 0))
        if demand <= 0:
            continue
        dist, along = point_to_segment_km(
            float(stop.stop_lat),
            float(stop.stop_lon),
            float(row["origin_lat"]),
            float(row["origin_lon"]),
            float(destination["lat"]),
            float(destination["lon"]),
        )
        if dist > BUFFER_KM or along <= 0.08 or along >= 0.96:
            continue
        candidates.append(
            {
                "stop_id": sid,
                "stop_name": stop.stop_name,
                "stop_lat": float(stop.stop_lat),
                "stop_lon": float(stop.stop_lon),
                "commute_boardings_07_09": demand,
                "line_dist_km": dist,
                "line_position": along,
            }
        )

    selected = []
    selected_names = set()
    for cand in sorted(candidates, key=lambda c: (-c["commute_boardings_07_09"], c["line_dist_km"])):
        if cand["stop_name"] in selected_names:
            continue
        selected.append(cand)
        selected_names.add(cand["stop_name"])
        if len(selected) >= target:
            break
    return sorted(selected, key=lambda c: c["line_position"])


def representative_stop_ids(row: pd.Series, stops: pd.DataFrame) -> list[str]:
    names = [name.strip() for name in str(row["representative_stops"]).split("·") if name.strip()]
    selected: list[str] = []
    used: set[str] = set()
    for name in names[:4]:
        candidates = stops[stops["stop_name"] == name]
        if candidates.empty:
            norm_name = name.replace(" ", "")
            norm_stops = stops["stop_name"].astype(str).str.replace(" ", "", regex=False)
            candidates = stops[norm_stops.str.contains(norm_name, regex=False, na=False)]
        if candidates.empty:
            chosen = nearest_stop(stops, row["origin_lat"], row["origin_lon"])
        else:
            chosen = nearest_stop(candidates, row["origin_lat"], row["origin_lon"])
        sid = str(chosen["stop_id"])
        if sid not in used:
            selected.append(sid)
            used.add(sid)
    if len(selected) < 2:
        for _, chosen in stops.assign(
            dist=(stops["stop_lat"] - row["origin_lat"]).pow(2)
            + ((stops["stop_lon"] - row["origin_lon"]) * math.cos(math.radians(row["origin_lat"]))).pow(2)
        ).sort_values("dist").head(4).iterrows():
            sid = str(chosen["stop_id"])
            if sid not in used:
                selected.append(sid)
                used.add(sid)
            if len(selected) >= 2:
                break
    return selected


def append_gtfs_rows(corridors: pd.DataFrame, destinations: dict[str, dict]) -> pd.DataFrame:
    stops = pd.read_csv(SCENARIO_DIR / "stops.txt", dtype={"stop_id": str})
    stop_by_id = stops.set_index("stop_id")
    boardings = commute_boardings_by_stop_name()
    routes_rows = []
    trips_rows = []
    stop_times_rows = []
    freq_rows = []
    metadata_rows = []

    for idx, row in enumerate(corridors.itertuples(index=False), start=1):
        row = pd.Series(row._asdict())
        dest = destinations[row["destination_sandan_id"]]
        dest_stop_id = f"SCN_DST_{row['destination_sandan_id']}"
        stops = pd.concat(
            [
                stops,
                pd.DataFrame(
                    [
                        {
                            "stop_id": dest_stop_id,
                            "stop_name": f"가상_{dest['name']}",
                            "stop_lat": dest["lat"],
                            "stop_lon": dest["lon"],
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        origin_stop_ids = representative_stop_ids(row, stop_by_id.reset_index())
        middle_stops = select_middle_stop_ids(row, stop_by_id.reset_index(), dest, origin_stop_ids, boardings)
        stop_ids = origin_stop_ids + [s["stop_id"] for s in middle_stops] + [dest_stop_id]
        route_id = f"SCN_EXPRESS_{idx}"
        trip_id = f"T_{route_id}"
        routes_rows.append(
            {
                "route_id": route_id,
                "agency_id": "ULSAN",
                "route_short_name": f"가상급행{idx}",
                "route_type": 3,
            }
        )
        trips_rows.append({"route_id": route_id, "service_id": "WD", "trip_id": trip_id})
        elapsed = 0
        seq_meta = []
        for seq, sid in enumerate(stop_ids, start=1):
            if seq > 1:
                prev = stop_by_id.loc[stop_ids[seq - 2]] if stop_ids[seq - 2] in stop_by_id.index else stops[stops.stop_id == stop_ids[seq - 2]].iloc[0]
                cur = stop_by_id.loc[sid] if sid in stop_by_id.index else stops[stops.stop_id == sid].iloc[0]
                km = haversine_km(prev.stop_lat, prev.stop_lon, cur.stop_lat, cur.stop_lon)
                elapsed += int(round(km / SPEED_KMPH * 3600)) + DWELL_SECONDS
            ts = seconds_to_time(elapsed)
            stop_times_rows.append(
                {
                    "trip_id": trip_id,
                    "arrival_time": ts,
                    "departure_time": ts,
                    "stop_id": sid,
                    "stop_sequence": seq,
                }
            )
            cur_stop = stops[stops.stop_id == sid].iloc[0]
            seq_meta.append(f"{sid}:{cur_stop.stop_name}")
        freq_rows.append(
            {
                "trip_id": trip_id,
                "start_time": "07:00:00",
                "end_time": "09:00:00",
                "headway_secs": 900,
            }
        )
        metadata_rows.append(
            {
                "corridor_id": row["corridor_id"],
                "destination_sandan_id": row["destination_sandan_id"],
                "route_id": route_id,
                "trip_id": trip_id,
                "middle_stop_count": len(middle_stops),
                "middle_stops": " · ".join(
                    f"{s['stop_name']}({s['commute_boardings_07_09']})" for s in middle_stops
                ),
                "additional_cover_boardings_07_09": sum(s["commute_boardings_07_09"] for s in middle_stops),
                "stop_sequence": " -> ".join(seq_meta),
            }
        )

    stops.to_csv(SCENARIO_DIR / "stops.txt", index=False, quoting=csv.QUOTE_MINIMAL)
    for filename, rows in [
        ("routes.txt", routes_rows),
        ("trips.txt", trips_rows),
        ("stop_times.txt", stop_times_rows),
        ("frequencies.txt", freq_rows),
    ]:
        existing = pd.read_csv(SCENARIO_DIR / filename)
        pd.concat([existing, pd.DataFrame(rows)], ignore_index=True).to_csv(
            SCENARIO_DIR / filename, index=False, quoting=csv.QUOTE_MINIMAL
        )
    meta = pd.DataFrame(metadata_rows)
    meta.to_csv(OUT / "express_virtual_routes.csv", index=False)
    return meta


def build_gtfs_and_config() -> pd.DataFrame:
    if SCENARIO_DIR.exists():
        shutil.rmtree(SCENARIO_DIR)
    shutil.copytree(GTFS_DIR, SCENARIO_DIR)

    corridors = pd.read_csv(OUT / "solutions_corridors.csv", encoding="utf-8-sig")
    corridors = corridors[corridors["corridor_id"].isin(TOP_CORRIDORS)].copy()
    corridors["order"] = corridors["corridor_id"].map({cid: i for i, cid in enumerate(TOP_CORRIDORS)})
    corridors = corridors.sort_values("order")
    meta = append_gtfs_rows(corridors, read_destinations())

    if SCENARIO_ZIP.exists():
        SCENARIO_ZIP.unlink()
    with zipfile.ZipFile(SCENARIO_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SCENARIO_DIR.glob("*.txt")):
            zf.write(path, path.name)

    cfg = yaml.safe_load((ROOT / "config" / "ulsan_sandan.yaml").read_text(encoding="utf-8"))
    cfg["inputs"]["gtfs"] = str(SCENARIO_ZIP.relative_to(ROOT))
    SCENARIO_CFG.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return meta


def compare_results() -> pd.DataFrame:
    before = pd.read_csv(OUT / "sandan_accessibility_by_stop.csv")
    after = pd.read_csv(EXPRESS_ACCESS)
    v9_access_path = OUT / "scenario_accessibility_by_stop.csv"
    v9_access = pd.read_csv(v9_access_path) if v9_access_path.exists() else None
    corridors = pd.read_csv(OUT / "solutions_corridors.csv", encoding="utf-8-sig")
    corridors = corridors[corridors["corridor_id"].isin(TOP_CORRIDORS)].copy()
    corridors["order"] = corridors["corridor_id"].map({cid: i for i, cid in enumerate(TOP_CORRIDORS)})
    corridors = corridors.sort_values("order")

    rows = []
    for row in corridors.itertuples(index=False):
        representative_names = [
            name.strip() for name in str(row.representative_stops).split("·") if name.strip()
        ]
        origin_ids = before.loc[before["name"].isin(representative_names), "id"].tolist()
        joined = (
            before[before["id"].isin(origin_ids)][["id", "name", "demand", row.destination_sandan_id]]
            .rename(columns={row.destination_sandan_id: "before"})
            .merge(
                after[after["id"].isin(origin_ids)][["id", row.destination_sandan_id]].rename(
                    columns={row.destination_sandan_id: "after"}
                ),
                on="id",
                how="inner",
            )
        )
        if v9_access is not None:
            joined = joined.merge(
                v9_access[v9_access["id"].isin(origin_ids)][["id", row.destination_sandan_id]].rename(
                    columns={row.destination_sandan_id: "v9_direct_after"}
                ),
                on="id",
                how="left",
            )
        valid = joined.dropna(subset=["before", "after"])
        valid = valid[valid["demand"] > 0]
        weight = valid["demand"]
        before_min = (valid["before"] * weight).sum() / weight.sum()
        after_min = (valid["after"] * weight).sum() / weight.sum()
        v9_direct_after = None
        if "v9_direct_after" in valid.columns:
            v9_valid = valid.dropna(subset=["v9_direct_after"])
            if not v9_valid.empty:
                v9_direct_after = (v9_valid["v9_direct_after"] * v9_valid["demand"]).sum() / v9_valid["demand"].sum()
        improved = int((valid["after"] < valid["before"]).sum())
        result = {
            "corridor_id": row.corridor_id,
            "origin_area": row.origin_area,
            "destination_sandan_id": row.destination_sandan_id,
            "destination_sandan": row.destination_sandan,
            "representative_stop_count": len(representative_names),
            "valid_origin_stop_count": int(len(valid)),
            "weighted_demand": int(weight.sum()),
            "before_access_min": round(before_min, 1),
            "after_access_min": round(after_min, 1),
            "saved_min": round(before_min - after_min, 1),
            "improved_origin_stops": improved,
        }
        if v9_direct_after is not None:
            result["v9_direct_after_access_min"] = round(v9_direct_after, 1)
            result["v10_minus_v9_after_min"] = round(after_min - v9_direct_after, 1)
        rows.append(result)
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "express_corridor_comparison.csv", index=False)
    return out


def write_report(meta: pd.DataFrame, comparison: pd.DataFrame) -> None:
    meta_by_corridor = meta.set_index("corridor_id")
    lines = [
        "# 산단 가상 급행 통근버스 R5 시나리오 결과",
        "",
        "본 결과는 원본 `gtfs.zip`을 변경하지 않고 `experiments/sandan/gtfs_sandan_scenario.zip` 사본에 가상 급행 통근버스 3개를 추가한 뒤, `r5py`/R5 `TravelTimeMatrix` 실제 출력(`express_accessibility_by_stop.csv`)으로 재계산한 before/after 비교다.",
        "",
        "## 공통 가정",
        "",
        "- 운행일: `WD` calendar, 분석일 2026-06-15 포함",
        "- 운행시간: 07:00-09:00",
        "- 배차: 15분(`frequencies.txt` headway 900초)",
        "- 주행시간: 정류장간 직선거리 / 평속 35km/h + 정차 30초",
        "- 중간정류장: 출발권역-산단 직선경로 1.5km buffer 안 실제 GTFS 정류장 중 07-09시 승차 상위, 경로순 정렬",
        "- 비교권역: `solutions_corridors.csv`의 대표 출발정류장 4곳",
        "",
        "## Corridor별 접근분",
        "",
        "| corridor | 목적 산단 | 대표 출발정류장 | 중간정차 | 추가커버 07-09 | before | after | 단축 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in comparison.itertuples(index=False):
        m = meta_by_corridor.loc[r.corridor_id]
        lines.append(
            f"| `{r.corridor_id}` | {r.destination_sandan} | {r.valid_origin_stop_count}/{r.representative_stop_count} | "
            f"{int(m.middle_stop_count)} | {int(m.additional_cover_boardings_07_09):,} | "
            f"{r.before_access_min:.1f}분 | {r.after_access_min:.1f}분 | {r.saved_min:.1f}분 |"
        )
    if "v10_minus_v9_after_min" in comparison.columns:
        deltas = comparison.dropna(subset=["v10_minus_v9_after_min"])
        if not deltas.empty:
            delta_text = "; ".join(
                f"{r.corridor_id} {r.v10_minus_v9_after_min:+.1f}분"
                for r in deltas.itertuples(index=False)
            )
            lines.extend(
                [
                    "",
                    f"v9 순수직행 대비 v10 급행 after는 중간정차 반영으로 현실적으로 늘었다: {delta_text}.",
                ]
            )
    lines.extend(
        [
            "",
            "## 가상 급행 노선",
            "",
            "| corridor | route_id | 중간정류장(07-09 승차) | stop sequence |",
            "|---|---|---|---|",
        ]
    )
    for r in meta.itertuples(index=False):
        lines.append(f"| `{r.corridor_id}` | `{r.route_id}` | {r.middle_stops} | {r.stop_sequence} |")
    lines.extend(
        [
            "",
            "## 한계",
            "",
            "- 수요전환, 차량/운영비, 도로 혼잡, 실제 정류장 승하차 용량은 반영하지 않았다.",
            "- 산단 목적지는 config 대표좌표이며, 가상 목적 정류장은 해당 좌표에 둔 임시 GTFS 정류장이다.",
            "- 출발권역 접근분은 corridor CSV의 대표 출발정류장명과 수요 정류장명을 매칭해 수요가중 평균으로 산출했다.",
        ]
    )
    (OUT / "EXPRESS_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    meta = build_gtfs_and_config()
    print(f"[scenario] wrote {SCENARIO_ZIP.relative_to(ROOT)}")
    print(f"[scenario] wrote {SCENARIO_CFG.relative_to(ROOT)}")
    print("[scenario] virtual express routes:")
    for r in meta.itertuples(index=False):
        print(f"  {r.corridor_id}: {r.stop_sequence}")

    if EXPRESS_ACCESS.exists():
        comparison = compare_results()
        write_report(meta, comparison)
        print("[scenario] comparison/report updated")


if __name__ == "__main__":
    main()
