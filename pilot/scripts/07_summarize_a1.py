#!/usr/bin/env python3
"""彙整 A1 收集資料：以綠線車站附近的『虛擬計時點』計算
- 站間（如 G11→G15）實際行駛時間（同一車牌、同方向、依序通過兩計時點的時間差）
- 各計時點之車次通過時刻 → 班距（headway）平均、標準差、變異係數（CV）
注意：取樣時間短時結果僅供格式示範，不能作為結論。"""
import os, glob, sys, pandas as pd, numpy as np, geopandas as gpd
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files=sorted(glob.glob(f'{BASE}/data/a1/a1_*.csv.gz'))
if not files: print('尚無 A1 資料（data/a1/ 為空）。'); sys.exit(0)
df=pd.concat([pd.read_csv(f) for f in files]).dropna(subset=['lat','lon'])
df['t']=pd.to_datetime(df['GPSTime'],errors='coerce',utc=True).dt.tz_convert('Asia/Taipei')
os.makedirs(f'{BASE}/outputs',exist_ok=True)
polls=df.poll_time.nunique() if 'poll_time' in df else None
samp=df.groupby('RouteName').agg(polls_with_bus=('poll_time','nunique'),buses_seen=('PlateNumb','nunique'),rows=('PlateNumb','size')).reset_index().sort_values('rows',ascending=False)
with open(f'{BASE}/outputs/A3_sample_status.txt','w',encoding='utf-8') as f:
    f.write('【短期樣本，非基準】A1 收集狀態\n')
    f.write(f'輪詢時間範圍（Asia/Taipei）：{df.poll_time.min()} ~ {df.poll_time.max()}；輪詢次數：{polls}；資料列：{len(df)}；車輛數：{df.PlateNumb.nunique()}\n')
    f.write(samp.to_string(index=False)+'\n')
print(open(f'{BASE}/outputs/A3_sample_status.txt',encoding='utf-8').read())
st=pd.read_csv(f'{BASE}/data/stations_green_north.csv')
stg=gpd.GeoDataFrame(st,geometry=gpd.points_from_xy(st.lon,st.lat),crs=4326).to_crs(3826)
g=gpd.GeoDataFrame(df,geometry=gpd.points_from_xy(df.lon,df.lat),crs=4326).to_crs(3826)
R=150  # 計時點半徑（m）
passes=[]
for _,s in stg.iterrows():
    near=g[g.geometry.distance(s.geometry)<=R]
    for (plate,dirn),d in near.groupby(['PlateNumb','Direction']):
        d=d.sort_values('t'); gap=d.t.diff().dt.total_seconds().fillna(9e9)
        for _,grp in d.groupby((gap>600).cumsum()):
            passes.append(dict(station=s.code,plate=plate,dir=dirn,route=grp.RouteName.iloc[0],t=grp.t.min()))
P=pd.DataFrame(passes)
if P.empty:
    open(f'{BASE}/outputs/A3_sample_status.txt','a',encoding='utf-8').write('取樣期間內無車輛通過計時點（150 m），尚無法計算班距與站間行駛時間。\n')
    print('取樣期間內無車輛通過計時點。'); sys.exit(0)
hw=[]
for (stn,rt,dirn),d in P.groupby(['station','route','dir']):
    t=d.t.sort_values(); h=t.diff().dt.total_seconds().dropna()/60
    if len(h): hw.append(dict(station=stn,route=rt,dir=dirn,n_pass=len(t),headway_mean_min=round(h.mean(),1),headway_sd_min=round(h.std(),1) if len(h)>1 else np.nan,cv=round(h.std()/h.mean(),2) if len(h)>1 and h.mean()>0 else np.nan))
H=pd.DataFrame(hw)
tt=[]
order=list(st.code)
for (plate,dirn),d in P.groupby(['plate','dir']):
    d=d.sort_values('t')
    for i in range(len(d)-1):
        a,b=d.iloc[i],d.iloc[i+1]
        dtm=(b.t-a.t).total_seconds()/60
        if 0<dtm<90 and a.station!=b.station: tt.append(dict(route=a.route,dir=dirn,from_st=a.station,to_st=b.station,minutes=round(dtm,1),depart=a.t))
T=pd.DataFrame(tt)
span=f"{df.t.min()} ~ {df.t.max()}"
os.makedirs(f'{BASE}/outputs',exist_ok=True)
H.to_csv(f'{BASE}/outputs/A3_headway_sample.csv',index=False,encoding='utf-8-sig')
T.to_csv(f'{BASE}/outputs/A3_traveltime_sample.csv',index=False,encoding='utf-8-sig')
print('資料期間',span,'筆數',len(df)); print(H.to_string()); print(T.groupby(['route','from_st','to_st']).minutes.describe().to_string() if len(T) else '無站間行駛時間樣本')
