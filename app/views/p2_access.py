import glob
import os

import folium
import pandas as pd
import plotly.express as px
import shapely
import streamlit as st
from streamlit_folium import st_folium

from lib import data as D, metrics as M, proxy as X, ui

ui.banner()
st.title("🚶 接駁缺口")
st.caption("以 OSM 步行路網計算 300／500／800 m 步行等時圈，統計範圍內的公車站牌、路線與 65 歲以上人口估計。")
if not ui.require_data():
    st.stop()
src = D.current_source()
iso = D.isochrones()
if iso is None:
    st.warning("尚無等時圈檔案 pilot/outputs/A2_isochrones.gpkg（需先執行 05_access.py）。")
    st.stop()
acc = M.access_table(src, D.routes_sig(src), D.sig("outputs/A2_isochrones.gpkg"), D.sig("data/villages_pop65.gpkg"))


# ---- 班次頻率：自動偵測 outputs/ 內含班次欄位的檔案，沒有就顯示「待實測」
PEAK = ["peak_trips_per_h", "freq_peak"]
OFF = ["offpeak_trips_per_h", "freq_offpeak"]
DAY = ["weekday_trips"]


def load_freq():
    res, used = {}, []
    base = D.pilot_dir()
    files = ["outputs/A2_station_access.csv"] + [os.path.relpath(f, base) for f in sorted(glob.glob(str(base / "outputs" / "*freq*.csv")))]
    for rel in files:
        df = D.read_csv(rel)
        if df is None or not {"code", "dist_m"} <= set(df.columns):
            continue
        got = False
        for tag, names in (("peak", PEAK), ("off", OFF), ("day", DAY)):
            c = D.first_col(df, names)
            if not c:
                continue
            v = pd.to_numeric(df[c], errors="coerce")
            for code, d, val in zip(df.code, df.dist_m, v):
                if pd.notna(val):
                    res[(str(code), int(d), tag)] = float(val)
                    got = True
        if got:
            used.append(rel)
    return res, used


freq, freq_files = load_freq()
acc["尖峰班次"] = [freq.get((c, d, "peak"), "待實測") for c, d in zip(acc.code, acc.dist_m)]
acc["離峰班次"] = [freq.get((c, d, "off"), "待實測") for c, d in zip(acc.code, acc.dist_m)]
acc["平日班次"] = [freq.get((c, d, "day"), "待實測") for c, d in zip(acc.code, acc.dist_m)]

with st.sidebar:
    st.markdown("**本頁設定**")
    rank_d = st.select_slider("以哪個步行距離判定弱站", [300, 500, 800], value=500)
    n_weak = st.slider("標紅的最弱車站數", 1, 4, 2)
    show_d = st.multiselect("地圖顯示等時圈", [300, 500, 800], default=[300, 500, 800])

piv = acc.pivot_table(index=["code", "name"], columns="dist_m", values=["stop_positions", "n_routes", "pop65_est"], aggfunc="first")
rk = acc[acc.dist_m == rank_d].copy()
rk["_tie"] = rk.code.map(acc[acc.dist_m == 800].set_index("code").stop_positions)
rk = rk.sort_values(["stop_positions", "n_routes", "_tie"])
weak = list(rk.code.head(n_weak))

stg = D.stations()
cols = {800: "#9ecae1", 500: "#4292c6", 300: "#08519c"}
m = ui.base_map(zoom=13, fit=True)
for d in sorted(show_d, reverse=True):
    sub = iso[iso.dist_m == d]
    for _, g in sub.iterrows():
        red = g.code in weak
        folium.GeoJson(ui.to_ll(g.geometry).__geo_interface__,
                       style_function=lambda f, c=cols[d], red=red: dict(fillColor="#d62728" if red else c, color="#d62728" if red else c,
                                                                       weight=0.8, fillOpacity=0.18 if red else 0.3),
                       tooltip=f"{g.code} 步行 {d} m 等時圈").add_to(m)
S = D.stop_positions(D.routes(src))
near = S[shapely.contains_xy(iso[iso.dist_m == 800].union_all(), S.x.values, S.y.values)]
grp = near.groupby(["kx", "ky"]).agg(name=("name", "first"), lat=("lat", "first"), lon=("lon", "first"),
                                    routes=("route", lambda x: " ".join(sorted(set(map(str, x)))))).reset_index()
for _, p in grp.iterrows():
    folium.CircleMarker([p.lat, p.lon], radius=3, color="#333", weight=1, fill=True, fill_opacity=0.9,
                        tooltip=f"{p['name']}｜{p.routes}").add_to(m)
IND = X.load_industrial()
with st.sidebar:
    show_ind = st.checkbox("地圖顯示產業用地（移工通勤代理）", value=IND is not None, disabled=IND is None)
if IND is not None and show_ind:
    from shapely.ops import unary_union as _uu
    _corr = _uu([g.buffer(X.NEAR_R) for g in stg.geometry])
    for _, g in IND[IND.intersects(_corr)].iterrows():
        col = "#8c510a" if g.source.startswith("OSM") else "#542788"
        folium.GeoJson(ui.to_ll(g.geometry.intersection(_corr)).__geo_interface__,
                       style_function=lambda f, c=col: dict(fillColor=c, color=c, weight=1, fillOpacity=0.25, dashArray="3 3"),
                       tooltip=f"產業用地｜{g['name'] or '（未命名）'}｜{g.source}").add_to(m)
ui.add_stations(m, highlight=set(weak))

c1, c2 = st.columns([3, 2])
with c1:
    st_folium(m, height=600, use_container_width=True, returned_objects=[], key=f"accmap_{src}")
    st.caption("藍色：步行等時圈（深→淺：300／500／800 m）；紅色：最弱車站；黑點：公車站牌位置；棕色虛線：OSM 產業用地；紫色虛線：產管局產業園區範圍（走廊 1,500 m 內）。* 表示車站點位為估計。")
with c2:
    st.markdown(f"**最弱車站（依 {rank_d} m 內站牌位置數，同分再比路線數、800 m 站牌數）**")
    for i, c in enumerate(weak):
        r = rk.set_index("code").loc[c]
        est = "（點位為估計）" if bool(stg.set_index("code").estimated.get(c, False)) else ""
        pk = freq.get((c, rank_d, "peak"))
        ftxt = f"；尖峰每小時 {pk:g} 班" if pk is not None else "；班次待實測"
        st.error(f"**{c} {r['name']}**{est}：{rank_d} m 內 {r.stop_positions} 個站牌位置、{r.n_routes} 條路線{ftxt}；"
                 f"65+ 估計 {ui.fmt_int(r.pop65_est)} 人")
    fig = px.bar(acc, x="code", y="stop_positions", color=acc.dist_m.astype(str), barmode="group",
                 labels={"code": "車站", "stop_positions": "站牌位置數", "color": "步行距離 m"},
                 color_discrete_map={"300": cols[300], "500": cols[500], "800": cols[800]})
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), title="各站步行範圍內公車站牌位置數")
    st.plotly_chart(fig, width="stretch")
    fig2 = px.bar(acc, x="code", y="pop65_est", color=acc.dist_m.astype(str), barmode="group",
                  labels={"code": "車站", "pop65_est": "65 歲以上人口（估計）", "color": "步行距離 m"},
                  color_discrete_map={"300": cols[300], "500": cols[500], "800": cols[800]})
    fig2.update_layout(height=260, margin=dict(l=10, r=10, t=30, b=10), title="步行範圍內 65 歲以上人口（村里面積比例估計）")
    st.plotly_chart(fig2, width="stretch")

st.subheader("各站明細")
tbl = acc.copy()
tbl["弱站"] = tbl.code.isin(weak)
tbl = tbl[["code", "name", "dist_m", "stop_positions", "n_routes", "尖峰班次", "離峰班次", "平日班次", "pop65_est", "pop_est", "iso_area_ha", "弱站", "routes"]]
tbl.columns = ["車站", "站名", "步行距離 m", "站牌位置數", "路線數", "尖峰班次/時", "離峰班次/時", "平日班次", "65+ 人口估計", "總人口估計", "等時圈面積 ha", "弱站", "路線"]
for c in ["尖峰班次/時", "離峰班次/時", "平日班次"]:
    tbl[c] = [f"{v:g}" if isinstance(v, float) else str(v) for v in tbl[c]]


def hl(row):
    return ["background-color:#fde0dd" if row["弱站"] else ""] * len(row)


st.dataframe(tbl.style.apply(hl, axis=1), hide_index=True, height=560)
if not freq:
    st.info("班次頻率（尖峰／離峰）：**待實測**。需要 TDX Schedule／DailyStopTimeTable，產出後本頁會自動顯示。")
else:
    st.caption(f"班次讀自 {', '.join('pilot/' + f for f in freq_files)}（{D.mtime_str(freq_files[-1])} UTC+8）。定義依 pilot/scripts/10_frequency.py："
               "平日以星期三有營運的班次代表；尖峰 07–09、17–19 時，離峰 09–17 時；TDX 桃園班表只有起點發車時刻，故以起點發車時刻判定時段；"
               "等時圈內只要有任一站牌就計入該路線方向，同一班次只計一次。班次為**時刻表**，不是實際準點情形。")
    pk = acc[acc["尖峰班次"].apply(lambda v: isinstance(v, float))]
    if not pk.empty:
        figf = px.bar(pk, x="code", y="尖峰班次", color=pk.dist_m.astype(str), barmode="group",
                      labels={"code": "車站", "尖峰班次": "尖峰每小時班次（時刻表）", "color": "步行距離 m"},
                      color_discrete_map={"300": cols[300], "500": cols[500], "800": cols[800]})
        figf.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), title="各站步行範圍內的尖峰每小時公車班次")
        st.plotly_chart(figf, width="stretch")
st.caption("站牌位置以 5 m 網格去重；路線數只計入目前資料來源所含路線。等時圈由 pilot/scripts/05_access.py 產生（車站最近路網節點起算，路段兩側各緩衝 50 m）。"
           "65+ 人口為內政部戶政司村里人口依面積比例分配，假設村里內人口均勻分布。")


# ---------------------------------------------------------------- 產業用地（移工通勤代理指標）
st.divider()
st.subheader("🏭 產業用地（移工通勤代理指標）")
st.warning("**探索性指標，不是移工人口。** 目前沒有公開的移工居住或工作地點空間資料，因此以「產業用地」代表可能有輪班通勤需求的就業地點。"
           "產業用地不等於移工人數；宿舍位置、雇用人數、國籍與班別時間都不知道。正式研究需以市府（勞動局等）彙總資料或訪談驗證，本平台未做任何訪談。")
if IND is None:
    st.info("尚未建立產業用地資料（app/derived/A4_industrial_*.gpkg）。請執行 `python tools/build_industrial.py` 與 `python tools/build_official_parks.py`。")
else:
    @st.cache_data(show_spinner="計算產業用地指標…")
    def _proxy(src, rsig, isig, xsig):
        net0 = M.build_network(src, [], [])
        e0 = M.evaluate(net0, 300)
        S = D.stop_positions(D.routes(src))
        T1 = X.station_table(X.load_industrial(), D.isochrones())
        T2, summ = X.reach_table(X.load_industrial(), D.stations(), S, e0["conn_by_station"], 300)
        return T1, T2, summ

    T1, T2, summ = _proxy(src, D.routes_sig(src), D.sig("outputs/A2_isochrones.gpkg"), X.industrial_sig())
    a, b, c = st.columns(3)
    a.metric("走廊內產業用地（7 站各 1,500 m）", f"{summ['total_ha']:,.1f} ha", f"{len(T2)} 塊", delta_color="off")
    b.metric("其中距任一公車站牌 300 m 內", f"{summ['any_ha']:,.1f} ha", f"{summ['any_ha'] / summ['total_ha']:.0%}" if summ["total_ha"] else "—", delta_color="off")
    c.metric("其中距『可一車直達最近綠線車站』路線站牌 300 m 內", f"{summ['direct_ha']:,.1f} ha",
             f"{summ['direct_ha'] / summ['total_ha']:.0%}" if summ["total_ha"] else "—", delta_color="off")
    piv = T1.pivot(index="code", columns="dist_m", values="ind_ha").rename(columns=lambda d: f"步行 {d} m 內 ha")
    agg = T2.groupby("nearest_station").agg(塊數=("area_ha", "size"), 面積_ha=("area_ha", "sum"),
                                            距站牌300m內=("stop_within_R", "sum"), 可直達最近車站=("direct_within_R", "sum")).round(2)
    tb = piv.join(agg, how="outer").fillna(0).reset_index().rename(columns={"index": "車站", "code": "車站", "nearest_station": "車站"})
    tb.insert(1, "站名", tb.iloc[:, 0].map(dict(zip(stg.code, stg.name))))
    st.markdown("**各站：步行範圍內的產業用地面積，以及最近車站為本站的產業用地之公車可達性**")
    st.dataframe(tb, hide_index=True, width="stretch")
    with st.expander(f"走廊內每塊產業用地明細（{len(T2)} 塊）"):
        st.dataframe(T2.sort_values("area_ha", ascending=False).rename(columns={
            "source": "來源", "name": "名稱", "area_ha": "走廊內面積 ha", "nearest_station": "最近車站", "station_dist_m": "距車站 m",
            "nearest_stop_m": "距最近站牌 m", "stop_within_R": "300 m 內有站牌", "direct_within_R": "300 m 內有直達最近車站路線", "direct_routes": "直達路線"}),
            hide_index=True)
    st.caption(f"資料：OSM landuse=industrial（{(X.DERIVED / 'A4_industrial_retrieved_at.txt').read_text(encoding='utf-8').split('；')[0] if (X.DERIVED / 'A4_industrial_retrieved_at.txt').exists() else '—'} 取得，© OpenStreetMap contributors）；"
               "經濟部產業園區管理局「產業園區範圍圖」（政府資料開放授權條款第1版，檔案日期 2026-04-30；只含該局彙整的園區，未含零星工廠用地）。"
               "兩來源重疊處以聯集計算面積；明細表的面積只計走廊（7 站各 1,500 m）內的部分；距離為直線距離。OSM 標註完整度未經查核，部分範圍（如機場管制區）不一定是製造業用地。")
