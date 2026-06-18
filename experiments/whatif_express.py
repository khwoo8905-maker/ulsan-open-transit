#!/usr/bin/env python3
"""What-if: 동구 남목↔시청 급행버스 신설 시 접근성 개선 시뮬 (ATOM r5py).
기존 GTFS에 급행 노선(정차 최소, 평일 10분 배차) 추가 → 동구 수요 정류장의 시청 소요 before/after 비교.
"""
import json, datetime, shutil, zipfile, os, math
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from r5py import TransportNetwork, TravelTimeMatrix, TransportMode

BASE = "/home/atom/ulsan-sim"
G = f"{BASE}/gtfs"
G2 = f"{BASE}/gtfs_whatif"

stops = pd.read_csv(f"{G}/stops.txt")


# 급행 경유 실제 정류장 (방어진→남목→명촌→공업탑→시청, 동구 사각지대 직결)
CORRIDOR_IDS = ["S00807", "S00883", "S00698", "S00300", "S00333"]
corridor = [stops[stops.stop_id == sid].iloc[0] for sid in CORRIDOR_IDS]
print("급행 경유 정류장:", [s.stop_name for s in corridor], flush=True)

# GTFS 복사 후 급행 추가
if os.path.exists(G2):
    shutil.rmtree(G2)
shutil.copytree(G, G2)

with open(f"{G2}/routes.txt", "a") as f:
    f.write("\nEXP1,ULSAN,급행남목,3")
# 평일 서비스 id 확인
cal = pd.read_csv(f"{G}/calendar.txt")
svc = cal.iloc[0]["service_id"]

trips, stoptimes = [], []
tid = 0
# 06:00~22:00, 10분 배차, 양방향
for direction, seq in [(0, corridor), (1, corridor[::-1])]:
    for minute in range(6 * 60, 22 * 60, 10):
        tid += 1
        trip = f"EXP1_{direction}_{minute}"
        trips.append(f"EXP1,{svc},{trip}")
        t = float(minute)
        for i, s in enumerate(seq):
            if i > 0:  # 직전 정류장과 거리 기반 소요(급행 평속 30km/h)
                p = seq[i - 1]
                R = 6371.0
                dlat = math.radians(s.stop_lat - p.stop_lat)
                dlon = math.radians(s.stop_lon - p.stop_lon)
                a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(p.stop_lat)) * \
                    math.cos(math.radians(s.stop_lat)) * math.sin(dlon / 2) ** 2
                km = 2 * R * math.asin(math.sqrt(a))
                t += max(2, km / 30 * 60)  # 30km/h, 최소 2분
            hh, mm = divmod(int(round(t)), 60)
            ts = f"{hh:02d}:{mm:02d}:00"
            stoptimes.append(f"{trip},{ts},{ts},{s.stop_id},{i+1}")

with open(f"{G2}/trips.txt", "a") as f:
    f.write("\n" + "\n".join(trips))
with open(f"{G2}/stop_times.txt", "a") as f:
    f.write("\n" + "\n".join(stoptimes))

# zip
zpath = f"{BASE}/gtfs_whatif.zip"
with zipfile.ZipFile(zpath, "w") as z:
    for fn in os.listdir(G2):
        z.write(f"{G2}/{fn}", fn)
print(f"급행 추가 GTFS 생성 (trip {len(trips)}개)", flush=True)

# 동구 수요 정류장 (lon>129.40)
geo = json.load(open(f"{BASE}/demand_stops_geo.json"))
dg = pd.DataFrame(geo, columns=["name", "ride", "goff", "lat", "lon"])
dg = dg[(dg.lon > 129.39) & (dg.lat.between(35.45, 35.56))].copy()
dg["수요"] = dg.ride + dg.goff
dg["id"] = ["E%03d" % i for i in range(len(dg))]
print(f"동구권 수요 정류장 {len(dg)}개", flush=True)

origins = gpd.GeoDataFrame(dg.assign(id=dg.id),
    geometry=gpd.points_from_xy(dg.lon, dg.lat), crs="EPSG:4326")
dest = gpd.GeoDataFrame({"id": ["시청"]}, geometry=[Point(129.3114, 35.5384)], crs="EPSG:4326")
dep = datetime.datetime(2026, 6, 15, 8, 0)


def access(gtfs_zip):
    net = TransportNetwork(f"{BASE}/ulsan.osm.pbf", [gtfs_zip])
    ttm = TravelTimeMatrix(net, origins=origins, destinations=dest, departure=dep,
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK])
    return pd.DataFrame(ttm).set_index("from_id")["travel_time"]


print("baseline 계산...", flush=True)
base = access(f"{BASE}/gtfs.zip")
print("급행 추가 후 계산...", flush=True)
new = access(zpath)

dg = dg.set_index("id")
dg["before"] = base
dg["after"] = new
dg["개선"] = dg.before - dg.after
imp = dg.dropna(subset=["before", "after"])
print(f"\n=== 동구권 시청 접근성 (급행 신설 전→후) ===", flush=True)
print(f"수요가중 평균: {(imp['before']*imp['수요']).sum()/imp['수요'].sum():.1f}분 → "
      f"{(imp['after']*imp['수요']).sum()/imp['수요'].sum():.1f}분", flush=True)
top = imp.sort_values("개선", ascending=False).head(12)
print("\n개선 큰 정류장 TOP12:", flush=True)
for _, r in top.iterrows():
    print(f"  {r['before']:.0f}→{r['after']:.0f}분 ({r['개선']:+.0f})  수요{int(r['수요']):,}  {r['name']}", flush=True)
imp.reset_index()[["name", "수요", "before", "after", "개선"]].to_csv(f"{BASE}/whatif_result.csv", index=False)
print("\n→ whatif_result.csv 저장", flush=True)
