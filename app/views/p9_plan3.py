"""改良方案三：G12 補強（長者多、接駁弱）。"""
import branca.colormap as cm
import folium
import numpy as np
import pandas as pd
import streamlit as st

from lib import data as D, plans as P, ui

src, rts, stg = P.need()
P.head("3️⃣ 方案三｜G12 補強",
       "G12 蘆興埤附近長者多，但直達公車少。該補在哪裡、需要補多少？",
       "G12 走路 500 公尺內尖峰每小時只有約 4 班，但 800 公尺內大約有 1,400 位 65 歲以上居民，是「長者多、接駁弱」最明顯的站。補強位置是候選，不是指定路線。")
rsig = D.routes_sig(src)
net0, e0 = P.base(src, rsig)
g12 = stg[stg.code == "G12"].iloc[0]
sx, sy = g12.geometry.x, g12.geometry.y

f500 = P.peak_freq("G12", 500)
p800 = P.pop65_within("G12", 800)
direct = e0["coverage"]["per_station"]["G12"]
c1, c2, c3 = st.columns(3)
c1.metric("500 m 內尖峰每小時班次", f"{f500:.1f} 班" if f500 is not None else "—", help="TDX 時刻表；約每 %d 分鐘一班。" % (60 / f500) if f500 else "")
c2.metric("800 m 內 65 歲以上（估計）", f"{p800:,.0f} 人" if p800 is not None else "—", help="村里人口依面積比例分配。")
c3.metric("1.5 km 內可一車直達 G12 的 65 歲以上", f"{direct['direct']:,.0f}／{direct['total']:,.0f} 人", help="站牌 300 公尺內、有路線 500 公尺步行範圍內可到 G12。")

# 可一車到 G12 的路線站牌
keys = e0["conn_by_station"].get("G12", set())
dx, dy = [], []
for k in keys:
    s = net0[k]["stops"]
    dx += list(s.x.values); dy += list(s.y.values)
dx, dy = np.array(dx), np.array(dy)

vil = D.villages().copy()
vil["den"] = vil.pop65 / (vil.geometry.area / 1e6)
cen = vil.geometry.centroid
vil["d_station"] = np.hypot(cen.x - sx, cen.y - sy)
vil["d_direct"] = [float(np.min(np.hypot(dx - x, dy - y))) if len(dx) else np.nan for x, y in zip(cen.x, cen.y)]

st.subheader("地圖：65 歲以上人口密度與直達站牌")
near = vil[vil.d_station <= 3000]
cmap = cm.LinearColormap(["#ffffcc", "#fd8d3c", "#800026"], vmin=0, vmax=float(near.den.max()), caption="65 歲以上人口密度（人／km²）")
m = P.new_map((sx, sy), 14)
for _, r in near.iterrows():
    folium.GeoJson(ui.to_ll(r.geometry).__geo_interface__,
                   style_function=lambda f, c=cmap(r.den): dict(fillColor=c, color="white", weight=0.6, fillOpacity=0.55),
                   tooltip=f"{r.village}：65 歲以上約 {r.pop65:,.0f} 人（{r.den:,.0f} 人/km²）").add_to(m)
cmap.add_to(m)
for x, y in zip(dx, dy):
    la, lo = ui.xy_to_ll(x, y)
    folium.CircleMarker([la, lo], radius=3, color=P.ORANGE, fill=True, fill_opacity=1, weight=0).add_to(m)
folium.Circle([g12.lat, g12.lon], radius=500, color=P.RED, fill=False, weight=2, tooltip="500 m").add_to(m)
folium.Circle([g12.lat, g12.lon], radius=800, color=P.GREEN, fill=False, weight=2, dash_array="6 6", tooltip="800 m").add_to(m)
ui.add_stations(m)
P.show_map(m, "p3_map", 520)
st.caption("橘點＝可一車到 G12 的路線之站牌；紅圈＝500 公尺、綠虛線＝800 公尺；底色越深＝65 歲以上人口越密（村里均分估計）。")

st.subheader("候選補強地點（G12 周邊 2 公里內的村里，示意）")
cand = near[(near.pop65 > 0) & (near.d_station <= 2000)].sort_values("pop65", ascending=False).head(8)
tb = pd.DataFrame({"村里": cand.village.values, "65 歲以上（估計）": cand.pop65.round().astype(int).values,
                   "距 G12 直線（m）": cand.d_station.round().astype(int).values,
                   "距最近直達站牌（m）": cand.d_direct.round().astype(int).values})
tb["判斷"] = np.where(tb["距最近直達站牌（m）"] > P.WALK, "⚠️ 超過走路 300 m，候選補強", "✅ 300 m 內已有直達站牌")
st.dataframe(tb, hide_index=True, width="stretch")
st.caption("以村里中心點到直達站牌的直線距離判斷，只是粗略篩選；村里內人口不均、中心點不等於居民位置。")

st.subheader("做法與需要補多少")
st.markdown("- **增班：** 提高現有經過 G12 的路線尖峰班次。\n- **改道：** 把原本不經 G12 的路線改道經過上表的候選地點。\n- 與方案一的關係：裁切 GR 之後，G12 一車到站人數會略減（約 −33），所以方案三是方案一的前提。")
target = st.slider("目標尖峰班距（分鐘）【示範，可調】", 5, 30, 10, 1)
need_tph = 60 / target
if f500 is not None:
    st.metric("需要的尖峰每小時班次", f"{need_tph:.1f}", f"{need_tph - f500:+.1f}（現況 {f500:.1f}）", delta_color="off",
              help="只算 500 公尺內的合併班次，沒有指定由哪條路線補。")
    st.caption("這裡只回答「差多少班」，不指定由哪條路線補；補多少、誰補，要看載客量與駕駛排班。")
P.goto_scenario()
P.limits(["沒有上下車量，無法判斷補班後實際會有多少人搭。",
          "人口依村里面積比例分配，工業區與農地占比高的村里會失真；移工不在戶籍統計內。",
          "候選地點是村里層級的粗略篩選，不是路線。尖峰班次以起點發車時刻判定，可能偏移。"])
