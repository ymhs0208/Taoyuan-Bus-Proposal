#!/usr/bin/env python3
"""分析三：班距可靠度（通車前基準）。讀 06_collect_a1.py 蒐集的 A1 公車位置，不呼叫 TDX、不需金鑰。

方法（與 07_summarize_a1.py 的「150 m 圈內第一筆」不同）：
  1. 每條路線方向取 TDX Shape 線型；車站投影到線型上，得到計時點的里程 s*（站距線型 > --radius 者不分析）。
  2. 每輛車（PlateNumb＋SubRouteUID＋Direction）把每筆位置投影到線型得到里程 s_i。
  3. 相鄰兩筆（GPS 時間差 ≤ --max-gap 秒、同向前進）若 s_i < s* ≤ s_{i+1}，以線性內插求通過計時點的時刻。
     尖峰每 90 秒輪詢一次，一輛車一次移動約數百公尺，因此不能只看「圈內有沒有點」。
  4. 同一計時點相鄰兩班通過時刻的差＝實際班距；時刻表班距取 Schedule 同方向、當天星期別營運班次的起點發車間隔
     （假設起點班距≈計時點班距，【假設】）。
  5. 每個（路線,方向,車站,時段）輸出：
     cv（實際班距變異係數）、gap_rate（實際班距 > gap_mult × 時刻表）、bunch_rate（< bunch_mult × 時刻表）、ratio_median。
     gap_mult=2、bunch_mult=0.25 為暫定門檻，可用參數調整，不是結論。
時段：AM 07–09、MID 09–17、PM 17–19（平日）。自家蒐集器離峰每 10 分鐘才輪詢，相鄰兩筆超過 --max-gap 會被濾掉，
因此 MID 只會出現在取樣夠密的資料（如 TDX 歷史檔，每 20 秒一筆）。

限制（輸出與報告須一併註明）：
  - 抽樣漏車（車輛沒回報、離開服務時段、兩次輪詢間 GPS 缺漏）會被當成「大間隔」，使 gap_rate 偏高；
    coverage 子指令會列出每個計時點的通過數，樣本太少者標 sufficient=False，不應引用。
  - 線型自我折返或迴圈的路線（如 GR2）投影可能落在另一段，已用「相鄰兩筆里程差 0–3 km」過濾，但仍應人工檢查 coverage 的 fwd_share；
  - 時刻表只有起點發車時刻；末班前、收班與調度空車未排除。
  - 欄位名稱（SubRouteUID、Direction、GPSTime、DutyStatus、BusStatus）已對 10/24 實際檔核對；
    DutyStatus=2（結束勤務）與 BusStatus=99（非營運）視為不在服務中而剔除，其餘代碼意義【待核對 TDX 文件】。

用法（在 pilot/ 下）：
  python scripts/11_headway.py coverage            # 資料量夠不夠
  python scripts/11_headway.py analyze             # 寫 outputs/A3_headway_*.csv
  python scripts/11_headway.py selftest            # 合成資料驗證演算法
"""
import os, sys, ast, glob, gzip, json, argparse, datetime
import numpy as np, pandas as pd
from shapely import wkt
from shapely.geometry import LineString, Point
import pyproj

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = 'Asia/Taipei'
PEAKS = {'AM': (7, 9), 'MID': (9, 17), 'PM': (17, 19)}   # MID 只有取樣密（≤180 s）時才有資料；自家蒐集器離峰 10 分鐘一筆會被 max_gap 濾掉
DAYCOL = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MIN_HEADWAYS = 5   # 每組至少幾個實際班距才算 sufficient
_T = pyproj.Transformer.from_crs(4326, 3826, always_xy=True)


# ---------------------------------------------------------------- 讀資料
_COLMAP = {'PositionLat': 'lat', 'PositionLon': 'lon', 'RouteNameZh_tw': 'RouteName'}
_DIR = {'去程': 0, '返程': 1}
_DUTY_END = {2, '結束'}         # TDX DutyStatus：0 正常、1 開始、2 結束（歷史檔為中文字串，已對 10/21 檔核對）
_BUS_OFF = {99, '非營運狀態'}   # TDX BusStatus：99 非營運
_NEED = ['PlateNumb', 'SubRouteUID', 'Direction', 'GPSTime', 'DutyStatus', 'BusStatus', 'lat', 'lon', 'RouteName']


def _norm(d: pd.DataFrame) -> pd.DataFrame:
    """統一自家蒐集器（lat/lon、Direction 0/1、DutyStatus 數字）與 TDX 歷史檔（PositionLat、去程/返程、中文狀態）。"""
    d = d.rename(columns=_COLMAP)
    d['Direction'] = d.Direction.map(lambda v: _DIR.get(v, v))
    return d[[c for c in _NEED if c in d.columns]]


def load_a1(files=None) -> pd.DataFrame:
    files = files or sorted(glob.glob(f'{BASE}/data/a1/a1_*.csv*') + glob.glob(f'{BASE}/data/a1_hist/*.[cC][sS][vV]'))
    dfs = []
    for f in files:
        try:
            raw = pd.read_csv(f, low_memory=False, on_bad_lines='skip', encoding='utf-8-sig')
            dfs.append(_norm(raw))
        except Exception as e:
            print(f'略過 {os.path.basename(f)}：{e}', file=sys.stderr)   # 收集器可能正在寫入
    if not dfs:
        return pd.DataFrame()
    d = pd.concat(dfs, ignore_index=True)
    d['lat'] = pd.to_numeric(d.lat, errors='coerce'); d['lon'] = pd.to_numeric(d.lon, errors='coerce')
    d['t'] = pd.to_datetime(d.GPSTime, errors='coerce', utc=True).dt.tz_convert(TZ)
    d = d.dropna(subset=['lat', 'lon', 't'])
    if 'DutyStatus' in d:
        d = d[~d.DutyStatus.isin(_DUTY_END)]
    if 'BusStatus' in d:
        d = d[~d.BusStatus.isin(_BUS_OFF)]
    d['Direction'] = pd.to_numeric(d.Direction, errors='coerce').fillna(0).astype(int)
    d = d.drop_duplicates(['PlateNumb', 't']).sort_values(['PlateNumb', 't'])
    d['x'], d['y'] = _T.transform(d.lon.values, d.lat.values)
    return d


def load_lines() -> dict:
    """{(SubRouteUID, Direction): (名稱, LineString EPSG:3826)}"""
    out = {}
    for r in json.load(gzip.open(f'{BASE}/data/tdx/Shape_Taoyuan.json.gz')):
        g = r.get('Geometry')
        if not g:
            continue
        ll = wkt.loads(g)
        if ll.geom_type != 'LineString' or len(ll.coords) < 2:
            continue
        xs, ys = _T.transform([c[0] for c in ll.coords], [c[1] for c in ll.coords])
        nm = r['SubRouteName']
        nm = ast.literal_eval(nm)['Zh_tw'] if isinstance(nm, str) and nm.startswith('{') else (nm.get('Zh_tw') if isinstance(nm, dict) else nm)
        out[(r['SubRouteUID'], int(r['Direction']))] = (nm, LineString(list(zip(xs, ys))))
    return out


def load_stations() -> pd.DataFrame:
    s = pd.read_csv(f'{BASE}/data/stations_green_north.csv')
    s['x'], s['y'] = _T.transform(s.lon.values, s.lat.values)
    return s


def load_schedule() -> dict:
    """{(SubRouteUID, Direction): [(發車時刻 HH:MM, 營運星期集合)]}；只有起點時刻。"""
    f = f'{BASE}/data/tdx/Schedule_Taoyuan_800m_routes.json.gz'
    out = {}
    if not os.path.exists(f):
        return out
    for r in json.load(gzip.open(f)):
        k = (r['SubRouteUID'], int(r['Direction']))
        for tt in r.get('Timetables', []):
            days = {i for i, c in enumerate(DAYCOL) if (tt.get('ServiceDay') or {}).get(c)}
            st = tt.get('StopTimes') or []
            if st:
                out.setdefault(k, []).append((st[0].get('DepartureTime') or st[0].get('ArrivalTime'), days))
    return out


# ---------------------------------------------------------------- 計時點通過時刻
def passes_for_line(bus: pd.DataFrame, line: LineString, timing: dict, max_gap=180, off_line=100):
    """bus：同一路線方向的位置；timing：{station: s*（m）}。回傳 DataFrame(station, plate, t)。
    也回傳前進比例 fwd_share（診斷 Shape 方向是否與 Direction 一致）。"""
    rows, fwd, tot = [], 0, 0
    for plate, d in bus.groupby('PlateNumb'):
        d = d.sort_values('t')
        pts = [Point(x, y) for x, y in zip(d.x, d.y)]
        s = np.array([line.project(p) for p in pts])
        off = np.array([line.distance(p) for p in pts])
        t = list(d.t)   # 保留時區（.values 會變 UTC naive，使尖峰判斷偏 8 小時）
        for i in range(len(d) - 1):
            dt = (t[i + 1] - t[i]).total_seconds()
            if not (0 < dt <= max_gap) or off[i] > off_line or off[i + 1] > off_line:
                continue
            ds = s[i + 1] - s[i]
            if abs(ds) > 3000:          # 迴圈路線或投影跳點
                continue
            if abs(ds) > 10:            # 停在總站不動的車不計入前進比例
                tot += 1; fwd += ds > 0
            if ds <= 0:
                continue
            for stn, ss in timing.items():
                if s[i] < ss <= s[i + 1]:
                    tp = t[i] + pd.Timedelta(seconds=dt * (ss - s[i]) / ds)
                    rows.append(dict(station=stn, plate=plate, t=tp))
    return pd.DataFrame(rows, columns=['station', 'plate', 't']), (fwd / tot if tot else np.nan)


def period_of(ts: pd.Timestamp):
    if ts.weekday() > 4:
        return None
    h = ts.hour + ts.minute / 60
    for k, (a, b) in PEAKS.items():
        if a <= h < b:
            return k
    return None


def sched_headways(times: list, date: datetime.date, period: str, weekday: int) -> list:
    """同一天、同時段、當天營運班次的起點發車間隔（分鐘）。"""
    a, b = PEAKS[period]
    mins = sorted(int(t[:2]) * 60 + int(t[3:5]) for t, days in times if weekday in days and t)
    mins = [m for m in mins if a * 60 <= m < b * 60]
    return list(np.diff(mins))


# ---------------------------------------------------------------- 主流程
def compute(a1: pd.DataFrame, radius=500, max_gap=180, gap_mult=2.0, bunch_mult=0.25):
    lines, stg, sched = load_lines(), load_stations(), load_schedule()
    pr, hw = [], []
    diag = []
    fwd_of = {}
    groups = {k: g for k, g in a1.groupby(['SubRouteUID', 'Direction'])} if not a1.empty else {}
    for (sub, dr), (nm, line) in lines.items():
        bus = groups.get((sub, dr), a1.iloc[0:0])
        timing = {}
        for _, s in stg.iterrows():
            p = Point(s.x, s.y)
            if line.distance(p) <= radius:
                timing[s.code] = line.project(p)
        if not timing:
            continue
        if bus.empty:
            diag.append(dict(route=nm, sub=sub, dir=dr, stations=len(timing), buses=0, peak_pairs=0, fwd_share=np.nan))
            continue
        P, fwd = passes_for_line(bus, line, timing, max_gap)
        fwd_of[(nm, dr)] = fwd
        diag.append(dict(route=nm, sub=sub, dir=dr, stations=len(timing), buses=bus.PlateNumb.nunique(),
                         peak_pairs=len(P), fwd_share=round(fwd, 2) if fwd == fwd else np.nan))
        if P.empty:
            continue
        P['route'], P['sub'], P['dir'] = nm, sub, dr
        P['period'] = P.t.map(period_of)
        pr.append(P)
        for (stn, per, day), g in P.dropna(subset=['period']).assign(day=lambda x: x.t.dt.date).groupby(['station', 'period', 'day']):
            g = g.sort_values('t')
            # 同一輛車連續兩次通過不算班距；時間差 > 120 分視為斷檔
            h = g.t.diff().dt.total_seconds().div(60)
            ok = (g.plate != g.plate.shift()) & h.notna() & (h < 120)
            sh = sched_headways(sched.get((sub, dr), []), day, per, day.weekday())
            sched_med = float(np.median(sh)) if sh else np.nan
            for ix, v in h[ok].items():
                hw.append(dict(route=nm, sub=sub, dir=dr, station=stn, period=per, day=day, time=g.t.loc[ix], headway_min=v, sched_min=sched_med))
    passes = pd.concat(pr, ignore_index=True) if pr else pd.DataFrame()
    H = pd.DataFrame(hw)
    rows = []
    if not H.empty:
        for (nm, sub, dr, stn, per), g in H.groupby(['route', 'sub', 'dir', 'station', 'period']):
            h = g.headway_min.values
            sm = g.sched_min.dropna()
            ratio = (g.headway_min / g.sched_min).dropna()
            rows.append(dict(route=nm, dir=dr, station=stn, period=per, days=g.day.nunique(), n_headways=len(h),
                             mean_min=round(h.mean(), 1), cv=round(h.std(ddof=1) / h.mean(), 2) if len(h) > 1 and h.mean() > 0 else np.nan,
                             sched_min=round(float(sm.iloc[0]), 1) if len(sm) else np.nan,
                             ratio_median=round(float(ratio.median()), 2) if len(ratio) else np.nan,
                             gap_rate=round(float((ratio > gap_mult).mean()), 2) if len(ratio) else np.nan,
                             bunch_rate=round(float((ratio < bunch_mult).mean()), 2) if len(ratio) else np.nan,
                             # 前進比例 < 0.8（Shape 方向可能不符或為迴圈）者不採用
                             sufficient=len(h) >= MIN_HEADWAYS and len(ratio) >= MIN_HEADWAYS and not (fwd_of.get((nm, dr), 1) < 0.8)))
    return pd.DataFrame(rows), H, passes, pd.DataFrame(diag)


def cmd_coverage(a):
    a1 = load_a1()
    if a1.empty:
        print('尚無 A1 資料。'); return
    dts = a1.groupby('PlateNumb').t.diff().dt.total_seconds().dropna()
    pk = a1[a1.t.map(period_of).notna()]
    print(f'A1 列數 {len(a1)}；時間 {a1.t.min()} ~ {a1.t.max()}；車輛 {a1.PlateNumb.nunique()}；資料天數 {a1.t.dt.date.nunique()}')
    print(f'取樣間隔（同車相鄰兩筆）中位數 {dts.median():.0f} 秒；≤{a.max_gap:.0f} 秒的比例 {(dts <= a.max_gap).mean():.1%}')
    print(f'平日分析時段（AM/MID/PM）列數 {len(pk)}；平日天數 {pk.t.dt.date.nunique()}')
    S, H, P, D = compute(a1, a.radius, a.max_gap, a.gap_mult, a.bunch_mult)
    print(f'\n有計時點的路線方向 {len(D)} 個（站距線型 ≤ {a.radius} m）')
    if not D.empty:
        print(D.sort_values('peak_pairs', ascending=False).head(15).to_string(index=False))
        bad = D[D.fwd_share < 0.8]
        if len(bad):
            print('\n⚠ 前進比例 < 0.8（Shape 方向可能與 Direction 相反或為迴圈）：', list(bad.route.unique()))
    n = len(H)
    print(f'\n可用實際班距 {n} 筆；達 {MIN_HEADWAYS} 筆以上的（路線,方向,站,時段）組合 {int(S.sufficient.sum()) if len(S) else 0} 組')
    if n < 50:
        print('→ 樣本仍太少，不要引用任何班距指標。持續蒐集到有多個平日尖峰再分析。')


def cmd_analyze(a):
    a1 = load_a1()
    if a1.empty:
        print('尚無 A1 資料。'); return
    S, H, P, D = compute(a1, a.radius, a.max_gap, a.gap_mult, a.bunch_mult)
    os.makedirs(f'{BASE}/outputs', exist_ok=True)
    S.to_csv(f'{BASE}/outputs/A3_headway_summary.csv', index=False, encoding='utf-8-sig')
    H.to_csv(f'{BASE}/outputs/A3_headway_detail.csv', index=False, encoding='utf-8-sig')
    D.to_csv(f'{BASE}/outputs/A3_headway_coverage.csv', index=False, encoding='utf-8-sig')
    with open(f'{BASE}/outputs/A3_headway_params.txt', 'w', encoding='utf-8') as f:
        f.write(f'radius={a.radius} m; max_gap={a.max_gap} s; gap_mult={a.gap_mult}（暫定）; bunch_mult={a.bunch_mult}（暫定）\n'
                f'A1 時間 {a1.t.min()} ~ {a1.t.max()}；時刻表班距以起點發車間隔代替計時點班距【假設】\n')
    print(f'summary {len(S)} 組（sufficient {int(S.sufficient.sum()) if len(S) else 0}）、detail {len(H)} 筆 → outputs/A3_headway_*.csv')
    if len(S):
        print(S[S.sufficient].to_string(index=False) if S.sufficient.any() else '無 sufficient 的組合，數字僅供除錯，不可引用。')


# ---------------------------------------------------------------- 自我測試（合成資料）
def _synthetic(headways_min, speed_kmh=18.0, poll=90, length_m=12000, jitter_m=0):
    """直線路線＋依指定班距發車的車；以 poll 秒輪詢，回傳 (a1, line, 真實通過計時點時刻)。"""
    v = speed_kmh / 3.6
    day = pd.Timestamp('2026-11-10 07:00', tz=TZ)  # 星期二
    starts = np.concatenate([[0], np.cumsum(np.array(headways_min) * 60)])
    ts_end = starts[-1] + length_m / v
    rows = []
    for i, t0 in enumerate(starts):
        for pt in np.arange(0, ts_end + poll, poll):
            tt = pt - t0
            if tt < 0 or tt * v > length_m:
                continue
            x = 300000 + tt * v
            rows.append(dict(PlateNumb=f'T{i:03d}', t=day + pd.Timedelta(seconds=float(pt)), x=x, y=2700000 + jitter_m,
                             SubRouteUID='SYN', Direction=0, poll_time='x'))
    d = pd.DataFrame(rows)
    line = LineString([(300000, 2700000), (300000 + length_m, 2700000)])
    s_star = 6000
    truth = [day + pd.Timedelta(seconds=float(t0 + s_star / v)) for t0 in starts]
    return d, line, s_star, truth


def cmd_selftest(_a):
    ok = True
    def check(name, cond, info=''):
        nonlocal ok
        ok &= bool(cond); print(('PASS ' if cond else 'FAIL ') + name, info)
    hws = [10] * 6 + [1] * 2 + [10] * 4 + [25] * 2 + [10] * 4        # 含併班與大間隔
    d, line, s, truth = _synthetic(hws, poll=90)
    P, fwd = passes_for_line(d, line, {'X': s}, 180)
    got = sorted(P.t)
    check('每輛車各通過一次', len(got) == len(truth), f'{len(got)}/{len(truth)}')
    err = np.abs([(g - t).total_seconds() for g, t in zip(got, sorted(truth))])
    check('內插誤差 < 3 秒（等速、無雜訊）', err.max() < 3, f'max={err.max():.2f}s')
    check('前進比例 = 1', fwd == 1.0, f'{fwd}')
    h = np.diff([g.timestamp() for g in got]) / 60
    check('還原實際班距', np.allclose(h, hws, atol=0.1), f'{np.round(h, 1).tolist()}')
    # 輪詢間隔過大（> max_gap）應不產生通過
    d2, line2, s2, _ = _synthetic([10] * 4, poll=300)
    P2, _f = passes_for_line(d2, line2, {'X': s2}, 180)
    check('輪詢間隔 > max_gap 不內插', P2.empty, f'{len(P2)} 筆')
    # 反向行駛不計
    d3 = d.copy(); d3['x'] = 2 * 300000 + 12000 - d3.x
    P3, f3 = passes_for_line(d3, line, {'X': s}, 180)
    check('反向行駛不計通過，前進比例 ≈ 0', P3.empty and f3 < 0.05, f'fwd={f3:.2f}')
    # 偏離線型過遠的點不使用
    d4, line4, s4, _ = _synthetic([10] * 4, poll=90, jitter_m=250)
    P4, _f = passes_for_line(d4, line4, {'X': s4}, 180)
    check('偏離線型 > 100 m 不使用', P4.empty, f'{len(P4)} 筆')
    # 指標
    sched = 10.0
    r = np.array(hws) / sched
    check('合成資料 gap/bunch 計數', (r > 2).sum() == 2 and (r < 0.25).sum() == 2, f'gap={(r>2).sum()} bunch={(r<0.25).sum()}')
    print('\nselftest', 'OK' if ok else '失敗'); sys.exit(0 if ok else 1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['coverage', 'analyze', 'selftest'])
    ap.add_argument('--radius', type=float, default=500, help='車站距線型多遠內才分析（m）')
    ap.add_argument('--max-gap', type=float, default=180, help='相鄰兩筆位置最大時間差（秒）')
    ap.add_argument('--gap-mult', type=float, default=2.0, help='大間隔：實際 > 倍數×時刻表（暫定）')
    ap.add_argument('--bunch-mult', type=float, default=0.25, help='併班：實際 < 倍數×時刻表（暫定）')
    a = ap.parse_args()
    {'coverage': cmd_coverage, 'analyze': cmd_analyze, 'selftest': cmd_selftest}[a.cmd](a)
