"""由 OSM admin_level=9 村里邊界（含 nat_ref=戶政區域代碼）組成多邊形，並與內政部戶政司 ODRP014（115年9月）村里單一年齡人口合併，計算 65 歲以上人口。"""
import os, json, pandas as pd, geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d=json.load(open(f'{BASE}/data/villages_osm.json'))
rows=[]
for e in d['elements']:
    lines=[LineString([(p['lon'],p['lat']) for p in m['geometry']]) for m in e.get('members',[]) if m.get('type')=='way' and m.get('role') in ('outer','') and m.get('geometry')]
    polys=list(polygonize(unary_union(lines)))
    if not polys: continue
    t=e['tags']; rows.append(dict(osm_rel=e['id'],name=t.get('name'),town=t.get('is_in:town'),nat_ref=t.get('nat_ref'),geometry=unary_union(polys)))
v=gpd.GeoDataFrame(rows,crs=4326)
pop=pd.read_csv(f'{BASE}/data/taoyuan_village_pop65_11509.csv',dtype={'district_code':str})
v=v.merge(pop,left_on='nat_ref',right_on='district_code',how='left')
print('villages',len(v),'matched',v.pop65.notna().sum())
v.to_file(f'{BASE}/data/villages_pop65.gpkg',driver='GPKG')
