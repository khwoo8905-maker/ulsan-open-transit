#!/usr/bin/env python3
"""수요 × 접근성 진단 (ATOM r5py).
각 수요 정류장에서 주요 거점까지 버스+도보 소요시간 계산 → 실수요(승하차)와 교차.
'수요 큰데 거점 접근 나쁜 정류장' = 개선 우선순위. 정류장별 결과 저장.
"""
import json, datetime
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from r5py import TransportNetwork, TravelTimeMatrix, TransportMode

BASE = "/home/atom/ulsan-sim"

# 주요 거점 (lon, lat)
HUBS = {
    "시청": (129.3114, 35.5384),
    "공업탑": (129.3186, 35.5316),
    "KTX울산역": (129.1389, 35.5519),
    "태화강역": (129.3389, 35.5497),
    "현대자동차": (129.3897, 35.5167),
    "현대중공업": (129.4275, 35.4942),
    "대학병원": (129.4194, 35.5392),
}

print("수요 정류장 로드...", flush=True)
demand = json.load(open(f"{BASE}/demand_stops_geo.json"))  # [name, ride, goff, la, lo]
df = pd.DataFrame(demand, columns=["name", "ride", "goff", "lat", "lon"])
df["sid"] = ["D%04d" % i for i in range(len(df))]
origins = gpd.GeoDataFrame(df.assign(id=df.sid),
    geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326")
dests = gpd.GeoDataFrame({"id": list(HUBS)},
    geometry=[Point(lon, lat) for lon, lat in HUBS.values()], crs="EPSG:4326")

print("네트워크 빌드(OSM+GTFS)...", flush=True)
net = TransportNetwork(f"{BASE}/ulsan.osm.pbf", [f"{BASE}/gtfs.zip"])
print("빌드 완료. 접근성 계산...", flush=True)

ttm = TravelTimeMatrix(net, origins=origins, destinations=dests,
    departure=datetime.datetime(2026, 6, 15, 8, 0),
    transport_modes=[TransportMode.TRANSIT, TransportMode.WALK])
tt = pd.DataFrame(ttm)  # from_id, to_id, travel_time

# 정류장별 거점 소요시간 피벗
piv = tt.pivot(index="from_id", columns="to_id", values="travel_time")
res = df.set_index("sid").join(piv)
# 도심(시청/공업탑) 접근성 = 둘 중 빠른 쪽
res["도심분"] = res[["시청", "공업탑"]].min(axis=1)
res["거점최소분"] = res[list(HUBS)].min(axis=1)
res["수요"] = res["ride"] + res["goff"]

# 우선순위 점수: 수요 높고 도심 접근 느릴수록 ↑ (도달불가는 90분 처리)
res["도심분_f"] = res["도심분"].fillna(90).clip(upper=90)
res["우선순위"] = res["수요"] * res["도심분_f"]

out = res.reset_index()[["name", "수요", "ride", "goff", "도심분", "거점최소분", "우선순위"]]
out = out.sort_values("우선순위", ascending=False)
out.to_csv(f"{BASE}/diagnose_result.csv", index=False)

print(f"\n=== 진단: 수요 큰데 도심 접근 느린 정류장 TOP20 ===", flush=True)
print(f"(전체 {len(out)}개 정류장, 평일 08시 기준)\n", flush=True)
for _, r in out.head(20).iterrows():
    dc = f"{r['도심분']:.0f}분" if pd.notna(r["도심분"]) else "도달불가"
    print(f"  수요 {int(r['수요']):5,}  도심 {dc:>6}  {r['name']}", flush=True)

# 요약 통계
reachable = res["도심분"].notna()
print(f"\n도심 도달가능 정류장: {reachable.sum()}/{len(res)}", flush=True)
print(f"수요가중 평균 도심소요: {(res['수요']*res['도심분_f']).sum()/res['수요'].sum():.1f}분", flush=True)
# 도심 30분 초과인데 수요 상위 정류장 = 사각지대
far = res[(res["도심분_f"] > 30)].sort_values("수요", ascending=False)
print(f"\n도심 30분 초과 & 고수요 정류장 TOP10 (교통 사각지대 후보):", flush=True)
for _, r in far.head(10).iterrows():
    print(f"  수요 {int(r['수요']):5,}  도심 {r['도심분_f']:.0f}분  {r['name']}", flush=True)
