#!/usr/bin/env python3
"""온산 급행 corridor(onsan_1) R5 시나리오 — 격리 실행 (기존 산출물 불변).

run_r5_scenario.py를 모듈로 로드해 상수만 온산용으로 패치.
산출물은 전부 onsan_* / *_onsan_* 이름으로 분리, 기존 express_* 파일은 백업 후 복원.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments" / "sandan"

spec = importlib.util.spec_from_file_location("rs", OUT / "run_r5_scenario.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

SPEEDS = [25, 30, 35]
VIRTUAL_ROUTES = OUT / "express_virtual_routes.csv"


def build(speed: int) -> None:
    tag = f"{speed}kph"
    rs.TOP_CORRIDORS = ["onsan_1"]
    rs.MID_STOP_TARGET = {"onsan_1": 3}
    rs.SPEED_KMPH = float(speed)
    rs.SCENARIO_DIR = OUT / f"gtfs_scenario_onsan_{tag}"
    rs.SCENARIO_ZIP = OUT / f"gtfs_sandan_onsan_{tag}.zip"
    rs.SCENARIO_CFG = ROOT / "config" / f"ulsan_sandan_onsan_{tag}.yaml"

    backup = VIRTUAL_ROUTES.read_bytes()  # append_gtfs_rows가 이 파일을 덮어씀
    try:
        meta = rs.build_gtfs_and_config()
        meta.to_csv(OUT / f"onsan_express_virtual_routes_{tag}.csv", index=False)
    finally:
        VIRTUAL_ROUTES.write_bytes(backup)
    print(f"[onsan] built {rs.SCENARIO_ZIP.name}", flush=True)


def run_r5(speed: int) -> None:
    tag = f"{speed}kph"
    out_csv = f"experiments/sandan/onsan_express_accessibility_{tag}_by_stop.csv"
    subprocess.run(
        [sys.executable, str(ROOT / "accessibility.py"),
         "-c", str(ROOT / "config" / f"ulsan_sandan_onsan_{tag}.yaml"),
         "--out", out_csv],
        check=True, cwd=ROOT,
    )
    print(f"[onsan] R5 done {tag}", flush=True)


if __name__ == "__main__":
    for s in SPEEDS:
        build(s)
        run_r5(s)
    print("[onsan] ALL DONE", flush=True)
