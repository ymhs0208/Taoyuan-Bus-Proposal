"""改良方案二：G14 社區接駁線。"""
import pandas as pd
import streamlit as st

from lib import data as D, plans as P, rules as RU, ui

src, rts, stg = P.need()
P.head("2️⃣ 方案二｜G14 社區接駁線",
       "接駁最弱的 G14，加一條從站出發、繞社區的接駁線，長者會不會比較容易搭到車？車型夠不夠？",
       "G14 走路 300 公尺內沒有公車站牌，500 公尺內尖峰每小時只有約 4 班。加一條接駁線，可一車直達 G14 的 65 歲以上大約從 1,000 人增到 2,300 人。")
rsig = D.routes_sig(src)
with st.sidebar:
    st.markdown("### 方案二參數")
    K = st.slider("接駁線最多停幾個既有站牌", 3, 8, 6, 1, help="演算法從 G14 周圍 300–1,500 公尺的既有站牌中貪婪挑選。")
    VEH = st.radio("車型", ["大型公車", "桃小巴"], horizontal=True)
    CAP = st.number_input("載客數（座＋站）【假設】", 5, 120, 60 if VEH == "大型公車" else 25, 5, help="請以業者規格取代。")
    TPH = st.number_input("尖峰每小時班次【假設】", 1.0, 20.0, 4.0, 0.5, help="4 班＝約 15 分鐘一班。")
    LCAP = st.number_input("整圈長度上限（公里）【假設】", 2.0, 30.0, 8.0, 0.5)

R = P.plan2(src, rsig, "G14", K)
if R is None:
    st.warning("G14 周邊 300–1,500 公尺內找不到能增加直達覆蓋的既有站牌。")
    st.stop()
a, b = R["people"]
f500, f300 = P.peak_freq("G14", 500), None
c1, c2, c3 = st.columns(3)
c1.metric("可一車直達 G14 的 65 歲以上", f"{b:,.0f} 人", f"{b - a:+,.0f}（現況 {a:,.0f}）")
c2.metric("接駁線整圈長度（直線，下限）", f"{R['length']:.2f} km", help="點到點的直線，實際沿路會更長。")
c3.metric("G14 現況：500 m 內尖峰每小時班次", f"{f500:.1f} 班" if f500 is not None else "—", help="TDX 時刻表，以起點發車時刻判定。")

st.subheader("改前改後")
sx, sy = stg[stg.code == "G14"].geometry.iloc[0].x, stg[stg.code == "G14"].geometry.iloc[0].y
ca, cb = st.columns(2)
with ca:
    st.markdown("**現況：G14 周邊既有路線**")
    m = P.new_map((sx, sy), 14)
    ui.add_stations(m, circles=500)
    P.show_map(m, "p2_before")
with cb:
    st.markdown("**方案二：加一條社區循環接駁**")
    m = P.new_map((sx, sy), 14)
    fd = R["net1"]["FEEDER-0"]
    P.draw_lines(m, fd["lines"], P.PURPLE, 4, tip="新接駁線（點間直線）")
    import folium
    for i, p in enumerate(fd["stops"].itertuples()):
        la, lo = ui.xy_to_ll(p.x, p.y)
        folium.CircleMarker([la, lo], radius=5, color=P.PURPLE, fill=True, fill_color="white", fill_opacity=1, weight=2, tooltip=f"{i}. {p.name}").add_to(m)
    ui.add_stations(m, circles=500)
    P.show_map(m, "p2_after")
st.caption("紫色＝新接駁線，圈點＝停靠的既有站牌（演算法挑的，需實地確認）。")

st.subheader("車型與長度檢查")
cp = RU.capacity(int(CAP), TPH, max(b - a, 0))
lg = RU.length_gate(R["length"], LCAP)
st.dataframe(pd.DataFrame([{
    "車型": f"{VEH}（{int(CAP)} 人）", "每小時單向載客上限": int(cp["per_hr"]), "新增可一車到站的長者": int(round(b - a)),
    "載客上限相當於這群長者的": f"{cp['share']:.0%}" if cp["share"] is not None else "—",
    "長度": "✅ 在上限內" if lg["ok"] else f"⚠️ 超過 {LCAP:g} km"}]), hide_index=True, width="stretch")
st.caption("不假設有多少人搭。「相當於 X%」＝同一小時只要這群長者有 X% 搭乘車就滿了；X 越小越容易擠不上。")
P.goto_scenario()
P.limits(["停靠點是演算法從既有站牌挑出，不代表真的開得成；路型、場站、路口數都沒檢查。",
          "接駁線長度是點間直線，實際會更長；號誌路口數沒有資料。",
          "車型載客數、尖峰班次、長度上限都是假設，請以業者與市府規則取代。",
          "新線沒有歷史班距，須通車後監測才能確認班距是否穩定（規則一）。"])
