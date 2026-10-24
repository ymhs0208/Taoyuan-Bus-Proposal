import re

import branca.colormap as cm
import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from lib import data as D, metrics as M, ui

ui.banner()
st.title("🗺️ 路線重疊地圖")
st.caption("哪些公車路線與綠線北段平行？以車站圓形範圍內的路線長度與站牌數量化。")
if not ui.require_data():
    st.stop()

src = D.current_source()
rts = D.routes(src)
with st.sidebar:
    st.markdown("**本頁設定**")
    radius = st.select_slider("車站範圍半徑（m）", [300, 500, 800], value=500, help="提案預設 500 m；可做敏感度分析")
    ov = M.overlap_table(src, radius, D.routes_sig(src))
    if ov.empty:
        st.warning("沒有任何路線站牌落在範圍內。")
        st.stop()
    topn = st.slider("顯示排行前 N 名", 5, min(60, len(ov)), min(15, len(ov)))
    opts = list(ov.key)
    lab = dict(zip(ov.key, ov.排名.astype(str) + ". " + ov.方向 + "｜" + ov.起訖))
    chosen = st.multiselect("或指定路線（會覆蓋前 N 名）", opts, format_func=lambda k: lab[k])

trips = D.weekday_trips() if src == "tdx" else {}
if trips:
    ov = ov.copy()
    ov["平日班次"] = [trips.get(k) for k in ov.key]
    ov["範圍內平日車公里"] = [round(t * l, 1) if t is not None else None for t, l in zip(ov.平日班次, ov.範圍內長度_km)]
show = ov[ov.key.isin(chosen)] if chosen else ov.head(topn)
vmax = max(0.05, float(ov.長度占比.max()))
cmap = cm.LinearColormap(["#fde725", "#fd8d3c", "#d7301f", "#67000d"], vmin=0, vmax=vmax,
                         caption=f"路線長度落在車站 {radius} m 範圍內的比例")

m = ui.base_map(zoom=13, fit=True)
ui.add_stations(m, circles=radius)
for _, r in show.iloc[::-1].iterrows():
    rr = rts[r.key]
    col = cmap(r.長度占比)
    for part in ui.line_coords(rr["line"]):
        folium.PolyLine(part, color=col, weight=4 if r.排名 > 3 else 6, opacity=0.85,
                        tooltip=f"{rr['label']}｜範圍內 {r.範圍內長度_km} km（{r.長度占比:.1%}）｜代碼 {r.key}").add_to(m)
cmap.add_to(m)

c1, c2 = st.columns([3, 2])
with c1:
    out = st_folium(m, height=580, use_container_width=True, returned_objects=["last_object_clicked_tooltip"], key=f"ovmap_{src}_{radius}")
clicked = None
if out and out.get("last_object_clicked_tooltip"):
    mm = re.search(r"代碼\s*(\S+)", out["last_object_clicked_tooltip"])
    if mm and mm.group(1) in rts:
        clicked = mm.group(1)

with c2:
    st.markdown(f"**重疊排行**（{len(ov)} 個路線方向有站牌落在 {radius} m 範圍內）")
    st.dataframe(ov[["排名", "方向", "範圍內長度_km", "長度占比", "範圍內站牌", "觸及車站數"] + (["平日班次", "範圍內平日車公里"] if trips else []) + ["觸及車站"]],
                 hide_index=True, height=540,
                 column_config={"長度占比": st.column_config.ProgressColumn("長度占比", format="percent", min_value=0, max_value=1),
                                "範圍內長度_km": st.column_config.NumberColumn("範圍內長度 km", format="%.2f")})

st.divider()
st.subheader("路線詳細資料")
keys = list(show.key) if clicked is None or clicked in set(show.key) else [clicked] + list(show.key)
if clicked and st.session_state.get("_ov_last_click") != clicked:
    st.session_state["_ov_last_click"] = clicked
    st.session_state["ov_detail"] = clicked
if st.session_state.get("ov_detail") not in keys:
    st.session_state["ov_detail"] = keys[0]
k = st.selectbox("選擇路線（也可直接在地圖上點選路線）", keys, format_func=lambda k: rts[k]["label"], key="ov_detail")
r = ov.set_index("key").loc[k]
rr = rts[k]
a, b, c, d = st.columns(4)
a.metric("全長", f"{r.全長_km} km", help=rr["line_kind"])
b.metric(f"{radius} m 範圍內長度", f"{r.範圍內長度_km} km", f"{r.長度占比:.1%}", delta_color="off")
c.metric("範圍內站牌／總站數", f"{r.範圍內站牌}／{r.站數}")
d.metric("觸及車站", f"{r.觸及車站數} 站", r.觸及車站, delta_color="off")
if trips and pd.notna(r.get("平日班次")):
    st.caption(f"TDX 班表：平日 {int(r.平日班次)} 班（單向）→ 範圍內平日約 {r.範圍內平日車公里} 車公里（＝班次 × 範圍內長度，時刻表值）。")

s = rr["stops"].reset_index(drop=True).copy()
stg = D.stations()
import numpy as np
dd = np.hypot(s.x.values[:, None] - stg.geometry.x.values[None, :], s.y.values[:, None] - stg.geometry.y.values[None, :])
s["最近車站"] = stg.code.values[dd.argmin(axis=1)]
s["距最近車站_m"] = dd.min(axis=1).round().astype(int)
s["站序"] = range(1, len(s) + 1)
s["範圍內"] = np.where(s.距最近車站_m <= radius, "是", "否")
fig = px.bar(s, x="站序", y="距最近車站_m", color="範圍內", hover_data=["name", "最近車站"],
             color_discrete_map={"是": "#d7301f", "否": "#9ecae1"},
             labels={"距最近車站_m": "距最近綠線車站（m，直線）", "站序": "站序", "範圍內": f"{radius} m 內"})
fig.add_hline(y=radius, line_dash="dot", line_color="#555")
fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), title="沿線各站與綠線車站的距離（紅色＝落在範圍內，可看出平行區段）")
st.plotly_chart(fig, width="stretch")
with st.expander("站序表"):
    st.dataframe(s[["站序", "name", "最近車站", "距最近車站_m", "範圍內"]].rename(columns={"name": "站名"}), hide_index=True)

import glob, os
_a1files = sorted([os.path.relpath(f, D.pilot_dir()) for f in glob.glob(str(D.pilot_dir() / "outputs" / "A1_*.csv"))], key=lambda f: ("tdx" not in f, f))
with st.expander(f"試行分析原始輸出（pilot/outputs/A1_*.csv，共 {len(_a1files)} 個檔）"):
    if not _a1files:
        st.info("尚無 A1 輸出檔。")
    for f in _a1files:
        if "qc_cleaning" in f:
            continue
        a1 = D.read_csv(f)
        if a1 is not None:
            st.markdown(f"**{os.path.basename(f)}**（{D.mtime_str(f)} UTC+8）")
            st.dataframe(a1, hide_index=True)
    qc = D.read_csv("outputs/A1_qc_cleaning_log.csv")
    if qc is not None:
        st.markdown(f"資料清理紀錄（{len(qc)} 筆）：drop_spike＝座標尖刺點剔除；split_jump_gt8km＝站間 >8 km 跳躍處切開")
        st.dataframe(qc, hide_index=True)
st.caption(f"計算方式：路線線型與車站 {radius} m 圓形範圍聯集的交集長度（EPSG:3826）。線型：{'TDX Shape' if src == 'tdx' else '站間直線近似'}。"
           "「方向」在 TDX 為去／返程，在 PDF 版為站址表欄位型態（不等於 TDX SubRoute）。")
