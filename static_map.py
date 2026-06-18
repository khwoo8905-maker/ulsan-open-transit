#!/usr/bin/env python3
"""정적 PNG 지도 (폰에서 바로 보이게). ATOM 실행.
정류장 산점도: 크기=수요, 색=도심 접근시간. 한글 폰트 이슈 피하려 영문 라벨.
"""
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = "/home/atom/ulsan-sim"
geo = json.load(open(f"{BASE}/demand_stops_geo.json"))
df = pd.DataFrame(geo, columns=["name", "ride", "goff", "lat", "lon"])
df["demand"] = df.ride + df.goff
df = df[(df.lat.between(35.30, 35.80)) & (df.lon.between(128.95, 129.55))]
diag = pd.read_csv(f"{BASE}/diagnose_result.csv")
df = df.merge(diag[["name", "도심분"]], on="name", how="left")
df["acc"] = df["도심분"].fillna(90).clip(upper=90)

fig, ax = plt.subplots(figsize=(11, 10))
sc = ax.scatter(df.lon, df.lat, s=(df.demand ** 0.5) * 1.6,
                c=df.acc, cmap="RdYlGn_r", vmin=10, vmax=80,
                alpha=0.75, edgecolors="none")
cb = plt.colorbar(sc, ax=ax, shrink=0.7)
cb.set_label("Minutes to downtown by bus  (green=fast, red=slow)", fontsize=11)

HUBS = {"City Hall": (35.5384, 129.3114), "Gongeoptap": (35.5316, 129.3186),
        "KTX Ulsan St.": (35.5519, 129.1389), "Taehwagang St.": (35.5497, 129.3389),
        "Hyundai Motor": (35.5167, 129.3897), "Hyundai Heavy": (35.4942, 129.4275)}
for nm, (la, lo) in HUBS.items():
    ax.scatter(lo, la, marker="*", s=420, c="blue", edgecolors="white", linewidths=1.2, zorder=5)
    ax.annotate(nm, (lo, la), fontsize=9, fontweight="bold", color="navy",
                xytext=(4, 4), textcoords="offset points")

# 사각지대 주석 (영문)
ax.annotate("Dong-gu (Bangeojin)\nhigh demand, slow access",
            (129.42, 35.50), fontsize=10, color="darkred",
            ha="center", bbox=dict(boxstyle="round", fc="white", ec="red", alpha=0.8))
ax.annotate("West (Eonyang)\nfar from downtown",
            (129.16, 35.55), fontsize=10, color="darkred",
            ha="center", bbox=dict(boxstyle="round", fc="white", ec="red", alpha=0.8))

ax.set_title("Ulsan City Bus — Demand (size) x Access to Downtown (color)\nby Dambaek",
             fontsize=13, fontweight="bold")
ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
ax.set_aspect(1.23)
ax.grid(alpha=0.2)
plt.tight_layout()
plt.savefig(f"{BASE}/ulsan_map.png", dpi=140)
print("saved ulsan_map.png")
