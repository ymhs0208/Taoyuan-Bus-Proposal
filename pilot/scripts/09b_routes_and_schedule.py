"""由 TDX StopOfRoute 產生 data/tdx/stop_of_route.csv 與 config/collector_routes.txt（7 站 800 m 步行等時圈內有站牌的路線＋GR2），
並以 $filter 分批取得這些路線的 TDX Schedule（data/tdx/Schedule_Taoyuan_800m_routes.json.gz）。
參數 --no-schedule 只產生清單、不呼叫 API。"""
import os,sys,gzip,json,datetime,urllib.parse,pandas as pd,geopandas as gpd
sys.path.insert(0,os.path.dirname(__file__)); import tdx
B=tdx.BASE
sor=json.load(gzip.open(f'{B}/data/tdx/StopOfRoute_Taoyuan.json.gz'))
df=pd.DataFrame([dict(RouteUID=r['RouteUID'],route=r['RouteName']['Zh_tw'],SubRouteUID=r['SubRouteUID'],sub=r['SubRouteName']['Zh_tw'],dir=r['Direction'],seq=s['StopSequence'],StopUID=s['StopUID'],name=s['StopName']['Zh_tw'],lat=s['StopPosition']['PositionLat'],lon=s['StopPosition']['PositionLon']) for r in sor for s in r['Stops']])
df.to_csv(f'{B}/data/tdx/stop_of_route.csv',index=False,encoding='utf-8-sig')
g=gpd.GeoDataFrame(df,geometry=gpd.points_from_xy(df.lon,df.lat),crs=4326).to_crs(3826)
iso=gpd.read_file(f'{B}/outputs/A2_isochrones.gpkg'); i8=iso[iso.dist_m==800]
routes=sorted(gpd.sjoin(g,i8[['code','geometry']],predicate='within').route.unique())
routes=['GR','GR2']+[r for r in routes if r not in ('GR','GR2')]
os.makedirs(f'{B}/config',exist_ok=True); open(f'{B}/config/collector_routes.txt','w').write('\n'.join(routes)+'\n')
print(len(routes),'routes')
if '--no-schedule' in sys.argv: sys.exit(0)
allj=[]
for i in range(0,len(routes),30):
    b=routes[i:i+30]
    allj+=tdx.get('https://tdx.transportdata.tw/api/basic/v2/Bus/Schedule/City/Taoyuan?'+urllib.parse.urlencode({'$filter':' or '.join(f"RouteName/Zh_tw eq '{r}'" for r in b),'$format':'JSON'}))
with gzip.open(f'{B}/data/tdx/Schedule_Taoyuan_800m_routes.json.gz','wt') as f: json.dump(allj,f,ensure_ascii=False)
open(f'{B}/data/tdx/Schedule_retrieved_at.txt','w').write(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S (UTC+8)'))
