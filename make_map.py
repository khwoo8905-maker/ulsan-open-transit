#!/usr/bin/env python3
"""울산 수요×접근성 지도 (folium HTML). ATOM에서 실행.
정류장 원: 크기=수요(승하차합), 색=도심접근분(초록 빠름→빨강 느림/도달불가).
좌표 클린업: 울산 bbox 밖 = 이름충돌 아티팩트로 제외.
"""
import json, csv
import folium
import pandas as pd

BASE = "/home/atom/ulsan-sim"
# 울산 대략 bbox
LAT0, LAT1, LON0, LON1 = 35.30, 35.80, 128.95, 129.55

geo = json.load(open(f"{BASE}/demand_stops_geo.json"))  # name,ride,goff,lat,lon
df = pd.DataFrame(geo, columns=["name", "ride", "goff", "lat", "lon"])
df["수요"] = df.ride + df.goff

# 클린업: bbox 밖 제외
before = len(df)
df = df[(df.lat.between(LAT0, LAT1)) & (df.lon.between(LON0, LON1))].copy()
print(f"클린업: {before} → {len(df)}개 (bbox 밖 {before-len(df)}개 제외)", flush=True)

# 접근성 병합
diag = pd.read_csv(f"{BASE}/diagnose_result.csv")
df = df.merge(diag[["name", "도심분"]], on="name", how="left")


def color(m):
    if pd.isna(m):
        return "#444444"  # 도달불가
    if m <= 20: return "#1a9850"
    if m <= 35: return "#91cf60"
    if m <= 50: return "#fee08b"
    if m <= 65: return "#fc8d59"
    return "#d73027"


m = folium.Map(location=[35.54, 129.31], zoom_start=11, tiles="cartodbpositron")
for _, r in df.iterrows():
    dm = r["도심분"]
    label = f"{r['name']}<br>수요 {int(r['수요']):,}<br>도심 {'%.0f분'%dm if pd.notna(dm) else '도달불가'}"
    folium.CircleMarker(
        location=[r.lat, r.lon],
        radius=max(3, min(20, (r["수요"] ** 0.5) / 4)),
        color=color(dm), fill=True, fill_color=color(dm), fill_opacity=0.7,
        weight=0.5, popup=folium.Popup(label, max_width=200),
    ).add_to(m)

# 거점 마커
HUBS = {"시청": (35.5384, 129.3114), "공업탑": (35.5316, 129.3186),
        "KTX울산역": (35.5519, 129.1389), "태화강역": (35.5497, 129.3389),
        "현대차": (35.5167, 129.3897), "현대중공업": (35.4942, 129.4275)}
for nm, (la, lo) in HUBS.items():
    folium.Marker([la, lo], popup=nm, icon=folium.Icon(color="blue", icon="star")).add_to(m)

out = f"{BASE}/ulsan_demand_access_map.html"
m.save(out)
print(f"지도 저장: {out} ({len(df)}개 정류장)", flush=True)
