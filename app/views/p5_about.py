import pandas as pd
import streamlit as st

from lib import data as D, metrics as M, ui

ui.banner()
st.title("ℹ️ 關於資料")
st.caption("資料來源、取得時間與限制。本頁內容由資料夾內的檔案即時讀取。")
if D.pilot_dir() is None:
    ui.require_data()
    st.stop()


def when(rel_txt, rel_file):
    t = D.read_text(rel_txt) if rel_txt else None
    if t:
        return t
    m = D.mtime_str(rel_file) if rel_file else None
    return f"{m} (UTC+8，檔案時間)" if m else "—"


a2 = D.read_csv("outputs/A2_station_access.csv")
a2_t = str(a2["computed_at"].iloc[0]) if a2 is not None and "computed_at" in a2.columns and len(a2) else D.mtime_str("outputs/A2_station_access.csv")
rows = [
    ("公車路線、站序、站牌座標（TDX）", "交通部 TDX 運輸資料流通服務 /v2/Bus/StopOfRoute/City/Taoyuan", "data/tdx/stop_of_route.csv", when("data/tdx/StopOfRoute_retrieved_at.txt", "data/tdx/stop_of_route.csv")),
    ("公車路線線型（TDX）", "TDX /v2/Bus/Shape/City/Taoyuan", "data/tdx/Shape_Taoyuan.json.gz", when("data/tdx/Shape_retrieved_at.txt", "data/tdx/Shape_Taoyuan.json.gz")),
    ("公車站序與座標（PDF 版）", "桃園市政府資料開放平台「公車路線資料」所列官方站址表 PDF（ebus.tycg.gov.tw）", "data/route_stops_parsed.csv", when(None, "data/route_stops_parsed.csv")),
    ("公車班表（平日班次、尖離峰每小時班次）", "TDX /v2/Bus/Schedule/City/Taoyuan（只取 800 m 範圍內路線）", "data/tdx/Schedule_Taoyuan_800m_routes.json.gz", when("data/tdx/Schedule_retrieved_at.txt", "data/tdx/Schedule_Taoyuan_800m_routes.json.gz")),
    ("綠線 G11–G15b 車站點位", "OpenStreetMap（© OpenStreetMap contributors, ODbL）；G15b 為估計", "data/stations_green_north.csv", when("data/stations_retrieved_at.txt", "data/stations_green_north.csv")),
    ("步行路網", "OpenStreetMap，OSMnx network_type=walk，每站 1,100 m", "data/walk/*.graphml", when(None, "data/walk/G11.graphml")),
    ("步行等時圈 300／500／800 m", "由 pilot/scripts/05_access.py 計算", "outputs/A2_isochrones.gpkg", f"{a2_t}（計算時間）" if a2_t else "—"),
    ("村里人口與 65 歲以上人口", "內政部戶政司 人口統計資料開放 API ODRP014/11509（115 年 9 月）", "data/taoyuan_village_pop65_11509.csv", when(None, "data/taoyuan_village_pop65_11509.csv")),
    ("村里界", "OpenStreetMap admin_level=9（以村里代碼對應戶政資料）", "data/villages_pop65.gpkg", when(None, "data/villages_pop65.gpkg")),
    ("公車即時動態 A1", "TDX /v2/Bus/RealTimeByFrequency/City/Taoyuan（收集器 06_collect_a1.py）", "data/a1/a1_*.csv.gz",
     f"{len(D.a1_files())} 個收集檔" if D.a1_files() else "尚未收集（待實測）"),
]
from lib import proxy as X
_t = lambda f: (X.DERIVED / f).read_text(encoding="utf-8").split("；")[0] if (X.DERIVED / f).exists() else "—"
rows += [
    ("產業用地（OSM）", "OpenStreetMap landuse=industrial（Overpass），移工通勤代理指標", "app/derived/A4_industrial_osm.gpkg", _t("A4_industrial_retrieved_at.txt")),
    ("產業園區範圍", "經濟部產業園區管理局「產業園區範圍圖」SHP（data.gov.tw 資料集 25598，政府資料開放授權條款第1版）", "app/derived/A4_industrial_official.gpkg", _t("A4_industrial_official_retrieved_at.txt")),
]
tbl = pd.DataFrame(rows, columns=["資料", "來源", "檔案（pilot/ 底下）", "取得／計算時間"])
tbl["狀態"] = ["✅ 有" if (f.startswith("app/") and (D.APP_DIR / f[4:]).exists()) or (D.P(f) is not None or (f.endswith("*.graphml") and D.P("data/walk") is not None) or (f.startswith("data/a1") and D.a1_files())) else "— 無"
              for f in tbl["檔案（pilot/ 底下）"]]
st.subheader("資料來源")
st.dataframe(tbl, hide_index=True, width="stretch")
st.caption("「檔案」欄以 pilot/ 為起點；app/derived/ 開頭者為本平台自行產生的衍生資料。")

st.subheader("限制（展示與簡報時請一併說明）")
pr = D.read_csv("data/parse_report.csv")
lim = []
src = D.current_source()
if pr is not None and "status" in pr.columns:
    bad = pr[pr.status != "ok"]
    n_ok = int((pr.status == "ok").sum())
    txt = (f"**PDF 站址表解析**：共 {len(pr)} 份站址表，{n_ok} 份可解析，**{len(bad)} 份無法解析**"
           f"（{', '.join(f'{k} {v} 份' for k, v in bad.status.value_counts().items())}），PDF 版資料不含這些路線。")
    if "tdx" in D.available_sources():
        tdx_routes = {r["sub"] for r in D.routes("tdx").values()}
        miss = sorted(set(bad.route.astype(str)))
        covered = [r for r in miss if r in tdx_routes]
        txt += f" 其中 {len(covered)} 條在 TDX 資料中有站序（使用 TDX 來源時已納入）。"
    lim.append(txt)
lim.append("**路線線型**：TDX 來源使用 TDX Shape 線型；PDF 來源以相鄰站牌直線連線近似，轉彎多的路段長度會低估。PDF 版另做兩項清理：剔除座標尖刺點、站間 >8 km 跳躍處切開（見 A1_qc_cleaning_log.csv）。PDF 的「型態」不等於 TDX 的 SubRoute。")
stg = D.stations()
est = stg[stg.estimated]
lim.append("**車站點位**：取自 OSM 志工標註的施工中車站點，不是官方出入口座標。" +
           (f"**{'、'.join(est.code + ' ' + est.name)} 的點位為估計**（" + "；".join(est.note) + "）。" if len(est) else ""))
lim.append("**步行等時圈**：從車站點最近的路網節點起算路網距離，可達路段兩側各緩衝 50 m；車站點與最近節點有數十至一百多公尺的落差。")
lim.append(f"**65 歲以上人口**：村里人口依面積比例分配（假設村里內人口均勻分布），工業區、農地占比高的村里會失真；移工不在戶籍統計內。情境模擬另以 {M.GRID} m 格點計算、到站牌距離為直線距離。")
import glob as _g
freq_ok = bool(_g.glob(str(D.pilot_dir() / "outputs" / "*freq*.csv"))) or bool(_g.glob(str(D.pilot_dir() / "data" / "tdx" / "Schedule_*.json.gz")))
lim.append("**班次頻率**：" + ("已取得 TDX 班表（時刻表，不是實際營運）。桃園班表只有起點發車時刻，尖離峰以起點發車時刻判定，長路線可能偏移數十分鐘；"
                              "平日以星期三有營運的班次代表；班表只抓 800 m 範圍內路線，其他路線的班次與車公里不計。" if freq_ok else
                              "尖峰／離峰班次需要 TDX 班表，目前為【待實測】；所有可及性指標都只看站牌與路線，沒有反映班次多寡。"))
lim.append("**情境模擬**：只計算站牌覆蓋、65+ 覆蓋與路線單程長度；未計車公里、旅行時間、轉乘次數、道路是否可行駛公車、駕駛人力。預設接駁線由演算法從既有站牌挑選，只是示意。")
lim.append("**駕駛人力換算**：平日班次取自 TDX 班表；pilot 資料中沒有 TDX S2STravelTime，桃園班表只有起點發車時刻，因此營運速率預設 18 km/h 為【假設，可調整】，"
           "A1 即時動態樣本足夠（每路線方向 ≥30 組 90 秒輪詢）時可改用實測；每班駕駛 8 小時為【假設，可調整】；接駁線班次預設採 GR 現況平日單向班次，為【假設，可調整】。"
           "只計行駛時間，未含端點休息、調度空車、場站往返、備勤與輪休；「可移轉駕駛人力」是換算值，不代表可裁減人員。")
lim.append("**移工（探索性）**：沒有移工空間資料，以產業用地（OSM landuse=industrial＋產管局產業園區範圍圖）作為通勤需求的代理指標。產業用地不等於移工人口；"
           "宿舍位置、雇用人數、班別時間都不知道；OSM 標註完整度未查核；產管局圖資未含零星工廠用地。正式研究需以市府彙總資料或訪談驗證。")
lim.append("**通車前後比較**：需在通車前收集 2–3 週即時動態並於通車後再測；資料未滿前任何圖表都只是方法示範。")
lim.append("**未做任何問卷、訪談或實地調查**；本平台不代表桃園市政府、交通局或任何營運業者的立場或方案。")
lim.append("**AI 協助**：本平台程式與試行分析由 AI 協助撰寫與執行，團隊需自行複核並重跑（依簡章須於報名表說明 AI 使用方式）。")
for i, t in enumerate(lim, 1):
    st.markdown(f"{i}. {t}")

st.subheader("車站點位")
st.dataframe(stg[["code", "name", "lat", "lon", "source", "note"]].rename(columns={"code": "代碼", "name": "站名", "source": "來源", "note": "備註"}),
             hide_index=True, width="stretch")

if pr is not None and "status" in pr.columns:
    with st.expander(f"無法解析的站址表清單（{int((pr.status != 'ok').sum())} 份）"):
        st.dataframe(pr[pr.status != "ok"], hide_index=True)

st.subheader("pilot/outputs 檔案清單")
ol = D.outputs_list()
if ol:
    st.dataframe(pd.DataFrame(ol, columns=["檔案", "修改時間（UTC+8）", "大小（bytes）"]), hide_index=True)
st.caption("所有時間為 Asia/Taipei（UTC+8）。重跑方式見 pilot/README.md。")
