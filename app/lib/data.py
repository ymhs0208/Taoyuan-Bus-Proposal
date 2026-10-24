"""資料載入層（唯讀）。

- 自動尋找試行分析資料夾 pilot/（環境變數 TAOYUAN_PILOT_DIR 優先）。
  路徑以本檔位置推得（app/lib/data.py → 儲存庫根目錄的 pilot/），與程序的工作目錄無關。
  Streamlit Community Cloud 從儲存庫根目錄執行，因此不要改成相對於工作目錄的路徑。
- 所有讀取以「檔案修改時間＋大小」作為快取鍵：另一個程序更新檔案後，重新整理頁面就會讀到最新版本。
- 欄位缺漏或檔案不存在時回傳 None／空表，由頁面顯示「待實測」或「資料尚未產生」，不補任何數字。
- 本模組絕不寫入 pilot/ 資料夾。
"""
from __future__ import annotations

import glob
import gzip
import json
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st
from shapely import wkt
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

APP_DIR = Path(__file__).resolve().parent.parent
CRS_M = 3826  # TWD97 / TM2，單位公尺
DISTS = [300, 500, 800]


# ---------------------------------------------------------------- 路徑與檔案
def pilot_dir() -> Path | None:
    cands = []
    if os.environ.get("TAOYUAN_PILOT_DIR"):
        cands.append(Path(os.environ["TAOYUAN_PILOT_DIR"]))
    cands += [APP_DIR.parent / "pilot", APP_DIR / "pilot", APP_DIR.parent / "pilot_data"]
    for c in cands:
        if (c / "data").is_dir() or (c / "outputs").is_dir():
            return c.resolve()
    return None


def P(rel: str) -> Path | None:
    base = pilot_dir()
    if base is None:
        return None
    p = base / rel
    return p if p.exists() else None


def sig(rel: str) -> str:
    """檔案簽章（用於快取失效）。"""
    p = P(rel)
    if p is None:
        return "missing"
    s = p.stat()
    return f"{s.st_mtime_ns}-{s.st_size}"


def glob_sig(pattern: str) -> tuple:
    base = pilot_dir()
    if base is None:
        return ()
    out = []
    for f in sorted(glob.glob(str(base / pattern))):
        s = os.stat(f)
        out.append((f, s.st_mtime_ns, s.st_size))
    return tuple(out)


def read_text(rel: str) -> str | None:
    p = P(rel)
    if p is None:
        return None
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def first_col(df: pd.DataFrame, names: list[str]):
    for n in names:
        if n in df.columns:
            return n
    return None


@st.cache_data(show_spinner=False)
def _read_csv(rel: str, fsig: str) -> pd.DataFrame | None:
    p = P(rel)
    if p is None:
        return None
    try:
        return pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return None


def read_csv(rel: str) -> pd.DataFrame | None:
    return _read_csv(rel, sig(rel))


# ---------------------------------------------------------------- 車站
@st.cache_data(show_spinner=False)
def _stations(fsig: str) -> gpd.GeoDataFrame | None:
    df = _read_csv("data/stations_green_north.csv", fsig)
    if df is None:
        return None
    lat, lon = first_col(df, ["lat", "PositionLat", "緯度"]), first_col(df, ["lon", "PositionLon", "經度"])
    code, name = first_col(df, ["code", "StationID", "代碼"]), first_col(df, ["name", "StationName", "站名"])
    if not all([lat, lon, code]):
        return None
    out = pd.DataFrame({
        "code": df[code].astype(str),
        "name": df[name].astype(str) if name else "",
        "lat": pd.to_numeric(df[lat], errors="coerce"),
        "lon": pd.to_numeric(df[lon], errors="coerce"),
        "note": df["note"].astype(str) if "note" in df.columns else "",
        "source": df["source"].astype(str) if "source" in df.columns else "",
    }).dropna(subset=["lat", "lon"])
    out["estimated"] = out["note"].str.contains("估計") | out["code"].eq("G15b")
    g = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(out.lon, out.lat), crs=4326).to_crs(CRS_M)
    return g.reset_index(drop=True)


def stations():
    return _stations(sig("data/stations_green_north.csv"))


# ---------------------------------------------------------------- 等時圈與村里
@st.cache_data(show_spinner=False)
def _isochrones(fsig: str):
    p = P("outputs/A2_isochrones.gpkg")
    if p is None:
        return None
    try:
        g = gpd.read_file(p)
    except Exception:
        return None
    if g.crs is None:
        g = g.set_crs(CRS_M)
    g = g.to_crs(CRS_M)
    dcol = first_col(g, ["dist_m", "dist", "distance"])
    ccol = first_col(g, ["code", "station"])
    if not dcol or not ccol:
        return None
    g = g.rename(columns={dcol: "dist_m", ccol: "code"})
    g["dist_m"] = pd.to_numeric(g["dist_m"], errors="coerce").astype("Int64")
    return g[["code", "dist_m", "geometry"]]


def isochrones():
    return _isochrones(sig("outputs/A2_isochrones.gpkg"))


@st.cache_data(show_spinner=False)
def _villages(fsig: str):
    p = P("data/villages_pop65.gpkg")
    if p is None:
        return None
    try:
        v = gpd.read_file(p).to_crs(CRS_M)
    except Exception:
        return None
    if "pop65" not in v.columns:
        return None
    v["pop65"] = pd.to_numeric(v["pop65"], errors="coerce").fillna(0)
    v["pop"] = pd.to_numeric(v.get("pop", 0), errors="coerce").fillna(0)
    v["area"] = v.geometry.area
    return v


def villages():
    return _villages(sig("data/villages_pop65.gpkg"))


# ---------------------------------------------------------------- 公車路線（兩種來源）
SOURCES = {
    "tdx": "TDX 運輸資料流通服務（StopOfRoute＋Shape 實際線型）",
    "pdf": "市府開放平台官方站址表 PDF（站間直線近似）",
}


def available_sources() -> list[str]:
    out = []
    if P("data/tdx/stop_of_route.csv") is not None:
        out.append("tdx")
    if P("data/route_stops_parsed.csv") is not None:
        out.append("pdf")
    return out


def _qc_clean(df: pd.DataFrame) -> pd.DataFrame:
    """與 pilot/scripts/04_overlap.py 相同的 QC：剔除尖刺點、>8 km 跳躍處切開保留最長片段。"""
    df = df.reset_index(drop=True)
    while True:
        xs, ys = df.x.values, df.y.values
        drop = None
        for i in range(1, len(df) - 1):
            d1 = np.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])
            d2 = np.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i])
            d3 = np.hypot(xs[i + 1] - xs[i - 1], ys[i + 1] - ys[i - 1])
            if d1 > 3000 and d2 > 3000 and d3 < 1500:
                drop = i
                break
        if drop is None:
            break
        df = df.drop(index=drop).reset_index(drop=True)
    xs, ys = df.x.values, df.y.values
    cuts = [i + 1 for i in range(len(df) - 1) if np.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) > 8000]
    if cuts:
        b = [0] + cuts + [len(df)]
        parts = [df.iloc[b[k]:b[k + 1]] for k in range(len(b) - 1)]
        df = max(parts, key=len).reset_index(drop=True)
    return df


@st.cache_resource(show_spinner="載入公車路線資料中…")
def _routes(source: str, fsig: str, fsig2: str) -> dict:
    """回傳 {route_key: dict(route, label, desc, dir, stops(DataFrame x,y,name,lat,lon), line(LineString, EPSG:3826), line_kind)}"""
    out = {}
    if source == "tdx":
        s = _read_csv("data/tdx/stop_of_route.csv", fsig)
        if s is None:
            return out
        need = {"SubRouteUID": ["SubRouteUID", "sub_uid"], "route": ["route", "RouteName"], "sub": ["sub", "SubRouteName"],
                "dir": ["dir", "Direction"], "seq": ["seq", "StopSequence"], "name": ["name", "StopName"],
                "lat": ["lat", "PositionLat"], "lon": ["lon", "PositionLon"]}
        cols = {k: first_col(s, v) for k, v in need.items()}
        if not all(cols[k] for k in ["SubRouteUID", "lat", "lon"]):
            return out
        s = pd.DataFrame({k: (s[c] if c else "") for k, c in cols.items()})
        s["dir"] = pd.to_numeric(s["dir"], errors="coerce").fillna(0).astype(int)
        s["seq"] = pd.to_numeric(s["seq"], errors="coerce")
        shapes = {}
        p = P("data/tdx/Shape_Taoyuan.json.gz")
        if p is not None:
            try:
                for rec in json.load(gzip.open(p)):
                    geom = rec.get("Geometry")
                    if not geom:
                        continue
                    try:
                        shapes[(str(rec.get("SubRouteUID")), int(rec.get("Direction", 0) or 0))] = wkt.loads(geom)
                    except Exception:
                        pass
            except Exception:
                shapes = {}
        if shapes:
            shp = gpd.GeoSeries(list(shapes.values()), crs=4326).to_crs(CRS_M)
            shapes = dict(zip(shapes.keys(), shp))
        for (uid, d), df in s.groupby(["SubRouteUID", "dir"], sort=False):
            df = df.sort_values("seq")
            sub = str(df["sub"].iloc[0]) or str(df["route"].iloc[0])
            out_key = f"{uid}-{d}"
            out[out_key] = dict(route=str(df["route"].iloc[0]), sub=sub, dir=int(d), _df=df, shape=shapes.get((str(uid), int(d))))
    else:
        s = _read_csv("data/route_stops_parsed.csv", fsig2)
        if s is None:
            return out
        if not {"route_id", "pattern", "lat", "lon"} <= set(s.columns):
            return out
        s["order"] = pd.to_numeric(s.get("order", s.get("seq")), errors="coerce")
        s = s.rename(columns={"stop_name": "name"})
        if "name" not in s.columns:
            s["name"] = ""
        for (rid, pat), df in s.groupby(["route_id", "pattern"], sort=False):
            df = df.sort_values("order")
            out[f"{rid}-{pat}"] = dict(route=str(df["route"].iloc[0]) if "route" in df else str(rid), sub=str(df["route"].iloc[0]) if "route" in df else str(rid),
                                       dir=int(pat), _df=df, shape=None, ddesc=str(df["ddesc"].iloc[0]) if "ddesc" in df else "")
    # 統一處理：投影、QC、線型
    allpts = []
    for k, r in out.items():
        df = r.pop("_df")
        df = df[pd.to_numeric(df.lat, errors="coerce").between(24.5, 25.4) & pd.to_numeric(df.lon, errors="coerce").between(120.9, 121.6)]
        allpts.append(pd.DataFrame({"key": k, "lat": df.lat.astype(float).values, "lon": df.lon.astype(float).values, "name": df.name.astype(str).values}))
    if not allpts:
        return {}
    A = pd.concat(allpts, ignore_index=True)
    G = gpd.GeoSeries(gpd.points_from_xy(A.lon, A.lat), crs=4326).to_crs(CRS_M)
    A["x"], A["y"] = G.x.values, G.y.values
    final = {}
    for k, df in A.groupby("key", sort=False):
        r = out[k]
        df = df.reset_index(drop=True)
        if source == "pdf":
            df = _qc_clean(df)
        if len(df) < 2:
            continue
        line = r.get("shape")
        kind = "TDX Shape 實際線型"
        if line is None or line.is_empty or line.geom_type != "LineString":
            if line is not None and line.geom_type == "MultiLineString":
                from shapely.ops import linemerge
                m = linemerge(line)
                line = m if m.geom_type == "LineString" else None
            else:
                line = None
        if line is None:
            line = LineString(list(zip(df.x, df.y)))
            kind = "站間直線近似"
        dirname = {0: "去程", 1: "返程"}.get(r["dir"], f"方向{r['dir']}") if source == "tdx" else f"型態{r['dir']}"
        frm, to = df.name.iloc[0], df.name.iloc[-1]
        final[k] = dict(key=k, route=r["route"], sub=r["sub"], dir=r["dir"],
                        label=f"{r['sub']}｜{frm}→{to}（{dirname}）", short=f"{r['sub']}（{dirname}）",
                        stops=df[["name", "lat", "lon", "x", "y"]], line=line, line_kind=kind)
    return final


def routes(source: str) -> dict:
    return _routes(source, sig("data/tdx/stop_of_route.csv") + sig("data/tdx/Shape_Taoyuan.json.gz"), sig("data/route_stops_parsed.csv"))


def current_source() -> str | None:
    av = available_sources()
    if not av:
        return None
    s = st.session_state.get("source")
    return s if s in av else av[0]


def stop_positions(rts: dict) -> pd.DataFrame:
    """所有站牌列（含路線），加上 5 m 網格去重鍵。"""
    rows = []
    for k, r in rts.items():
        d = r["stops"]
        rows.append(pd.DataFrame({"key": k, "route": r["sub"], "name": d.name.values, "x": d.x.values, "y": d.y.values,
                                  "lat": d.lat.values, "lon": d.lon.values}))
    if not rows:
        return pd.DataFrame(columns=["key", "route", "name", "x", "y", "lat", "lon", "kx", "ky"])
    S = pd.concat(rows, ignore_index=True)
    S["kx"] = (S.x / 5).round().astype(int)
    S["ky"] = (S.y / 5).round().astype(int)
    return S


# ---------------------------------------------------------------- A1 即時資料
def a1_files() -> tuple:
    return glob_sig("data/a1/a1_*.csv*")


@st.cache_data(show_spinner="讀取即時動態資料中…")
def _a1(files: tuple) -> pd.DataFrame | None:
    dfs = []
    for f, *_ in files:
        try:
            dfs.append(pd.read_csv(f, low_memory=False, on_bad_lines="skip"))
        except Exception:
            # 收集器可能正在寫入同一檔：略過讀不到的檔案，不中斷
            continue
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


def a1_raw():
    f = a1_files()
    return _a1(f) if f else None


def outputs_list() -> list[tuple[str, str, int]]:
    base = pilot_dir()
    if base is None:
        return []
    out = []
    for f in sorted(glob.glob(str(base / "outputs" / "*"))):
        s = os.stat(f)
        out.append((os.path.basename(f), pd.Timestamp(s.st_mtime, unit="s", tz="UTC").tz_convert("Asia/Taipei").strftime("%Y-%m-%d %H:%M"), s.st_size))
    return out


def mtime_str(rel: str) -> str | None:
    p = P(rel)
    if p is None:
        return None
    return pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC").tz_convert("Asia/Taipei").strftime("%Y-%m-%d %H:%M")


def routes_sig(source: str) -> str:
    if source == "tdx":
        return sig("data/tdx/stop_of_route.csv") + sig("data/tdx/Shape_Taoyuan.json.gz")
    return sig("data/route_stops_parsed.csv")


@st.cache_data(show_spinner=False)
def _weekday_trips(fsig: str, csig: str) -> dict:
    """平日（星期三有營運）班次數，鍵為 TDX 'SubRouteUID-Direction'。
    優先由 data/tdx/Schedule_*.json.gz 計算（定義同 pilot/scripts/10_frequency.py），否則讀 outputs 中含 weekday_trips 的排行檔。"""
    out = {}
    base = pilot_dir()
    if base is None:
        return out
    for f in sorted(glob.glob(str(base / "data" / "tdx" / "Schedule_*.json.gz"))):
        try:
            for s in json.load(gzip.open(f)):
                key = f"{s.get('SubRouteUID')}-{int(s.get('Direction', 0) or 0)}"
                seen = set()
                for t in s.get("Timetables") or []:
                    if not (t.get("ServiceDay") or {}).get("Wednesday"):
                        continue
                    stt = t.get("StopTimes") or []
                    if not stt:
                        continue
                    seen.add((t.get("TripID"), stt[0].get("DepartureTime") or stt[0].get("ArrivalTime")))
                if seen or key not in out:
                    out[key] = out.get(key, 0) + len(seen)
        except Exception:
            continue
    if out:
        return out
    for f in sorted(glob.glob(str(base / "outputs" / "*ranking*.csv"))):
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
        except Exception:
            continue
        if {"SubRouteUID", "dir", "weekday_trips"} <= set(df.columns):
            for u, d, n in zip(df.SubRouteUID, df.dir, pd.to_numeric(df.weekday_trips, errors="coerce")):
                if pd.notna(n):
                    out[f"{u}-{int(d)}"] = int(n)
    return out


def weekday_trips() -> dict:
    return _weekday_trips(str(glob_sig("data/tdx/Schedule_*.json.gz")), str(glob_sig("outputs/*ranking*.csv")))
