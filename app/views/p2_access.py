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
st.markdown("**這頁在回答：** 每一站附近，長者走得到公車站嗎？一天開的班夠不夠？")
st.caption("藍色範圍是沿著人行道走 300、500、800 公尺到得了的地方，不是直線距離。")
if not ui.require_data():
    st.stop()
src = D.current_source()
iso = D.isochrones()
if iso is None:
    st.warning("還沒有「沿人行道走得到的範圍」，這頁沒辦法算。技術檔名：pilot/outputs/A2_isochrones.gpkg。")
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
    rank_d = st.select_slider("用走路多遠來找最弱的站（公尺）", [300, 500, 800], value=500,
                              help="沿人行道走的距離，不是直線。")
    n_weak = st.slider("地圖上標紅幾座最弱的站", 1, 4, 2)
    show_d = st.multiselect("地圖上顯示哪些步行範圍", [300, 500, 800], default=[300, 500, 800])

piv = acc.pivot_table(index=["code", "name"], columns="dist_m", values=["stop_positions", "n_routes", "pop65_est"], aggfunc="first")
rk = acc[acc.dist_m == rank_d].copy()
rk["_tie"] = rk.code.map(acc[acc.dist_m == 800].set_index("code").stop_positions)
rk = rk.sort_values(["stop_positions", "n_routes", "_tie"])
weak = list(rk.code.head(n_weak))
names = "、".join(f"{c} {rk.set_index('code').loc[c, 'name']}" for c in weak)
st.info(f"**先看這句：** 以走路 {rank_d} 公尺來看，最難接到公車的是 {names}。")

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
                       tooltip=f"{g.code} 沿人行道走 {d} 公尺").add_to(m)
S = D.stop_positions(D.routes(src))
near = S[shapely.contains_xy(iso[iso.dist_m == 800].union_all(), S.x.values, S.y.values)]
grp = near.groupby(["kx", "ky"]).agg(name=("name", "first"), lat=("lat", "first"), lon=("lon", "first"),
                                    routes=("route", lambda x: " ".join(sorted(set(map(str, x)))))).reset_index()
for _, p in grp.iterrows():
    folium.CircleMarker([p.lat, p.lon], radius=3, color="#333", weight=1, fill=True, fill_opacity=0.9,
                        tooltip=f"{p['name']}｜{p.routes}").add_to(m)
IND = X.load_industrial()
with st.sidebar:
    show_ind = st.checkbox("地圖顯示產業用地（用來猜通勤，不是移工人數）", value=IND is not None, disabled=IND is None)
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
    st.caption("深藍到淺藍：沿人行道走 300、500、800 公尺到得了的地方。紅色：最弱的站。黑點：公車站。棕色虛線：地圖上標成工業用地的範圍。紫色虛線：官方產業園區（只畫車站 1,500 公尺內）。星號表示車站位置是估計的。")
with c2:
    st.markdown(f"**最弱的站**（先比走路 {rank_d} 公尺內有幾個公車站，一樣再比路線數）")
    for i, c in enumerate(weak):
        r = rk.set_index("code").loc[c]
        est = "（點位為估計）" if bool(stg.set_index("code").estimated.get(c, False)) else ""
        pk = freq.get((c, rank_d, "peak"))
        ftxt = f"；尖峰每小時約 {pk:g} 班（時刻表）" if pk is not None else "；班次還沒有資料"
        st.error(f"**{c} {r['name']}**{est}：走路 {rank_d} 公尺內有 {r.stop_positions} 個公車站、{r.n_routes} 條路線{ftxt}；"
                 f"65 歲以上約 {ui.fmt_int(r.pop65_est)} 人")
    fig = px.bar(acc, x="code", y="stop_positions", color=acc.dist_m.astype(str), barmode="group",
                 labels={"code": "車站", "stop_positions": "站牌位置數", "color": "步行距離 m"},
                 color_discrete_map={"300": cols[300], "500": cols[500], "800": cols[800]})
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), title="各站步行範圍內有幾個公車站")
    st.plotly_chart(fig, width="stretch")
    fig2 = px.bar(acc, x="code", y="pop65_est", color=acc.dist_m.astype(str), barmode="group",
                  labels={"code": "車站", "pop65_est": "65 歲以上人口（估計）", "color": "步行距離 m"},
                  color_discrete_map={"300": cols[300], "500": cols[500], "800": cols[800]})
    fig2.update_layout(height=260, margin=dict(l=10, r=10, t=30, b=10), title="步行範圍內的 65 歲以上人數（依村里人口估計）")
    st.plotly_chart(fig2, width="stretch")

st.subheader("各站明細")
tbl = acc.copy()
tbl["弱站"] = tbl.code.isin(weak)
tbl = tbl[["code", "name", "dist_m", "stop_positions", "n_routes", "尖峰班次", "離峰班次", "平日班次", "pop65_est", "pop_est", "iso_area_ha", "弱站", "routes"]]
tbl.columns = ["車站", "站名", "步行距離 m", "站牌位置數", "路線數", "尖峰每小時幾班", "離峰每小時幾班", "平日開幾班", "65 歲以上（估計）", "總人口（估計）", "步行可達面積（公頃）", "弱站", "路線"]
for c in ["尖峰每小時幾班", "離峰每小時幾班", "平日開幾班"]:
    tbl[c] = [f"{v:g}" if isinstance(v, float) else str(v) for v in tbl[c]]


def hl(row):
    return ["background-color:#fde0dd" if row["弱站"] else ""] * len(row)


st.dataframe(tbl.style.apply(hl, axis=1), hide_index=True, height=560)
if not freq:
    st.info("尖峰、離峰一天開幾班：**還沒有班表**。補上交通部的時刻表之後，這裡會自動出現。")
else:
    st.caption("班次是時刻表，不是實際有沒有準時。尖峰大約是平日早上 7–9 點、傍晚 5–7 點；離峰是平日白天 9–17 點。")
    with st.expander("班次怎麼算"):
        st.markdown("用星期三有開的班代表平日。時刻表只有起點發車時間，所以用發車時間判斷尖峰或離峰，長路線可能差幾十分鐘。"
                    "步行範圍裡只要有一個站牌，這條路線這個方向就列入；同一班只算一次。")
    pk = acc[acc["尖峰班次"].apply(lambda v: isinstance(v, float))]
    if not pk.empty:
        figf = px.bar(pk, x="code", y="尖峰班次", color=pk.dist_m.astype(str), barmode="group",
                      labels={"code": "車站", "尖峰班次": "尖峰每小時班次（時刻表）", "color": "步行距離 m"},
                      color_discrete_map={"300": cols[300], "500": cols[500], "800": cols[800]})
        figf.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), title="各站步行範圍內，尖峰每小時大約幾班公車")
        st.plotly_chart(figf, width="stretch")
with st.expander("站牌和人口怎麼算"):
    st.markdown("5 公尺以內的站牌算同一個位置。步行範圍從離捷運站最近的人行道路口起算，路的兩側各加 50 公尺。"
                "65 歲以上人數用內政部的村里人口，依面積比例分配，假設人在村里裡平均分布。")


# ---------------------------------------------------------------- 產業用地（移工通勤代理指標）
st.divider()
st.subheader("🏭 產業用地（代理指標，不是移工人數）")
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
    a.metric("七站各 1.5 公里內的產業用地", f"{summ['total_ha']:,.1f} 公頃", f"{len(T2)} 塊", delta_color="off")
    b.metric("其中 300 公尺內有公車站", f"{summ['any_ha']:,.1f} 公頃", f"{summ['any_ha'] / summ['total_ha']:.0%}" if summ["total_ha"] else "—", delta_color="off")
    c.metric("其中能一車到最近的捷運站", f"{summ['direct_ha']:,.1f} 公頃",
             f"{summ['direct_ha'] / summ['total_ha']:.0%}" if summ["total_ha"] else "—", delta_color="off",
             help="300 公尺內有站牌，而且那條公車不用轉車就能到最近的綠線車站。")
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
    with st.expander("產業用地的資料從哪來"):
        st.caption(f"資料：OSM landuse=industrial（{(X.DERIVED / 'A4_industrial_retrieved_at.txt').read_text(encoding='utf-8').split('；')[0] if (X.DERIVED / 'A4_industrial_retrieved_at.txt').exists() else '—'} 取得，© OpenStreetMap contributors）；"
                   "經濟部產業園區管理局「產業園區範圍圖」（政府資料開放授權條款第1版，檔案日期 2026-04-30；只含該局彙整的園區，未含零星工廠用地）。"
                   "兩來源重疊處以聯集計算面積；明細表的面積只計七站各 1,500 公尺內的部分；距離為直線距離。OSM 標註完整度未經查核，部分範圍（如機場管制區）不一定是製造業用地。")
