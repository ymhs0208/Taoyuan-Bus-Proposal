"""分析一：路線重疊排行。
以官方站址表之站序座標連線（站間直線）近似路線線型（因開放平台線型資料服務目前僅回傳 1 條路線，TDX Shape 需金鑰）。
指標（以 TWD97 / EPSG:3826 計算）：
- len_share_500：路線近似線型落在 7 站 500 m 圓形範圍聯集內之長度比例
- len_in_500_km：落在範圍內之長度（km）
- stop_share_500：站牌位於任一站 500 m 內之比例
- stations_touched：路線有站牌落在其 500 m 內的綠線車站數"""
import os, pandas as pd, geopandas as gpd, numpy as np, datetime
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R=500
st=pd.read_csv(f'{BASE}/data/stations_green_north.csv')
stg=gpd.GeoDataFrame(st,geometry=gpd.points_from_xy(st.lon,st.lat),crs=4326).to_crs(3826)
buf=unary_union([g.buffer(R) for g in stg.geometry])
s=pd.read_csv(f'{BASE}/data/route_stops_parsed.csv')
s=s[(s.lat.between(24.5,25.4))&(s.lon.between(120.9,121.6))]
g=gpd.GeoDataFrame(s,geometry=gpd.points_from_xy(s.lon,s.lat),crs=4326).to_crs(3826)
rows=[];qc=[]
def clean(df,rid,pat):
    """QC：(1) 尖刺點：與前後站皆 >3 km、而前後站彼此 <1.5 km → 視為座標誤植並剔除；
    (2) 站間 >8 km 之跳躍 → 於該處切開，保留站數最多之片段（多為 PDF 兩欄合併時誤接的返程尾段）。"""
    df=df.sort_values('order').reset_index(drop=True)
    while True:
        P=list(df.geometry); drop=None
        for i in range(1,len(P)-1):
            if P[i-1].distance(P[i])>3000 and P[i].distance(P[i+1])>3000 and P[i-1].distance(P[i+1])<1500: drop=i;break
        if drop is None: break
        qc.append(dict(route_id=rid,pattern=pat,action='drop_spike',stop=str(df.loc[drop,'stop_name']),seq=int(df.loc[drop,'seq'])))
        df=df.drop(index=drop).reset_index(drop=True)
    P=list(df.geometry); cuts=[i+1 for i in range(len(P)-1) if P[i].distance(P[i+1])>8000]
    if cuts:
        b=[0]+cuts+[len(df)]; parts=[df.iloc[b[k]:b[k+1]] for k in range(len(b)-1)]
        keep=max(parts,key=len)
        qc.append(dict(route_id=rid,pattern=pat,action='split_jump_gt8km',stop=';'.join(str(df.loc[c,'stop_name']) for c in cuts),seq=len(df)-len(keep)))
        df=keep
    return df
for (rid,pat),df0 in g.groupby(['route_id','pattern']):
    df=clean(df0,rid,pat)
    pts=list(df.geometry)
    if len(pts)<2: continue
    line=LineString([(p.x,p.y) for p in pts])
    seglens=[pts[i].distance(pts[i+1]) for i in range(len(pts)-1)]
    L=line.length; Lin=line.intersection(buf).length
    inside=[any(p.distance(sg)<=R for sg in stg.geometry) for p in pts]
    touched=[c for c,sg in zip(stg.code,stg.geometry) if any(p.distance(sg)<=R for p in pts)]
    first=df.iloc[0];last=df.iloc[-1]
    rows.append(dict(route_id=rid,route=first.route,ddesc=first.ddesc,pattern=int(pat),
        from_stop=first.stop_name,to_stop=last.stop_name,n_stops=len(pts),
        approx_len_km=round(L/1000,2),len_in_500_km=round(Lin/1000,2),len_share_500=round(Lin/L,3) if L else 0,
        stops_in_500=int(sum(inside)),stop_share_500=round(sum(inside)/len(pts),3),
        stations_touched=len(touched),stations_list=' '.join(touched),
        max_seg_km=round(max(seglens)/1000,2),qc_cleaned=len(df)!=len(df0)))
res=pd.DataFrame(rows)
res=res[res.stops_in_500>0].sort_values(['len_in_500_km','len_share_500'],ascending=False)
ts=datetime.datetime.now().strftime('%Y-%m-%d %H:%M (UTC+8)')
res.insert(0,'rank',range(1,len(res)+1))
res.to_csv(f'{BASE}/outputs/A1_route_overlap_ranking.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(qc).to_csv(f'{BASE}/outputs/A1_qc_cleaning_log.csv',index=False,encoding='utf-8-sig')
print('patterns total',len(rows),'touching',len(res),'computed at',ts)
print(res.head(20).to_string())
# map
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
for fp in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']:
    font_manager.fontManager.addfont(fp)
plt.rcParams['font.family']='Noto Sans CJK TC'
fig,ax=plt.subplots(figsize=(9,10))
gpd.GeoSeries([buf],crs=3826).plot(ax=ax,color='#cfe8cf',edgecolor='#4a8a4a',alpha=.6)
top=res.head(10)
cmap=plt.get_cmap('tab10')
for i,(_,r) in enumerate(top.iterrows()):
    df=clean(g[(g.route_id==r.route_id)&(g.pattern==r.pattern)],r.route_id,r.pattern)
    ax.plot(df.geometry.x,df.geometry.y,'-',lw=2,color=cmap(i%10),label=f"{int(r['rank'])}. {r.route}（型態{r.pattern}）{r.len_in_500_km} km / {r.len_share_500:.0%}")
stg.plot(ax=ax,color='#0a6b0a',markersize=40,zorder=5)
for _,r in stg.iterrows(): ax.annotate(f"{r.code} {r['name']}",(r.geometry.x,r.geometry.y),xytext=(5,5),textcoords='offset points',fontsize=8)
xs,ys=stg.geometry.x,stg.geometry.y
ax.set_xlim(xs.min()-4000,xs.max()+4000);ax.set_ylim(ys.min()-4000,ys.max()+4000)
ax.set_title('綠線北段 7 站 500 m 範圍內長度最長之前 10 名公車路線型態\n（站間直線近似線型；資料：桃園市政府資料開放平台路線資訊 stopAddrUrl 官方站址表；OSM 車站點位）',fontsize=10)
ax.legend(fontsize=7,loc='lower left');ax.set_xticks([]);ax.set_yticks([])
fig.text(0.01,0.01,f'計算時間 {ts}；G15b 坑口站以機場捷運 A11 點位估計',fontsize=7)
plt.tight_layout();plt.savefig(f'{BASE}/outputs/A1_route_overlap_map.png',dpi=160)
