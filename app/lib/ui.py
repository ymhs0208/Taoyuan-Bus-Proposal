from __future__ import annotations

import folium
import numpy as np
import pyproj
import shapely
import streamlit as st
from shapely.geometry import mapping

from . import data as D

_TR = pyproj.Transformer.from_crs(D.CRS_M, 4326, always_xy=True)
_TR_INV = pyproj.Transformer.from_crs(4326, D.CRS_M, always_xy=True)

BANNER = "展示版：試行分析，數據待複核"


def presentation_style():
    st.markdown("""<style>
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
        color:#495567 !important; font-size:0.95rem !important;}
    [data-testid="stMetricLabel"] {white-space:normal; font-size:1rem;}
    [data-testid="stMetricLabel"] p {white-space:normal; overflow:visible;}
    [data-testid="stMetric"] {background:#f5f8f6; border:1px solid #dce6df;
        border-radius:12px; padding:16px; height:100%;}
    [data-testid="stMetricValue"] {font-size:2rem;}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {font-size:0.88rem !important;}
    @media (max-width:640px) {h1 {font-size:1.8rem !important;} h3 {font-size:1.35rem !important;}}
    </style>""", unsafe_allow_html=True)


def banner():
    presentation_style()
    src = D.current_source()
    src_txt = D.SOURCES.get(src, "（找不到公車資料）")
    st.markdown(
        f"""<div style="background:#fff4e5;border:1px solid #f0b46c;border-radius:6px;padding:6px 12px;margin-bottom:10px;
        font-size:0.92rem;color:#7a4a00">⚠️ <b>{BANNER}</b>　｜　目前公車資料來源：{src_txt}</div>""",
        unsafe_allow_html=True,
    )


def require_data() -> bool:
    if D.pilot_dir() is None:
        st.error("找不到試行分析資料夾 pilot/。請把 pilot 資料夾放在 app 資料夾旁邊（同一層），或設定環境變數 TAOYUAN_PILOT_DIR。")
        return False
    if D.stations() is None:
        st.error("找不到車站點位檔 pilot/data/stations_green_north.csv，無法繪圖。")
        return False
    if not D.available_sources():
        st.error("找不到公車站序資料（pilot/data/tdx/stop_of_route.csv 或 pilot/data/route_stops_parsed.csv）。")
        return False
    return True


def to_ll(geom):
    """EPSG:3826 幾何 → WGS84。"""
    return shapely.transform(geom, lambda c: np.column_stack(_TR.transform(c[:, 0], c[:, 1])))


def xy_to_ll(x, y):
    lon, lat = _TR.transform(x, y)
    return lat, lon


def ll_to_xy(lat, lon):
    return _TR_INV.transform(lon, lat)


def base_map(zoom=13, fit=False, quiet=False):
    stg = D.stations()
    lat, lon = stg.lat.mean(), stg.lon.mean()
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
    if quiet:
        m.get_root().header.add_child(folium.Element(
            "<style>.leaflet-tile-pane {filter:grayscale(85%);opacity:0.60;}</style>"))
    if fit:
        m.fit_bounds([[stg.lat.min() - 0.004, stg.lon.min() - 0.006], [stg.lat.max() + 0.004, stg.lon.max() + 0.006]])
    return m


def add_stations(m, highlight: set | None = None, circles: int | None = None, labels=True):
    stg = D.stations()
    highlight = highlight or set()
    for _, s in stg.iterrows():
        weak = s.code in highlight
        color = "#d62728" if weak else "#1a7f37"
        if circles:
            folium.Circle([s.lat, s.lon], radius=circles, color=color, weight=1, fill=True, fill_opacity=0.08,
                          dash_array="4 4").add_to(m)
        tip = f"{s.code} {s['name']}" + ("（點位為估計）" if s.estimated else "")
        folium.CircleMarker([s.lat, s.lon], radius=8 if weak else 7, color="white", weight=2, fill=True,
                            fill_color=color, fill_opacity=1, tooltip=tip).add_to(m)
        if labels:
            folium.Marker([s.lat, s.lon], icon=folium.DivIcon(
                html=f'<div style="font-size:11px;font-weight:700;color:{color};white-space:nowrap;'
                     f'text-shadow:0 0 3px #fff,0 0 3px #fff;transform:translate(10px,-8px)">{s.code} {s["name"]}'
                     f'{"*" if s.estimated else ""}</div>')).add_to(m)


def line_coords(line, simplify=4):
    g = to_ll(line.simplify(simplify))
    if g.geom_type == "LineString":
        return [[(y, x) for x, y in g.coords]]
    return [[(y, x) for x, y in part.coords] for part in getattr(g, "geoms", [])]


def fmt_int(v):
    try:
        return f"{int(round(float(v))):,}"
    except Exception:
        return "—"
