"""由 outputs/ 的 CSV 產生提案用 Markdown 表格（避免手抄數字）。輸出以空行分隔的多個表格。"""
import os, pandas as pd
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
o=lambda f:pd.read_csv(f'{BASE}/outputs/{f}')
t=o('A1_tdx_route_overlap_ranking.csv')
best=t.sort_values('len_in_500_km',ascending=False).drop_duplicates('route').head(12)
L=['| 子路線方向排名 | 子路線（方向） | TDX 線型全長 km | 500 m 範圍內長度 km | 長度占比 | 範圍內站牌／總站數 | 平日班次 | 觸及車站 |','|---|---|---|---|---|---|---|---|']
for _,r in best.iterrows():
    L.append(f"| {r['rank']} | {r['sub']}（{r.dir}） | {r.len_km} | {r.len_in_500_km} | {r.len_share_500:.1%} | {r.stops_in_500}/{r.n_stops} | {int(r.weekday_trips)} | {r.stations_list} |")
L.append('')
tot=t.veh_km_in_500_per_weekday.sum()
v=t.groupby('route').agg(len_in=('len_in_500_km','max'),trips=('weekday_trips','sum'),vk=('veh_km_in_500_per_weekday','sum'),st=('stations_list','first')).sort_values('vk',ascending=False).head(8)
L+=['| 路線（雙向合計） | 500 m 範圍內長度 km（較長方向） | 平日班次（雙向） | 範圍內車公里／平日 | 占全部重疊車公里 | 觸及車站 |','|---|---|---|---|---|---|']
for k,r in v.iterrows(): L.append(f"| {k} | {r.len_in} | {int(r.trips)} | {r.vk:.1f} | {r.vk/tot:.1%} | {r.st} |")
L.append(f"| 全部 {t.route.nunique()} 條路線合計 | | | {tot:.1f} | 100% | |")
L.append('')
c=o('A1_compare_tdx_vs_pdf.csv')
L+=['| 路線（方向） | PDF 近似：500 m 內長度 km（排名） | TDX：500 m 內長度 km（排名） | 差異 km | 說明 |','|---|---|---|---|---|']
for _,r in c[c.rank_pdf.notna()&c.rank_tdx.notna()].sort_values('rank_tdx').head(10).iterrows():
    L.append(f"| {r.route}（{int(r.dir)}） | {r.len_in_500_km_pdf}（{int(r.rank_pdf)}） | {r.len_in_500_km_tdx}（{int(r.rank_tdx)}） | {r.diff_len_km:+} | |")
L.append('')
a=o('A2_tdx_station_access_frequency.csv')
L+=['| 車站 | 站牌位置數 300／500／800 m | 路線數 300／500／800 m | 尖峰班次/時 300／500／800 m | 離峰班次/時 300／500／800 m | 平日班次（500 m） | 65 歲以上人口估計 300／500／800 m |','|---|---|---|---|---|---|---|']
for code,g in a.groupby('code',sort=False):
    g=g.set_index('dist_m'); f=lambda k:'／'.join(str(g.loc[d,k]) for d in (300,500,800))
    L.append(f"| {code} {g.loc[500,'name']} | {f('stop_positions_tdx')} | {f('n_routes_tdx')} | {f('peak_trips_per_h')} | {f('offpeak_trips_per_h')} | {g.loc[500,'weekday_trips']} | {f('pop65_est')} |")
print('\n'.join(L))
