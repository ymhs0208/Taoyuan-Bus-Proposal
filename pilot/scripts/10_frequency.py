"""分析二補充（TDX 版）：各站步行等時圈內的站牌（TDX StopOfRoute）與班次（TDX Schedule）。
定義：
- 平日：以 ServiceDay.Wednesday=1 之班次代表一般平日。
- 尖峰：平日 07:00–09:00 與 17:00–19:00（共 4 小時）；離峰：平日 09:00–17:00（8 小時）。
- 班次時間：TDX 桃園 Schedule 的 Timetables 只提供起點站發車時刻，故以「起點發車時刻」判定時段（未加計起點至該車站的行駛時間；長路線可能偏移數十分鐘）。
- 一個子路線方向（SubRouteUID+Direction）只要有任一站牌位於等時圈內即計入；同一班次只計一次。
- 每小時班次 = 時段內班次數 / 時段小時數。"""
import os, gzip, json, datetime, pandas as pd, geopandas as gpd
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sor=pd.read_csv(f'{BASE}/data/tdx/stop_of_route.csv')
sg=gpd.GeoDataFrame(sor,geometry=gpd.points_from_xy(sor.lon,sor.lat),crs=4326).to_crs(3826)
sg['kx']=(sg.geometry.x/5).round().astype(int); sg['ky']=(sg.geometry.y/5).round().astype(int)
iso=gpd.read_file(f'{BASE}/outputs/A2_isochrones.gpkg')
sch=json.load(gzip.open(f'{BASE}/data/tdx/Schedule_Taoyuan_800m_routes.json.gz'))
def mins(t): h,m=t.split(':')[:2]; return int(h)*60+int(m)
trips=[]
for s in sch:
    for t in s.get('Timetables') or []:
        if not (t.get('ServiceDay') or {}).get('Wednesday'): continue
        st=t.get('StopTimes') or []
        if not st: continue
        trips.append(dict(SubRouteUID=s['SubRouteUID'],dir=s['Direction'],route=s['RouteName']['Zh_tw'],trip=t.get('TripID'),m=mins(st[0].get('DepartureTime') or st[0].get('ArrivalTime'))))
T=pd.DataFrame(trips).drop_duplicates(['SubRouteUID','dir','trip','m'])
T['peak']=T.m.between(7*60,9*60-1)|T.m.between(17*60,19*60-1); T['off']=T.m.between(9*60,17*60-1)
a2=pd.read_csv(f'{BASE}/outputs/A2_station_access.csv')
sched_keys=set(zip(T.SubRouteUID,T.dir))
rows=[]
for _,p in iso.iterrows():
    ins=sg[sg.within(p.geometry)]
    keys=set(zip(ins.SubRouteUID,ins.dir)); tt=T[[k in keys for k in zip(T.SubRouteUID,T.dir)]]
    nosch=sorted({sr for sr,d in keys if (sr,d) not in sched_keys})
    base=a2[(a2.code==p.code)&(a2.dist_m==p.dist_m)].iloc[0]
    rows.append(dict(code=p.code,name=base['name'],dist_m=p.dist_m,stop_positions_tdx=len(ins.drop_duplicates(['kx','ky'])),
        n_routes_tdx=ins.route.nunique(),routes_tdx=' '.join(sorted(ins.route.astype(str).unique())),
        weekday_trips=len(tt),peak_trips_per_h=round(tt.peak.sum()/4,1),offpeak_trips_per_h=round(tt.off.sum()/8,1),
        subroutes_without_schedule=' '.join(nosch),pop65_est=base.pop65_est,stop_positions_pdf=base.stop_positions))
R=pd.DataFrame(rows)
ts=datetime.datetime.now().strftime('%Y-%m-%d %H:%M (UTC+8)'); R['computed_at']=ts
R.to_csv(f'{BASE}/outputs/A2_tdx_station_access_frequency.csv',index=False,encoding='utf-8-sig')
print('weekday trips total (sample routes)',len(T)); print(R.drop(columns=['routes_tdx']).to_string())
# map
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family']='Noto Sans CJK TC'
vil=gpd.read_file(f'{BASE}/data/villages_pop65.gpkg').to_crs(3826)
st=pd.read_csv(f'{BASE}/data/stations_green_north.csv'); stg=gpd.GeoDataFrame(st,geometry=gpd.points_from_xy(st.lon,st.lat),crs=4326).to_crs(3826)
fig,ax=plt.subplots(figsize=(9,11))
vil.plot(ax=ax,column=vil.pop65/vil.geometry.area*1e6,cmap='Oranges',alpha=.55,edgecolor='#bbb',lw=.3,legend=True,legend_kwds=dict(label='65 歲以上人口密度（人/km²，115年9月）',shrink=.5))
cols={800:'#9ecae1',500:'#4292c6',300:'#08519c'}
for d in [800,500,300]: iso[iso.dist_m==d].plot(ax=ax,facecolor=cols[d],alpha=.45,edgecolor=cols[d],lw=.6)
sg.drop_duplicates(['kx','ky']).plot(ax=ax,color='k',markersize=3,zorder=4)
stg.plot(ax=ax,color='#0a6b0a',markersize=50,zorder=5,marker='s')
for _,r in stg.iterrows():
    x=R[(R.code==r.code)&(R.dist_m==500)].iloc[0]
    ax.annotate(f"{r.code} {r['name']}\n500 m：尖峰 {x.peak_trips_per_h} 班/時、離峰 {x.offpeak_trips_per_h} 班/時",(r.geometry.x,r.geometry.y),xytext=(7,3),textcoords='offset points',fontsize=7.5,zorder=6,bbox=dict(boxstyle='round,pad=0.2',fc='white',alpha=.75,lw=0))
xs,ys=stg.geometry.x,stg.geometry.y; ax.set_xlim(xs.min()-1500,xs.max()+3000); ax.set_ylim(ys.min()-1500,ys.max()+1500)
ax.legend(handles=[Patch(color=cols[d],alpha=.6,label=f'步行 {d} m 路網距離') for d in (300,500,800)],loc='upper left',fontsize=8)
ax.set_title('分析二（TDX 站牌與班表）：7 站步行等時圈、站牌與平日班次（試行）'); ax.set_axis_off()
retr=open(f'{BASE}/data/tdx/Schedule_retrieved_at.txt').read().strip()
fig.text(.02,.01,f'資料：交通部 TDX Bus/StopOfRoute、Schedule（City/Taoyuan，取得 {retr}）；OSM 步行路網與車站點位（© OpenStreetMap contributors）；內政部戶政司村里人口 115年9月；OSM 村里界。\n尖峰＝平日 07–09、17–19；離峰＝平日 09–17；以起點發車時刻判定。計算時間 {ts}。G15b 點位為估計。',fontsize=6.3)
plt.savefig(f'{BASE}/outputs/A2_tdx_station_access_map.png',dpi=200,bbox_inches='tight'); print('saved')
