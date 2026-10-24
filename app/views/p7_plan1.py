"""改良方案一：GR 縮短成接駁。"""
import pandas as pd
import streamlit as st

from lib import data as D, plans as P, rules as RU

src, rts, stg = P.need()
P.head("1️⃣ 方案一｜GR 縮短成接駁",
       "GR 跟綠線走在同一條路的那一段，通車後可以裁掉嗎？裁掉能省多少駕駛、誰會受影響？",
       "GR 約三分之一的路程落在捷運站 500 公尺內，是並行最多的一條。只留桃園總站到 G11，省下的駕駛班次大約有 5 班；代價是 G12、G13、G15b 一車到站的長者略減，要靠方案二、三補位。")
rsig = D.routes_sig(src)
R = P.plan1(src, rsig)
names = dict(zip(stg.code, stg.name))

gr = R["gr"]
c1, c2, c3 = st.columns(3)
avg_before = sum(g["before"] for g in gr) / len(gr)
avg_after = sum(g["after"] for g in gr) / len(gr)
c1.metric("GR 單程長度（兩方向平均）", f"{avg_after:.1f} km", f"{avg_after - avg_before:+.1f}（原 {avg_before:.1f}）", delta_color="off")
c2.metric("平日約當駕駛班次", f"{R['shifts1']:.1f}", f"{R['shifts1'] - R['shifts0']:+.1f}（現況 {R['shifts0']:.1f}）", delta_color="inverse",
          help=f"估算，含假設：時速 {P.SPEED:g} km、每班 {P.SHIFT:g} 小時，只含行駛時間。不代表可裁減人員。")
lost = sum(max(a - b, 0) for a, b in R["people"].values())
c3.metric("一車到站的 65 歲以上，減少合計", f"{lost:,.0f} 人", help="各站 1.5 公里內、站牌 300 公尺內；相鄰站的範圍會重疊，這是各站減少人數的加總，只用來看量級。")
st.caption(f"依據：GR 在 7 站 500 公尺範圍內的長度 " + "、".join(
    f"{g['label']} {g['overlap_km']:.2f} km（{g['share']:.0%}）" for g in gr if g["overlap_km"] is not None) + "。班次來自 TDX 時刻表（星期三）。")

st.subheader("改前改後")
ca, cb = st.columns(2)
cx = (stg.geometry.x.mean(), stg.geometry.y.mean())
with ca:
    st.markdown("**現況：GR 沿綠線全程並行**")
    m = P.new_map(cx, 12)
    for g in gr:
        P.draw_lines(m, R["net0"][g["key"]]["lines"], "#1f6fb5", 5, tip=f"現況 {g['label']}")
    from lib import ui
    ui.add_stations(m, circles=500)
    P.show_map(m, "p1_before")
with cb:
    st.markdown("**方案一：裁掉並行段，只留兩端**")
    m = P.new_map(cx, 12)
    for g in gr:
        P.draw_lines(m, R["net0"][g["key"]]["lines"], P.RED, 3, dash="6 6", tip="被裁掉的並行段", opacity=0.85)
        P.draw_lines(m, R["net1"][g["key"]]["lines"], P.ORANGE, 5, tip=f"保留 {g['label']}")
    ui.add_stations(m, circles=500)
    P.show_map(m, "p1_after")
st.caption("藍色＝現況的 GR；紅色虛線＝被裁掉的並行段；橘色＝方案一保留的部分；圈圈＝車站 500 公尺。")

st.subheader("誰受影響：各站一車到站的 65 歲以上")
rows = [{"車站": f"{c} {names[c]}", "現況": round(a), "方案一": round(b), "變化": round(b - a)} for c, (a, b) in R["people"].items()]
df = pd.DataFrame(rows)
st.dataframe(df, hide_index=True, width="stretch")
st.caption("只有 G12、G13、G15b 減少，其餘站不變。G14 本來就沒有 GR 能一車直達，所以沒有改變，需靠方案二。")

st.subheader("規則檢查：班距穩定才裁切")
RELS = RU.reliability()
TH = RU.reliability_thresholds_default(RELS)
rows = []
for g in gr:
    gt = RU.route_gate(RELS, "GR", g["dir"], TH)
    ico = {"ok": "✅", "fail": "⚠️", "nodata": "❔"}[gt["status"]]
    rows.append({"路線": g["label"], "檢查": f"{ico} {gt['why']}",
                 "cv": "—" if gt["status"] == "nodata" else f"{gt['cv']:.2f}",
                 "大間隔比例": "—" if gt["status"] == "nodata" else f"{gt['gap']:.2f}"})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption(f"門檻是示範值（cv 上限 {TH['cv']}、大間隔上限 {TH['gap']}），不是標準；班距只有單日資料。保留下來的 GR 兩端會被依賴，所以要先看穩不穩。")
P.goto_scenario()
P.limits(["班距只有 2026-10-21 單日，不能推論為常態。",
          "約當駕駛班次只含行駛時間，不含休息、空駛、備勤、輪休；時速 18 km 是假設。",
          "拿掉並行段時，假設車在剩下的兩端掉頭，沒算掉頭與空車。",
          "65 歲以上人口依村里面積比例分配，走到站牌用直線 300 公尺。",
          "沒有上下車量，無法判斷 GR 的乘客是否真的會改搭捷運。"])
