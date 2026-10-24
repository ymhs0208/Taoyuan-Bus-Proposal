# 綠線接駁決策平台（展示版）

「捷運綠線通車後的公車路網重整」（115 年度 為桃園做研究・研究實作組）提案的互動展示原型。
Streamlit 網頁介面＋Folium 地圖，所有數字都由 `pilot/` 資料夾內的資料即時計算。

> ⚠️ 展示版：試行分析，數據待複核。情境皆為研究示意，不代表桃園市政府或營運業者的方案；未進行任何問卷、訪談或實地調查。

## 頁面

「G12／G14・先做哪一站」比較相同每日班次或相同服務工時上限，區分首次取得任一綠線站直達服務的人口與增加本站選擇的人口。
到站時間模型固定同一目的站及同一人口群，拆解起點步行、公車候車／車內、轉乘步行與捷運候車；時間假設可調，並非實際旅次效益。
預設資料下以首次服務人口／工時排序，G12 為優先現地驗證主方案。A＋B 仍保留為原始工具示範，不作為自動推薦。
研究說明與假設敏感度見 `docs/scenario/G12_G14_主方案與乘客效益.md`；可用 `python app/tools/build_passenger_report.py` 由同一套模型更新說明及 `app/derived/G12_G14_*`。

側欄依「① 看問題 → ② 比方案 → ③ 看結果」排列；五個改良方案、資料切換及本頁參數可展開查看。
情境模擬預設載入 A＋B，先呈現可移轉約當駕駛班次、G14 長者直達服務增減與服務減少車站，
再提供方案切換；自訂操作、地圖與完整比較均可展開。路線重疊圖以深綠粗線標出選中路線，其餘路線及底圖淡化。

| 頁面 | 內容 |
|---|---|
| 首頁 | 一句話問題、三個重點數字（連到情境模擬或路線重疊地圖）、怎麼看這個網站 |
| 路線重疊地圖 | 7 站 300／500／800 m 範圍、依「範圍內長度占比」上色的公車路線、重疊排行、點選路線看沿線各站與車站的距離；有 TDX 班表時另顯示平日班次與範圍內車公里 |
| 接駁缺口 | 各站 300／500／800 m 步行等時圈內的站牌、路線、65+ 人口估計、尖離峰班次（TDX 班表；沒有就顯示「待實測」）；最弱車站標紅；「產業用地（移工通勤代理指標）」：各站步行範圍內產業用地面積、產業用地 300 m 內有無可一車直達最近車站的站牌（探索性，代理≠移工人口） |
| 情境模擬 | 刪除路線與綠線平行的區段、截短、停駛；新增接駁線（挑選既有站牌、地圖點選自訂點，或用演算法產生預設線）；S0 與情境並排比較站牌數、可一車直達車站的 65+ 人口、路線長度、平日車公里、車輛小時、約當駕駛班次，以及「可移轉駕駛人力」（裁切節省班次 − 新增接駁所需班次） |
| 通車前後比較 | 讀取 TDX A1 即時動態收集檔（`pilot/data/a1/`），顯示資料期間、在線車數、計時點班距與站間行駛時間；通車後資料出現前只顯示說明 |
| 關於資料 | 資料來源、取得時間、限制、檔案清單 |

## 在自己的電腦安裝與執行（Windows／Mac）
建議 **Python 3.12**（requirements.txt 已固定 pandas 2.2.3、pyarrow 17.0.0、pyogrio 0.9.0、pyproj 3.6.1、geopandas 1.0.1；pyarrow 17 沒有 Python 3.13 安裝檔）。Python 3.10–3.12 皆可。

資料夾結構（`app` 和 `pilot` 必須放在同一層）：
```
綠線接駁決策平台_展示版/
├─ app/      ← 本程式
└─ pilot/    ← 試行分析資料（data/、outputs/）
```

**Mac／Linux**
```bash
cd 綠線接駁決策平台_展示版/app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

**Windows（PowerShell）**
```powershell
cd 綠線接駁決策平台_展示版\app
py -m venv .venv
.venv\Scripts\Activate.ps1      # 若被擋：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
streamlit run app.py
```
瀏覽器會自動開啟 http://localhost:8501 。現場展示不需要網路也能計算，但地圖底圖（OpenStreetMap 圖磚）需要網路；建議展示前先開過一次。

`pilot` 放在別的位置時，設定環境變數 `TAOYUAN_PILOT_DIR` 指向它。

## 資料更新
- 程式只**讀取** `pilot/`，不會寫入。重新執行 pilot 的分析腳本、或 A1 收集器寫入新檔後，按左側「🔄 重新讀取最新資料」即可。
- 有 `pilot/data/tdx/stop_of_route.csv` 時預設用 TDX（實際線型）；可在左側切回 PDF 站址表版，與提案初稿的表 A1／A2 對照。
- 欄位缺漏或檔案不存在時，頁面會顯示「待實測」或說明，不會補數字。

## 需要的 pilot 檔案
| 檔案 | 用途 |
|---|---|
| data/stations_green_north.csv | 車站點位（必要） |
| data/tdx/stop_of_route.csv、Shape_Taoyuan.json.gz | TDX 站序與線型（主要） |
| data/route_stops_parsed.csv、parse_report.csv | PDF 版站序（備援／對照） |
| data/tdx/Schedule_*.json.gz | 平日班次、車公里 |
| outputs/A2_isochrones.gpkg | 步行等時圈（接駁缺口、情境模擬必要） |
| data/villages_pop65.gpkg | 村里 65+ 人口（必要） |
| outputs/A2_tdx_station_access_frequency.csv | 尖離峰班次 |
| outputs/A1_*.csv、A3_sample_status.txt | 原始輸出對照 |
| data/a1/a1_*.csv.gz | 即時動態（通車前後比較；樣本足夠時也用來估路線速率） |

`app/derived/`（本程式自己產生，不寫入 pilot）：
| 檔案 | 來源／產生方式 |
|---|---|
| A4_industrial_osm.gpkg | OSM landuse=industrial（`python tools/build_industrial.py`，Overpass，需網路） |
| A4_industrial_official.gpkg | 經濟部產業園區管理局「產業園區範圍圖」（`python tools/build_official_parks.py`；data.gov.tw 25598，政府資料開放授權條款第1版） |
| A4_industrial_by_station.csv、A4_industrial_reach.csv、A4_industrial_summary.csv | `python tools/build_proxy.py`（頁面也會即時計算） |
| *_retrieved_at.txt | 取得時間（UTC+8）與來源 |

## 方法重點（簡報時請說明）
- 站牌位置以 5 m 網格去重；等時圈為 OSM 步行路網距離（pilot/scripts/05_access.py）。
- 「可一車直達本站」：路線有任一站牌位於該站 500 m 步行等時圈內（可調）。
- 65+ 人口：村里人口按面積比例均分到 25 m 格點；到站牌距離為直線 300 m（可調）。
- 接駁線為點間直線，長度是下限；「刪除平行區段」未計折返與調度空車距離。
- 預設接駁線：在車站 300–1,500 m 內的既有站牌中，以貪婪法挑選能增加最多「可一車直達本站的 65+ 人口」的站牌（最多 6 個），再以最近鄰＋2-opt 排序。只是示意起點。
- 車站點位取自 OSM（G15b 為估計）；班次為 TDX 時刻表（以起點發車時刻判定尖離峰），不是實際營運。
- 駕駛人力：平日車公里＝TDX 平日（週三）班次 × 單程長度；車輛小時＝車公里 ÷ 營運速率；約當駕駛班次＝車輛小時 ÷ 每班時數。TDX 桃園班表只有起點發車時刻、沒有站間行駛時間，因此速率預設 18 km/h【假設，可調整】，A1 樣本足夠（每路線方向 ≥30 組站間配對）時可改用實測；每班 8 小時【假設，可調整】；接駁線班次預設為 GR 現況平日單向班次（30）【假設，可調整】。只含行駛時間，未含休息、調度、備勤、輪休。
- 產業用地只是移工通勤的代理指標，不等於移工人口；宿舍位置與班別時間未知。

## 測試與截圖（開發用）
```bash
python tests/apptest_all.py            # Streamlit AppTest：每頁載入無例外
python tests/apptest_interactions.py   # 情境操作
python tests/apptest_driver.py         # A＋B 預設的駕駛人力數字
python tests/apptest_priority.py       # 同班次、同工時上限與無時間改善的情境
python -m unittest discover -s tests -p test_passenger.py  # 人口互斥分類、淨變化、時間分解與工時邊界
python tests/browser_presentation.py   # 啟動 8601 後，檢查結果順序、地圖樣式、清除與手機版，更新 optimized_* 截圖
pip install -r requirements-dev.txt && playwright install chromium
streamlit run app.py --server.port 8601 &   # 另開終端
python tests/screenshots.py            # 1280 寬截圖 → screens/
python tools/make_zip.py               # 打包 app＋pilot 資料快照
```

## AI 使用說明
本平台程式由 AI 協助撰寫；依簡章須於報名表說明 AI 工具名稱與使用方式，並由團隊自行複核。
