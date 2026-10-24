"""班距可靠度：「班距穩定才裁切」的檢查頁。讀 pilot/scripts/11_headway.py 產生的 outputs/A3_headway_*.csv。"""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lib import data as D, ui

ui.banner()
st.title("📏 班距可靠度")
st.markdown("**這頁在回答：** 一條公車平常有沒有準時、兩班車會不會擠在一起或隔太久？要把它當成接駁線、或裁短之前，先看這個。")

if D.pilot_dir() is None:
    ui.require_data()
    st.stop()

S = D.read_csv("outputs/A3_headway_summary.csv")
H = D.read_csv("outputs/A3_headway_detail.csv")
if S is None or S.empty:
    st.info("### 還沒有班距結果\n請先在 `pilot/` 執行 `python scripts/11_headway.py analyze`（說明見 pilot/README.md）。")
    st.stop()

ndays = int(S["days"].max()) if "days" in S else 0
suf = S[S.sufficient.astype(str).str.lower().isin(["true", "1"])].copy()
st.warning(f"**目前只有 {ndays} 個平日的資料，只能示範方法，不能當結論。** 班距是用公車位置推算通過車站的時間（TDX 歷史位置資料，2026-10-21），"
           "時刻表班距以起點發車間隔代替（假設）。樣本太少的組合已排除。")
st.info("**先看這句：** 「班距穩定才裁切」是設計原則：被當成接駁的路線，變異和大間隔要在門檻內。門檻要由更多天的資料和市府排班規則決定，這裡的數字只是讓你試著調。")

if suf.empty:
    st.error("目前沒有樣本夠多的組合，無法檢查。")
    st.stop()

with st.sidebar:
    st.markdown("### 班距門檻【示範值，可調】")
    cv_default = round(float(suf.cv.median()), 2)
    cv_max = st.slider("班距變異係數 cv 上限", 0.1, 1.5, min(max(cv_default, 0.1), 1.5), 0.05,
                       help="cv＝班距標準差÷平均。越大代表越不均勻。預設是目前資料的中位數，不是標準。")
    gap_max = st.slider("大間隔比例上限", 0.0, 0.6, 0.2, 0.05,
                        help="大間隔＝實際班距超過時刻表 2 倍的比例。倍數為暫定。")
    bunch_max = st.slider("併班比例上限", 0.0, 0.6, 0.1, 0.05,
                          help="併班＝實際班距低於時刻表 0.25 倍（兩班擠在一起）的比例。倍數為暫定。")

# 路線方向：取各站中最差的一項
g = suf.groupby(["route", "dir"]).agg(站數=("station", "nunique"), 班距數=("n_headways", "sum"),
                                       cv=("cv", "max"), 大間隔=("gap_rate", "max"), 併班=("bunch_rate", "max"),
                                       時刻表班距=("sched_min", "median"), 實際平均=("mean_min", "median")).reset_index()
g["檢查"] = np.where((g.cv <= cv_max) & (g.大間隔 <= gap_max) & (g.併班 <= bunch_max), "✅ 在門檻內", "⚠️ 超過門檻")
g["方向"] = g["dir"].map({0: "去程", 1: "返程"})
n_ok = int((g.檢查.str.startswith("✅")).sum())
c1, c2, c3 = st.columns(3)
c1.metric("可檢查的路線方向", len(g))
c2.metric("在門檻內", n_ok)
c3.metric("超過門檻", len(g) - n_ok)
st.caption("每個路線方向取各站最差的一項。**超過門檻不代表這條線不好，是代表現在不適合拿它當接駁或在它身上裁切。**")

show = g.sort_values(["檢查", "cv"], ascending=[False, False])[["route", "方向", "檢查", "cv", "大間隔", "併班", "時刻表班距", "實際平均", "班距數"]]
show = show.rename(columns={"route": "路線", "cv": "變異係數 cv", "大間隔": "大間隔比例", "併班": "併班比例",
                            "時刻表班距": "時刻表班距（分）", "實際平均": "實際平均（分）"})
st.dataframe(show, use_container_width=True, hide_index=True)

st.divider()
st.subheader("看單一路線一整天")
routes = sorted(g.route.unique(), key=lambda r: (not r.isdigit(), r))
default = routes.index("GR") if "GR" in routes else 0
c1, c2 = st.columns(2)
rt = c1.selectbox("路線", routes, index=default)
stn_opts = sorted(suf[suf.route == rt].station.unique())
stn = c2.selectbox("車站（通過計時點）", stn_opts)
if H is not None and not H.empty and "time" in H:
    d = H[(H.route == rt) & (H.station == stn)].copy()
    d["time"] = pd.to_datetime(d.time, utc=True, errors="coerce").dt.tz_convert("Asia/Taipei")
    d["方向"] = d["dir"].map({0: "去程", 1: "返程"})
    d["狀態"] = np.where(d.headway_min > 2 * d.sched_min, "超過時刻表 2 倍", "其他")
    if d.empty:
        st.caption("這個路線與車站沒有班距明細。")
    else:
        fig = px.bar(d, x="time", y="headway_min", color="狀態", facet_col="方向",
                     color_discrete_map={"超過時刻表 2 倍": "#d64545", "其他": "#1f6fb5"},
                     labels={"time": "通過時刻", "headway_min": "實際班距（分鐘）"})
        for a in fig.layout.annotations:
            a.text = a.text.split("=")[-1]
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("長條＝這一班和前一班之間隔了幾分鐘。單日資料，只看形狀，不要推論為常態。")

with st.expander("怎麼算的、有什麼限制"):
    st.markdown(
        "- 把公車位置投影到實際線型上，在相鄰兩筆位置（相隔不超過 180 秒）之間內插，求出通過車站的時刻；兩班通過時刻的差就是實際班距。\n"
        "- 時刻表班距用 TDX 時刻表起點發車間隔代替計時點班距【假設】；只分析平日 07–09、09–17、17–19。\n"
        "- 抽樣漏車會被當成大間隔，使「大間隔比例」偏高；每組至少 5 個班距才列入。\n"
        "- 前進比例太低（線型方向可能不符或為迴圈）的路線已排除。\n"
        "- 程式：`pilot/scripts/11_headway.py`（含 `selftest`，用合成資料驗證）。"
    )
