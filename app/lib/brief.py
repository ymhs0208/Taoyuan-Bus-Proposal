"""首頁用的三個重點。演算法與情境模擬頁的「A＋B 組合」相同（預設參數），不另寫一套數字。"""
from __future__ import annotations

import pandas as pd

from . import data as D, driver as DR, metrics as M

# 與 views/p3_scenario.py 側欄預設值相同
WALK_M = 300
CONN_M = 500
SPEED_KMH = 18.0
SHIFT_H = 8.0


def _direct(ev: dict, code: str) -> float | None:
    per = (ev.get("coverage") or {}).get("per_station") or {}
    row = per.get(code)
    if not row:
        return None
    return float(row["direct"])


def scenario_ab(source: str) -> dict | None:
    """重現情境模擬頁預設的 A＋B：GR 刪除 7 站 500 m 間的平行段，再加上 G14 演算法接駁線。"""
    rts = D.routes(source)
    stg = D.stations()
    if not rts or stg is None or D.isochrones() is None or D.villages() is None:
        return None
    codes = list(stg.code)
    net0 = M.build_network(source, [], [])
    e0 = M.evaluate(net0, WALK_M, CONN_M)
    ov = M.overlap_table(source, CONN_M, D.routes_sig(source))
    rank_keys = list(ov.key) if ov is not None and not ov.empty else []
    gr_keys = [k for k in rank_keys if rts[k]["sub"] == "GR"]
    if not gr_keys:
        gr_keys = [k for k, r in rts.items() if r["sub"] == "GR"]
    mods = [dict(type="drop_parallel", key=k, radius=CONN_M, stations=codes,
                 desc=f"{rts[k]['short']}：刪除 7 站 500 m 間的平行區段") for k in gr_keys]
    pts = M.greedy_feeder(source, "G14", e0, net0, WALK_M) if "G14" in set(codes) else []
    raw_feeders = []
    if pts:
        raw_feeders = [dict(name="G14 接駁線（演算法示意）", station="G14", points=[list(p) for p in pts],
                            loop=True, preset="G14", trips_default=True)]
    trips = D.weekday_trips() if source == "tdx" else {}
    gr_trips = [trips[k] for k in gr_keys if trips.get(k)]
    ft = int(max(gr_trips)) if gr_trips else 0
    feeders = [dict(f, trips=(ft or None)) if f.get("trips_default") else f for f in raw_feeders]
    net1 = M.build_network(source, mods, feeders)
    e1 = M.evaluate(net1, WALK_M, CONN_M)
    speeds = DR.a1_speeds() if source == "tdx" else {}
    ct = DR.corridor_totals(rts, net1, trips, speeds, SPEED_KMH, True, e1["length_km"], feeders)
    gr = []
    ov_ix = ov.set_index("key") if ov is not None and not ov.empty else None
    for k in gr_keys:
        before = rts[k]["line"].length / 1000
        after = float(e1["length_km"].get(k, before))
        overlap_km = share = None
        if ov_ix is not None and k in ov_ix.index:
            overlap_km = float(ov_ix.loc[k, "範圍內長度_km"])
            share = float(ov_ix.loc[k, "長度占比"])
        gr.append(dict(label=str(rts[k]["short"]), before=float(before), after=after,
                       overlap_km=overlap_km, share=share))
    ind_n = ind_nodirect = ind_anystop = None
    csv = D.APP_DIR / "derived" / "A4_industrial_reach.csv"
    if csv.exists():
        idf = pd.read_csv(csv)
        g = idf[idf.nearest_station.astype(str) == "G12"]
        ind_n = int(len(g))
        def _bool(col):
            s = g[col]
            if s.dtype == object:
                return s.astype(str).str.lower().isin(["true", "1", "yes"])
            return s.fillna(False).astype(bool)
        ind_nodirect = int((~_bool("direct_within_R")).sum())
        ind_anystop = int(_bool("stop_within_R").sum())
    return dict(
        speed=SPEED_KMH, shift_h=SHIFT_H, feeder_trips=ft,
        s0_h=float(ct["s0_h"]), s1_h=float(ct["s1_h"]),
        people={c: (_direct(e0, c), _direct(e1, c)) for c in ("G14", "G12", "G15b")},
        gr=gr,
        a1_routes=len([k for k in speeds if k != "_ALL"]),
        ind_n=ind_n, ind_nodirect=ind_nodirect, ind_anystop=ind_anystop,
    )
