#!/usr/bin/env python3
"""울산 급행노선 시나리오 탐색 (ATOM r5py).
(A) 노선 탐색: 고수요·원거리 앵커 → 시청 코리도 급행을 N개 생성,
각 시나리오의 도시 전역 수요가중 시청 접근성 개선(분)을 측정해 랭킹.
baseline 1회 계산 + 멀티프로세스 병렬(워커당 JVM heap 캡).
"""
import sys, os, json, math, time, zipfile, argparse, random
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE = "/home/atom/ulsan-sim"
CENTER = (35.5384, 129.3114)  # 시청 (lat, lon)
HEAP = os.environ.get("R5_HEAP", "3500M")


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------- 워커 (r5py) ----------------
_W = {}


def winit(heap):
    # r5py는 import 시 sys.argv에서 --max-memory를 파싱 → import 전에 세팅
    sys.argv = [sys.argv[0], "--max-memory", heap]
    # 워커별 캐시 격리: 공유 ~/.cache/r5py 레이스/잔재 오염 방지 (XDG_CACHE_HOME은 r5py가 존중)
    cdir = f"/tmp/r5cache_{os.getpid()}"
    os.makedirs(cdir, exist_ok=True)
    os.environ["XDG_CACHE_HOME"] = cdir
    import datetime
    import geopandas as gpd
    from shapely.geometry import Point
    from r5py import TransportNetwork, TravelTimeMatrix, TransportMode
    _W["mods"] = (TransportNetwork, TravelTimeMatrix, TransportMode)
    stops = pd.read_csv(f"{BASE}/gtfs/stops.txt")
    _W["sid2ll"] = {r.stop_id: (r.stop_lat, r.stop_lon) for r in stops.itertuples()}
    gb = {}
    with zipfile.ZipFile(f"{BASE}/gtfs.zip") as z:
        for n in z.namelist():
            gb[n] = z.read(n)
    _W["gtfs"] = gb
    geo = json.load(open(f"{BASE}/demand_stops_geo.json"))
    dg = pd.DataFrame(geo, columns=["name", "ride", "goff", "lat", "lon"])
    dg["demand"] = dg.ride + dg.goff
    dg["id"] = ["E%04d" % i for i in range(len(dg))]
    _W["dg"] = dg
    _W["origins"] = gpd.GeoDataFrame(dg, geometry=gpd.points_from_xy(dg.lon, dg.lat), crs="EPSG:4326")
    _W["dest"] = gpd.GeoDataFrame({"id": ["시청"]}, geometry=[Point(CENTER[1], CENTER[0])], crs="EPSG:4326")
    _W["dep"] = datetime.datetime(2026, 6, 15, 8, 0)


def _ttm(gtfs_path):
    TransportNetwork, TravelTimeMatrix, TransportMode = _W["mods"]
    net = TransportNetwork(f"{BASE}/ulsan.osm.pbf", [gtfs_path])
    m = TravelTimeMatrix(net, origins=_W["origins"], destinations=_W["dest"],
                         departure=_W["dep"], transport_modes=[TransportMode.TRANSIT, TransportMode.WALK])
    return pd.DataFrame(m).set_index("from_id")["travel_time"]


def _make_express_zip(idx, corridor_ids, path):
    gb = dict(_W["gtfs"])
    sid2ll = _W["sid2ll"]
    rid = f"EXP{idx}"
    gb["routes.txt"] = gb["routes.txt"] + f"\n{rid},ULSAN,급행{idx},3".encode()
    seq = [(sid, sid2ll[sid][0], sid2ll[sid][1]) for sid in corridor_ids]
    trips, st = [], []
    for direction, order in [(0, seq), (1, seq[::-1])]:
        for minute in range(6 * 60, 22 * 60, 10):
            trip = f"{rid}_{direction}_{minute}"
            trips.append(f"{rid},WD,{trip}")
            t = float(minute)
            for i, (sid, lat, lon) in enumerate(order):
                if i > 0:
                    _, plat, plon = order[i - 1]
                    km = haversine(plat, plon, lat, lon)
                    t += max(2, km / 30 * 60)
                hh, mm = divmod(int(round(t)), 60)
                ts = f"{hh:02d}:{mm:02d}:00"
                st.append(f"{trip},{ts},{ts},{sid},{i + 1}")
    gb["trips.txt"] = gb["trips.txt"] + ("\n" + "\n".join(trips)).encode()
    gb["stop_times.txt"] = gb["stop_times.txt"] + ("\n" + "\n".join(st)).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in gb.items():
            z.writestr(n, b)


def task_baseline(_):
    t0 = time.time()
    s = _ttm(f"{BASE}/gtfs.zip")
    return {"series": s.to_dict(), "secs": round(time.time() - t0, 1)}


def task_scen(arg):
    idx, corridor_ids, corridor_names, base = arg
    try:
        return _run_scen(idx, corridor_ids, corridor_names, base)
    except Exception as e:  # 시나리오 1개 실패가 풀 전체를 죽이지 않게
        return {"idx": idx, "corridor": " → ".join(corridor_names), "wbefore": None,
                "wafter": None, "saved_min": -999.0, "n_improved": 0,
                "demand_min_saved": 0.0, "top": f"ERROR: {type(e).__name__}: {e}", "secs": 0.0}


def _run_scen(idx, corridor_ids, corridor_names, base):
    path = f"/tmp/gtfs_scn_{os.getpid()}_{idx}.zip"
    _make_express_zip(idx, corridor_ids, path)
    t0 = time.time()
    after = _ttm(path)
    dt = round(time.time() - t0, 1)
    dg = _W["dg"].set_index("id")
    res = pd.DataFrame({"demand": dg["demand"], "name": dg["name"],
                        "before": pd.Series(base), "after": after})
    f = res.dropna(subset=["before", "after"])
    f = f[f["demand"] > 0]
    wb = (f.before * f.demand).sum() / f.demand.sum()
    wa = (f.after * f.demand).sum() / f.demand.sum()
    imp = f.assign(saved=f.before - f.after)
    nimp = int((imp.saved >= 1).sum())
    pop = float((imp.saved.clip(lower=0) * imp.demand).sum())
    top = imp.sort_values("saved", ascending=False).head(3)[["name", "saved"]].values.tolist()
    try:
        os.remove(path)
    except OSError:
        pass
    return {"idx": idx, "corridor": " → ".join(corridor_names),
            "wbefore": round(wb, 2), "wafter": round(wa, 2), "saved_min": round(wb - wa, 2),
            "n_improved": nimp, "demand_min_saved": round(pop, 0),
            "top": "; ".join(f"{n}({s:+.0f})" for n, s in top), "secs": dt}


# ---------------- 생성기 (main, r5py 불필요) ----------------
def to_xy(lat, lon):
    x = math.radians(lon - CENTER[1]) * math.cos(math.radians(CENTER[0])) * 6371
    y = math.radians(lat - CENTER[0]) * 6371
    return x, y


def seg_dist(px, py, ax, ay):
    L2 = ax * ax + ay * ay
    if L2 == 0:
        return math.hypot(px, py), 0.0
    t = (px * ax + py * ay) / L2
    tc = max(0.0, min(1.0, t))
    return math.hypot(px - tc * ax, py - tc * ay), t


def build_scenarios(N, seed=42):
    stops = pd.read_csv(f"{BASE}/gtfs/stops.txt")
    sx, sy = stops.stop_lon.values, stops.stop_lat.values
    sid = stops.stop_id.values

    def nearest_sid(lat, lon):
        d = (sx - lon) ** 2 * math.cos(math.radians(lat)) ** 2 + (sy - lat) ** 2
        return sid[int(np.argmin(d))]

    geo = json.load(open(f"{BASE}/demand_stops_geo.json"))
    dg = pd.DataFrame(geo, columns=["name", "ride", "goff", "lat", "lon"])
    dg["demand"] = dg.ride + dg.goff
    dg["dc"] = [haversine(r.lat, r.lon, *CENTER) for r in dg.itertuples()]
    dg["x"], dg["y"] = zip(*[to_xy(r.lat, r.lon) for r in dg.itertuples()])

    anchors = dg[(dg.dc > 5) & (dg.dc < 45)].sort_values("demand", ascending=False).head(120)
    anchors = anchors.to_dict("records")
    center_sid = nearest_sid(*CENTER)
    rng = random.Random(seed)
    out = []
    tries = 0
    while len(out) < N and tries < N * 20:
        tries += 1
        a = rng.choice(anchors)
        ax, ay = a["x"], a["y"]
        # 앵커→시청 코리도 버퍼(1.2km) 내, 앵커보다 도심에 가까운 고수요 정류장
        cand = []
        for r in dg.itertuples():
            if r.dc >= a["dc"] - 1 or r.dc < 2:
                continue
            d, t = seg_dist(r.x, r.y, ax, ay)
            if d < 1.2 and 0.05 < t < 0.95:
                cand.append((r.demand, r.name, r.lat, r.lon, t))
        cand.sort(reverse=True)
        cand = cand[:10]
        k = rng.randint(1, min(3, len(cand))) if cand else 0
        inter = rng.sample(cand, k) if k else []
        # 코리도 구성: 앵커 + 경유 + 시청, 도심거리 내림차순 정렬
        nodes = [(a["dc"], nearest_sid(a["lat"], a["lon"]), a["name"])]
        for dem, nm, lat, lon, t in inter:
            nodes.append((haversine(lat, lon, *CENTER), nearest_sid(lat, lon), nm))
        nodes.append((0.0, center_sid, "시청"))
        nodes.sort(key=lambda z: -z[0])
        ids, names, seen = [], [], set()
        for _, s, nm in nodes:
            if s in seen:
                continue
            seen.add(s)
            ids.append(s)
            names.append(nm)
        if len(ids) < 2:
            continue
        out.append((len(out), ids, names))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--num", type=int, default=100)
    ap.add_argument("-w", "--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=f"{BASE}/scenario_results.csv")
    args = ap.parse_args()

    # 이전 실행 캐시 잔재 청소 (r5py 공유 캐시 오염 방지)
    import shutil, glob
    shutil.rmtree(os.path.expanduser("~/.cache/r5py"), ignore_errors=True)
    for d in glob.glob("/tmp/r5cache_*"):
        shutil.rmtree(d, ignore_errors=True)
    for z in glob.glob("/tmp/gtfs_scn_*.zip"):
        try:
            os.remove(z)
        except OSError:
            pass

    print(f"[gen] 시나리오 {args.num}개 생성...", flush=True)
    scen = build_scenarios(args.num, args.seed)
    print(f"[gen] {len(scen)}개 생성 완료", flush=True)

    ctx_workers = max(1, args.workers)
    with ProcessPoolExecutor(max_workers=ctx_workers, initializer=winit, initargs=(HEAP,)) as ex:
        print("[base] baseline 계산...", flush=True)
        base = ex.submit(task_baseline, 0).result()
        print(f"[base] 완료 {base['secs']}s (정류장 {len(base['series'])}개)", flush=True)
        bser = base["series"]

        results = []
        futs = {ex.submit(task_scen, (i, ids, names, bser)): i for i, ids, names in scen}
        done = 0
        t0 = time.time()
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 5 == 0 or done == len(scen):
                el = time.time() - t0
                eta = el / done * (len(scen) - done)
                print(f"[{done}/{len(scen)}] best={max(x['saved_min'] for x in results):+.1f}분 "
                      f"경과{el:.0f}s ETA{eta:.0f}s", flush=True)
            # 증분 저장
            pd.DataFrame(sorted(results, key=lambda z: -z["saved_min"])).to_csv(args.out, index=False)

    errs = [r for r in results if r["saved_min"] == -999.0]
    if errs:
        print(f"[warn] 실패 시나리오 {len(errs)}개 (예: {errs[0]['top']})", flush=True)
    df = pd.DataFrame(sorted(results, key=lambda z: -z["saved_min"]))
    df.to_csv(args.out, index=False)
    print(f"\n=== 상위 10개 시나리오 (도시 전역 수요가중 시청접근 단축) ===", flush=True)
    for _, r in df.head(10).iterrows():
        print(f"  {r['saved_min']:+5.1f}분  사람·분{r['demand_min_saved']:>10,.0f}  개선{r['n_improved']:>4}곳  | {r['corridor']}", flush=True)
    print(f"\n→ {args.out} 저장 ({len(df)}행)", flush=True)


if __name__ == "__main__":
    main()
