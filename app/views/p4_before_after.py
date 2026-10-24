import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lib import data as D, ui

ui.banner()
st.title("⏱️ 通車前後比較")
st.markdown("**這頁在回答：** 綠線通車之後，公車會不會比較快、兩班車會不會隔得比較穩？")
st.info("**先看這句：** 通車後的紀錄還沒有。現在只有很短的通車前樣本，不能拿來下結論。")
st.caption("做法是記錄公車當時的位置。通車前先記一段，通車後用同樣的時段再記一次，才能比。")
if D.pilot_dir() is None:
    ui.require_data()
    st.stop()

files = D.a1_files()
routes_cfg = D.read_text("config/collector_routes.txt")
log = D.read_text("logs/collector.log")
last_log = log.splitlines()[-1] if log else None

if not files:
    st.info("### 還沒有可以比較的即時資料\n"
            "目前還沒有收集到公車位置，所以這頁**不顯示任何行駛時間或兩班車隔多久**。\n\n"
            "- **通車前**：要連續記大約 2–3 週，當作基準。\n"
            "- **通車後**：正式通車日（以官方公告為準）之後，用同樣的星期和時段再記一次。\n"
            "- 檔案一出現，重新整理就會看到圖。")
    with st.expander("收集設定（給要查證的人）"):
        st.markdown("程式每 90 秒記一次指定路線的車輛位置（尖峰時段）。檔案在 `pilot/data/a1/`。")
        if routes_cfg:
            rl = [r for r in routes_cfg.split() if r]
            st.caption(f"設定要收集的路線（{len(rl)} 條）：" + " ".join(rl))
        st.caption("收集紀錄最後一行：" + (f"`{last_log}`" if last_log else "（無）"))
    st.stop()

raw = D.a1_raw()
if raw is None or raw.empty:
    st.warning("偵測到收集檔，但目前讀不到內容（可能正在寫入），請稍後按「重新讀取最新資料」。")
    st.stop()



def to_taipei(sr):
    """含時區的字串照時區換算；沒有時區的字串（收集器以 UTC+8 寫入）直接視為台北時間。"""
    sr = sr.astype(str)
    has_tz = sr.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)
    out = pd.Series(pd.NaT, index=sr.index, dtype="datetime64[ns, Asia/Taipei]")
    if has_tz.any():
        out[has_tz] = pd.to_datetime(sr[has_tz], errors="coerce", utc=True, format="ISO8601").dt.tz_convert("Asia/Taipei")
    if (~has_tz).any():
        out[~has_tz] = pd.to_datetime(sr[~has_tz], errors="coerce", format="ISO8601").dt.tz_localize("Asia/Taipei")
    return out


raw["poll"] = to_taipei(raw["poll_time"]) if "poll_time" in raw else pd.NaT
raw["t"] = to_taipei(raw["GPSTime"]) if "GPSTime" in raw else raw["poll"]
raw["lat"] = pd.to_numeric(raw.get("lat"), errors="coerce")
raw["lon"] = pd.to_numeric(raw.get("lon"), errors="coerce")
rcol = "RouteName" if "RouteName" in raw.columns else None
t0, t1 = raw.poll.min(), raw.poll.max()
st.success(f"**已收集的時間**：{t0:%Y-%m-%d %H:%M} ～ {t1:%Y-%m-%d %H:%M}（台灣時間），共 {len(raw):,} 筆位置、"
           f"抓取 {raw.poll.nunique():,} 次、{raw.PlateNumb.nunique() if 'PlateNumb' in raw else 0:,} 輛車、"
           f"{raw[rcol].nunique() if rcol else 0} 條路線。")
span_days = (t1 - t0).total_seconds() / 86400 if pd.notna(t0) else 0
if span_days < 14:
    st.warning(f"目前只收集約 {span_days:.1f} 天（{span_days * 24:.1f} 小時），少於建議的 2–3 週。下面的圖只是確認方法能跑，不能當結論。")

with st.sidebar:
    st.markdown("**本頁設定**")
    open_date = st.date_input("綠線北段通車日（官方公告後再填）", value=None)
    R = st.slider("車站周圍多大範圍算「有車經過」（公尺）", 100, 300, 150, 25)

if open_date is not None:
    raw["期間"] = np.where(raw.poll.dt.date < open_date, "通車前", "通車後")
else:
    raw["期間"] = "通車前"

# 1. 每次輪詢的在線車數
if rcol:
    cnt = raw.groupby([raw.poll.dt.floor("15min"), rcol]).PlateNumb.nunique().reset_index(name="在線車數")
    top = raw[rcol].value_counts().head(8).index
    fig = px.line(cnt[cnt[rcol].isin(top)], x="poll", y="在線車數", color=rcol, labels={"poll": "時間（UTC+8）", rcol: "路線"},
                  title="各路線路上有幾輛車（每 15 分鐘，只畫最多的 8 條）")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch")


# 2. 計時點通過 → 班距、站間行駛時間（方法同 pilot/scripts/07_summarize_a1.py）
@st.cache_data(show_spinner="計算班距與旅行時間…")
def passes(files_sig, R, open_date):
    import geopandas as gpd
    df = raw.dropna(subset=["lat", "lon", "t"])
    stg = D.stations()
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326).to_crs(D.CRS_M)
    out = []
    for _, s in stg.iterrows():
        near = g[g.geometry.distance(s.geometry) <= R]
        for (plate, dirn), d in near.groupby(["PlateNumb", "Direction"]):
            d = d.sort_values("t")
            gap = d.t.diff().dt.total_seconds().fillna(9e9)
            for _, grp in d.groupby((gap > 600).cumsum()):
                out.append(dict(station=s.code, plate=plate, dir=dirn, route=grp[rcol].iloc[0] if rcol else "", t=grp.t.min(), 期間=grp["期間"].iloc[0]))
    return pd.DataFrame(out)


P = passes(tuple(files), R, open_date)
if P.empty:
    st.info("這段樣本裡，還沒有公車開進綠線車站附近。所以還看不出兩班隔多久、站和站要開多久。")
else:
    hw = []
    for (stn, rt, dirn, per), d in P.groupby(["station", "route", "dir", "期間"]):
        t = d.t.sort_values()
        for day, td in t.groupby(t.dt.date):
            h = td.diff().dt.total_seconds().dropna() / 60
            h = h[h < 180]
            for v in h:
                hw.append(dict(station=stn, route=rt, dir=dirn, 期間=per, headway=v))
    H = pd.DataFrame(hw)
    if not H.empty:
        S = H.groupby(["station", "route", "期間"]).headway.agg(["count", "mean", "std"]).reset_index()
        S["CV"] = (S["std"] / S["mean"]).round(2)
        c1, c2 = st.columns(2)
        with c1:
            fig = px.box(H, x="station", y="headway", color="期間", points=False, labels={"station": "車站", "headway": "兩班車隔幾分鐘"},
                         title="到站間隔（同一天、相鄰兩輛車）")
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig = px.bar(S[S["count"] >= 3], x="station", y="CV", color="route", barmode="group", facet_row="期間" if open_date else None,
                         labels={"station": "車站", "CV": "間隔穩不穩（愈低愈穩）"}, title="班距穩不穩（至少 3 筆才畫）")
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, width="stretch")
        st.dataframe(S.rename(columns={"count": "樣本數", "mean": "平均隔幾分鐘", "std": "起伏（分鐘）"}).round(1), hide_index=True)
    tt = []
    for (plate, dirn), d in P.groupby(["plate", "dir"]):
        d = d.sort_values("t")
        for i in range(len(d) - 1):
            a, b = d.iloc[i], d.iloc[i + 1]
            m = (b.t - a.t).total_seconds() / 60
            if 0 < m < 90 and a.station != b.station:
                tt.append(dict(route=a.route, 區間=f"{a.station}→{b.station}", minutes=m, 期間=a["期間"], 時段=a.t.hour))
    T = pd.DataFrame(tt)
    if not T.empty:
        fig = px.box(T, x="區間", y="minutes", color="期間", labels={"minutes": "開了幾分鐘"}, title="相鄰兩站之間實際開了多久")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, width="stretch")

status = D.read_text("outputs/A3_sample_status.txt")
if status:
    with st.expander(f"pilot 收集狀態摘要：outputs/A3_sample_status.txt（{D.mtime_str('outputs/A3_sample_status.txt')} UTC+8）"):
        st.code(status, language=None)
for f in ["outputs/A3_headway_sample.csv", "outputs/A3_traveltime_sample.csv"]:
    df = D.read_csv(f)
    if df is not None:
        with st.expander(f"pilot 摘要輸出：{f}（{D.mtime_str(f)} UTC+8）"):
            st.dataframe(df, hide_index=True)

if open_date is None or not (raw["期間"] == "通車後").any():
    st.info("**通車後的資料還沒有。** 要等綠線北段正式通車，並用同樣的時段再收集一次，才能比前後。")
with st.expander("這個「有車經過」怎麼判定"):
    st.markdown("以捷運站為圓心、用左側的半徑畫一個圈。同一車牌、同一方向，在圈裡連續出現、而且間隔不超過 10 分鐘，算一次經過。"
                "位置大約每 90 秒記一次，所以時間不會準到秒。")
