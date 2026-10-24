"""改良方案五：班次改善（不改路線）。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data as D, plans as P, rules as RU

src, rts, stg = P.need()
P.head("5️⃣ 方案五｜班次改善（不改路線）",
       "不動路線，只把班次排得更均勻，能不能讓乘客等得比較安心？要多花多少駕駛？",
       "同一條路線的實際班距常和時刻表有落差，有時一小時沒車、有時兩班擠在一起。這頁看實際 vs 時刻表，並算「把班距壓到某個目標」要多開幾班、多花幾個約當駕駛班次。")
rsig = D.routes_sig(src)
S = D.read_csv("outputs/A3_headway_summary.csv")
Hd = D.read_csv("outputs/A3_headway_detail.csv")
if S is None or Hd is None or S.empty:
    st.info("還沒有班距結果。請先在 pilot/ 執行 `python scripts/11_headway.py analyze`。")
    st.stop()
st.warning("**班距只有 1 個平日（2026-10-21），只能示範方法，不能當結論。** 時刻表班距以起點發車間隔代替（假設）。")

routes = sorted(Hd.route.astype(str).unique(), key=lambda r: (not r.isdigit(), r))
c1, c2, c3 = st.columns(3)
rt = c1.selectbox("路線", routes, index=routes.index("GR") if "GR" in routes else 0)
dr = c2.radio("方向", [0, 1], format_func=lambda d: "去程" if d == 0 else "返程", horizontal=True)
stns = sorted(Hd[(Hd.route.astype(str) == rt) & (Hd["dir"] == dr)].station.unique())
if not stns:
    st.info("這個路線方向沒有班距明細。")
    st.stop()
stn = c3.selectbox("通過的車站", stns)
d = Hd[(Hd.route.astype(str) == rt) & (Hd["dir"] == dr) & (Hd.station == stn)].copy()
d["time"] = pd.to_datetime(d.time, utc=True, errors="coerce").dt.tz_convert("Asia/Taipei")
d = d.sort_values("time")

m1, m2, m3 = st.columns(3)
m1.metric("實際平均班距", f"{d.headway_min.mean():.0f} 分", help=f"{len(d)} 個班距，單日。")
m2.metric("時刻表班距（中位）", f"{d.sched_min.median():.0f} 分")
m3.metric("超過時刻表 2 倍的班次", f"{int((d.headway_min > 2 * d.sched_min).sum())}／{len(d)}")
fig = go.Figure()
fig.add_bar(x=d.time, y=d.headway_min, marker_color=np.where(d.headway_min > 2 * d.sched_min, P.RED, "#1f6fb5"), name="實際班距")
fig.add_scatter(x=d.time, y=d.sched_min, mode="lines", line=dict(color="black", dash="dash", shape="hv"), name="時刻表班距")
fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="分鐘", legend=dict(orientation="h"))
st.plotly_chart(fig, width="stretch")
st.caption("長條＝這一班和前一班之間隔了幾分鐘；紅色＝超過時刻表 2 倍。")

st.subheader("如果把班距壓到目標：要多開幾班、多花多少駕駛？")
keymap = [k for k, r in rts.items() if str(r["sub"]) == rt and r["dir"] == dr]
dep = P.departures()
if not keymap or keymap[0] not in dep:
    st.info("這個路線方向沒有 TDX 發車時刻，算不出班次成本。")
else:
    k = keymap[0]
    mins = dep[k]
    span = mins[-1] - mins[0]
    cur = len(mins)
    L = rts[k]["line"].length / 1000
    target = st.slider("目標班距（分鐘）【示範，可調】", 5, 60, 20, 1)
    new_trips = int(span // target) + 1
    dtrips = new_trips - cur
    dkm = dtrips * L
    dshift = dkm / P.SPEED / P.SHIFT
    a, b, c = st.columns(3)
    a.metric("平日班次（單方向）", f"{new_trips}", f"{dtrips:+d}（現況 {cur}）", delta_color="off")
    b.metric("車公里變化", f"{dkm:+,.0f}", help=f"單程 {L:.1f} km × 班次變化。")
    c.metric("約當駕駛班次變化", f"{dshift:+.1f}", help=f"時速 {P.SPEED:g} km、每班 {P.SHIFT:g} 小時【假設】；只含行駛時間，不代表需增減人員。")
    st.caption(f"服務時段 {mins[0] // 60:02d}:{mins[0] % 60:02d}–{mins[-1] // 60:02d}:{mins[-1] % 60:02d}（TDX 星期三首末班，起點發車）；"
               f"假設全天等距發車。這是均勻班距的理想值，沒算尖離峰差異。")
st.info("班距均勻不等於準點：實際班距還受路況影響。真要改善，還要看延誤出在哪（路段、站停、調度），這要更多天的位置資料才看得出。")
P.goto_scenario()
P.limits(["班距只有單日資料；樣本不足的路線已排除。",
          "時刻表班距以起點發車間隔代替計時點班距；服務時段取星期三首末班。",
          "成本換算假設全天等距發車、時速 18 km、每班 8 小時，只含行駛時間，不含休息、空駛、備勤、輪休。",
          "沒有上下車量，無法判斷哪些時段值得加班。"])
