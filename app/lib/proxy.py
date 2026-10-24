"""移工通勤代理指標：產業用地（OSM landuse=industrial ＋ 經濟部產業園區管理局「產業園區範圍圖」）。
代理指標 ≠ 移工人口：不知道宿舍位置、雇用人數、班別時間；只代表「可能有通勤需求的就業地點」。
資料存於 app/derived/（由 tools/build_industrial.py 與 tools/build_proxy.py 產生），不寫入 pilot/。"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.ops import unary_union

from . import data as D

DERIVED = D.APP_DIR / "derived"
NEAR_R = 1500  # 走廊範圍：任一站 1,500 m 內


def _sig(p: Path):
    return f"{p.stat().st_mtime_ns}-{p.stat().st_size}" if p.exists() else "missing"


def industrial_sig() -> str:
    return _sig(DERIVED / "A4_industrial_osm.gpkg") + _sig(DERIVED / "A4_industrial_official.gpkg")


def load_industrial() -> gpd.GeoDataFrame | None:
    parts = []
    p = DERIVED / "A4_industrial_osm.gpkg"
    if p.exists():
        g = gpd.read_file(p).to_crs(D.CRS_M)
        g["source"] = "OSM landuse=industrial"
        g["name"] = g.get("name", "").fillna("")
        parts.append(g[["source", "name", "geometry"]])
    p = DERIVED / "A4_industrial_official.gpkg"
    if p.exists():
        g = gpd.read_file(p).to_crs(D.CRS_M)
        g["source"] = "產管局產業園區範圍圖"
        parts.append(g[["source", "name", "geometry"]])
    if not parts:
        return None
    g = pd.concat(parts, ignore_index=True)
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=D.CRS_M)
    g["geometry"] = g.geometry.buffer(0)
    g["area_ha"] = (g.geometry.area / 1e4).round(2)
    return g[g.area_ha > 0].reset_index(drop=True)


def station_table(ind, iso) -> pd.DataFrame:
    """各站步行等時圈內的產業用地面積（兩來源聯集，不重複計算）。"""
    allu = unary_union(list(ind.geometry))
    rows = []
    for _, g in iso.iterrows():
        poly = g.geometry
        inter = allu.intersection(poly)
        hits = ind[ind.intersects(poly)]
        rows.append(dict(code=g.code, dist_m=int(g.dist_m), ind_ha=round(inter.area / 1e4, 2),
                         ind_share=round(inter.area / poly.area, 3) if poly.area else 0.0,
                         n_polys=len(hits), names="、".join(sorted({n for n in hits.name if n})[:6])))
    return pd.DataFrame(rows)


def reach_table(ind, stations, stops: pd.DataFrame, conn_by_station: dict, R=300) -> tuple[pd.DataFrame, dict]:
    """走廊內（任一站 1,500 m）每塊產業用地：最近站牌距離、R m 內有無任何公車站牌、
    有無『可一車直達最近綠線車站』的路線站牌（該路線有站牌在最近車站 500 m 步行等時圈內）。"""
    corr = unary_union([g.buffer(NEAR_R) for g in stations.geometry])
    sel = ind[ind.intersects(corr)].copy()
    S = stops.drop_duplicates(["kx", "ky"])
    pts_all = shapely.points(S.x.values, S.y.values)
    tree_a = shapely.STRtree(pts_all)
    trees = {}
    for code, keys in conn_by_station.items():
        Sc = stops[stops.key.isin(keys)].drop_duplicates(["kx", "ky"])
        pc = shapely.points(Sc.x.values, Sc.y.values)
        trees[code] = (pc, shapely.STRtree(pc), Sc)
    out, direct_parts, any_parts, all_parts = [], [], [], []
    for i, r in sel.iterrows():
        g = r.geometry.intersection(corr)
        if g.is_empty:
            continue
        ia = tree_a.query(g, predicate="dwithin", distance=R)
        j = tree_a.nearest(g)
        dmin = float(g.distance(pts_all[j])) if j is not None else np.nan
        dst = [float(g.distance(s)) for s in stations.geometry]
        k = int(np.argmin(dst))
        code = stations.code.iloc[k]
        pc, tc, Sc = trees.get(code, (np.array([]), None, None))
        ic = tc.query(g, predicate="dwithin", distance=R) if tc is not None and len(pc) else []
        out.append(dict(source=r.source, name=r["name"] or "（未命名）", area_ha=round(g.area / 1e4, 2),
                        nearest_station=code, station_dist_m=round(dst[k]), nearest_stop_m=round(dmin),
                        stop_within_R=len(ia) > 0, direct_within_R=len(ic) > 0,
                        direct_routes=" ".join(sorted(set(Sc.route.iloc[list(ic)].astype(str))))[:120] if len(ic) else ""))
        all_parts.append(g)
        if len(ia):
            any_parts.append(g.intersection(unary_union(shapely.buffer(pts_all[ia], R))))
        if len(ic):
            direct_parts.append(g.intersection(unary_union(shapely.buffer(pc[ic], R))))
    T = pd.DataFrame(out)
    U = lambda parts: unary_union(parts).area / 1e4 if parts else 0.0
    summ = dict(total_ha=U(all_parts), any_ha=U(any_parts), direct_ha=U(direct_parts))
    return T, summ


def direct_area_ha(ind_union_corr, stop_xy: np.ndarray, R=300) -> float:
    if ind_union_corr is None or ind_union_corr.is_empty or len(stop_xy) == 0:
        return 0.0
    pts = shapely.points(stop_xy[:, 0], stop_xy[:, 1])
    pts = pts[shapely.intersects(pts, ind_union_corr.buffer(R))]
    if len(pts) == 0:
        return 0.0
    return ind_union_corr.intersection(unary_union(shapely.buffer(pts, R))).area / 1e4
