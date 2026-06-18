#!/usr/bin/env python3
"""울산(cityCode=26) 버스 노선 전수 수집 + 굴곡도/중복도 진단.
TAGO BusRouteInfoInqireService:
  - getRouteNoList: 노선 목록
  - getRouteAcctoThrghSttnList: 노선별 경유정류소(순서+좌표)
키 전파 간헐(200/403)이라 호출당 재시도. 출력: data/routes_stops.json + 콘솔 리포트.
"""
import urllib.request, urllib.parse, json, time, math
from pathlib import Path

BASE = Path(__file__).parent
KEY = (BASE / ".env").read_text().split("=", 1)[1].strip()
EP = "https://apis.data.go.kr/1613000/BusRouteInfoInqireService"


def call(op, params, tries=15):
    qs = "serviceKey=" + urllib.parse.quote(KEY, safe="") + "&" + urllib.parse.urlencode(
        {**{"cityCode": "26", "_type": "json", "numOfRows": "1000", "pageNo": "1"}, **params})
    url = f"{EP}/{op}?{qs}"
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("response", {}).get("header", {}).get("resultCode") == "00":
                return d["response"]["body"]
        except Exception:
            pass
        time.sleep(1.5)
    return None


def items_of(body):
    if not body:
        return []
    it = body.get("items", {})
    if not it:
        return []
    it = it.get("item", [])
    return [it] if isinstance(it, dict) else it


def hav(la1, lo1, la2, lo2):
    R = 6371000; p = math.radians
    dla = p(la2 - la1); dlo = p(lo2 - lo1)
    x = math.sin(dla / 2) ** 2 + math.cos(p(la1)) * math.cos(p(la2)) * math.sin(dlo / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def main():
    print("=== 1) 노선 목록 ===", flush=True)
    routes = []
    page = 1
    while True:
        body = call("getRouteNoList", {"pageNo": str(page)})
        its = items_of(body)
        routes += its
        total = int(body.get("totalCount", 0)) if body else 0
        print(f"  page{page}: +{len(its)} (누적 {len(routes)}/{total})", flush=True)
        if len(routes) >= total or not its:
            break
        page += 1
    # 중복 routeid 제거
    uniq = {r["routeid"]: r for r in routes if r.get("routeid")}
    routes = list(uniq.values())
    print(f"총 노선 {len(routes)}개", flush=True)

    print("\n=== 2) 노선별 경유정류소 수집 ===", flush=True)
    data = []
    for i, r in enumerate(routes, 1):
        rid = r["routeid"]
        body = call("getRouteAcctoThrghSttnList", {"routeId": rid})
        stops = items_of(body)
        seq = []
        for s in stops:
            try:
                seq.append({"ord": int(s.get("nodeord", 0)), "nm": s.get("nodenm", ""),
                            "la": float(s["gpslati"]), "lo": float(s["gpslong"])})
            except Exception:
                pass
        seq.sort(key=lambda x: x["ord"])
        data.append({"routeid": rid, "routeno": r.get("routeno"), "routetp": r.get("routetp"),
                     "start": r.get("startnodenm"), "end": r.get("endnodenm"), "stops": seq})
        if i % 20 == 0:
            print(f"  {i}/{len(routes)} 수집 (마지막 {r.get('routeno')}: {len(seq)}정류소)", flush=True)
    (BASE / "data" / "routes_stops.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"저장: data/routes_stops.json ({len(data)}노선)", flush=True)

    print("\n=== 3) 굴곡도 분석 ===", flush=True)
    rows = []
    for d in data:
        s = d["stops"]
        if len(s) < 3:
            continue
        path = sum(hav(s[i]["la"], s[i]["lo"], s[i + 1]["la"], s[i + 1]["lo"]) for i in range(len(s) - 1))
        straight = hav(s[0]["la"], s[0]["lo"], s[-1]["la"], s[-1]["lo"])
        if straight < 300:  # 순환노선(시종점 거의 같음)은 굴곡도 무의미 → 제외표시
            circ = None
        else:
            circ = path / straight
        rows.append((d["routeno"], len(s), path / 1000, circ, straight < 300))
    graded = [r for r in rows if r[3] is not None]
    graded.sort(key=lambda x: -x[3])
    print(f"분석노선 {len(rows)} (순환형 {sum(1 for r in rows if r[4])} 제외 → 굴곡도산정 {len(graded)})")
    print(f"평균 굴곡도: {sum(r[3] for r in graded)/len(graded):.2f}")
    print("\n[굴곡 심한 노선 TOP 12] (실제경로/직선 — 1.0=직선, 높을수록 빙 돌아감)")
    for no, ns, plen, circ, _ in graded[:12]:
        print(f"  노선 {no}: 굴곡도 {circ:.2f} | 정류소 {ns}개 | 실거리 {plen:.1f}km")

    print("\n=== 4) 노선 중복도(정류소 공유) ===", flush=True)
    from collections import Counter
    stop_routes = {}
    for d in data:
        for s in d["stops"]:
            stop_routes.setdefault(s["nm"], set()).add(d["routeno"])
    overlap = Counter({nm: len(rs) for nm, rs in stop_routes.items()})
    print("[가장 많은 노선이 지나는 정류소 TOP 12] (과밀 코리더 = 중복투자 후보)")
    for nm, cnt in overlap.most_common(12):
        print(f"  {nm}: {cnt}개 노선 경유")


if __name__ == "__main__":
    main()
