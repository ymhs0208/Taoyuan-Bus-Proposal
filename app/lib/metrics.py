"""所有指標都在這裡由資料即時計算，不含任何寫死的結果數字。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
import streamlit as st
from shapely.geometry import LineString, Point, MultiLineString
from shapely.ops import substring, unary_union

from . import data as D

STUDY_R = 1500  # 情境模擬人口分析範圍：各站 1,500 m 圓形聯集
GRID = 25       # 人口格點（m）


# ---------------------------------------------------------------- 分析一：重疊
@st.cache_data(show_spinner="計算路線重疊指標中…")
def overlap_table(source: str, radius: int, rsig: str) -> pd.DataFrame:
    rts = D.routes(source)
    stg = D.stations()
    if not rts or stg is None:
        return pd.DataFrame()
    buf = unary_union([g.buffer(radius) for g in stg.geometry])
    SX, SY, codes = stg.geometry.x.values, stg.geometry.y.values, stg.code.values
    rows = []
    for k, r in rts.items():
        line, s = r["line"], r["stops"]
        L = line.length
        Lin = line.intersection(buf).length
        dd = np.hypot(s.x.values[:, None] - SX[None, :], s.y.values[:, None] - SY[None, :])
        inside = (dd <= radius).any(axis=1)
        touched = [c for j, c in enumerate(codes) if (dd[:, j] <= radius).any()]
        rows.append(dict(key=k, 路線=r["sub"], 方向=r["short"], 起訖=f"{s.name.iloc[0]}→{s.name.iloc[-1]}", 站數=len(s),
                         全長_km=round(L / 1000, 2), 範圍內長度_km=round(Lin / 1000, 2),
                         長度占比=round(Lin / L, 3) if L else 0.0,
                         範圍內站牌=int(inside.sum()), 站牌占比=round(inside.mean(), 3),
                         觸及車站數=len(touched), 觸及車站=" ".join(touched), 線型=r["line_kind"]))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[df.範圍內站牌 > 0].sort_values(["範圍內長度_km", "長度占比"], ascending=False).reset_index(drop=True)
    df.insert(0, "排名", range(1, len(df) + 1))
    return df


# ---------------------------------------------------------------- 分析二：等時圈
@st.cache_data(show_spinner="計算等時圈指標中…")
def access_table(source: str, rsig: str, isig: str, vsig: str) -> pd.DataFrame:
    rts = D.routes(source)
    iso = D.isochrones()
    vil = D.villages()
    stg = D.stations()
    if iso is None or stg is None:
        return pd.DataFrame()
    S = D.stop_positions(rts)
    rows = []
    for _, g in iso.iterrows():
        poly = g.geometry
        m = shapely.contains_xy(poly, S.x.values, S.y.values) if len(S) else np.array([], bool)
        inside = S[m]
        uniq = inside.drop_duplicates(["kx", "ky"])
        rts_in = sorted(set(inside.route.astype(str)))
        p65 = pop = np.nan
        if vil is not None:
            inter = gpd.overlay(vil[["pop", "pop65", "area", "geometry"]], gpd.GeoDataFrame(geometry=[poly], crs=D.CRS_M), how="intersection")
            w = inter.geometry.area / inter["area"]
            p65, pop = float((inter.pop65 * w).sum()), float((inter["pop"] * w).sum())
        nm = stg.set_index("code").name.get(g.code, "")
        rows.append(dict(code=g.code, name=nm, dist_m=int(g.dist_m), stop_positions=len(uniq), stop_rows=len(inside),
                         n_routes=len(rts_in), routes=" ".join(rts_in), pop_est=round(pop) if pop == pop else None,
                         pop65_est=round(p65) if p65 == p65 else None, iso_area_ha=round(poly.area / 1e4, 1)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 人口格點（情境用）
@st.cache_resource(show_spinner="建立 65+ 人口格點中…")
def pop_grid(vsig: str, ssig: str):
    """把村里 65+ 人口以面積比例均分到 25 m 格點（等同面積加權法），範圍：各站 1,500 m 圓形聯集。"""
    vil, stg = D.villages(), D.stations()
    if vil is None or stg is None:
        return None
    study = unary_union([g.buffer(STUDY_R) for g in stg.geometry])
    x0, y0, x1, y1 = study.bounds
    xs = np.arange(x0 + GRID / 2, x1, GRID)
    ys = np.arange(y0 + GRID / 2, y1, GRID)
    X, Y = np.meshgrid(xs, ys)
    X, Y = X.ravel(), Y.ravel()
    m = shapely.contains_xy(study, X, Y)
    X, Y = X[m], Y[m]
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(X, Y), crs=D.CRS_M)
    j = gpd.sjoin(pts, vil[["pop65", "area", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    w = (j["pop65"] / j["area"] * GRID * GRID).fillna(0).values
    st_idx = {}
    for _, s in stg.iterrows():
        st_idx[s.code] = np.hypot(X - s.geometry.x, Y - s.geometry.y) <= STUDY_R
    return dict(x=X, y=Y, w=w, study=study, per_station=st_idx, total=float(w.sum()))


def covered_mask(grid, sx, sy, R):
    """格點是否在任一站牌 R m 直線距離內。"""
    cov = np.zeros(len(grid["x"]), bool)
    if len(sx) == 0:
        return cov
    # 只取研究範圍附近的站牌
    x0, y0, x1, y1 = grid["study"].bounds
    k = (sx > x0 - R) & (sx < x1 + R) & (sy > y0 - R) & (sy < y1 + R)
    sx, sy = sx[k], sy[k]
    R2 = R * R
    for i in range(0, len(sx), 200):
        dx = grid["x"][:, None] - sx[None, i:i + 200]
        dy = grid["y"][:, None] - sy[None, i:i + 200]
        cov |= ((dx * dx + dy * dy) <= R2).any(axis=1)
    return cov


# ---------------------------------------------------------------- 情境引擎
def monotone_positions(line: LineString, xs, ys):
    """沿線依序投影站牌（不回頭），回傳各站在線上的里程（m）。"""
    pos, out, L = 0.0, [], line.length
    for x, y in zip(xs, ys):
        rest = substring(line, pos, L) if pos < L else Point(line.coords[-1])
        d = pos + (rest.project(Point(x, y)) if rest.geom_type == "LineString" else 0.0)
        out.append(d)
        pos = d
    return np.array(out)


def apply_mod(r: dict, mod: dict, stg) -> dict | None:
    """回傳修改後路線 dict（stops, lines[list], length）；None 表示刪除。"""
    s, line = r["stops"].reset_index(drop=True), r["line"]
    if mod["type"] == "remove":
        return None
    pos = monotone_positions(line, s.x.values, s.y.values)
    if mod["type"] == "keep_range":
        a, b = int(mod["from"]), int(mod["to"])
        a, b = max(0, min(a, b)), min(len(s) - 1, max(a, b))
        keep = s.iloc[a:b + 1]
        if a == 0 and b == len(s) - 1:
            return dict(stops=s, lines=[line], removed_idx=[])
        seg = substring(line, pos[a], pos[b]) if pos[b] > pos[a] else LineString(list(zip(keep.x, keep.y))) if len(keep) > 1 else None
        lines = [seg] if seg is not None and seg.length > 0 else []
        return dict(stops=keep, lines=lines, removed_idx=[i for i in range(len(s)) if i < a or i > b])
    if mod["type"] == "drop_parallel":
        R = float(mod["radius"])
        sel = stg[stg.code.isin(mod["stations"])]
        if sel.empty:
            return dict(stops=s, lines=[line], removed_idx=[])
        dd = np.hypot(s.x.values[:, None] - sel.geometry.x.values[None, :], s.y.values[:, None] - sel.geometry.y.values[None, :])
        near = np.where((dd <= R).any(axis=1))[0]
        if len(near) < 2:
            return dict(stops=s, lines=[line], removed_idx=[])
        i0, i1 = near.min(), near.max()
        keep_idx = list(range(0, i0 + 1)) + list(range(i1, len(s)))
        lines = []
        if pos[i0] > 0:
            lines.append(substring(line, 0, pos[i0]))
        if pos[i1] < line.length and i1 < len(s) - 1:
            lines.append(substring(line, pos[i1], line.length))
        lines = [l for l in lines if l.length > 1]
        return dict(stops=s.iloc[keep_idx], lines=lines, removed_idx=list(range(i0 + 1, i1)))
    return dict(stops=s, lines=[line], removed_idx=[])


def terminal_point(code: str):
    """接駁線車站端點：車站點位若不在該站 300 m 步行等時圈內（車站點距最近路網節點較遠時），
    改用等時圈上離車站點最近的位置，代表「車站旁可步行抵達的路邊」。"""
    from shapely.ops import nearest_points
    stg, iso = D.stations(), D.isochrones()
    p = stg[stg.code == code].geometry.iloc[0]
    if iso is not None:
        g = iso[(iso.code == code) & (iso.dist_m == 300)]
        if len(g) and not g.geometry.iloc[0].contains(p):
            q = nearest_points(g.geometry.iloc[0].buffer(-2), p)[0]
            return float(q.x), float(q.y)
    return float(p.x), float(p.y)


def feeder_route(f: dict, stg) -> dict:
    """接駁線：車站端點 → 依序經過選定點 →（可選）回到車站。線型為點間直線（下限值）。"""
    srow = stg[stg.code == f["station"]].iloc[0]
    tx, ty = terminal_point(srow.code)
    pts = [(tx, ty, f"{srow.code} {srow['name']}（接駁端點）")] + [tuple(p) for p in f["points"]]
    coords = [(p[0], p[1]) for p in pts]
    if f.get("loop") and len(coords) > 1:
        coords = coords + [coords[0]]
    line = LineString(coords) if len(coords) > 1 else None
    stops = pd.DataFrame({"name": [p[2] for p in pts], "x": [p[0] for p in pts], "y": [p[1] for p in pts]})
    return dict(stops=stops, lines=[line] if line is not None else [], removed_idx=[])


def nn_order(sx, sy, pts):
    """最近鄰排序：從車站出發，每次走到最近的下一點。"""
    rest = list(pts)
    out, cx, cy = [], sx, sy
    while rest:
        j = int(np.argmin([np.hypot(p[0] - cx, p[1] - cy) for p in rest]))
        p = rest.pop(j)
        out.append(p)
        cx, cy = p[0], p[1]
    return out


def two_opt(sx, sy, pts, loop=True):
    """2-opt 改善停靠順序（減少交叉、縮短總長），起點固定為車站。"""
    P = [(sx, sy)] + [(p[0], p[1]) for p in pts]
    order = list(range(len(P)))

    def length(o):
        seq = o + ([o[0]] if loop else [])
        return sum(np.hypot(P[seq[i]][0] - P[seq[i + 1]][0], P[seq[i]][1] - P[seq[i + 1]][1]) for i in range(len(seq) - 1))

    best, improved = length(order), True
    while improved:
        improved = False
        for i in range(1, len(order) - 1):
            for j in range(i + 1, len(order)):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                L = length(cand)
                if L < best - 1e-6:
                    order, best, improved = cand, L, True
    return [pts[k - 1] for k in order[1:]]


def build_network(source: str, mods: list, feeders: list) -> dict:
    """回傳 {key: dict(stops(x,y,name), lines, label, modified, kind)}，包含所有路線（未修改者照原樣）。"""
    rts, stg = D.routes(source), D.stations()
    net = {}
    modmap = {}
    for m in mods:
        modmap[m["key"]] = m  # 同一路線以最後一次修改為準
    for k, r in rts.items():
        if k in modmap:
            res = apply_mod(r, modmap[k], stg)
            if res is None:
                continue
            net[k] = dict(stops=res["stops"], lines=res["lines"], label=r["label"], route=r["sub"], modified=True, kind="modified")
        else:
            net[k] = dict(stops=r["stops"], lines=[r["line"]], label=r["label"], route=r["sub"], modified=False, kind="base")
    for i, f in enumerate(feeders):
        if f["station"] not in set(stg.code):
            continue
        res = feeder_route(f, stg)
        net[f"FEEDER-{i}"] = dict(stops=res["stops"], lines=res["lines"], label=f["name"], route=f["name"], modified=True, kind="feeder")
    return net


def evaluate(net: dict, R: int, conn_dist: int = 500) -> dict:
    """計算情境指標。
    - 各站 300/500/800 m 步行等時圈內：有公車停靠之站牌位置數（5 m 去重）、路線數
    - 「直達綠線路線」：任一站牌落在任一車站 conn_dist m 步行等時圈內的路線
    - 65+ 覆蓋：研究範圍內，距「直達綠線路線」站牌 R m（直線）以內的 65+ 人口（格點面積加權）；另計任一路線
    """
    stg, iso = D.stations(), D.isochrones()
    grid = pop_grid(D.sig("data/villages_pop65.gpkg"), D.sig("data/stations_green_north.csv"))
    rows = []
    for k, r in net.items():
        s = r["stops"]
        if len(s):
            rows.append(pd.DataFrame({"key": k, "route": r["route"], "x": s.x.values, "y": s.y.values}))
    S = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["key", "route", "x", "y"])
    S["kx"] = (S.x.astype(float) / 5).round().astype(int)
    S["ky"] = (S.y.astype(float) / 5).round().astype(int)
    out = {"station": [], "coverage": {}, "conn_keys": set(), "conn_by_station": {}}
    conn_keys, conn_by = set(), {}
    if iso is not None:
        xs, ys = S.x.values.astype(float), S.y.values.astype(float)
        for code in stg.code:
            g = iso[(iso.code == code) & (iso.dist_m == conn_dist)]
            if len(g) and len(S):
                m = shapely.contains_xy(g.geometry.iloc[0], xs, ys)
                conn_by[code] = set(S.key[m])
                conn_keys |= conn_by[code]
        for _, g in iso.iterrows():
            m = shapely.contains_xy(g.geometry, xs, ys) if len(S) else np.array([], bool)
            ins = S[m]
            out["station"].append(dict(code=g.code, dist_m=int(g.dist_m), stops=int(ins[["kx", "ky"]].drop_duplicates().shape[0]),
                                       routes=int(ins.route.nunique()), route_list=" ".join(sorted(set(ins.route.astype(str))))))
    out["conn_keys"], out["conn_by_station"] = conn_keys, conn_by
    if grid is not None:
        Sc = S[S.key.isin(conn_keys)].drop_duplicates(["kx", "ky"])
        Sa = S.drop_duplicates(["kx", "ky"])
        cov_c = covered_mask(grid, Sc.x.values.astype(float), Sc.y.values.astype(float), R)
        cov_a = covered_mask(grid, Sa.x.values.astype(float), Sa.y.values.astype(float), R)
        per = {}
        for code, ix in grid["per_station"].items():
            Ss = S[S.key.isin(conn_by.get(code, set()))].drop_duplicates(["kx", "ky"])
            sub = dict(x=grid["x"][ix], y=grid["y"][ix], study=grid["study"])
            ms = covered_mask(sub, Ss.x.values.astype(float), Ss.y.values.astype(float), R)
            full = np.zeros(len(grid["x"]), bool)
            full[np.where(ix)[0][ms]] = True
            per[code] = dict(total=float(grid["w"][ix].sum()), direct=float(grid["w"][full].sum()),
                             any=float(grid["w"][ix & cov_a].sum()), mask=full)
        out["coverage"] = dict(total=grid["total"], conn=float(grid["w"][cov_c].sum()), any=float(grid["w"][cov_a].sum()),
                               mask_conn=cov_c, mask_any=cov_a, per_station=per)
    out["length_km"] = {k: sum(l.length for l in r["lines"] if l is not None) / 1000 for k, r in net.items() if r["modified"]}
    return out


def greedy_feeder(source: str, station: str, base_eval: dict, net0: dict, R: int, rmin=300, rmax=1500, k=6) -> list:
    """預設接駁線（演算法示意）：在車站 rmin–rmax m 範圍內的既有站牌中，
    以貪婪法逐一挑選「能新增最多尚未能一車直達本站之 65+ 人口」的站牌（最多 k 個），再以最近鄰＋2-opt 排序串接。"""
    stg = D.stations()
    grid = pop_grid(D.sig("data/villages_pop65.gpkg"), D.sig("data/stations_green_north.csv"))
    if grid is None or stg is None:
        return []
    srow = stg[stg.code == station].iloc[0]
    sx, sy = srow.geometry.x, srow.geometry.y
    S = D.stop_positions({kk: dict(sub=v["route"], stops=v["stops"].assign(lat=0.0, lon=0.0) if "lat" not in v["stops"] else v["stops"]) for kk, v in net0.items()})
    S = S.drop_duplicates(["kx", "ky"])
    d = np.hypot(S.x - sx, S.y - sy)
    C = S[(d >= rmin) & (d <= rmax)].reset_index(drop=True)
    if C.empty:
        return []
    covered = base_eval["coverage"]["per_station"][station]["mask"].copy()
    near = grid["per_station"][station]
    gx, gy, gw = grid["x"][near], grid["y"][near], grid["w"][near]
    cov = covered[near]
    pick = []
    R2 = R * R
    M = ((gx[:, None] - C.x.values[None, :]) ** 2 + (gy[:, None] - C.y.values[None, :]) ** 2) <= R2
    for _ in range(k):
        gain = ((M & ~cov[:, None]) * gw[:, None]).sum(axis=0)
        j = int(np.argmax(gain))
        if gain[j] <= 0.5:
            break
        pick.append((float(C.x[j]), float(C.y[j]), str(C.name[j])))
        cov |= M[:, j]
        M[:, j] = False
    return two_opt(sx, sy, nn_order(sx, sy, pick), loop=True)
