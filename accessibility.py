#!/usr/bin/env python3
"""울산 대중교통 다목적지 접근성 진단 (config 기반).
시청 단일 목적지 가정을 버리고, 생활권 거점 N개(config/ulsan.yaml)까지의 접근성을 측정.
정류장별: 각 거점 소요시간 + 최단거점시간(min_to_any) + 평균거점시간 + 45분내 도달거점수.
도시 전역: 수요가중 평균 + 거점별 사각지대 TOP.
도시 교체 = config 한 파일 + 입력 데이터만 바꾸면 동일하게 재실행.
"""
import sys, json, argparse, datetime
from pathlib import Path
import yaml
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from r5py import TransportNetwork, TravelTimeMatrix, TransportMode

MODES = {"TRANSIT": TransportMode.TRANSIT, "WALK": TransportMode.WALK,
         "BICYCLE": TransportMode.BICYCLE, "CAR": TransportMode.CAR}


def load_config(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config/ulsan.yaml")
    ap.add_argument("--base", default=".", help="입력 데이터 루트")
    ap.add_argument("--out", default="accessibility_by_stop.csv")
    args = ap.parse_args()

    cfg = load_config(args.config)
    base = Path(args.base)
    an = cfg["analysis"]
    dests = cfg["destinations"]
    crs = cfg.get("crs", "EPSG:4326")
    dep = datetime.datetime.fromisoformat(an["departure"])
    modes = [MODES[m] for m in an["modes"]]
    within = an.get("within_min", 45)

    print(f"[cfg] {cfg['city']} | 거점 {len(dests)}개 | 출발 {dep} | 모드 {an['modes']}", flush=True)

    # 출발지 = 수요 정류장 (좌표+수요)
    geo = json.load(open(base / cfg["inputs"]["demand"]))
    dg = pd.DataFrame(geo, columns=["name", "ride", "goff", "lat", "lon"])
    dg["demand"] = dg.ride + dg.goff
    dg["id"] = ["E%04d" % i for i in range(len(dg))]
    origins = gpd.GeoDataFrame(dg, geometry=gpd.points_from_xy(dg.lon, dg.lat), crs=crs)

    # 도착지 = 생활권 거점
    dest = gpd.GeoDataFrame(
        {"id": [d["id"] for d in dests]},
        geometry=[Point(d["lon"], d["lat"]) for d in dests], crs=crs)

    print("[net] 네트워크 빌드(OSM+GTFS)...", flush=True)
    net = TransportNetwork(str(base / cfg["inputs"]["osm_pbf"]), [str(base / cfg["inputs"]["gtfs"])])
    print("[ttm] 접근성 행렬 계산...", flush=True)
    m = TravelTimeMatrix(net, origins=origins, destinations=dest, departure=dep, transport_modes=modes)

    # wide: 행=정류장, 열=거점별 소요(분)
    wide = m.pivot(index="from_id", columns="to_id", values="travel_time")
    dcols = [d["id"] for d in dests]
    wide = wide.reindex(columns=dcols)

    res = dg.set_index("id").join(wide)
    res["min_to_any"] = res[dcols].min(axis=1)
    res["mean_to_centers"] = res[dcols].mean(axis=1)
    res["n_within"] = (res[dcols] <= within).sum(axis=1)

    res.reset_index().to_csv(base / args.out, index=False)

    # ---- 도시 전역 요약 (수요가중) ----
    r = res[res.demand > 0].dropna(subset=["min_to_any"])
    w = r.demand
    wmin = (r.min_to_any * w).sum() / w.sum()
    wmean = (r.mean_to_centers * w).sum() / w.sum()
    print(f"\n=== {cfg['city']} 다목적지 접근성 (수요가중, 평일 {dep:%H:%M}) ===", flush=True)
    print(f"  최단거점 평균: {wmin:.1f}분 | 전거점 평균: {wmean:.1f}분 | 거점 {len(dcols)}개", flush=True)
    print(f"  45분내 도달 거점수 분포(수요가중 평균): {(r.n_within*w).sum()/w.sum():.1f}/{len(dcols)}개", flush=True)
    hist = (r.assign(b=r.n_within).groupby("b").apply(lambda x: int(x.demand.sum()), include_groups=False))
    tot = int(w.sum())
    print("  도달 거점수별 수요 비중:", flush=True)
    for b in range(len(dcols) + 1):
        v = int(hist.get(b, 0))
        if v:
            print(f"    {b}개 거점: {v/tot*100:4.1f}% ({v:,}명)", flush=True)

    # ---- 거점별 수요가중 평균 + 사각지대 ----
    print(f"\n=== 거점별 수요가중 접근시간 + 30분초과 고수요 사각지대 ===", flush=True)
    name_by_id = {d["id"]: d["name"] for d in dests}
    cat_by_id = {d["id"]: d["category"] for d in dests}
    for did in dcols:
        rr = res.dropna(subset=[did])
        rr = rr[rr.demand > 0]
        wm = (rr[did] * rr.demand).sum() / rr.demand.sum()
        far = rr[rr[did] > 30].sort_values("demand", ascending=False).head(3)
        tops = "; ".join(f"{n}({int(t)}분/{int(d):,})" for n, t, d in
                         zip(far.name, far[did], far.demand))
        print(f"  [{cat_by_id[did]:<7}] {name_by_id[did]:<12} 수요가중 {wm:4.1f}분  | 사각: {tops}", flush=True)

    print(f"\n→ {args.out} 저장 ({len(res)}행)", flush=True)


if __name__ == "__main__":
    main()
