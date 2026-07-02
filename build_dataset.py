#!/usr/bin/env python3
"""공개 데이터셋 패키징 — 페르소나 데이터셋 방식(담백·정확·재현가능).
작업 파일들 → dataset/ 깨끗한 CSV + 데이터셋 카드.
"""
import json, csv, math, glob
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
OUT = BASE / "dataset"
OUT.mkdir(exist_ok=True)


def hav(a, b, c, d):
    R = 6371000; p = math.radians
    x = math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(d - b) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def oneway(s):
    if hav(s[0]["la"], s[0]["lo"], s[-1]["la"], s[-1]["lo"]) < 800 and len(s) > 6:
        far = max(range(len(s)), key=lambda i: hav(s[0]["la"], s[0]["lo"], s[i]["la"], s[i]["lo"]))
        if far >= 2:
            return s[:far + 1]
    return s


# 1) routes.csv — 노선 구조 지표 (편도 정규화)
routes = json.load(open(BASE / "data" / "routes_stops.json"))
n_route_rows = 0
with open(OUT / "routes.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["route_id", "route_no", "route_type", "n_stops", "length_km", "detour"])
    for d in routes:
        s = [{"la": float(x["la"]), "lo": float(x["lo"]), "nm": x["nm"]}
             for x in d["stops"] if x.get("la") and x.get("lo") and x["nm"]]
        if len(s) < 3:
            continue
        s1 = oneway(s)
        path = sum(hav(s1[i]["la"], s1[i]["lo"], s1[i + 1]["la"], s1[i + 1]["lo"]) for i in range(len(s1) - 1))
        pts = [(x["la"], x["lo"]) for x in s1]
        diam = max((hav(*pts[i], *pts[j]) for i in range(0, len(pts), 3) for j in range(i + 1, len(pts), 3)), default=0)
        detour = round(path / diam, 2) if diam > 500 else ""
        w.writerow([d["routeid"], d["routeno"], d.get("routetp", ""), len(s1),
                    round(path / 1000, 2), detour])
        n_route_rows += 1

# 2) stops_demand.csv — 정류장 좌표 + 실수요 (평일 기준)
geo = json.load(open(BASE / "data" / "demand_stops_geo.json"))
with open(OUT / "stops_demand.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["stop_name", "lat", "lon", "boardings", "alightings"])
    for nm, ride, goff, la, lo in geo:
        if 35.30 <= la <= 35.80 and 128.95 <= lo <= 129.55:
            w.writerow([nm, round(la, 6), round(lo, 6), ride, goff])

# 3) accessibility.csv — 다목적지 접근성 진단 (생활권 거점 8개)
#    원천 = accessibility_by_stop.csv (accessibility.py + config/ulsan.yaml 산출)
#    평일 08시, r5py(TRANSIT+WALK). 모델 추정배차 → 절대 分은 근사, 상대 순위·패턴이 메시지.
HUBS = [  # (원본 컬럼키, 공개 컬럼명) — config/ulsan.yaml 거점 순서와 일치
    ("cityhall",   "min_cityhall"),     # 시청·행정
    ("samsan",     "min_samsan"),       # 삼산·현대백화점(상업)
    ("taehwagang", "min_taehwagang"),   # 태화강역(철도환승)
    ("ulsanuniv",  "min_ulsanuniv"),    # 울산대학교(교육)
    ("hhi",        "min_hhi"),          # 현대중공업(동부·고용)
    ("uuh",        "min_uuh"),          # 울산대학교병원(동부·의료)
    ("ktx",        "min_ktx"),          # KTX울산역(광역·서부)
    ("eonyang",    "min_eonyang"),      # 언양터미널(광역·서부)
]
acc = list(csv.DictReader(open(BASE / "accessibility_by_stop.csv", encoding="utf-8")))
with open(OUT / "accessibility.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["stop_id", "stop_name", "lat", "lon", "boardings", "alightings", "demand"]
               + [pub for _, pub in HUBS]
               + ["min_to_any_hub", "mean_to_hubs", "hubs_within_45min"])
    for r in acc:
        w.writerow([r["id"], r["name"], r["lat"], r["lon"], r["ride"], r["goff"], r["demand"]]
                   + [r[key] for key, _ in HUBS]
                   + [r["min_to_any"], r["mean_to_centers"], r["n_within"]])

# 4) demand_hourly_sample.csv — 정류장·시간대·유형별 승하차 (대표 평일 1일)
n = 0
with open(OUT / "demand_hourly.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "district", "route_name", "stop_name", "stop_seq", "hour", "user_type", "boardings", "alightings"])
    for l in open(BASE / "data" / "demand_20251107.jsonl"):
        r = json.loads(l)
        w.writerow([r["ymd"], r["gu"], r["rte_nm"], r["sttn_nm"], r["sttn_seq"],
                    r["tzon"], r["utype"], r["ride"], r["goff"]])
        n += 1

print(f"dataset/ 생성: routes.csv({n_route_rows}행) / stops_demand.csv / accessibility.csv / demand_hourly.csv({n}행)")
for p in sorted(OUT.glob("*.csv")):
    print(f"  {p.name}: {p.stat().st_size//1024}KB")
