"""TDX 共用工具。
- 金鑰：每次需要 token 時才從環境變數 TDX_CLIENT_ID / TDX_CLIENT_SECRET 讀取；不輸出、不寫檔、不記錄。
- token 快取並於到期前 5 分鐘更新；401 時強制更新。
- 頻率：基礎（免費）方案 5 次/分/金鑰 → 每次呼叫至少間隔 MIN_GAP 秒（跨程序以檔案鎖時間戳協調）。
- 429 / 5xx / 網路錯誤：指數退避重試。
- 用量帳本 logs/tdx_usage.csv：時間,狀態,壓縮位元組,解壓位元組,端點（不含查詢參數與金鑰）。
- 點數估算（保守，採相加）：points = calls/1500 + MB(解壓)/150；基礎方案每月 3 點。"""
import os, json, time, gzip, fcntl, datetime, urllib.request, urllib.parse, urllib.error
TOKEN_URL='https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token'
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER=f'{BASE}/logs/tdx_usage.csv'; GAPFILE=f'{BASE}/logs/.tdx_last_call'
MIN_GAP=13
_tok={'v':None,'exp':0}
def token():
    if _tok['v'] and time.time()<_tok['exp']-300: return _tok['v']
    cid=os.environ.get('TDX_CLIENT_ID'); sec=os.environ.get('TDX_CLIENT_SECRET')
    if not cid or not sec: raise RuntimeError('TDX_CLIENT_ID / TDX_CLIENT_SECRET 未設定')
    d=urllib.parse.urlencode({'grant_type':'client_credentials','client_id':cid,'client_secret':sec}).encode()
    j=json.load(urllib.request.urlopen(urllib.request.Request(TOKEN_URL,data=d,headers={'content-type':'application/x-www-form-urlencoded'}),timeout=30))
    _tok['v']=j['access_token']; _tok['exp']=time.time()+int(j.get('expires_in',3600)); return _tok['v']
def _gap():
    os.makedirs(f'{BASE}/logs',exist_ok=True)
    with open(GAPFILE,'a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX); f.seek(0); t=f.read().strip()
        last=float(t) if t else 0; w=MIN_GAP-(time.time()-last)
        if w>0: time.sleep(w)
        f.seek(0); f.truncate(); f.write(str(time.time())); fcntl.flock(f,fcntl.LOCK_UN)
def _log(url,status,nz,nraw):
    with open(LEDGER,'a') as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')},{status},{nz},{nraw},{url.split('?')[0]}\n")
def month_usage(month=None):
    month=month or datetime.datetime.now().strftime('%Y-%m'); calls=0; mb=0.0
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            p=line.strip().split(',')
            if len(p)>=5 and p[0].startswith(month):
                calls+=1
                try: mb+=float(p[3])/1e6
                except ValueError: mb+=float(p[2])/1e6 if p[2].replace('.','').isdigit() else 0
    return calls,mb,calls/1500+mb/150
def get(url,tries=6,raw=False):
    for k in range(tries):
        _gap()
        try:
            req=urllib.request.Request(url,headers={'authorization':'Bearer '+token(),'Accept-Encoding':'gzip','User-Agent':'student-research-pilot'})
            r=urllib.request.urlopen(req,timeout=180); b=r.read(); nz=len(b)
            if r.headers.get('Content-Encoding')=='gzip': b=gzip.decompress(b)
            _log(url,r.status,nz,len(b))
            return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            _log(url,e.code,0,0)
            if e.code==401: _tok['v']=None
            if e.code in (401,429) or e.code>=500:
                time.sleep(min(300,5*2**k)); continue
            raise
        except Exception:
            time.sleep(min(300,5*2**k))
    raise RuntimeError('failed '+url.split('?')[0])
