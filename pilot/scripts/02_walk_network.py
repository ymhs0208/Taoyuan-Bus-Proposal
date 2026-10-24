"""以 osmnx 逐站下載綠線北段 7 站半徑 1,100 m 之 OSM 步行路網（較小查詢，降低 Overpass 負載），失敗時指數退避重試。"""
import os, time, osmnx as ox, pandas as pd
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ox.settings.requests_timeout=120
ox.settings.overpass_rate_limit=False
ox.settings.http_user_agent="student-research-pilot (Do Research for Taoyuan)"
eps=["https://overpass-api.de/api","https://overpass.private.coffee/api","https://maps.mail.ru/osm/tools/overpass/api"]
st=pd.read_csv(f'{BASE}/data/stations_green_north.csv')
os.makedirs(f'{BASE}/data/walk',exist_ok=True)
for _,s in st.iterrows():
    fn=f"{BASE}/data/walk/{s.code}.graphml"
    if os.path.exists(fn): continue
    for k in range(8):
        ox.settings.overpass_url=eps[k%len(eps)]
        try:
            G=ox.graph_from_point((s.lat,s.lon),dist=1100,network_type='walk',simplify=True)
            ox.save_graphml(G,fn); print(s.code,len(G.nodes),len(G.edges),ox.settings.overpass_url,flush=True); break
        except Exception as e:
            w=min(240,15*2**k); print(s.code,'retry',k,ox.settings.overpass_url,str(e)[:120],'wait',w,flush=True); time.sleep(w)
    time.sleep(10)
