"""設計規則檢查：班距可靠度（規則一）、新線長度上限（規則三）、接駁線載客容量，以及 S2a 切短接鐵路站的輔助函式。
全部門檻與車型容量都是【假設，可調】，不是標準；資料缺漏時回報「無法檢查」，不猜值。"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import data as D

RAIL_PAT = re.compile("火車站|車站|總站|轉運站|高鐵")


def reliability() -> pd.DataFrame | None:
    """11_headway.py 的摘要（只留樣本夠的組合）。沒有檔案回傳 None。"""
    S = D.read_csv("outputs/A3_headway_summary.csv")
    if S is None or S.empty:
        return None
    ok = S.sufficient.astype(str).str.lower().isin(["true", "1"])
    return S[ok].copy()


def reliability_thresholds_default(S: pd.DataFrame | None) -> dict:
    cv = round(float(S.cv.median()), 2) if S is not None and len(S) else 0.5
    return dict(cv=min(max(cv, 0.1), 1.5), gap=0.2, bunch=0.1)


def route_gate(S: pd.DataFrame | None, route: str, direction: int, th: dict) -> dict:
    """規則一：該路線方向各站取最差值，與門檻比較。status：ok／fail／nodata。"""
    if S is None:
        return dict(status="nodata", why="沒有班距結果檔")
    g = S[(S.route.astype(str) == str(route)) & (S["dir"] == direction)]
    if g.empty:
        return dict(status="nodata", why="樣本不足或未達 5 個班距，無法檢查")
    cv, gap, bun = float(g.cv.max()), float(g.gap_rate.max()), float(g.bunch_rate.max())
    ok = cv <= th["cv"] and gap <= th["gap"] and bun <= th["bunch"]
    return dict(status="ok" if ok else "fail", cv=cv, gap=gap, bunch=bun, mean_min=float(g.mean_min.median()),
                sched_min=float(g.sched_min.median()), n=int(g.n_headways.sum()),
                why="在門檻內" if ok else "超過門檻：" + "、".join(
                    n for n, bad in (("cv", cv > th["cv"]), ("大間隔", gap > th["gap"]), ("併班", bun > th["bunch"])) if bad))


def length_gate(length_km: float, cap_km: float) -> dict:
    """規則三：新接駁線整圈（或單程）長度上限。長度是點間直線，為下限值；號誌路口數無資料，未檢查。"""
    return dict(ok=length_km <= cap_km, length=length_km, cap=cap_km)


def capacity(veh_cap: int, trips_per_hr: float, beneficiaries: float) -> dict:
    """每小時單向載客上限，以及相當於受益長者的幾成。不假設搭乘率：只說明『多少比例的人同時段搭乘就會滿』。"""
    per_hr = veh_cap * trips_per_hr
    share = per_hr / beneficiaries if beneficiaries > 0 else None
    return dict(per_hr=per_hr, share=share, headway_min=60 / trips_per_hr if trips_per_hr > 0 else None)


def rail_end(stops: pd.DataFrame):
    """路線兩端中，站名含火車站／總站／轉運站／高鐵者：回傳 (索引, 站名)；兩端皆是則取第一端；皆無回傳 None。"""
    s = stops.reset_index(drop=True)
    for i in (0, len(s) - 1):
        if len(s) and RAIL_PAT.search(str(s.name[i])):
            return i, str(s.name[i])
    return None


def s2a_range(stops: pd.DataFrame, sx: float, sy: float):
    """S2a：保留『鐵路端』到『最靠近指定車站的站牌』。回傳 dict(from,to,rail,cut_name,walk_m)；找不到鐵路端回傳 None。"""
    s = stops.reset_index(drop=True)
    r = rail_end(s)
    if r is None or len(s) < 3:
        return None
    ri, rname = r
    d = np.hypot(s.x.values - sx, s.y.values - sy)
    ci = int(np.argmin(d))
    if ci == ri:
        return None
    a, b = (ri, ci) if ri < ci else (ci, ri)
    return dict(**{"from": a, "to": b}, rail=rname, cut_name=str(s.name[ci]), walk_m=float(d[ci]), rail_idx=ri, cut_idx=ci)
