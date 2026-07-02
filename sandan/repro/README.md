# 재현 재료 (repro)

산단 접근성 진단·급행 시뮬의 산출물과 입력을 그대로 둔 폴더입니다.

- `sandan_accessibility_{0600,0800,2200}_by_stop.csv` — 시간대별 R5 정류장×산단 접근분 (진단 원출력)
- `express_accessibility_{25,30,35}kph_by_stop.csv` — 가상 급행 투입 후 R5 재계산 출력 (평속 3안)
- `express_corridor_comparison.csv` / `express_speed_sensitivity.csv` — corridor별 before/after 정정 집계 (문서 표의 진실원)
- `express_virtual_routes.csv` — 가상 급행 노선 정의
- `solutions_corridors.csv` — corridor 후보 18개 상세
- `corrected_headline_stats.csv` — 헤드라인 정정 통계
- `time_window_*.csv` — 교대시간대 집계
- `parking_area_summary.csv` — 불법주정차 단속 권역 집계 (참고용)
- `demand_stops_geo.json` — 정류장 좌표+일수요 (가중치 입력, 2025-11-07 평일)
- `ulsan_sandan_*.yaml` — R5 시나리오 설정 (시간대·평속별)
- `gtfs_sandan_*.zip` — 가상 급행이 추가된 시나리오 GTFS 사본 (원본 gtfs.zip 불변)
- `run_r5_scenario.py` — 시나리오 GTFS 생성+R5 실행 스크립트. ※ 원 위치(`experiments/sandan/`) 기준 상대경로를 쓰므로 그대로 실행하려면 repo 루트에 `experiments/sandan/`으로 두고 돌려야 합니다.

집계 정의·모집단은 [../CORRECTED_STATS.md](../CORRECTED_STATS.md) 참고.

## 온산(onsan_1) 추가 시뮬 (별도 시나리오)

- `onsan_express_accessibility_{25,30,35}kph_by_stop.csv` — 온산 급행 투입 후 R5 출력
- `onsan_express_comparison.csv` — 온산 before/after 수요가중 집계 (v11 동일 기준)
- `onsan_express_virtual_routes_*.csv` / `gtfs_sandan_onsan_*.zip` — 온산 가상노선 정의·시나리오 GTFS
- `run_r5_onsan.py` / `compare_onsan.py` — 격리 실행·집계 스크립트 (설정: `config/ulsan_sandan_onsan_*.yaml`)
