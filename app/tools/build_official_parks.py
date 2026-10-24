"""經濟部產業園區管理局「產業園區範圍圖」SHP（政府資料開放授權條款第1版，data.gov.tw 資料集 25598）
→ 只保留綠線北段 7 站 3 km 內的範圍，存 derived/A4_industrial_official.gpkg。"""
import datetime, io, urllib.parse, urllib.request, zipfile
from pathlib import Path
import geopandas as gpd, pandas as pd
APP = Path(__file__).resolve().parent.parent
OUT = APP / "derived"; RAW = OUT / "raw"; RAW.mkdir(parents=True, exist_ok=True)
URL = "https://land.bip.gov.tw/supply/content/files/public_files/" + urllib.parse.quote("範圍圖資料集.zip")
z = RAW / "bip_parks.zip"
if not z.exists():
    z.write_bytes(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read())
zipfile.ZipFile(z).extractall(RAW / "bip")
shp = next((RAW / "bip").glob("*.shp"))
g = gpd.read_file(shp)
if g.crs is None:
    g = g.set_crs(3826)
g = g.to_crs(3826)
st = pd.read_csv(APP.parent / "pilot/data/stations_green_north.csv")
s = gpd.GeoSeries(gpd.points_from_xy(st.lon, st.lat), crs=4326).to_crs(3826)
g = g[g.distance(s.union_all()) < 3000].copy()
g["name"] = g["NAME"]
g[["name", "TYPENAME", "STAYE", "MNG", "CITYNAME", "geometry"]].to_file(OUT / "A4_industrial_official.gpkg", driver="GPKG")
(OUT / "A4_industrial_official_retrieved_at.txt").write_text(
    f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} (UTC+8)；{URL}；檔案內日期 2026-04-30；資料集 data.gov.tw/dataset/25598", encoding="utf-8")
print(len(g), list(g.name))
