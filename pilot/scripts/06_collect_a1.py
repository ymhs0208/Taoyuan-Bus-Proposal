#!/usr/bin/env python3
"""分析三：通車前基準 — TDX 桃園市區公車 A1（RealTimeByFrequency）收集器 v2。

- 金鑰：由 scripts/tdx.py 在每次需要 token 時自環境變數 TDX_CLIENT_ID / TDX_CLIENT_SECRET 讀取（不輸出、不寫檔）。
- 每次輪詢只發 1 次 API 呼叫：以 OData $filter 一次取回 config/collector_routes.txt 所列全部路線。
- 時段排程（Asia/Taipei）：
    平日 07–09、17–19（尖峰）每 90 秒；平日 06–07、09–17、19–22 每 10 分鐘；
    週末 07–22 每 20 分鐘；其餘時段不呼叫。
- 額度保護：依 logs/tdx_usage.csv 計算當月估計點數（calls/1500 + MB/150，保守相加），
  超過 --max-points（預設 2.7，基礎方案每月 3 點）即暫停到下個月；到 --until 自動結束。
- 429 / 5xx / 401：指數退避重試（tdx.get）；SIGTERM / SIGINT 安全結束。
- 輸出：data/a1/a1_YYYYMMDD.csv.gz（每日一檔，gzip 追加）；日誌 logs/collector.log。
用法：
  nohup .venv/bin/python scripts/06_collect_a1.py --until 2026-11-14T23:59 > logs/collector.out 2>&1 &
  echo $! > logs/collector.pid
停止：kill $(cat logs/collector.pid)"""
import os, sys, time, gzip, csv, signal, argparse, logging, datetime, urllib.parse
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); import tdx
BASE=tdx.BASE
API='https://tdx.transportdata.tw/api/basic/v2/Bus/RealTimeByFrequency/City/Taoyuan?'
FIELDS=['poll_time','PlateNumb','OperatorID','RouteUID','RouteName','SubRouteUID','SubRouteName','Direction','lat','lon','Speed','Azimuth','DutyStatus','BusStatus','GPSTime','SrcUpdateTime','UpdateTime']
stop=False
def _sig(*a):
    global stop; stop=True
signal.signal(signal.SIGTERM,_sig); signal.signal(signal.SIGINT,_sig)
def interval_for(now):
    h=now.hour+now.minute/60; wd=now.weekday()<5
    if wd:
        if 7<=h<9 or 17<=h<19: return 90
        if 6<=h<22: return 600
        return None
    return 1200 if 7<=h<22 else None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--routes-file',default=f'{BASE}/config/collector_routes.txt')
    ap.add_argument('--until',default='2026-11-14T23:59')
    ap.add_argument('--max-points',type=float,default=2.7)
    a=ap.parse_args()
    os.makedirs(f'{BASE}/data/a1',exist_ok=True)
    logging.basicConfig(filename=f'{BASE}/logs/collector.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    log=logging.getLogger()
    if not os.environ.get('TDX_CLIENT_ID') or not os.environ.get('TDX_CLIENT_SECRET'):
        log.error('TDX_CLIENT_ID / TDX_CLIENT_SECRET 未設定，停止。'); sys.exit(2)
    routes=[r.strip() for r in open(a.routes_file,encoding='utf-8') if r.strip()]
    url=API+urllib.parse.urlencode({'$filter':' or '.join(f"RouteName/Zh_tw eq '{r}'" for r in routes),'$format':'JSON'})
    until=datetime.datetime.fromisoformat(a.until)
    log.info(f'start pid={os.getpid()} routes={len(routes)} until={a.until} max_points={a.max_points}')
    while not stop:
        now=datetime.datetime.now()
        if now>=until: log.info('reached --until, stopping'); break
        iv=interval_for(now)
        if iv is None:
            time.sleep(60); continue
        calls,mb,pts=tdx.month_usage()
        if pts>=a.max_points:
            log.warning(f'month budget reached ({calls} calls, {mb:.1f} MB, ~{pts:.2f} pts); pausing'); time.sleep(1800); continue
        t0=time.time()
        try:
            data=tdx.get(url)
        except Exception as e:
            log.error(f'poll failed: {e}'); data=None
        if data is not None:
            fn=f"{BASE}/data/a1/a1_{now:%Y%m%d}.csv.gz"; new=not os.path.exists(fn)
            with gzip.open(fn,'at',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=FIELDS)
                if new: w.writeheader()
                for b in data:
                    pos=b.get('BusPosition') or {}
                    w.writerow({'poll_time':now.isoformat(timespec='seconds'),'PlateNumb':b.get('PlateNumb'),'OperatorID':b.get('OperatorID'),'RouteUID':b.get('RouteUID'),
                        'RouteName':(b.get('RouteName') or {}).get('Zh_tw'),'SubRouteUID':b.get('SubRouteUID'),
                        'SubRouteName':(b.get('SubRouteName') or {}).get('Zh_tw'),'Direction':b.get('Direction'),
                        'lat':pos.get('PositionLat'),'lon':pos.get('PositionLon'),'Speed':b.get('Speed'),'Azimuth':b.get('Azimuth'),
                        'DutyStatus':b.get('DutyStatus'),'BusStatus':b.get('BusStatus'),
                        'GPSTime':b.get('GPSTime'),'SrcUpdateTime':b.get('SrcUpdateTime'),'UpdateTime':b.get('UpdateTime')})
            log.info(f'poll ok rows={len(data)} interval={iv}s month_calls={calls+1}')
        dt=iv-(time.time()-t0)
        while dt>0 and not stop:
            time.sleep(min(5,dt)); dt-=5
            if interval_for(datetime.datetime.now())!=iv: break
    log.info('stopped')
if __name__=='__main__': main()
