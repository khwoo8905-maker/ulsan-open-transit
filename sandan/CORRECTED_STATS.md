# 울산 산단 v11 정정 통계

기준 파일: `sandan_accessibility_summary.csv`. 접근분은 산단별 정류장 수요가중 R5 결과(`weighted_access_min`)다.

## 헤드라인 정정

| 지표 | 값 |
|---|---:|
| 29개 단순평균(기존 91.6의 실제 정의) | 91.6분 |
| 고용>0 산단 단순평균 | 92.4분 |
| 고용>0 산단 고용가중 평균 | 86.7분 |
| 고용>0 & 좌표검증(상/중) 산단 고용가중 평균 | 86.7분 |
| 고용>0 & 좌표검증(상/중) 45분내 | 0 / 14 |
| 고용>0 & 좌표검증(상/중) 60분내 | 0 / 14 |

## 모집단 정의

- 전체 산단: 29개.
- 고용>0 산단: 20개.
- 핵심 유효 산단: 고용>0이고 `coord_confidence`가 상/중인 14개.
- 고용 0 또는 공백 산단: 9개, 핵심 집계에서 제외.

## 고용 0/공백 산단

- `doha` 울산도하일반산업단지: employment=0, coord=미검증
- `automotive_nammok` 자동차일반산업단지[구:남목]: employment=0, coord=미검증
- `daedae` 대대일반산업단지: employment=0, coord=미검증
- `ktx_station_area` 울산KT역세권일반산업단지: employment=0, coord=미검증
- `jakdong` 작동: employment=0, coord=미검증
- `muggerbon` 머거본: employment=0, coord=미검증
- `cheongyang` 청양: employment=0, coord=미검증
- `ihwa` 이화: employment=공백, coord=미검증
- `janghyeon` 울산장현: employment=공백, coord=미검증

## 고용>0이나 좌표 미검증으로 핵심 집계 제외

- `maegok3` 매곡3: employment=756, coord=미검증
- `gw` GW: employment=549, coord=미검증
- `mobile_tech_valley` 모바일테크밸리: employment=569, coord=미검증
- `jungsan` 중산: employment=364, coord=미검증
- `jeoneup` 전읍: employment=82, coord=미검증
- `maegok2` 매곡2: employment=170, coord=미검증

## 급행 평속 민감도: 미포 corridor

동일 before(`repro/sandan_accessibility_0800_by_stop.csv`), 동일 대표정류장 4곳, 동일 수요가중 기준.

| 평속 | before | after | 단축 |
|---:|---:|---:|---:|
| 25km/h | 109.8분 | 46.3분 | 63.4분 |
| 30km/h | 109.8분 | 43.0분 | 66.8분 |
| 35km/h | 109.8분 | 39.7분 | 70.1분 |

미포 단축폭 범위: 63.4-70.1분.
