"""駕駛人力換算：平日車公里 → 車輛小時 → 約當駕駛班次。
- 平日班次：TDX Schedule（星期三有營運的班次）。
- 營運速率：pilot/data/tdx 沒有 S2STravelTime，桃園班表只有起點發車時刻，無法由班表算行駛時間。
  因此先嘗試由 A1 即時動態樣本估計（同車同路線相鄰兩次輪詢間隔 ≤180 秒的直線位移 ÷ 時間，含停站時間）；
  樣本不足時使用側欄的預設值【假設，可調整】。
- 車輛小時只算行駛時間，未含端點休息、調度空車、場站往返（會低估所需人力）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from . import data as D

MIN_PAIRS = 30  # 每路線至少 30 組相鄰輪詢樣本才採用


@st.cache_data(show_spinner=False)
def _a1_speeds(files: tuple) -> dict:
    raw = D._a1(files) if files else None
    if raw is None or raw.empty or not {"PlateNumb", "lat", "lon"} <= set(raw.columns):
        return {}
    df = raw.copy()
    df["lat"] = pd.to_numeric(df.lat, errors="coerce")
    df["lon"] = pd.to_numeric(df.lon, errors="coerce")
    tcol = "GPSTime" if "GPSTime" in df.columns else "poll_time"
    df["t"] = pd.to_datetime(df[tcol], errors="coerce", utc=True, format="ISO8601")
    df = df.dropna(subset=["lat", "lon", "t"])
    if df.empty:
        return {}
    import pyproj
    x, y = pyproj.Transformer.from_crs(4326, D.CRS_M, always_xy=True).transform(df.lon.values, df.lat.values)
    df["x"], df["y"] = x, y
    sub = "SubRouteUID" if "SubRouteUID" in df.columns else "RouteUID"
    df["dir"] = pd.to_numeric(df.get("Direction", 0), errors="coerce").fillna(0).astype(int)
    df = df.drop_duplicates(["PlateNumb", "t"]).sort_values(["PlateNumb", "t"])
    out = {}
    g = df.groupby("PlateNumb")
    dt = g.t.diff().dt.total_seconds()
    dd = np.hypot(g.x.diff(), g.y.diff())
    same = (df[sub] == g[sub].shift()) & (df["dir"] == g["dir"].shift())
    ok = same & dt.between(30, 180) & (dd < 3000)
    P = pd.DataFrame({"key": df[sub].astype(str) + "-" + df["dir"].astype(str), "d": dd, "t": dt})[ok]
    for k, d in P.groupby("key"):
        if len(d) >= MIN_PAIRS and d.t.sum() > 0:
            out[k] = dict(kmh=float(d.d.sum() / d.t.sum() * 3.6), n=int(len(d)))
    tot = P
    if len(tot) >= MIN_PAIRS:
        out["_ALL"] = dict(kmh=float(tot.d.sum() / tot.t.sum() * 3.6), n=int(len(tot)))
    return out


def a1_speeds() -> dict:
    return _a1_speeds(D.a1_files())


def speed_for(key: str, speeds: dict, default_kmh: float, use_a1: bool) -> tuple[float, str]:
    if use_a1 and key in speeds:
        return speeds[key]["kmh"], f"A1 樣本（{speeds[key]['n']} 組）"
    return default_kmh, "預設值【假設】"


def driver_table(rts: dict, net1: dict, mods: list, feeders: list, trips: dict, speeds: dict,
                 default_kmh: float, shift_h: float, use_a1: bool, e1_len: dict) -> pd.DataFrame:
    rows = []
    for m in mods:
        k = m["key"]
        t = trips.get(k)
        L0 = rts[k]["line"].length / 1000
        L1 = e1_len.get(k, 0.0)
        v, vs = speed_for(k, speeds, default_kmh, use_a1)
        rows.append(dict(路線=rts[k]["label"], 類型="調整既有路線", 平日班次=t, 速率_kmh=round(v, 1), 速率來源=vs,
                         S0_車公里=t * L0 if t else np.nan, 情境_車公里=t * L1 if t else np.nan))
    for i, f in enumerate(feeders):
        t = f.get("trips")
        L1 = e1_len.get(f"FEEDER-{i}", 0.0)
        rows.append(dict(路線=f["name"], 類型="新增接駁線", 平日班次=t, 速率_kmh=round(default_kmh, 1), 速率來源="預設值【假設】",
                         S0_車公里=0.0, 情境_車公里=t * L1 if t else np.nan))
    T = pd.DataFrame(rows)
    if T.empty:
        return T
    T["S0_車小時"] = T.S0_車公里 / T.速率_kmh
    T["情境_車小時"] = T.情境_車公里 / T.速率_kmh
    T["S0_班次"] = T.S0_車小時 / shift_h
    T["情境_班次"] = T.情境_車小時 / shift_h
    return T


def corridor_totals(rts: dict, net1: dict, trips: dict, speeds, default_kmh, use_a1, e1_len, feeders):
    """有 TDX 班表的所有路線（7 站 800 m 範圍內的路線）平日車公里與車輛小時：S0 vs 情境。"""
    s0k = s0h = s1k = s1h = 0.0
    for k, t in trips.items():
        if k not in rts or not t:
            continue
        v, _ = speed_for(k, speeds, default_kmh, use_a1)
        L0 = rts[k]["line"].length / 1000
        L1 = e1_len.get(k, L0) if k in net1 else 0.0
        s0k += t * L0; s0h += t * L0 / v
        s1k += t * L1; s1h += t * L1 / v
    for i, f in enumerate(feeders):
        t = f.get("trips") or 0
        L = e1_len.get(f"FEEDER-{i}", 0.0)
        s1k += t * L; s1h += t * L / default_kmh
    return dict(s0_km=s0k, s0_h=s0h, s1_km=s1k, s1_h=s1h)
