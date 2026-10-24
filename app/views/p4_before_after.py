import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lib import data as D, ui

ui.banner()
st.title("⏱️ 通車前後比較")
st.caption("以 TDX 公車即時動態 A1（定時車輛位置）建立通車前營運基準，通車後同時段再測，比較旅行時間、班距與班距穩定度。")
if D.pilot_dir() is None:
    ui.require_data()
    st.stop()

files = D.a1_files()
routes_cfg = D.read_text("config/collector_routes.txt")
log = D.read_text("logs/collector.log")
last_log = log.splitlines()[-1] if log else None

if not files:
    st.info("### 資料蒐集進行中，尚無可比較的即時資料\n"
            "目前 `pilot/data/a1/` 還沒有收集檔，因此本頁**不顯示任何旅行時間或班距數字**。\n\n"
            "- **通車前**：收集器 `06_collect_a1.py` 每 90 秒記錄一次指定路線的車輛位置，建議連續收集 2–3 週，作為通車前基準。\n"
            "- **通車後**：綠線北段正式通車（日期依官方公告）後，於相同星期與時段再收集一次，才能進行前後比較。\n"
            "- 資料一出現，本頁會自動偵測並顯示資料期間、車輛數、班距與站間旅行時間圖表（按左側「重新讀取最新資料」即可）。")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**預計比較的指標**")
        st.markdown("- 綠線車站附近計時點之間的實際行駛時間（同一車牌、同方向）\n- 各計時點的班距平均、標準差、變異係數（CV）\n- 尖峰／離峰差異；必要時以未受影響路線作為對照組")
    with c2:
        st.markdown("**收集器狀態（讀自 pilot/logs，唯讀）**")
        if routes_cfg:
            rl = [r for r in routes_cfg.split() if r]
            st.caption(f"設定的收集路線（{len(rl)} 條）：" + " ".join(rl))
        st.caption("收集日誌最後一行：" + (f"`{last_log}`" if last_log else "（無）"))
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
st.success(f"**資料期間**：{t0:%Y-%m-%d %H:%M} ～ {t1:%Y-%m-%d %H:%M}（UTC+8），共 {len(raw):,} 筆位置紀錄、"
           f"{raw.poll.nunique():,} 次輪詢、{raw.PlateNumb.nunique() if 'PlateNumb' in raw else 0:,} 輛車、"
           f"{raw[rcol].nunique() if rcol else 0} 條路線；收集檔 {len(files)} 個。")
span_days = (t1 - t0).total_seconds() / 86400 if pd.notna(t0) else 0
if span_days < 14:
    st.warning(f"目前只收集約 {span_days:.1f} 天（{span_days * 24:.1f} 小時），少於建議的 2–3 週：以下圖表只用來確認資料與方法可行，不能作為結論。")

with st.sidebar:
    st.markdown("**本頁設定**")
    open_date = st.date_input("綠線北段通車日（官方公告後再填）", value=None)
    R = st.slider("計時點半徑（m）", 100, 300, 150, 25)

if open_date is not None:
    raw["期間"] = np.where(raw.poll.dt.date < open_date, "通車前", "通車後")
else:
    raw["期間"] = "通車前"

# 1. 每次輪詢的在線車數
if rcol:
    cnt = raw.groupby([raw.poll.dt.floor("15min"), rcol]).PlateNumb.nunique().reset_index(name="在線車數")
    top = raw[rcol].value_counts().head(8).index
    fig = px.line(cnt[cnt[rcol].isin(top)], x="poll", y="在線車數", color=rcol, labels={"poll": "時間（UTC+8）", rcol: "路線"},
                  title="各路線在線車輛數（每 15 分鐘，取前 8 條路線）")
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
    st.info("取樣期間內還沒有車輛通過綠線車站附近的計時點。")
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
            fig = px.box(H, x="station", y="headway", color="期間", points=False, labels={"station": "計時點（車站）", "headway": "班距（分鐘）"},
                         title="各計時點班距分布（同日相鄰兩車）")
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig = px.bar(S[S["count"] >= 3], x="station", y="CV", color="route", barmode="group", facet_row="期間" if open_date else None,
                         labels={"station": "計時點", "CV": "班距變異係數（越低越規律）"}, title="班距規律性（樣本 ≥3）")
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, width="stretch")
        st.dataframe(S.rename(columns={"count": "樣本數", "mean": "平均班距(分)", "std": "標準差(分)"}).round(1), hide_index=True)
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
        fig = px.box(T, x="區間", y="minutes", color="期間", labels={"minutes": "行駛時間（分鐘）"}, title="相鄰計時點之間的實際行駛時間")
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
    st.info("**通車後資料：尚未存在。** 前後比較要等綠線北段正式通車、並於相同時段再收集後才能進行。")
st.caption("計時點：以車站點位為圓心、半徑 R 的範圍；同一車牌同方向在範圍內的連續紀錄（間隔 ≤10 分鐘）視為一次通過。A1 為約每 90 秒輪詢的位置，時間解析度有限。")
