#!/usr/bin/env python3
"""개편(2024-12-21) 전/후 승하차 비교 분석.
공정비교 원칙: 같은 요일·공휴일 제외·계절 매칭. 기본 쌍 = 2024-11-01(금) vs 2025-11-07(금).
- 전체 총승차 변화
- 구별 변화
- 노선별 증감 TOP (개편 수혜/피해 노선 식별)
주의: 1년 간격이라 개편효과 외 일반 추세도 섞임 → 단정 아닌 "관찰" 톤으로 리포트.
출력: data/reform_compare.json + 콘솔 요약.
"""
import json
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
PRE = "20241101"   # 금, 개편 전
POST = "20251107"  # 금, 개편 후(계절·요일 매칭)


def load(ymd):
    fp = BASE / "data" / f"demand_{ymd}.jsonl"
    recs = [json.loads(l) for l in fp.read_text().splitlines()]
    return recs


def agg(recs):
    total_ride = total_goff = 0
    by_gu = defaultdict(int)
    by_route = defaultdict(int)         # rte_nm -> 승차
    route_id2nm = {}
    for r in recs:
        ride = int(r.get("ride") or 0)
        goff = int(r.get("goff") or 0)
        total_ride += ride
        total_goff += goff
        by_gu[r["gu"]] += ride
        rid = r.get("rte_id")
        by_route[rid] += ride
        route_id2nm[rid] = r.get("rte_nm")
    return {"total_ride": total_ride, "total_goff": total_goff,
            "by_gu": dict(by_gu), "by_route": dict(by_route), "names": route_id2nm}


def pct(a, b):
    return (b - a) / a * 100 if a else float("nan")


def main():
    pre, post = agg(load(PRE)), agg(load(POST))
    print(f"=== 개편 전후 비교: {PRE}(금) → {POST}(금) ===\n")
    print(f"[전체 총승차] {pre['total_ride']:,} → {post['total_ride']:,}  ({pct(pre['total_ride'],post['total_ride']):+.1f}%)")
    print(f"[전체 총하차] {pre['total_goff']:,} → {post['total_goff']:,}  ({pct(pre['total_goff'],post['total_goff']):+.1f}%)\n")

    print("[구별 승차 변화]")
    for gu in ["중구", "남구", "동구", "북구", "울주"]:
        a, b = pre["by_gu"].get(gu, 0), post["by_gu"].get(gu, 0)
        print(f"  {gu}: {a:,} → {b:,}  ({pct(a,b):+.1f}%)")

    # 노선별 증감 (양쪽 다 존재하는 노선만 비율비교 + 신설/폐지 별도)
    names = {**pre["names"], **post["names"]}
    rows = []
    for rid in set(pre["by_route"]) | set(post["by_route"]):
        a, b = pre["by_route"].get(rid, 0), post["by_route"].get(rid, 0)
        rows.append((names.get(rid, rid), a, b, b - a))
    gained = sorted([r for r in rows if r[1] > 0], key=lambda x: -x[3])[:15]
    lost = sorted([r for r in rows if r[1] > 0], key=lambda x: x[3])[:15]
    new_routes = [r for r in rows if r[1] == 0 and r[2] > 0]
    gone_routes = [r for r in rows if r[2] == 0 and r[1] > 0]

    print(f"\n[승차 급증 노선 TOP15]")
    for nm, a, b, d in gained:
        print(f"  {nm}: {a:,} → {b:,}  ({d:+,})")
    print(f"\n[승차 급감 노선 TOP15]")
    for nm, a, b, d in lost:
        print(f"  {nm}: {a:,} → {b:,}  ({d:+,})")
    print(f"\n[개편 후 신설(전0→후有): {len(new_routes)}개]  [사라짐(전有→후0): {len(gone_routes)}개]")

    out = {"pre": PRE, "post": POST,
           "total_ride": [pre["total_ride"], post["total_ride"]],
           "by_gu": {gu: [pre["by_gu"].get(gu, 0), post["by_gu"].get(gu, 0)]
                     for gu in ["중구", "남구", "동구", "북구", "울주"]},
           "gained_top": [(nm, a, b, d) for nm, a, b, d in gained],
           "lost_top": [(nm, a, b, d) for nm, a, b, d in lost],
           "n_new": len(new_routes), "n_gone": len(gone_routes)}
    (BASE / "data" / "reform_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("\n→ data/reform_compare.json 저장")


if __name__ == "__main__":
    main()
