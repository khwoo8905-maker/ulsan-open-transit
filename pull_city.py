#!/usr/bin/env python3
"""벤치마크 도시 노선 구조 수집 (울산과 동일 지표 비교용). TAGO BusRouteInfoInqireService.
사용: python3 pull_city.py <cityCode> <약칭>
출력: data/<약칭>_routes_stops.json (울산 routes_stops.json과 동일 구조)
"""
import urllib.request, urllib.parse, json, sys, time
from pathlib import Path

BASE = Path(__file__).parent
KEY = (BASE / ".env").read_text().split("=", 1)[1].strip()
CITY = sys.argv[1] if len(sys.argv) > 1 else "38010"
TAG = sys.argv[2] if len(sys.argv) > 2 else "changwon"
B = "https://apis.data.go.kr/1613000/BusRouteInfoInqireService"


def get(ep, params, tries=5):
    qs = "serviceKey=" + urllib.parse.quote(KEY, safe="") + "&" + urllib.parse.urlencode(params)
    for t in range(tries):
        try:
            with urllib.request.urlopen(f"{B}/{ep}?{qs}", timeout=30) as r:
                d = json.load(r)
            body = d["response"]["body"]
            it = body.get("items", {})
            it = it.get("item", []) if it else []
            return [it] if isinstance(it, dict) else it, int(body.get("totalCount", 0) or 0)
        except Exception:
            time.sleep(1.5)
    return [], 0


def main():
    # 전체 노선 목록 (페이징)
    routes, page = [], 1
    while True:
        items, total = get("getRouteNoList", {"cityCode": CITY, "_type": "json",
                                              "numOfRows": 200, "pageNo": page})
        routes += items
        if page * 200 >= total or not items:
            break
        page += 1
        time.sleep(0.3)
    print(f"{TAG}({CITY}) 노선 {len(routes)}개. 경유정류소 수집...", flush=True)

    out = []
    for i, rt in enumerate(routes, 1):
        rid = rt.get("routeid")
        stops, p = [], 1
        while True:
            items, total = get("getRouteAcctoThrghSttnList",
                               {"cityCode": CITY, "routeId": rid, "_type": "json",
                                "numOfRows": 500, "pageNo": p})
            for s in items:
                stops.append({"ord": s.get("nodeord"), "nm": s.get("nodenm"),
                              "la": s.get("gpslati"), "lo": s.get("gpslong")})
            if p * 500 >= total or not items:
                break
            p += 1
        out.append({"routeid": rid, "routeno": rt.get("routeno"),
                    "routetp": rt.get("routetp"), "stops": stops})
        if i % 50 == 0:
            print(f"  {i}/{len(routes)}", flush=True)
        time.sleep(0.2)
    (BASE / "data" / f"{TAG}_routes_stops.json").write_text(
        json.dumps(out, ensure_ascii=False))
    print(f"완료: {len(out)}노선 → {TAG}_routes_stops.json", flush=True)


if __name__ == "__main__":
    main()
