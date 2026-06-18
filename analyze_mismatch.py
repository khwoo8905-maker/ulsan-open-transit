#!/usr/bin/env python3
"""수요-공급 미스매치 분석 (데이터 없인 못 보는 인사이트).
승하차 데이터만으로:
  A. 노선별 효율 — 일 승객수, 정류장당 승객. 저수요(텅 빈 채 도는) 노선 식별.
  B. 정류장별 수요 vs 경유 노선 수 — 고수요인데 노선 적음(과소공급) / 저수요인데 노선 많음(과잉).
중립 원칙: '후보'까지만. 저수요=커버리지·형평성일 수 있음(단정 금지).
"""
import json
from collections import defaultdict

SRC = "data/demand_20251107.jsonl"
route = defaultdict(lambda: {"nm": "", "dem": 0, "stops": set()})
stop = defaultdict(lambda: {"nm": "", "dem": 0, "routes": set(), "gu": ""})

for l in open(SRC):
    r = json.loads(l)
    d = int(r["ride"] or 0) + int(r["goff"] or 0)
    rid, sid = r["rte_id"], r["sttn_id"]
    route[rid]["nm"] = r["rte_nm"]; route[rid]["dem"] += d; route[rid]["stops"].add(sid)
    stop[sid]["nm"] = r["sttn_nm"]; stop[sid]["dem"] += d; stop[sid]["routes"].add(rid)
    stop[sid]["gu"] = r["gu"]

n_routes, n_stops = len(route), len(stop)
tot_dem = sum(v["dem"] for v in route.values())
print(f"노선 {n_routes}개 / 정류장 {n_stops}개 / 총 통행 {tot_dem:,}\n")

# 집중도
rd = sorted((v["dem"] for v in route.values()), reverse=True)
top10 = sum(rd[:max(1, n_routes // 10)])
print(f"[집중도] 상위 10% 노선({max(1,n_routes//10)}개)이 전체 통행의 {top10*100//tot_dem}% 담당\n")

# A. 노선별 효율 = 정류장당 일 승객 (낮을수록 '도는데 승객 적음')
rows = []
for rid, v in route.items():
    ns = len(v["stops"])
    if ns < 3:
        continue
    rows.append((v["nm"], v["dem"], ns, v["dem"] / ns))
print("=== A. 저효율 후보: 정류장당 승객 최저 노선 TOP15 (운행 대비 승객 적음) ===")
for nm, dem, ns, eff in sorted(rows, key=lambda x: x[3])[:15]:
    print(f"  정류장당 {eff:5.1f}명 | 총 {dem:5,} | 정류장 {ns:3d} | {nm}")

print("\n=== A-2. 일 통행 최저 노선 TOP10 (절대 승객 적음) ===")
for nm, dem, ns, eff in sorted(rows, key=lambda x: x[1])[:10]:
    print(f"  총 {dem:5,} | 정류장 {ns:3d} | {nm}")

# B. 정류장: 수요 vs 노선수
srows = []
for sid, v in stop.items():
    nr = len(v["routes"])
    srows.append((v["nm"], v["gu"], v["dem"], nr, v["dem"] / nr))
print("\n=== B. 과소공급 후보: 고수요인데 경유 노선 적은 정류장 (노선당 승객 최고) ===")
# 수요 상위 40% 중 노선당 승객 높은 = 적은 노선이 많은 수요 감당
srows_sorted = sorted(srows, key=lambda x: -x[2])
hi = srows_sorted[:int(len(srows) * 0.4)]
for nm, gu, dem, nr, per in sorted(hi, key=lambda x: -x[4])[:15]:
    print(f"  노선당 {per:5.0f}명 | 수요 {dem:5,} | 노선 {nr:2d}개 | {gu} {nm}")

print("\n=== B-2. 과잉공급 후보: 저수요인데 노선 많은 정류장 (노선당 승객 최저) ===")
lo = [s for s in srows if s[3] >= 8]  # 노선 8개 이상인데
for nm, gu, dem, nr, per in sorted(lo, key=lambda x: x[4])[:12]:
    print(f"  노선당 {per:4.0f}명 | 수요 {dem:4,} | 노선 {nr:2d}개 | {gu} {nm}")
