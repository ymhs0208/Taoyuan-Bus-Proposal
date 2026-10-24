"""改良方案四：長路線切短、站內轉乘（S2a）。"""
import pandas as pd
import streamlit as st

from lib import data as D, plans as P, rules as RU, ui

src, rts, stg = P.need()
P.head("4️⃣ 方案四｜長路線切短、站內轉乘",
       "一條很長的公車，能不能在某座綠線站切成兩段、讓乘客在站內轉乘？切完班距穩不穩、轉乘要走多遠、等多久？",
       "長線只要一處延誤，整條都亂。切短可以讓各段班距更穩，但前提是「轉乘站的班距要穩」，否則轉乘等候反而更差。這頁讓你選路線和切點，看兩段各多長、轉乘要走多遠。")
rsig = D.routes_sig(src)
CODES = list(stg.code)
NAMES = dict(zip(stg.code, stg.name))
rail_keys = [k for k in rts if RU.rail_end(rts[k]["stops"]) is not None]
default = next((k for k in rail_keys if rts[k]["sub"] == "703" and rts[k]["dir"] == 0), rail_keys[0] if rail_keys else None)
if default is None:
    st.warning("找不到兩端有火車站／總站／轉運站的路線。")
    st.stop()
c1, c2 = st.columns(2)
k = c1.selectbox("路線（兩端有鐵路站或轉運站者）", rail_keys, index=rail_keys.index(default), key="p4_route",
                 format_func=lambda k: f"{rts[k]['label']}｜{RU.rail_end(rts[k]['stops'])[1]}")
code = c2.selectbox("在哪一座綠線站轉乘", CODES, index=CODES.index("G15") if "G15" in CODES else 0, key="p4_code",
                    format_func=lambda c: f"{c} {NAMES[c]}")
srow = stg[stg.code == code].iloc[0]
r = rts[k]
rg = RU.s2a_range(r["stops"], srow.geometry.x, srow.geometry.y)
if rg is None:
    st.warning("這條路線的鐵路端已經是最靠近該站的站牌，無法切短。請換路線或換車站。")
    st.stop()

from shapely.ops import substring
from lib import metrics as M
line = r["line"]
s = r["stops"].reset_index(drop=True)
pos = M.monotone_positions(line, s.x.values, s.y.values)
cut = pos[rg["cut_idx"]]
if rg["rail_idx"] == 0:
    kept, rest = substring(line, 0, cut), substring(line, cut, line.length)
else:
    kept, rest = substring(line, cut, line.length), substring(line, 0, cut)
Lk, Lr, Lt = kept.length / 1000, rest.length / 1000, line.length / 1000

RELS = RU.reliability()
TH = RU.reliability_thresholds_default(RELS)
gt = RU.route_gate(RELS, r["sub"], r["dir"], TH)
c1, c2, c3 = st.columns(3)
c1.metric("原路線長度", f"{Lt:.1f} km")
c2.metric("保留段（接鐵路站）", f"{Lk:.1f} km", f"{Lk - Lt:+.1f}", delta_color="off")
c3.metric("被切出去的另一段", f"{Lr:.1f} km", help="這一段需要另外安排（由其他路線接、或改成接駁），本頁不評估。")
st.caption(f"保留：{rg['rail']} → {rg['cut_name']}（第 {rg['from'] + 1}–{rg['to'] + 1} 站）。切點站牌距 {code} 直線約 {rg['walk_m']:.0f} 公尺（轉乘步行距離的下限）。")

st.subheader("改前改後")
ca, cb = st.columns(2)
cx = (srow.geometry.x, srow.geometry.y)
with ca:
    st.markdown("**現況：一整條**")
    m = P.new_map(cx, 11)
    P.draw_lines(m, [line], P.GRAY, 4, tip=f"現況 {r['label']}")
    ui.add_stations(m, labels=False)
    P.show_map(m, "p4_before")
with cb:
    st.markdown("**方案四：在切點分成兩段**")
    m = P.new_map(cx, 11)
    P.draw_lines(m, [kept], P.ORANGE, 5, tip="保留段（接鐵路站）")
    P.draw_lines(m, [rest], P.PURPLE, 4, dash="8 6", tip="被切出去的另一段（另行安排）")
    ui.add_stations(m, labels=False)
    import folium
    folium.CircleMarker([srow.lat, srow.lon], radius=12, color="black", fill=False, weight=3, tooltip=f"轉乘站 {code}").add_to(m)
    P.show_map(m, "p4_after")
st.caption("橘色＝保留、接鐵路站的一段；紫色虛線＝被切出去的另一段；黑圈＝轉乘的綠線站。")

st.subheader("規則檢查")
ico = {"ok": "✅", "fail": "⚠️", "nodata": "❔"}[gt["status"]]
rows = [{"項目": "班距穩定（規則一）", "結果": f"{ico} {gt['why']}",
         "數字": "—" if gt["status"] == "nodata" else f"cv {gt['cv']:.2f}、大間隔 {gt['gap']:.2f}、併班 {gt['bunch']:.2f}"},
        {"項目": "轉乘步行距離（直線，下限）", "結果": f"{rg['walk_m']:.0f} m", "數字": ""},
        {"項目": "預估轉乘等候", "結果": "—" if gt["status"] == "nodata" else f"{gt['mean_min'] / 2:.1f} 分",
         "數字": "實際平均班距 ÷ 2（隨機到站的期望值；單日樣本）" if gt["status"] != "nodata" else "這條路線沒有足夠班距資料"}]
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
if gt["status"] != "ok":
    st.warning("這條路線目前班距不穩或缺資料，依設計原則**不建議在它身上切短**；只是示意。")
P.goto_scenario("到「情境模擬」把這個切法放進整體比較")
P.limits(["班距只有 2026-10-21 單日，且許多路線樣本不足（顯示「❔」）。",
          "轉乘等候只算平均班距的一半，沒算班距不穩造成的額外等待，也沒算兩段班次是否銜接。",
          "被切出去的另一段怎麼處理沒有評估；切點只是示意，實際要看班距變異與轉乘等候。",
          "切點站牌用「最靠近該綠線站的站牌」，轉乘步行距離是直線下限。"])
