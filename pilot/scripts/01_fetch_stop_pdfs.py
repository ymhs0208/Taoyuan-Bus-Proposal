"""下載桃園市政府資料開放平台「桃園市市區公車路線資訊」中 stopAddrUrl 欄位所列之官方路線站址表 PDF。
禮貌抓取：每次請求間隔 1.2 秒，已下載者略過。"""
import json, os, time, urllib.request, datetime
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=json.load(open(f'{BASE}/data/tycg_route_info.json',encoding='utf-8'))
out=f'{BASE}/data/stop_pdfs'; os.makedirs(out,exist_ok=True)
seen=set(); log=open(f'{BASE}/logs/fetch_pdfs.log','a')
for r in rows:
    u=(r.get('stopAddrUrl') or '').strip()
    if not u or u in seen: continue
    seen.add(u)
    u=u.replace('http://','https://')
    fn=f"{out}/{r['ID']}.pdf"
    if os.path.exists(fn) and os.path.getsize(fn)>1000: continue
    for attempt in range(3):
        try:
            req=urllib.request.Request(u,headers={'User-Agent':'student-research-pilot (Do Research for Taoyuan)'})
            data=urllib.request.urlopen(req,timeout=60).read()
            open(fn,'wb').write(data); log.write(f"{datetime.datetime.now().isoformat()} OK {u} {len(data)}\n"); break
        except Exception as e:
            log.write(f"{datetime.datetime.now().isoformat()} ERR {u} {e}\n"); time.sleep(3*(attempt+1))
    log.flush(); time.sleep(1.2)
print('done', len(seen))
