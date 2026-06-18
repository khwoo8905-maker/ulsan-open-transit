#!/usr/bin/env python3
"""우리 수집 데이터(routes_stops.json + routes_meta.json) → GTFS v1 생성.
시뮬레이터(r5py) 입력용. 모델링 근사:
  - stop_times: 정류장간 거리/평속(18km/h)으로 소요시간 추정
  - frequencies: 노선종류별 기본 배차(간선15/지선30/마을·외곽60분) — 추후 실시간 데이터로 정밀화
  - calendar: 평일 서비스
출력: gtfs/ 폴더 (txt 6종) + gtfs.zip
⚠️ 실측 시각표 아님 = 모델 추정. 리포트에 명시.
"""
import json, csv, math, zipfile, re
from pathlib import Path

BASE = Path(__file__).parent
G = BASE / "gtfs"; G.mkdir(exist_ok=True)
SPEED_MPS = 18 * 1000 / 3600  # 18km/h 평속(정차 포함 도시버스 근사)
HEADWAY = {"간선버스": 900, "지선버스": 1800, "광역버스": 1800, "마을버스": 3600, "공영버스": 3600}
DEFAULT_HEADWAY = 1800


def hav(a, b, c, d):
    R = 6371000; p = math.radians
    x = math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(d - b) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def hms(sec):
    sec = int(sec); return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"


def to_sec(v):
    s = str(v).zfill(4); return int(s[:2]) * 3600 + int(s[2:]) * 60


def main():
    routes = json.load(open(BASE / "data" / "routes_stops.json", encoding="utf-8"))
    meta = {r["routeid"]: r for r in json.load(open(BASE / "data" / "routes_meta.json", encoding="utf-8"))}

    # 전역 정류장 dedup (좌표 5자리)
    stopid = {}  # (rla,rlo) -> sid
    stops = []   # sid, name, la, lo
    def get_sid(nm, la, lo):
        k = (round(la, 5), round(lo, 5))
        if k not in stopid:
            sid = f"S{len(stopid)+1:05d}"; stopid[k] = sid
            stops.append((sid, nm, la, lo))
        return stopid[k]

    trips_rows, st_rows, freq_rows, route_rows = [], [], [], []
    for d in routes:
        seq = d["stops"]
        if len(seq) < 3:
            continue
        rid = d["routeid"]; rno = str(d.get("routeno")); rtp = d.get("routetp", "")
        route_rows.append((rid, rno, rtp))
        tid = f"T_{rid}"
        m = meta.get(rid, {})
        sv = m.get("startvehicletime"); ev = m.get("endvehicletime")
        start = to_sec(sv) if sv else 6 * 3600
        end = to_sec(ev) if ev else 22 * 3600
        if end <= start:
            end += 24 * 3600
        trips_rows.append((rid, tid, "WD"))
        # stop_times: 누적거리/평속
        t = 0.0
        for i, s in enumerate(seq):
            sid = get_sid(s["nm"], s["la"], s["lo"])
            if i > 0:
                t += hav(seq[i-1]["la"], seq[i-1]["lo"], s["la"], s["lo"]) / SPEED_MPS + 20  # +정차 20s
            st_rows.append((tid, hms(t), hms(t), sid, i + 1))
        hw = HEADWAY.get(rtp, DEFAULT_HEADWAY)
        freq_rows.append((tid, hms(start), hms(end), hw))

    # 파일 쓰기
    def w(fn, header, rows):
        with open(G / fn, "w", newline="", encoding="utf-8") as f:
            cw = csv.writer(f); cw.writerow(header); cw.writerows(rows)

    w("agency.txt", ["agency_id", "agency_name", "agency_url", "agency_timezone"],
      [["ULSAN", "울산시내버스", "https://its.ulsan.kr", "Asia/Seoul"]])
    w("stops.txt", ["stop_id", "stop_name", "stop_lat", "stop_lon"],
      [[s[0], s[1], f"{s[2]:.6f}", f"{s[3]:.6f}"] for s in stops])
    w("routes.txt", ["route_id", "agency_id", "route_short_name", "route_type"],
      [[r[0], "ULSAN", r[1], "3"] for r in route_rows])  # 3=bus
    w("trips.txt", ["route_id", "service_id", "trip_id"],
      [[t[0], t[2], t[1]] for t in trips_rows])
    w("stop_times.txt", ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
      st_rows)
    w("frequencies.txt", ["trip_id", "start_time", "end_time", "headway_secs"],
      [[f[0], f[1], f[2], f[3]] for f in freq_rows])
    w("calendar.txt", ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
      [["WD", 1, 1, 1, 1, 1, 0, 0, "20260601", "20261231"]])

    # zip
    with zipfile.ZipFile(BASE / "gtfs.zip", "w") as z:
        for fn in ["agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt", "frequencies.txt", "calendar.txt"]:
            z.write(G / fn, fn)
    print(f"GTFS 생성: 정류장 {len(stops)}, 노선 {len(route_rows)}, stop_times {len(st_rows)}행")
    print(f"→ {G}/ + gtfs.zip")


if __name__ == "__main__":
    main()
