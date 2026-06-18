#!/usr/bin/env python3
"""울산 정류장·노선·시간대별 승하차(수요) 수집. 국가 이용량 API.
RoutebyStopTripVolume/getDailyRoutebyStopTripVolume — ctpv_cd=31(울산), 구 단위.
⚠️ WAF가 curl/기본 UA 차단 → 브라우저 User-Agent 헤더 필수.
개편(2024-12-21) 전/후 날짜 모두 수집 → "개편 전후 비교" 한 방 분석 토대.
출력: data/demand_<opr_ymd>.jsonl (구·노선·정류장·시간대·이용자유형별 ride/goff).
"""
import urllib.request, urllib.parse, json, time, sys
from pathlib import Path

BASE = Path(__file__).parent
KEY = (BASE / ".env").read_text().split("=", 1)[1].strip()
EP = "https://apis.data.go.kr/1613000/RoutebyStopTripVolume/getDailyRoutebyStopTripVolume"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")  # ⚠️WAF 우회 필수
CTPV = "31"  # 울산
SGG = {"31110": "중구", "31140": "남구", "31170": "동구", "31200": "북구", "31710": "울주"}
# 개편 2024-12-21. 전(20241101) / 후(20250301, 20260301)
DATES = ["20241101", "20250301", "20260301"]
ROWS = 1000


def call(sgg, ymd, page, tries=5):
    qs = "serviceKey=" + urllib.parse.quote(KEY, safe="") + "&" + urllib.parse.urlencode(
        {"pageNo": page, "numOfRows": ROWS, "opr_ymd": ymd,
         "ctpv_cd": CTPV, "sgg_cd": sgg, "dataType": "JSON"})
    for t in range(tries):
        try:
            req = urllib.request.Request(f"{EP}?{qs}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read().decode())
            resp = d.get("Response") or d.get("response") or {}
            if resp.get("header", {}).get("resultCode") not in ("200", "00", None):
                pass
            body = resp.get("body", {})
            items = body.get("items", {})
            items = items.get("item", []) if isinstance(items, dict) else items
            if isinstance(items, dict):
                items = [items]
            total = int(body.get("totalCount", 0) or 0)
            return items, total
        except Exception as ex:
            if t == tries - 1:
                print(f"  ! {sgg} {ymd} p{page} 실패: {ex}", flush=True)
            time.sleep(2)
    return None, 0


def main():
    n_calls = 0
    for ymd in DATES:
        out = BASE / "data" / f"demand_{ymd}.jsonl"
        done = set()
        if out.exists():
            for ln in out.read_text().splitlines():
                try:
                    done.add(json.loads(ln)["_k"])
                except Exception:
                    pass
        total_recs = 0
        with open(out, "a", encoding="utf-8") as f:
            for sgg, gu in SGG.items():
                page = 1
                got = 0
                while True:
                    items, total = call(sgg, ymd, page)
                    n_calls += 1
                    if items is None:
                        break
                    for it in items:
                        # 중복키: 노선+정류장순번+시간대+이용유형
                        k = f"{ymd}|{sgg}|{it.get('rte_id')}|{it.get('sttn_seq')}|{it.get('tzon')}|{it.get('users_type_nm')}"
                        if k in done:
                            continue
                        done.add(k)
                        rec = {"_k": k, "ymd": ymd, "sgg": sgg, "gu": gu,
                               "rte_id": it.get("rte_id"), "rte_nm": it.get("rte_nm"),
                               "sttn_id": it.get("sttn_id"), "sttn_nm": it.get("sttn_nm"),
                               "sttn_seq": it.get("sttn_seq"), "tzon": it.get("tzon"),
                               "utype": it.get("users_type_nm"),
                               "ride": it.get("ride_nope"), "goff": it.get("goff_nope")}
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        got += 1
                    f.flush()
                    if page * ROWS >= total or not items:
                        break
                    page += 1
                    time.sleep(0.3)
                print(f"[{ymd}] {gu}({sgg}): {got}건 (total {total})", flush=True)
                total_recs += got
        print(f"=== {ymd} 완료: {total_recs}건 → {out.name}\n", flush=True)
    print(f"총 API 호출 {n_calls}회 (한도 1000/일)", flush=True)


if __name__ == "__main__":
    main()
