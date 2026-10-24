"""移工通勤代理指標：抓取 OSM landuse=industrial（Overpass），存到 app/derived/。
不寫入 pilot/。用法：python tools/build_industrial.py
輸出：derived/A4_industrial_osm.gpkg（EPSG:3826）、derived/A4_industrial_retrieved_at.txt"""
import datetime, json, sys, time, urllib.parse, urllib.request
from pathlib import Path
import geopandas as gpd, pandas as pd
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union, polygonize, linemerge

APP = Path(__file__).resolve().parent.parent
OUT = APP / "derived"; OUT.mkdir(exist_ok=True)
PILOT = APP.parent / "pilot"
st = pd.read_csv(PILOT / "data/stations_green_north.csv")
pad = 0.03  # 約 3 km
s, w, n, e = st.lat.min() - pad, st.lon.min() - pad, st.lat.max() + pad, st.lon.max() + pad
q = f"""[out:json][timeout:120];
(way["landuse"="industrial"]({s},{w},{n},{e});
 relation["landuse"="industrial"]({s},{w},{n},{e}););
out tags geom;"""
EPS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
data = None
for k in range(6):
    url = EPS[k % len(EPS)]
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": "student-research-pilot"})
        data = json.load(urllib.request.urlopen(req, timeout=180)); break
    except Exception as ex:
        print("retry", url, ex); time.sleep(10 * (k + 1))
if data is None:
    sys.exit("Overpass 無法連線")
rows = []
for el in data["elements"]:
    tags = el.get("tags", {})
    geom = None
    if el["type"] == "way" and el.get("geometry"):
        c = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(c) >= 4 and c[0] == c[-1]:
            geom = Polygon(c)
    elif el["type"] == "relation":
        outers = [m for m in el.get("members", []) if m.get("role") in ("outer", "") and m.get("geometry")]
        inners = [m for m in el.get("members", []) if m.get("role") == "inner" and m.get("geometry")]
        from shapely.geometry import LineString
        ol = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in outers]
        il = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in inners]
        op = list(polygonize(linemerge(ol))) if ol else []
        ip = list(polygonize(linemerge(il))) if il else []
        if op:
            geom = unary_union(op)
            if ip:
                geom = geom.difference(unary_union(ip))
    if geom is None or geom.is_empty:
        continue
    if not geom.is_valid:
        geom = geom.buffer(0)
    rows.append(dict(osm_id=f"{el['type']}/{el['id']}", name=tags.get("name", ""), industrial=tags.get("industrial", ""), geometry=geom))
g = gpd.GeoDataFrame(rows, crs=4326).to_crs(3826)
g["area_ha"] = (g.geometry.area / 1e4).round(2)
g.to_file(OUT / "A4_industrial_osm.gpkg", driver="GPKG")
(OUT / "A4_industrial_retrieved_at.txt").write_text(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S (UTC+8)") + "；OSM Overpass landuse=industrial；bbox " + f"{s:.4f},{w:.4f},{n:.4f},{e:.4f}", encoding="utf-8")
print(len(g), "polygons", round(g.area_ha.sum(), 1), "ha")
