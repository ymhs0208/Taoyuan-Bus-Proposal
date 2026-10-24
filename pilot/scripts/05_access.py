"""分析二：車站接駁可及性（步行等時圈 300/500/800 m）。
- 步行路網：OSM（osmnx network_type='walk'），每站 1,100 m 範圍，data/walk/{code}.graphml
- 等時圈：自車站最近路網節點起算之路網距離 ≤ d 的路段，兩側各緩衝 50 m 後聯集（edge-buffer 法）
  註：車站點位為 OSM 車站中心點，非出入口，可能低估或高估實際步行距離。
- 站牌：官方站址表解析結果（data/route_stops_parsed.csv），以座標去重（5 m 內視為同一站牌位置）
- 65+ 人口：內政部戶政司村里人口（115年9月）× OSM 村里界，以面積比例分配（假設村里內人口均勻分布）
- 班次頻率（尖峰/離峰）：需 TDX Schedule（金鑰），本腳本不計算 → 【待實測】"""
import os, datetime, pandas as pd, geopandas as gpd, numpy as np, networkx as nx, osmnx as ox
from shapely.ops import unary_union
from shapely.geometry import LineString
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D=[300,500,800]; EB=50
st=pd.read_csv(f'{BASE}/data/stations_green_north.csv')
stg=gpd.GeoDataFrame(st,geometry=gpd.points_from_xy(st.lon,st.lat),crs=4326).to_crs(3826)
s=pd.read_csv(f'{BASE}/data/route_stops_parsed.csv')
s=s[(s.lat.between(24.5,25.4))&(s.lon.between(120.9,121.6))]
sg=gpd.GeoDataFrame(s,geometry=gpd.points_from_xy(s.lon,s.lat),crs=4326).to_crs(3826)
sg['kx']=(sg.geometry.x/5).round().astype(int); sg['ky']=(sg.geometry.y/5).round().astype(int)
vil=gpd.read_file(f'{BASE}/data/villages_pop65.gpkg').to_crs(3826)
vil['area']=vil.geometry.area
rows=[];polys=[]
for _,r in stg.iterrows():
    fn=f'{BASE}/data/walk/{r.code}.graphml'
    if not os.path.exists(fn):
        rows.append(dict(code=r.code,name=r['name'],status='步行路網未取得'));continue
    G=ox.load_graphml(fn); Gp=ox.project_graph(G,to_crs='EPSG:3826'); Gu=Gp.to_undirected()
    n0=ox.distance.nearest_nodes(Gp,r.geometry.x,r.geometry.y)
    snap=((Gp.nodes[n0]['x']-r.geometry.x)**2+(Gp.nodes[n0]['y']-r.geometry.y)**2)**.5
    dist=nx.single_source_dijkstra_path_length(Gu,n0,cutoff=max(D),weight='length')
    for d in D:
        segs=[]
        for u,v,k,data in Gu.edges(keys=True,data=True):
            du,dv=dist.get(u),dist.get(v)
            if du is None and dv is None: continue
            geom=data.get('geometry') or LineString([(Gu.nodes[u]['x'],Gu.nodes[u]['y']),(Gu.nodes[v]['x'],Gu.nodes[v]['y'])])
            L=data['length']
            if du is not None and dv is not None and du<=d and dv<=d: segs.append(geom)
            else:  # 部分路段：自可達端點延伸剩餘距離
                for end,de in ((u,du),(v,dv)):
                    if de is not None and de<d:
                        rem=min(d-de,L)
                        g2=geom if (abs(geom.coords[0][0]-Gu.nodes[end]['x'])<1e-6 and abs(geom.coords[0][1]-Gu.nodes[end]['y'])<1e-6) else LineString(list(geom.coords)[::-1])
                        from shapely.ops import substring
                        segs.append(substring(g2,0,rem*g2.length/L if L else 0))
        poly=unary_union([x.buffer(EB) for x in segs]) if segs else r.geometry.buffer(1)
        inside=sg[sg.within(poly)]
        uniq=inside.drop_duplicates(['kx','ky'])
        routes=sorted(set(inside.route.astype(str)))
        inter=gpd.overlay(vil,gpd.GeoDataFrame(geometry=[poly],crs=3826),how='intersection')
        inter['w']=inter.geometry.area/inter['area']
        pop=(inter['pop']*inter.w).sum(); p65=(inter['pop65']*inter.w).sum()
        cover=inter.geometry.area.sum()/poly.area
        circle=r.geometry.buffer(d)
        rows.append(dict(code=r.code,name=r['name'],dist_m=d,status='ok',snap_m=round(snap),
            iso_area_ha=round(poly.area/1e4,1),circle_area_ha=round(circle.area/1e4,1),
            iso_to_circle=round(poly.area/circle.area,2),
            stop_positions=len(uniq),stop_rows=len(inside),n_routes=len(routes),routes=' '.join(routes[:60]),
            pop_est=round(pop),pop65_est=round(p65),village_cover=round(cover,3),
            freq_peak='【待實測】',freq_offpeak='【待實測】'))
        polys.append(dict(code=r.code,dist_m=d,geometry=poly))
res=pd.DataFrame(rows)
ts=datetime.datetime.now().strftime('%Y-%m-%d %H:%M (UTC+8)')
res['computed_at']=ts
res.to_csv(f'{BASE}/outputs/A2_station_access.csv',index=False,encoding='utf-8-sig')
pg=gpd.GeoDataFrame(polys,crs=3826); pg.to_file(f'{BASE}/outputs/A2_isochrones.gpkg',driver='GPKG')
print(res.drop(columns=['routes']).to_string())
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams['font.family']='Noto Sans CJK TC'
fig,ax=plt.subplots(figsize=(9,11))
vil.plot(ax=ax,column=vil.pop65/vil.area*1e6,cmap='Oranges',alpha=.55,edgecolor='#bbb',lw=.3,legend=True,
         legend_kwds=dict(label='65 歲以上人口密度（人/km²，115年9月）',shrink=.5))
cols={800:'#9ecae1',500:'#4292c6',300:'#08519c'}
for d in [800,500,300]:
    sub=pg[pg.dist_m==d]
    if len(sub): sub.plot(ax=ax,facecolor=cols[d],alpha=.45,edgecolor=cols[d],lw=.6)
sg.drop_duplicates(['kx','ky']).plot(ax=ax,color='k',markersize=3,zorder=4)
stg.plot(ax=ax,color='#0a6b0a',markersize=50,zorder=5,marker='s')
for _,r in stg.iterrows(): ax.annotate(f"{r.code} {r['name']}",(r.geometry.x,r.geometry.y),xytext=(6,4),textcoords='offset points',fontsize=8,zorder=6)
xs,ys=stg.geometry.x,stg.geometry.y
ax.set_xlim(xs.min()-1500,xs.max()+1500); ax.set_ylim(ys.min()-1500,ys.max()+1500)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=cols[d],alpha=.6,label=f'步行 {d} m 路網距離') for d in D],loc='upper left',fontsize=8)
ax.set_title('分析二：綠線北段 7 站步行等時圈與公車站牌（試行）'); ax.set_axis_off()
fig.text(.02,.01,f'資料：OSM 步行路網與車站點位（© OpenStreetMap contributors）；桃園市公車站址表（ebus.tycg.gov.tw，經市府開放平台路線資料集連結）；\n內政部戶政司村里人口 115年9月；OSM 村里界。計算時間 {ts}。G15b 坑口站點位為估計。',fontsize=6.5)
plt.savefig(f'{BASE}/outputs/A2_station_access_map.png',dpi=200,bbox_inches='tight')
print('saved',ts)
