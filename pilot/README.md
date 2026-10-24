# 前期試行分析（為桃園做研究 115 年度・綠線北段公車路網重整）

所有時間均為 Asia/Taipei（UTC+8）。本資料夾的每個數字都由下列腳本實際計算；無法取得的項目一律標示【待實測】，不得手動填值。

## 環境
```bash
cd /workspace/taoyuan_research/pilot
python3 -m venv .venv            # 系統 pip 受 PEP 668 限制，需用 venv
.venv/bin/pip install osmnx geopandas shapely matplotlib scipy pandas
sudo apt-get install poppler-utils   # 需要 pdftotext
# 中文字型：/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc（Noto Sans CJK TC）
```

## 資料來源
| 資料 | 來源 | 檔案 |
|---|---|---|
| 公車路線清單與站址表連結 | 桃園市政府資料開放平台「公車路線資料」資料集（d7a0513d），XML | data/tycg_route_info.xml / .json |
| 各路線站序與站牌座標 | 上述資料集的 stopAddrUrl 欄位所列官方 PDF（https://ebus.tycg.gov.tw/cms/api/route/{ID}/stop-address.pdf） | data/stop_pdfs/, data/route_stops_parsed.csv |
| 綠線 G11–G15b 車站點位 | OpenStreetMap（Overpass），節點編號見 CSV；G15b 為估計 | data/stations_green_north.csv |
| 步行路網 | OpenStreetMap，osmnx network_type=walk，每站 1,100 m | data/walk/{code}.graphml |
| 村里人口／65 歲以上 | 內政部戶政司 RIS API ODRP014/11509（115年9月） | data/taoyuan_village_pop65_11509.csv |
| 村里界 | OSM admin_level=9（nat_ref 對應戶政村里代碼） | data/villages_pop65.gpkg |
| TDX 線型、站序、班表 | TDX Bus/Shape、StopOfRoute、Schedule（City/Taoyuan） | data/tdx/ |
| A1 公車動態（分析三） | TDX RealTimeByFrequency（需會員金鑰） | data/a1/ |

## 執行順序
```bash
# 0. TDX 金鑰（由使用者設定在環境變數；程式只讀取，不輸出、不寫檔）
export TDX_CLIENT_ID=...; export TDX_CLIENT_SECRET=...
# 早期 PDF 版（對照用）
.venv/bin/python scripts/01_fetch_stop_pdfs.py      # 下載站址 PDF（間隔 1.2 秒）
.venv/bin/python scripts/03_parse_stop_pdfs.py      # 解析 PDF → route_stops_parsed.csv
.venv/bin/python scripts/04_overlap.py              # 分析一 PDF 近似版 → outputs/A1_route_overlap_*
# 共用
.venv/bin/python scripts/02_walk_network.py         # 7 站 OSM 步行路網
.venv/bin/python scripts/05a_villages.py            # 村里界＋人口
.venv/bin/python scripts/05_access.py               # 等時圈（outputs/A2_isochrones.gpkg）＋PDF 站牌計數
# TDX 版（主要結果）
.venv/bin/python scripts/09_tdx_static.py Shape StopOfRoute   # 各 1 次呼叫；已存在的檔案會略過
.venv/bin/python scripts/09b_routes_and_schedule.py    # stop_of_route.csv、collector_routes.txt（800 m 範圍內路線＋GR2）、Schedule（2 次呼叫）
.venv/bin/python scripts/04b_overlap_tdx.py         # 分析一 TDX 版 → outputs/A1_tdx_*、A1_compare_tdx_vs_pdf.csv
.venv/bin/python scripts/10_frequency.py            # 分析二 TDX 版 → outputs/A2_tdx_*
.venv/bin/python scripts/07_summarize_a1.py         # 分析三摘要（未滿 2–3 週前僅為樣本）→ outputs/A3_*
.venv/bin/python scripts/08_report_tables.py        # 由 CSV 產生提案用 Markdown 表格
```
`scripts/tdx.py` 是共用模組，負責：
- token 取得與更新；
- 每次呼叫至少間隔 13 秒（跨程序共用，以 `logs/.tdx_last_call` 協調）；
- 429／5xx 時指數退避重試；
- 用量帳本 `logs/tdx_usage.csv`，只記時間、狀態、位元組與端點，不含金鑰。

## A1 收集器（分析三）
- 啟動時間：2026-10-24 10:13（UTC+8）。PID 記在 `logs/collector.pid`，以 setsid＋nohup 啟動，離開終端後仍會繼續執行。
- 路線清單：`config/collector_routes.txt`（59 條：GR、GR2，以及 7 站 800 m 步行範圍內有 TDX 站牌的全部路線，含 5015、5019、5022A、13、13A、NL、L331D）。
- 每次輪詢只發 1 次 API 呼叫（OData `$filter` 一次取回全部路線）。
- 排程（Asia/Taipei）：
  - 平日 07–09、17–19：每 90 秒
  - 平日 06–07、09–17、19–22：每 10 分鐘
  - 週末 07–22：每 20 分鐘
  - 其餘時段不呼叫
- 預定結束：`--until 2026-11-14T23:59`（約 3 週），到時自動停止。若綠線北段通車日早於此日，請在通車前一天手動停止（通車日【待查證】）。
- 額度保護：當月估計點數 ≥ 2.7 點時自動暫停到下個月（估計方式見下節）。

**檢查是否在執行**
```bash
ps -o pid,etime,cmd -p $(cat logs/collector.pid)    # 有輸出表示執行中
tail -n 5 logs/collector.log                        # 每次輪詢一行 "poll ok rows=..."
zcat data/a1/a1_$(date +%Y%m%d).csv.gz | wc -l       # 今日資料列數（含表頭）
.venv/bin/python -c "import sys;sys.path.insert(0,'scripts');import tdx;print(tdx.month_usage())"   # (當月呼叫數, MB, 估計點數)
```
**停止**：`kill $(cat logs/collector.pid)`（SIGTERM，會寫完當次資料後結束）
**重新啟動**（例如 box 重開機後）：
```bash
setsid nohup .venv/bin/python scripts/06_collect_a1.py --until 2026-11-14T23:59 >> logs/collector.out 2>&1 < /dev/null &
sleep 2; pgrep -f scripts/06_collect_a1.py > logs/collector.pid
```

## TDX 額度估算（假設為預設的「基礎」免費方案；若已訂閱付費方案可提高頻率）
- 方案限制【R30：https://tdx.transportdata.tw/pricing，2026-10-24 查詢】：
  - 存取頻率 5 次/分/金鑰。
  - 每月 3 點；1 點＝1,500 次呼叫，或 150 MB 傳輸量。
- 本專案保守估算：點數＝呼叫數/1,500＋解壓後 MB/150（兩者相加）。
- 收集器呼叫數：
  - 平日每天 232 次（尖峰 160 次＋其他時段 72 次）；週末每天 45 次。
  - 2026-10-24 10:14 至 10-31：約 1,286 次。
  - 11-01 至 11-14：約 2,500 次（約 1.67 點）。
- 每次回應：週六上午約 7 KB（解壓後，14 輛車）。若尖峰約 30 KB，11 月約 75 MB（約 0.5 點），合計約 2.2 點，低於每月 3 點。
- 靜態資料（Shape、StopOfRoute、Schedule）共 6 次呼叫、約 14 MB，約 0.1 點，計在 10 月。
- 頻率：尖峰每 90 秒 1 次，遠低於每分鐘 5 次；所有腳本共用 13 秒最小間隔。
- 若實際回應較大，2.7 點的上限會先讓收集器暫停，不會超額。月中請以上面的 `tdx.month_usage()` 檢查用量。

## 方法與限制（必須寫進報告）
1. **（PDF 對照版）路線線型為近似值**：開放平台的線型服務目前只回傳 1A 一條路線，TDX Shape 又需要金鑰，所以改以官方站址表中相鄰站牌的直線連線近似路線。轉彎較多的路段，長度會低估。
2. **只含可解析的 PDF**：部分站址表是圖片格式的 PDF，box 上沒有 OCR，所以未納入，清單見 parse_report.csv（status≠ok）。站址表左右兩欄視為去程與返程；站序從 1 重新開始時視為新的型態（pattern），型態不等於 TDX 的 SubRoute。
3. **車站點位**：取自 OSM 志工標註的施工中車站點，不是官方出入口；G15b 坑口站為估計點位。
4. **等時圈**：從離車站點最近的路網節點起算路網距離，可達路段兩側各緩衝 50 m（edge-buffer 法）。人口以村里面積比例分配，假設村里內人口均勻分布。
5. **班次頻率**：取自 TDX Schedule。平日以週三代表；尖峰為平日 07–09、17–19，離峰為平日 09–17。桃園班表只有起點發車時刻，所以以起點發車時刻判定時段。
6. **分析三（通車前基準）**：2026-10-24 起收集中，收滿 2–3 週前的摘要只是樣本，不是基準。週六上午 TDX 全市 A1 只有 71 輛車，涵蓋率【待查證】。

## 班距可靠度（分析三，`scripts/11_headway.py`）
不需金鑰，只讀 `data/a1/`。方法與限制寫在腳本開頭說明。
```bash
.venv/bin/python scripts/11_headway.py selftest    # 合成資料驗證（不依賴真實資料）
.venv/bin/python scripts/11_headway.py coverage    # 資料量夠不夠
.venv/bin/python scripts/11_headway.py analyze     # outputs/A3_headway_{summary,detail,coverage}.csv
```
只分析平日尖峰（離峰每 10 分鐘輪詢，內插誤差過大）。`gap_mult=2`、`bunch_mult=0.25` 為暫定門檻。`sufficient=False` 的組合不得引用。
