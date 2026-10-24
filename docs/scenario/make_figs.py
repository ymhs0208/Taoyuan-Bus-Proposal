# -*- coding: utf-8 -*-
"""產生「綠線通車後公車改善方案」說明圖。資料全部來自 pilot/、app/lib（與決策平台同一套算法，來源 TDX 實際線型）。
用法（在儲存庫根目錄）：python docs/scenario/make_figs.py
圖皆為示意：無底圖，路線線型本身即道路輪廓；方案不是市府決定。"""
import os, sys, warnings
warnings.filterwarnings('ignore')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'app'))
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from shapely.geometry import box, Point
from shapely.ops import substring
from lib import data as D, metrics as M

for f in ('/System/Library/Fonts/STHeiti Medium.ttc', '/System/Library/Fonts/Hiragino Sans GB.ttc'):
    if os.path.exists(f):
        fm.fontManager.addfont(f); plt.rcParams['font.family'] = fm.FontProperties(fname=f).get_name(); break
plt.rcParams['axes.unicode_minus'] = False
OUT = os.path.join(ROOT, 'docs', 'scenario', 'fig'); os.makedirs(OUT, exist_ok=True)
SRC = 'tdx'
C_BASE, C_KEEP, C_CUT, C_NEW, C_ST = '#c9ced6', '#1f6fb5', '#d64545', '#2a9d4b', '#0b6e3a'

stg = D.stations(); vil = D.villages()
net0 = M.build_network(SRC, [], [])
rts = D.routes(SRC)
codes = list(stg.code)
sx = {r.code: (r.geometry.x, r.geometry.y) for r in stg.itertuples()}
name = {r.code: r.name for r in stg.itertuples()}


def frame(ax, cx, cy, half, title):
    ax.set_xlim(cx - half, cx + half); ax.set_ylim(cy - half, cy + half); ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([]); ax.set_title(title, fontsize=13, pad=8)
    for s in ax.spines.values(): s.set_color('#999')
    x0, y0 = cx - half + half * .08, cy - half + half * .08   # 比例尺 1 km
    ax.plot([x0, x0 + 1000], [y0, y0], 'k', lw=3); ax.text(x0 + 500, y0 + half * .03, '1 km', ha='center', fontsize=9)


def base_lines(ax, net, bb, skip=()):
    for k, r in net.items():
        if k in skip: continue
        for l in r['lines']:
            g = l.intersection(bb)
            for part in ([g] if g.geom_type == 'LineString' else list(getattr(g, 'geoms', []))):
                if part.length: ax.plot(*part.xy, color=C_BASE, lw=1.0, zorder=1)


def draw_stations(ax, which=None, label=True):
    for c in (which or codes):
        x, y = sx[c]; ax.scatter(x, y, marker='D', s=70, color=C_ST, edgecolor='white', zorder=6)
        if label: ax.annotate(f'{c} {name[c]}', (x, y), xytext=(7, 7), textcoords='offset points', fontsize=9, color=C_ST, zorder=7,
                              bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=.8))


def circles(ax, which, r, **kw):
    for c in which:
        ax.add_patch(plt.Circle(sx[c], r, fill=kw.get('fill', False), fc=kw.get('fc', 'none'), ec=kw.get('ec', C_ST), lw=1, ls=kw.get('ls', '--'), alpha=kw.get('alpha', .8), zorder=2))


def save(fig, fn):
    fig.savefig(os.path.join(OUT, fn), dpi=200, bbox_inches='tight', facecolor='white'); plt.close(fig); print('saved', fn)


# ---------- 方案一：GR 縮短 ----------
def fig1():
    gr = [k for k, r in rts.items() if r['sub'] == 'GR']
    mods = [dict(type='drop_parallel', key=k, radius=500, stations=codes, desc='') for k in gr]
    net1 = M.build_network(SRC, mods, [])
    allx = [sx[c][0] for c in codes]; ally = [sx[c][1] for c in codes]
    cx, cy = np.mean(allx), np.mean(ally); half = 6500
    bb = box(cx - half, cy - half, cx + half, cy + half)
    fig, axs = plt.subplots(1, 2, figsize=(15, 8))
    for ax, ttl, net in ((axs[0], '現況：GR 沿綠線全程並行', net0), (axs[1], '方案一：裁掉並行段，GR 只留桃園總站到 G11', net1)):
        frame(ax, cx, cy, half, ttl); base_lines(ax, net0, bb, skip=gr)
        circles(ax, codes, 500, fill=True, fc=C_ST, ec=C_ST, alpha=.12, ls='-')
        for k in gr:
            full = rts[k]['line']
            kept = net['lines'] if False else net[k]['lines']
            for l in full.intersection(bb).geoms if full.intersection(bb).geom_type != 'LineString' else [full.intersection(bb)]:
                ax.plot(*l.xy, color=C_CUT if net is net1 else C_KEEP, lw=2.2, ls='--' if net is net1 else '-', zorder=3, alpha=.9)
            if net is net1:
                for l in kept:
                    ll = l.intersection(bb)
                    for part in ([ll] if ll.geom_type == 'LineString' else list(getattr(ll, 'geoms', []))):
                        ax.plot(*part.xy, color=C_KEEP, lw=3.2, zorder=4)
        draw_stations(ax)
    axs[1].plot([], [], color=C_CUT, ls='--', lw=2.2, label='被裁掉的並行段（捷運取代）')
    axs[1].plot([], [], color=C_KEEP, lw=3.2, label='保留的 GR')
    axs[0].plot([], [], color=C_KEEP, lw=2.2, label='GR（去程與返程）')
    for ax in axs: ax.add_patch(plt.Circle((0, 0), 1, fc=C_ST, alpha=.12, label='車站 500 m 範圍') if False else plt.Rectangle((0, 0), 0, 0, fc=C_ST, alpha=.12, label='車站 500 m 範圍')); ax.legend(loc='lower right', fontsize=9, framealpha=.9)
    fig.suptitle('圖1　方案一：GR 縮短成接駁（示意，資料：TDX 線型）', fontsize=15, y=.97)
    save(fig, 'fig_s1_gr_trim.png')


# ---------- 方案二：G14 接駁線 ----------
def fig2():
    e0 = M.evaluate(net0, 300, 500)
    pts = M.greedy_feeder(SRC, 'G14', e0, net0, 300)
    f = [dict(name='G14 接駁線（演算法示意）', station='G14', points=[list(p) for p in pts], loop=True)]
    net1 = M.build_network(SRC, [], f)
    cx, cy = sx['G14']; half = 3200; bb = box(cx - half, cy - half, cx + half, cy + half)
    S = D.stop_positions(rts)
    S = S[(abs(S.x - cx) < half) & (abs(S.y - cy) < half)].drop_duplicates(['kx', 'ky'])
    fig, axs = plt.subplots(1, 2, figsize=(15, 7.6))
    for ax, ttl in ((axs[0], '現況：G14 300 m 內沒有公車站牌'), (axs[1], '方案二：G14 出發的社區循環接駁')):
        frame(ax, cx, cy, half, ttl); base_lines(ax, net0, bb)
        ax.scatter(S.x, S.y, s=10, color='#8d96a3', zorder=2, label='現有公車站牌')
        circles(ax, ['G14'], 300, ec=C_CUT, ls='-'); circles(ax, ['G14'], 500)
        draw_stations(ax, ['G14'])
    ax = axs[1]
    feeder = net1['FEEDER-0']
    for l in feeder['lines']: ax.plot(*l.xy, color=C_NEW, lw=3, zorder=4, label='新接駁線（點間直線，實際道路會更長）')
    st = feeder['stops']
    ax.scatter(st.x.iloc[1:], st.y.iloc[1:], s=60, color=C_NEW, edgecolor='white', zorder=5, label='接駁線停靠點（演算法選自既有站牌）')
    for i, r in enumerate(st.iloc[1:].itertuples(), 1): ax.annotate(str(i), (r.x, r.y), xytext=(4, 4), textcoords='offset points', fontsize=9, color=C_NEW)
    axs[0].plot([], [], color=C_CUT, label='步行 300 m'); axs[0].plot([], [], color=C_ST, ls='--', label='步行 500 m（直線示意）')
    for a in axs: a.legend(loc='lower right', fontsize=9, framealpha=.9)
    fig.suptitle('圖2　方案二：G14 社區接駁線（示意；停靠點為演算法選出，需實地確認）', fontsize=15, y=.97)
    save(fig, 'fig_s2_g14_feeder.png')


# ---------- 方案三：G12 長者多、接駁弱 ----------
def fig3():
    cx, cy = sx['G12']; half = 3000; bb = box(cx - half, cy - half, cx + half, cy + half)
    v = vil.copy(); v['den'] = v.pop65 / (v.geometry.area / 1e6)
    S = D.stop_positions(rts)
    d = np.hypot(S.x - cx, S.y - cy)
    near_keys = set(S[d <= 500].key)          # 500 m 內有站牌的路線方向＝可一車到 G12
    Sx = S[(abs(S.x - cx) < half) & (abs(S.y - cy) < half)]
    fig, ax = plt.subplots(figsize=(9.5, 8.6))
    frame(ax, cx, cy, half, '')
    vv = v.cx[cx - half:cx + half, cy - half:cy + half] if hasattr(v, 'cx') else v
    p = vv.plot(column='den', ax=ax, cmap='YlOrRd', alpha=.75, edgecolor='white', linewidth=.6, zorder=0,
                legend=True, legend_kwds=dict(label='65 歲以上人口密度（人/km²，村里均分估計）', shrink=.7))
    base_lines(ax, net0, bb)
    ax.scatter(Sx.x, Sx.y, s=10, color='#8d96a3', zorder=3, label='公車站牌')
    direct = Sx[Sx.key.isin(near_keys)]
    ax.scatter(direct.x, direct.y, s=22, color=C_KEEP, zorder=4, label='可一車到 G12 的路線之站牌')
    circles(ax, ['G12'], 500, ec=C_CUT, ls='-'); circles(ax, ['G12'], 800)
    draw_stations(ax, ['G12'])
    ax.plot([], [], color=C_CUT, label='500 m'); ax.plot([], [], color=C_ST, ls='--', label='800 m')
    ax.set_xlabel(''); ax.set_ylabel('')
    ax.legend(loc='lower right', fontsize=9, framealpha=.92)
    ax.set_title('圖3　方案三：G12 蘆興埤——800 m 內約 1,379 位 65 歲以上，500 m 內尖峰每小時僅約 4.2 班\n（候選補強位置，非指定路線；人口為村里面積比例估計）', fontsize=12)
    save(fig, 'fig_s3_g12_gap.png')
    return len(near_keys)


# ---------- 方案四：長路線切短（示意：703） ----------
def fig4():
    ks = [k for k, r in rts.items() if r['sub'] == '703']
    k = ks[0]; line = rts[k]['line']
    cut_st = 'G15'; proj = line.project(Point(sx[cut_st]))
    a, b = substring(line, 0, proj), substring(line, proj, line.length)
    allx = [sx[c][0] for c in codes]; ally = [sx[c][1] for c in codes]
    cx, cy = np.mean(allx), np.mean(ally); half = 9500; bb = box(cx - half, cy - half, cx + half, cy + half)
    fig, axs = plt.subplots(1, 2, figsize=(15, 8))
    for ax, ttl in ((axs[0], f'現況：{rts[k]["short"]} 一條長線（約 {line.length/1000:.1f} km）'), (axs[1], f'方案四示意：在 {cut_st} 切成兩段、站內轉乘')):
        frame(ax, cx, cy, half, ttl); base_lines(ax, net0, bb, skip=[k])
        draw_stations(ax, label=False); draw_stations(ax, [cut_st])
    for l in (line,):
        g = l.intersection(bb)
        for part in ([g] if g.geom_type == 'LineString' else list(g.geoms)): axs[0].plot(*part.xy, color=C_KEEP, lw=2.6, zorder=3)
    for seg, col, lab in ((a, C_KEEP, f'第一段 {a.length/1000:.1f} km'), (b, '#e08a1e', f'第二段 {b.length/1000:.1f} km')):
        g = seg.intersection(bb)
        for part in ([g] if g.geom_type == 'LineString' else list(g.geoms)): axs[1].plot(*part.xy, color=col, lw=3, zorder=3, label=lab)
        axs[1].plot([], [], color=col, lw=3, label=lab) if False else None
    axs[1].scatter(*sx[cut_st], s=260, marker='o', facecolor='none', edgecolor='k', lw=2, zorder=8, label='轉乘點（需班距穩定才可行）')
    axs[1].legend(loc='lower right', fontsize=9, framealpha=.92)
    fig.suptitle('圖4　方案四：長路線切短（以 703 為例的示意，非建議路線；實際切點需看班距變異與轉乘等候）', fontsize=14, y=.97)
    save(fig, 'fig_s4_split_route.png'); return rts[k]['short'], a.length / 1000, b.length / 1000


# ---------- 方案五：GR 實際班距 vs 時刻表（10/21 單日） ----------
def fig6():
    f = os.path.join(ROOT, 'pilot', 'outputs', 'A3_headway_detail.csv')
    h = pd.read_csv(f, encoding='utf-8-sig'); h['time'] = pd.to_datetime(h.time, utc=True).dt.tz_convert('Asia/Taipei')
    g = h[(h.route == 'GR') & (h.station == 'G12')]
    fig, axs = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for ax, dr, nm in ((axs[0], 0, '去程'), (axs[1], 1, '返程')):
        d = g[g.dir == dr].sort_values('time')
        ax.axhspan(0, 15, color='#e6f4ea', zorder=0); ax.text(.01, 16, '市府公開說法：尖峰 10–15 分鐘（綠帶；口徑待驗證）', transform=ax.get_yaxis_transform(), ha='left', fontsize=8, color='#2a7a45', zorder=5, bbox=dict(fc='white', ec='none', alpha=.8, pad=1))
        ax.bar(d.time, d.headway_min, width=pd.Timedelta(minutes=12), color=np.where(d.headway_min > 2 * d.sched_min, C_CUT, C_KEEP), zorder=2)
        ax.step(d.time, d.sched_min, where='mid', color='k', lw=1.5, ls='--', zorder=3, label='時刻表班距（起點發車間隔）')
        ax.set_title(f'GR {nm}（G12 站通過時刻）', fontsize=12); ax.set_xlabel('2026-10-21（週三）'); ax.grid(axis='y', alpha=.3)
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M', tz='Asia/Taipei'))
    axs[0].set_ylabel('實際班距（分鐘）'); axs[0].legend(loc='upper left', fontsize=9)
    from matplotlib.patches import Patch
    axs[1].legend(handles=[plt.Line2D([], [], color='k', ls='--', label='時刻表班距（起點發車間隔）'), Patch(color=C_CUT, label='實際 > 2 倍時刻表'), Patch(color=C_KEEP, label='其他')], loc='upper left', fontsize=9)
    fig.suptitle('圖5　方案五：GR 實際班距與時刻表（單日初步觀察，TDX 歷史資料；不可推論為常態）', fontsize=13, y=1.02)
    save(fig, 'fig_s5_gr_headway.png')


if __name__ == '__main__':
    fig1(); fig2(); n = fig3(); print('G12 direct route-dirs', n); print(fig4()); fig6()
