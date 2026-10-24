import re

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from lib import data as D, metrics as M, ui

ui.banner()
st.title("🗺️ 路線重疊地圖")
st.markdown("**這頁在回答：** 哪些公車和即將通車的綠線走在同一條路上？")
st.caption("深綠色是目前選中的路線，灰色是其他路線；先選一條，就能看清楚它與綠線各站的關係。")
if not ui.require_data():
    st.stop()

src = D.current_source()
rts = D.routes(src)
with st.sidebar.expander("地圖範圍與路線篩選"):
    st.markdown("**本頁設定**")
    radius = st.select_slider("捷運站周圍看多遠（公尺）", [300, 500, 800], value=500, help="預設 500 公尺，就是站點附近一條街的距離。可改成 300 或 800，看結論會不會變。")
    ov = M.overlap_table(src, radius, D.routes_sig(src))
    if ov.empty:
        st.warning("這個距離內沒有任何公車的站牌。")
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
top = ov.iloc[0]
st.info(f"**先看這句：** 重疊最多的是 {top.方向}，約 {top.範圍內長度_km:.2f} 公里（這條路線的 {top.長度占比:.0%}）走在捷運站 {radius} 公尺以內。")
keys = list(show.key)
pending = st.session_state.pop("_ov_pending", None)
if pending in keys:
    st.session_state["ov_detail"] = pending
if st.session_state.get("ov_detail") not in keys:
    st.session_state["ov_detail"] = keys[0]
k = st.selectbox("選擇要聚焦的路線（也可點選地圖）", keys,
                 format_func=lambda k: rts[k]["label"], key="ov_detail")
st.caption("深綠粗線＝目前選中路線　｜　灰色細線＝其他路線　｜　綠色圓點＝捷運站")
m = ui.base_map(zoom=13, fit=True, quiet=True)
# Draw the selected route last so shared road sections remain visible.
for _, r in show[show.key != k].iterrows():
    for part in ui.line_coords(rts[r.key]["line"]):
        folium.PolyLine(part, color="#7c8994", weight=2, opacity=0.22,
                        tooltip=f"{rts[r.key]['label']}｜代碼 {r.key}").add_to(m)
r = ov.set_index("key").loc[k]
for part in ui.line_coords(rts[k]["line"]):
    folium.PolyLine(part, color="white", weight=9, opacity=0.95, interactive=False).add_to(m)
    folium.PolyLine(part, color="#146b3a", weight=5, opacity=1,
                    tooltip=f"{rts[k]['label']}｜範圍內 {r.範圍內長度_km} km（{r.長度占比:.1%}）｜代碼 {k}").add_to(m)
ui.add_stations(m, circles=radius)

c1, c2 = st.columns([3, 2])
with c1:
    out = st_folium(m, height=580, use_container_width=True, returned_objects=["last_object_clicked_tooltip"], key=f"ovmap_{src}_{radius}")
clicked = None
if out and out.get("last_object_clicked_tooltip"):
    mm = re.search(r"代碼\s*(\S+)", out["last_object_clicked_tooltip"])
    if mm and mm.group(1) in rts:
        clicked = mm.group(1)

with c2:
    st.markdown(f"**重疊排行**（{len(ov)} 個方向在捷運站 {radius} 公尺內有站牌）")
    st.dataframe(ov[["排名", "方向", "範圍內長度_km"]],
                 hide_index=True, height=540, width="stretch",
                 column_config={"排名": st.column_config.NumberColumn("排名", width="small"),
                                "方向": st.column_config.TextColumn("路線方向", width="medium"),
                                "範圍內長度_km": st.column_config.NumberColumn("重疊 km", format="%.2f", width="small")})
    st.caption("依重疊公里數排序；選擇上方路線或點地圖，可查看該路線。")
if clicked and st.session_state.get("_ov_last_click") != clicked:
    st.session_state["_ov_last_click"] = clicked
    st.session_state["_ov_pending"] = clicked
    st.rerun()

with st.expander("完整重疊排行與班表"):
    st.dataframe(ov.drop(columns="key"), hide_index=True, width="stretch")
    st.caption("車公里＝平日班次數 × 重疊路段長度；班次來自時刻表。")

st.divider()
st.subheader("路線詳細資料")
r = ov.set_index("key").loc[k]
rr = rts[k]
a, b, c = st.columns(3)
a.metric("整條路線多長", f"{r.全長_km} km", help="沿實際道路" if src == "tdx" else "站和站用直線連，會比實際路短")
b.metric(f"其中在捷運站 {radius} 公尺內", f"{r.範圍內長度_km} km", f"{r.長度占比:.1%}", delta_color="off")
c.metric("周圍站牌／全部站牌", f"{r.範圍內站牌}／{r.站數}")
st.caption(f"靠近 {r.觸及車站數} 座捷運站：{r.觸及車站}")
if trips and pd.notna(r.get("平日班次")):
    st.caption(f"時刻表：平日這個方向開 {int(r.平日班次)} 班，所以周圍這段一天大約 {r.範圍內平日車公里} 車公里（班次數 × 長度）。")

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
fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), title="沿線每一站離最近的綠線車站有多遠（紅色＝在你選的範圍裡，可看出哪一段跟綠線平行）")
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
        st.markdown(f"資料清理紀錄（{len(qc)} 筆）：剔除明顯跳開的座標；站和站直線超過 8 公里時，把路線切開、只留最長的一段。")
        st.dataframe(qc, hide_index=True)
st.caption(f"路線形狀：{'車子實際走的路' if src == 'tdx' else '站和站用直線連接'}。")
with st.expander("算法（給要查證的人）"):
    st.markdown(f"把路線和「每個捷運站周圍 {radius} 公尺圓圈」重叠的長度加總（座標系統 EPSG:3826）。"
                "「方向」在交通部資料是去程／回程；在市府站牌表是表上的不同欄，兩者不一定是同一件事。")
