"""「改良方案」五個頁面共用：頁面守門、現況快取、各方案的計算、地圖小工具。
演算法與「情境模擬」頁同一套（lib/metrics、lib/driver），預設參數相同：步行 300 m、一車到站 500 m、時速 18 km、每班 8 小時（皆為假設）。"""
from __future__ import annotations

import gzip
import json

import folium
import numpy as np
import pandas as pd
import streamlit as st

from . import data as D, driver as DR, metrics as M, rules as RU, ui

WALK, CONN, SPEED, SHIFT = 300, 500, 18.0, 8.0
GREEN, GRAY, ORANGE, RED, PURPLE = "#1a7f37", "#888888", "#ff7f0e", "#d62728", "#6a3d9a"


def need():
    """共用守門：橫幅、資料齊備、只用 TDX 實際線型。回傳 (src, rts, stg)。"""
    ui.banner()
    if not ui.require_data():
        st.stop()
    src = D.current_source()
    if src != "tdx":
        st.warning("改良方案頁以「交通部公開資料」（車子實際走的路線、有班表）計算。請在左側「路線形狀用哪一份」選交通部公開資料。")
        st.stop()
    if D.isochrones() is None or D.villages() is None:
        st.warning("還沒有「沿人行道走得到的範圍」或村里人口，這頁算不出來。檔名在「關於資料」。")
        st.stop()
    return src, D.routes(src), D.stations()


def head(title: str, answers: str, first: str):
    st.title(title)
    st.markdown(f"**這頁在回答：** {answers}")
    st.info(f"**先看這句：** {first}")
    st.caption("研究示意，不是市府或業者的方案。數字含假設（時速、工時、班次、車型），已在各處標明。")


def goto_scenario(label="到「情境模擬」自己調參數"):
    st.page_link("views/p3_scenario.py", label=label, icon="🧪")


@st.cache_resource(max_entries=4, show_spinner="整理現況…")
def base(source: str, rsig: str):
    net0 = M.build_network(source, [], [])
    return net0, M.evaluate(net0, WALK, CONN)


def gr_keys(source: str, rsig: str):
    rts = D.routes(source)
    ov = M.overlap_table(source, 500, rsig)
    keys = [k for k in (list(ov.key) if ov is not None and not ov.empty else []) if rts[k]["sub"] == "GR"]
    return keys or [k for k, r in rts.items() if r["sub"] == "GR"]


def peak_freq(code: str, dist_m: int):
    """TDX 班表算出的尖峰每小時班次（pilot/outputs/A2_tdx_station_access_frequency.csv）。"""
    f = D.read_csv("outputs/A2_tdx_station_access_frequency.csv")
    if f is None:
        return None
    r = f[(f.code == code) & (f.dist_m == dist_m)]
    return float(r.peak_trips_per_h.iloc[0]) if len(r) else None


def pop65_within(code: str, dist_m: int):
    f = D.read_csv("outputs/A2_tdx_station_access_frequency.csv")
    if f is None:
        return None
    r = f[(f.code == code) & (f.dist_m == dist_m)]
    return float(r.pop65_est.iloc[0]) if len(r) else None


# ---------------------------------------------------------------- 方案一
@st.cache_resource(max_entries=4, show_spinner="計算方案一…")
def plan1(source: str, rsig: str):
    rts, stg = D.routes(source), D.stations()
    codes = list(stg.code)
    net0, e0 = base(source, rsig)
    keys = gr_keys(source, rsig)
    mods = [dict(type="drop_parallel", key=k, radius=500, stations=codes, desc="") for k in keys]
    net1 = M.build_network(source, mods, [])
    e1 = M.evaluate(net1, WALK, CONN)
    trips = D.weekday_trips()
    ct = DR.corridor_totals(rts, net1, trips, {}, SPEED, False, e1["length_km"], [])
    ov = M.overlap_table(source, 500, rsig)
    ovx = ov.set_index("key") if ov is not None and not ov.empty else None
    gr = []
    for k in keys:
        before = rts[k]["line"].length / 1000
        gr.append(dict(key=k, label=rts[k]["label"], dir=rts[k]["dir"], before=before, after=float(e1["length_km"].get(k, before)),
                       overlap_km=float(ovx.loc[k, "範圍內長度_km"]) if ovx is not None and k in ovx.index else None,
                       share=float(ovx.loc[k, "長度占比"]) if ovx is not None and k in ovx.index else None,
                       trips=trips.get(k)))
    people = {c: (e0["coverage"]["per_station"][c]["direct"], e1["coverage"]["per_station"][c]["direct"]) for c in codes}
    return dict(gr=gr, shifts0=ct["s0_h"] / SHIFT, shifts1=ct["s1_h"] / SHIFT, people=people, net0=net0, net1=net1, keys=keys)


# ---------------------------------------------------------------- 方案二
@st.cache_resource(max_entries=12, show_spinner="挑選接駁站牌並計算…")
def plan2(source: str, rsig: str, station: str, k: int):
    rts, stg = D.routes(source), D.stations()
    net0, e0 = base(source, rsig)
    pts = M.greedy_feeder(source, station, e0, net0, WALK, 300, 1500, k)
    if not pts:
        return None
    f = [dict(name=f"{station} 接駁線（演算法示意）", station=station, points=[list(p) for p in pts], loop=True)]
    net1 = M.build_network(source, [], f)
    e1 = M.evaluate(net1, WALK, CONN)
    return dict(pts=pts, net1=net1, e0=e0, e1=e1, length=float(e1["length_km"].get("FEEDER-0", 0.0)),
                people=(e0["coverage"]["per_station"][station]["direct"], e1["coverage"]["per_station"][station]["direct"]))


# ---------------------------------------------------------------- 方案五：發車時刻
@st.cache_data(show_spinner=False)
def _departures(fsig: str) -> dict:
    out = {}
    base_dir = D.pilot_dir()
    if base_dir is None:
        return out
    f = base_dir / "data" / "tdx" / "Schedule_Taoyuan_800m_routes.json.gz"
    if not f.exists():
        return out
    for s in json.load(gzip.open(f)):
        key = f"{s.get('SubRouteUID')}-{int(s.get('Direction', 0) or 0)}"
        mins = set()
        for t in s.get("Timetables") or []:
            if not (t.get("ServiceDay") or {}).get("Wednesday"):
                continue
            st_ = t.get("StopTimes") or []
            tm = (st_[0].get("DepartureTime") or st_[0].get("ArrivalTime")) if st_ else None
            if tm:
                mins.add(int(tm[:2]) * 60 + int(tm[3:5]))
        if mins:
            out[key] = sorted(mins)
    return out


def departures() -> dict:
    return _departures(D.sig("data/tdx/Schedule_Taoyuan_800m_routes.json.gz"))


# ---------------------------------------------------------------- 地圖
def new_map(center_xy=None, zoom=14):
    m = ui.base_map(zoom=zoom)
    if center_xy is not None:
        la, lo = ui.xy_to_ll(*center_xy)
        m.location = [la, lo]
    return m


def draw_lines(m, lines, color, weight=4, dash=None, tip="", opacity=0.9):
    for ln in lines:
        if ln is None:
            continue
        for part in ui.line_coords(ln):
            folium.PolyLine(part, color=color, weight=weight, opacity=opacity, dash_array=dash, tooltip=tip).add_to(m)


def show_map(m, key, height=430):
    from streamlit_folium import st_folium
    st_folium(m, height=height, use_container_width=True, returned_objects=[], key=key)


def limits(items: list[str]):
    with st.expander("限制與尚未做到的事（簡報時請一併說明）"):
        for i in items:
            st.markdown(f"- {i}")
