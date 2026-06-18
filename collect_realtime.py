#!/usr/bin/env python3
"""울산 버스 실시간 위치 수집 (정시성·배차 실측용). TAGO BusLcInfoInqireService.
핵심노선 ~25개를 5분 간격으로 종일 폴링 → data/realtime_YYYYMMDD.jsonl 누적.
quota: 25노선 × 12/h × 18h ≈ 5,400/일 (개발키 1만 한도 내 안전).
선정: 최장 10 + 최우회 10 + 간선 샘플. (전수 아님 = quota 한계, 무엇을 봤는지 로그 남김)
"""
import urllib.request, urllib.parse, json, time, math
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
KEY = (BASE / ".env").read_text().split("=", 1)[1].strip()
EP = "https://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList"
KST = timezone(timedelta(hours=9))
INTERVAL = 360  # 6분(노선 37개라 한도여유 확보)
MUST_NOS = {'1421','314','318','513','523','1115','713','743','753'}  # 민원·이슈 노선(김상욱: 만차/구영리/UNIST)


def hav(a, b, c, d):
    R = 6371000; p = math.radians
    x = math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(d - b) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def pick_targets():
    routes = json.load(open(BASE / "data" / "routes_stops.json", encoding="utf-8"))
    feat = []
    for d in routes:
        s = d["stops"]
        if len(s) < 5:
            continue
        path = sum(hav(s[i]["la"], s[i]["lo"], s[i + 1]["la"], s[i + 1]["lo"]) for i in range(len(s) - 1))
        diam = 0
        pts = [(x["la"], x["lo"]) for x in s]
        for i in range(0, len(pts), 2):
            for j in range(i + 1, len(pts), 2):
                dd = hav(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
                if dd > diam: diam = dd
        detour = path / diam if diam > 500 else 0
        feat.append({"rid": d["routeid"], "no": d["routeno"], "tp": d.get("routetp"),
                     "km": path / 1000, "detour": detour})
    must = [f for f in feat if str(f['no']) in MUST_NOS]
    longest = sorted(feat, key=lambda x: -x["km"])[:10]
    windy = sorted([f for f in feat if f["detour"] < 50], key=lambda x: -x["detour"])[:10]
    trunk = [f for f in feat if f.get("tp") == "간선버스"][:8]
    seen, targets = set(), []
    for f in must + longest + windy + trunk:
        if f["rid"] not in seen:
            seen.add(f["rid"]); targets.append(f)
    return targets


def call(rid, tries=6):
    qs = "serviceKey=" + urllib.parse.quote(KEY, safe="") + "&" + urllib.parse.urlencode(
        {"cityCode": "26", "routeId": rid, "_type": "json", "numOfRows": "200", "pageNo": "1"})
    for t in range(tries):
        try:
            with urllib.request.urlopen(f"{EP}?{qs}", timeout=20) as r:
                d = json.loads(r.read().decode())
            if d.get("response", {}).get("header", {}).get("resultCode") == "00":
                it = d["response"]["body"].get("items", {})
                it = it.get("item", []) if it else []
                return [it] if isinstance(it, dict) else it
        except Exception:
            pass
        time.sleep(1.5)
    return None


def main():
    targets = pick_targets()
    print(f"수집 노선 {len(targets)}개: " + ", ".join(str(t["no"]) for t in targets), flush=True)
    print(f"간격 {INTERVAL}s (날짜별 파일 자동 롤오버)", flush=True)
    cycle = 0
    # 운영시간만(05~24시), 그 외엔 대기 줄임
    while True:
        h = datetime.now(KST).hour
        if h < 5:  # 새벽 운휴 시간 폴링 의미없음 → 30분 슬립
            time.sleep(1800); continue
        cycle += 1
        ts = datetime.now(KST).isoformat()
        out = BASE / "data" / f"realtime_{datetime.now(KST).strftime('%Y%m%d')}.jsonl"  # 매 사이클 날짜 반영(자정 롤오버)
        n_veh = 0
        with open(out, "a", encoding="utf-8") as f:
            for t in targets:
                buses = call(t["rid"])
                if not buses:
                    continue
                for v in buses:
                    rec = {"ts": ts, "routeno": t["no"], "rid": t["rid"],
                           "veh": v.get("vehicleno"), "nodeord": v.get("nodeord"),
                           "nodenm": v.get("nodenm"), "la": v.get("gpslati"), "lo": v.get("gpslong")}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_veh += 1
        print(f"[{ts[11:16]}] cycle{cycle}: {n_veh}대 위치 기록", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
