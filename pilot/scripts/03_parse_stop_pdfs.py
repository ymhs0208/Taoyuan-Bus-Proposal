"""解析官方「路線站址表」PDF（pdftotext -layout），輸出每條路線各『站序型態』(pattern) 的站序、站名、經緯度。
- 支援十進位座標（24.98667 121.31388）與度分秒寫法（N 24.59 40.645 E 121.18 5.061 = 24°59'40.645"）。
- 依『站序重新從 1 開始』切分去程／返程等型態。
- 無法擷取文字（掃描影像）或座標者記入 parse_report.csv。"""
import os, re, json, subprocess, csv
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=json.load(open(f'{BASE}/data/tycg_route_info.json',encoding='utf-8'))
meta={}
for r in rows:
    meta.setdefault(r['ID'],r)
DEC=re.compile(r'(?<![\d.])N?\s?(2[1-6]\.\d{3,7})[\s,]+E?\s?(1[12]\d\.\d{3,7})(?![\d.])')
DMS=re.compile(r'N\s*(2[1-6])\.(\d{1,2})\s+(\d{1,2}(?:\.\d+)?)\s*E\s*(1[12]\d)\.(\d{1,2})\s+(\d{1,2}(?:\.\d+)?)')
def parse_line(line):
    recs=[];prev=0
    ms=[(m.start(),m.end(),float(m.group(1)),float(m.group(2))) for m in DEC.finditer(line)]
    if not ms:
        for m in DMS.finditer(line):
            lat=int(m.group(1))+int(m.group(2))/60+float(m.group(3))/3600
            lon=int(m.group(4))+int(m.group(5))/60+float(m.group(6))/3600
            ms.append((m.start(),m.end(),lat,lon))
    for s,e,lat,lon in ms:
        chunk=line[prev:s]; prev=e
        # 去掉上一筆尾端的里程/站距數字
        mm=re.search(r'(?:^|\s)(\d{1,3})\s+(\S+)\s+.*$',chunk.strip()+' ') if chunk.strip() else None
        toks=chunk.split()
        # 找第一個 1-3 位整數且後面接非數字 token
        seq=name=None
        for i,t in enumerate(toks):
            if re.fullmatch(r'\d{1,3}',t) and i+1<len(toks) and not re.fullmatch(r'[\d.\-–km]+',toks[i+1]):
                seq=int(t);name=toks[i+1];break
        if seq is None:
            ints=[t for t in toks if re.fullmatch(r'\d{1,3}',t)]
            if ints: seq=int(ints[0]); name=''
        if seq is None: continue
        recs.append((seq,name,lat,lon))
    return recs
out=[];report=[]
pdfdir=f'{BASE}/data/stop_pdfs'
for fn in sorted(os.listdir(pdfdir)):
    if not fn.endswith('.pdf'): continue
    rid=fn[:-4]; m=meta.get(rid,{})
    try:
        txt=subprocess.run(['pdftotext','-layout',f'{pdfdir}/{fn}','-'],capture_output=True,text=True,timeout=60).stdout
    except Exception as e:
        report.append(dict(route_id=rid,route=m.get('nameZh'),status='pdftotext_error',n=0));continue
    lines=txt.splitlines()
    title=next((l.strip() for l in lines if l.strip()),'')
    left=[];right=[]
    for l in lines:
        recs=parse_line(l)
        if recs: left.append(recs[0])
        if len(recs)>1: right.extend(recs[1:])
    seqs=left+right
    if len(seqs)<2:
        report.append(dict(route_id=rid,route=m.get('nameZh'),status='no_coords_extracted' if txt.strip() else 'no_text(image_pdf?)',n=len(seqs),title=title[:60]));continue
    # 切 pattern：站序回到 1 時開新段
    pats=[];cur=[]
    for rec in seqs:
        if cur and rec[0]==1: pats.append(cur);cur=[]
        cur.append(rec)
    if cur: pats.append(cur)
    for pi,p in enumerate(pats):
        for k,(seq,name,lat,lon) in enumerate(p):
            out.append(dict(route_id=rid,route=m.get('nameZh'),ddesc=m.get('ddesc'),route_type=m.get('RouteType'),pattern=pi,seq=seq,order=k,stop_name=name,lat=round(lat,6),lon=round(lon,6)))
    report.append(dict(route_id=rid,route=m.get('nameZh'),status='ok',n=len(seqs),patterns=len(pats),title=title[:60]))
with open(f'{BASE}/data/route_stops_parsed.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(out[0].keys()));w.writeheader();w.writerows(out)
with open(f'{BASE}/data/parse_report.csv','w',encoding='utf-8-sig',newline='') as f:
    keys=['route_id','route','status','n','patterns','title']
    w=csv.DictWriter(f,fieldnames=keys);w.writeheader();[w.writerow({k:r.get(k,'') for k in keys}) for r in report]
import collections
print(collections.Counter(r['status'] for r in report), len(out))
