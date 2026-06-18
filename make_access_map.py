#!/usr/bin/env python3
"""울산 다목적지 접근성 지도 (config 기반, folium).
accessibility_by_stop.csv + config/ulsan.yaml → 레이어 토글 HTML.
레이어: 최단거점(min_to_any) + 선택 거점별 + 거점 마커. 색=접근시간, 원크기=수요.
도시 교체 = config + csv만 바꾸면 동일 재생성.
"""
import json, argparse
from pathlib import Path
import yaml
import pandas as pd
import folium

# 접근시간(분) → 색: 좋음 초록 ~ 나쁨 빨강
def color(t):
    if pd.isna(t):
        return "#555555"      # 도달불가
    if t <= 15: return "#1a9850"
    if t <= 30: return "#91cf60"
    if t <= 45: return "#fee08b"
    if t <= 60: return "#fc8d59"
    return "#d73027"


def radius(demand):
    return max(2.5, (max(demand, 0) ** 0.5) / 6)


def add_layer(fmap, df, col, label, show=False):
    fg = folium.FeatureGroup(name=label, show=show)
    for r in df.itertuples():
        t = getattr(r, col)
        folium.CircleMarker(
            location=[r.lat, r.lon], radius=radius(r.demand),
            color=color(t), fill=True, fill_color=color(t), fill_opacity=0.7, weight=0.5,
            popup=folium.Popup(f"{r.name}<br>수요 {int(r.demand):,}<br>{label}: "
                               f"{'도달불가' if pd.isna(t) else f'{t:.0f}분'}", max_width=220),
        ).add_to(fg)
    fg.add_to(fmap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config/ulsan.yaml")
    ap.add_argument("--csv", default="accessibility_by_stop.csv")
    ap.add_argument("--out", default="ulsan_access_map.html")
    ap.add_argument("--center-layers", default="uuh,ktx",
                    help="거점별 레이어로 추가할 id (쉼표)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    dests = cfg["destinations"]
    name_by = {d["id"]: d["name"] for d in dests}
    df = pd.read_csv(args.csv)

    lat0 = df.lat.median(); lon0 = df.lon.median()
    m = folium.Map(location=[lat0, lon0], zoom_start=11, tiles="cartodbpositron")

    # 1) 최단거점 접근 (헤드라인, 기본 표시)
    add_layer(m, df, "min_to_any", "① 최단거점 접근(min_to_any)", show=True)
    # 2) 선택 거점별
    for did in [x.strip() for x in args.center_layers.split(",") if x.strip()]:
        if did in df.columns:
            add_layer(m, df, did, f"② {name_by.get(did, did)} 접근", show=False)

    # 거점 마커 (항상 표시)
    fg = folium.FeatureGroup(name="★ 생활권 거점", show=True)
    for d in dests:
        folium.Marker(
            [d["lat"], d["lon"]], tooltip=f"{d['name']} ({d['category']})",
            icon=folium.Icon(color="blue", icon="star", prefix="fa"),
        ).add_to(fg)
    fg.add_to(m)

    # 범례
    legend = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;background:white;
    padding:10px;border:1px solid #888;border-radius:6px;font-size:12px;line-height:1.6">
    <b>접근시간(분)</b><br>
    <span style="color:#1a9850">●</span>≤15 &nbsp;<span style="color:#91cf60">●</span>≤30 &nbsp;
    <span style="color:#fee08b">●</span>≤45 &nbsp;<span style="color:#fc8d59">●</span>≤60 &nbsp;
    <span style="color:#d73027">●</span>&gt;60 &nbsp;<span style="color:#555">●</span>도달불가<br>
    원 크기 = 정류장 승하차 수요 · 평일 08시 기준
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(args.out)
    print(f"→ {args.out} 저장 (정류장 {len(df)}개, 거점 {len(dests)}개)", flush=True)


if __name__ == "__main__":
    main()
