"""分析一（TDX 版）：以 TDX Shape（實際路線線型）與 StopOfRoute（站序）計算與綠線北段 7 站 500 m 範圍之重疊，並與站址表 PDF 近似版比較。
資料：data/tdx/Shape_Taoyuan.json.gz、StopOfRoute_Taoyuan.json.gz（scripts/09_tdx_static.py 取得）。"""
import os, gzip, json, datetime, pandas as pd, geopandas as gpd
from shapely import wkt
from shapely.ops import unary_union
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); R=500
st=pd.read_csv(f'{BASE}/data/stations_green_north.csv')
stg=gpd.GeoDataFrame(st,geometry=gpd.points_from_xy(st.lon,st.lat),crs=4326).to_crs(3826)
buf=unary_union([g.buffer(R) for g in stg.geometry])
sh=json.load(gzip.open(f'{BASE}/data/tdx/Shape_Taoyuan.json.gz'))
shp=gpd.GeoDataFrame([dict(route=s['RouteName']['Zh_tw'],RouteUID=s['RouteUID'],SubRouteUID=s['SubRouteUID'],sub=s['SubRouteName']['Zh_tw'],dir=s['Direction'],geometry=wkt.loads(s['Geometry'])) for s in sh],crs=4326).to_crs(3826)
sor=pd.read_csv(f'{BASE}/data/tdx/stop_of_route.csv')
sg=gpd.GeoDataFrame(sor,geometry=gpd.points_from_xy(sor.lon,sor.lat),crs=4326).to_crs(3826)
rows=[]
for _,r in shp.iterrows():
    L=r.geometry.length; Lin=r.geometry.intersection(buf).length
    if Lin==0: continue
    s=sg[(sg.SubRouteUID==r.SubRouteUID)&(sg.dir==r.dir)]
    ins=[any(p.distance(x)<=R for x in stg.geometry) for p in s.geometry]
    touched=[c for c,x in zip(stg.code,stg.geometry) if r.geometry.distance(x)<=R]
    rows.append(dict(route=r.route,sub=r['sub'],SubRouteUID=r.SubRouteUID,dir=int(r.dir),len_km=round(L/1000,2),len_in_500_km=round(Lin/1000,2),
        len_share_500=round(Lin/L,3),n_stops=len(s),stops_in_500=int(sum(ins)),stop_share_500=round(sum(ins)/len(s),3) if len(s) else None,
        stations_touched=len(touched),stations_list=' '.join(touched)))
res=pd.DataFrame(rows).sort_values(['len_in_500_km','len_share_500'],ascending=False)
res.insert(0,'rank',range(1,len(res)+1))
# 班次加權：平日（週三）班次數 × 500 m 範圍內長度 = 每日在範圍內行駛的車公里（需先有 Schedule 檔）
fs=f'{BASE}/data/tdx/Schedule_Taoyuan_800m_routes.json.gz'
if os.path.exists(fs):
    sch=json.load(gzip.open(fs)); n={}
    for x in sch:
        n[(x['SubRouteUID'],x['Direction'])]=sum(1 for t in x.get('Timetables') or [] if (t.get('ServiceDay') or {}).get('Wednesday'))
    res['weekday_trips']=[n.get((a,b)) for a,b in zip(res.SubRouteUID,res.dir)]
    res['veh_km_in_500_per_weekday']=(res.len_in_500_km*res.weekday_trips).round(1)
ts=datetime.datetime.now().strftime('%Y-%m-%d %H:%M (UTC+8)')
retr=open(f'{BASE}/data/tdx/Shape_retrieved_at.txt').read().strip()
res.to_csv(f'{BASE}/outputs/A1_tdx_route_overlap_ranking.csv',index=False,encoding='utf-8-sig')
print('subroute-directions with overlap',len(res)); print(res.head(25).to_string())
# 比較：PDF 版（型態 0/1 視為方向 0/1；同一路線名多型態時取 len_in_500 最大者）
pdf=pd.read_csv(f'{BASE}/outputs/A1_route_overlap_ranking.csv')
pdf=pdf.rename(columns={'pattern':'dir'}); pdf['route']=pdf.route.astype(str)
pb=pdf.sort_values('len_in_500_km',ascending=False).drop_duplicates(['route','dir'])[['route','dir','rank','len_in_500_km','len_share_500','stops_in_500','stations_list']]
tb=res.sort_values('len_in_500_km',ascending=False).drop_duplicates(['route','dir'])[['route','dir','rank','len_in_500_km','len_share_500','stops_in_500','stations_list']]
cmp_=tb.merge(pb,on=['route','dir'],how='outer',suffixes=('_tdx','_pdf'))
cmp_['diff_len_km']=(cmp_.len_in_500_km_tdx-cmp_.len_in_500_km_pdf).round(2)
cmp_['note']=cmp_.apply(lambda x:'僅 TDX（PDF 未解析或未觸及）' if pd.isna(x.rank_pdf) else ('僅 PDF 近似（TDX 線型未進入 500 m）' if pd.isna(x.rank_tdx) else ''),axis=1)
cmp_=cmp_.sort_values('rank_tdx')
cmp_.to_csv(f'{BASE}/outputs/A1_compare_tdx_vs_pdf.csv',index=False,encoding='utf-8-sig')
print(cmp_.head(30).to_string())
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family']='Noto Sans CJK TC'
fig,ax=plt.subplots(figsize=(9,10))
gpd.GeoSeries([buf],crs=3826).plot(ax=ax,color='#cfe8cf',edgecolor='#4a8a4a',alpha=.6)
top=res.drop_duplicates('SubRouteUID').head(10); cmap=plt.get_cmap('tab10')
for i,(_,r) in enumerate(top.iterrows()):
    g=shp[(shp.SubRouteUID==r.SubRouteUID)&(shp.dir==r.dir)]
    g.plot(ax=ax,color=cmap(i),lw=2.2 if i<3 else 1.4,label=f"{int(r['rank'])}. {r['sub']}（方向{r.dir}）{r.len_in_500_km} km / {r.len_share_500:.0%}")
stg.plot(ax=ax,color='#0a6b0a',markersize=40,zorder=5)
for _,r in stg.iterrows(): ax.annotate(f"{r.code} {r['name']}",(r.geometry.x,r.geometry.y),xytext=(5,5),textcoords='offset points',fontsize=8)
xs,ys=stg.geometry.x,stg.geometry.y; ax.set_xlim(xs.min()-4000,xs.max()+4000); ax.set_ylim(ys.min()-4000,ys.max()+3000)
ax.legend(loc='lower left',fontsize=7.5); ax.set_axis_off()
ax.set_title('分析一（TDX 線型）：綠線北段 7 站 500 m 範圍內重疊長度前 10 名子路線')
fig.text(.02,.01,f'資料：交通部 TDX 運輸資料流通服務 Bus/Shape、StopOfRoute（City/Taoyuan，取得 {retr}）；OSM 車站點位（© OpenStreetMap contributors）。\n計算時間 {ts}；G15b 坑口站點位為估計。每個子路線僅繪出排名最高的方向。',fontsize=6.5)
plt.savefig(f'{BASE}/outputs/A1_tdx_route_overlap_map.png',dpi=200,bbox_inches='tight'); print('saved',ts)
