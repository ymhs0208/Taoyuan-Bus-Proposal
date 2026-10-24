"""取得 TDX 靜態資料（Shape、StopOfRoute、Route；Schedule 由 10_frequency.py 依路線篩選取得）。原始回應以 gzip 存於 data/tdx/。"""
import os,sys,gzip,json,datetime
sys.path.insert(0,os.path.dirname(__file__)); import tdx
B='https://tdx.transportdata.tw/api/basic/v2/Bus'
out=f'{tdx.BASE}/data/tdx'; os.makedirs(out,exist_ok=True)
for name in sys.argv[1:] or ['Shape','StopOfRoute','Route']:
    fn=f'{out}/{name}_Taoyuan.json.gz'
    if os.path.exists(fn): print('skip',name); continue
    b=tdx.get(f'{B}/{name}/City/Taoyuan?%24format=JSON',raw=True)
    with gzip.open(fn,'wb') as f: f.write(b)
    open(f'{out}/{name}_retrieved_at.txt','w').write(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S (UTC+8)'))
    print(name,len(json.loads(b)),'records',round(len(b)/1e6,2),'MB')
