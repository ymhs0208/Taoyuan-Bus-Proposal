"""公平比較接駁候選線。人口是潛在覆蓋，時間是明示假設下的到站模型，不是旅次預測。"""
from __future__ import annotations

import numpy as np
import shapely
import streamlit as st

from . import data as D, metrics as M


def population_changes(before, after, code, weights):
    """新增目的站服務分成互斥兩組；全廊帶首次服務及流失另以聯集計算。"""
    b, a = before["coverage"], after["coverage"]
    gain = a["per_station"][code]["mask"] & ~b["per_station"][code]["mask"]
    total = lambda mask: float(weights[mask].sum())
    return dict(
        first=total(gain & ~b["mask_conn"]),
        choice=total(gain & b["mask_conn"]),
        target_gain=total(gain),
        new_any=total(a["mask_conn"] & ~b["mask_conn"]),
        lost_any=total(b["mask_conn"] & ~a["mask_conn"]),
        net_any=float(a["conn"] - b["conn"]),
    )


def cycle_minutes(length_km, stops, speed, road_factor, dwell, layover):
    return length_km * road_factor / speed * 60 + stops * dwell + layover


def allocation(cycle_min, mode, trips, hours):
    count = int(trips) if mode == "相同班次" else int(np.floor(hours * 60 / cycle_min))
    return count, count * cycle_min / 60


def best_access(x, y, station_xy, options, walk_kmh, walk_limit, rail_headway):
    """固定同一目標站、同一人口群；在全程步行與有方向的單一公車中選最短時間。

    options=(上車x, 上車y, 期望候車分, 車內分, 下車至車站步行m)。
    不合併不同目的地路線頻率；沒有班表的公車不參與時間模型。
    """
    walking = np.hypot(x - station_xy[0], y - station_xy[1]) / (walk_kmh * 1000 / 60)
    n = len(x)
    result = dict(walk=walking.copy(), interchange_walk=np.zeros(n), wait=np.zeros(n), ride=np.zeros(n),
                  transfer=np.full(n, rail_headway / 2), feeder=np.zeros(n, bool))
    best = walking + rail_headway / 2
    for sx, sy, wait, ride, exit_walk, feeder in options:
        distance = np.hypot(x - sx, y - sy)
        wm = (distance + exit_walk) / (walk_kmh * 1000 / 60)
        total = wm + wait + ride + rail_headway / 2
        take = (distance <= walk_limit) & (total < best)
        best[take] = total[take]
        for key, value in [("walk", distance / (walk_kmh * 1000 / 60)),
                           ("interchange_walk", exit_walk / (walk_kmh * 1000 / 60)), ("wait", wait), ("ride", ride),
                           ("transfer", rail_headway / 2), ("feeder", feeder)]:
            result[key][take] = value[take] if isinstance(value, np.ndarray) else value
    result["total"] = best
    return result


@st.cache_resource(max_entries=12, show_spinner="建立有方向的到站時間模型…")
def baseline_time(source, rsig, isig, vsig, ssig, schedule_sig, code,
                  walk_kmh, walk_limit, conn, speed, service_hours, rail_headway):
    rts, stations, iso = D.routes(source), D.stations(), D.isochrones()
    grid = M.pop_grid(vsig, ssig)
    ix = grid["per_station"][code] & (grid["w"] > 0)
    x, y, weights = grid["x"][ix], grid["y"][ix], grid["w"][ix]
    station = stations[stations.code == code].geometry.iloc[0]
    poly = iso[(iso.code == code) & (iso.dist_m == conn)].geometry.iloc[0]
    trips = D.weekday_trips()
    options = []
    for key, route in rts.items():
        count = trips.get(key)
        if not count or count <= 0:
            continue
        stops = route["stops"].reset_index(drop=True)
        alight = np.flatnonzero(shapely.contains_xy(poly, stops.x.values, stops.y.values))
        if not len(alight):
            continue
        positions = M.monotone_positions(route["line"], stops.x.values, stops.y.values)
        # An alighting stop must occur after the boarding stop in this direction.
        for i in range(int(alight.max())):
            row = stops.iloc[i]
            if not ((np.hypot(x - row.x, y - row.y) <= walk_limit).any()):
                continue
            exits = alight[alight > i]
            exit_walk = np.hypot(stops.x.values[exits] - station.x, stops.y.values[exits] - station.y)
            rides = (positions[exits] - positions[i]) / (speed * 1000 / 60)
            j = int(np.argmin(rides + exit_walk / (walk_kmh * 1000 / 60)))
            options.append((row.x, row.y, service_hours * 60 / count / 2,
                            float(rides[j]), float(exit_walk[j]), False))
    baseline = best_access(x, y, (station.x, station.y), options, walk_kmh, walk_limit, rail_headway)
    return dict(x=x, y=y, weights=weights, station=(station.x, station.y), baseline=baseline)


def time_changes(profile, feeder, length, count, walk_kmh, walk_limit, speed,
                 road_factor, dwell, service_hours, rail_headway):
    baseline = profile["baseline"]
    if count <= 0:
        return dict(improved=0.0, mean_saved=0.0, components=[], users=0.0, feeder_components=[])
    route = M.feeder_route(feeder, D.stations())
    stops = route["stops"]
    xy = stops[["x", "y"]].to_numpy()
    along = np.r_[0.0, np.cumsum(np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1])))]
    terminal_walk = np.hypot(xy[0, 0] - profile["station"][0], xy[0, 1] - profile["station"][1])
    wait = service_hours * 60 / count / 2
    options = []
    for i in range(1, len(stops)):
        # One-way circular feeder returns to the station after visiting the remaining stops.
        ride = (length * 1000 - along[i]) * road_factor / (speed * 1000 / 60) + (len(stops) - i) * dwell
        options.append((xy[i, 0], xy[i, 1], wait, ride, terminal_walk, True))
    candidate = best_access(profile["x"], profile["y"], profile["station"], options,
                            walk_kmh, walk_limit, rail_headway)
    # Adding an option never forces baseline passengers to switch.
    use = candidate["total"] < baseline["total"] - 1e-9
    after = {k: np.where(use, candidate[k], baseline[k]) for k in baseline}
    weights = profile["weights"]
    improved = baseline["total"] - after["total"] >= 1.0
    total = weights[improved].sum()
    users = weights[use].sum()
    component_rows = []
    for label, key in [("起點步行", "walk"), ("公車候車", "wait"), ("公車車內", "ride"),
                       ("轉乘步行", "interchange_walk"), ("捷運候車", "transfer"), ("到站並候車合計", "total")]:
        a = float(np.average(baseline[key][improved], weights=weights[improved])) if total else None
        b = float(np.average(after[key][improved], weights=weights[improved])) if total else None
        component_rows.append(dict(項目=label, 現況分鐘=a, 改後分鐘=b, 變化分鐘=b-a if a is not None else None))
    return dict(improved=float(total), users=float(users),
                mean_saved=float(np.average((baseline["total"] - after["total"])[improved], weights=weights[improved])) if total else 0.0,
                components=component_rows,
                feeder_components=[dict(站牌=str(stops.iloc[i]["name"]), 公車候車分鐘=wait,
                                        車內至車站分鐘=float(opt[3]), 轉乘步行分鐘=float(opt[4] / (walk_kmh * 1000 / 60)))
                                   for i, opt in enumerate(options, start=1)])


def recommend(rows, objective):
    # At least half a person/hour separates candidates; smaller differences are model ties.
    # If neither candidate reaches half a previously unserved resident, use additional
    # destination choices as a declared secondary objective, never call them new users.
    first_tie = all(r["first"] < 0.5 for r in rows)
    def score(row):
        if objective == "補服務空白優先":
            return row["choice_per_hour"] if first_tie else row["first_per_hour"]
        return row["time_per_hour"]
    ranked = sorted(rows, key=score, reverse=True)
    if len(ranked) < 2 or abs(score(ranked[0]) - score(ranked[1])) < 0.5:
        return None
    return ranked[0]["station"]


@st.cache_data(max_entries=24, show_spinner="以相同資源比較 G12、G14…")
def compare(source, rsig, isig, vsig, ssig, schedule_sig, mode="相同班次", trips=30,
            hours=8.0, speed=18.0, road_factor=1.3, dwell=0.5, layover=5.0,
            service_hours=16.0, walk_kmh=3.0, rail_headway=8.0, walk_limit=300, conn=500):
    net0 = M.build_network(source, [], [])
    e0 = M.evaluate(net0, walk_limit, conn)
    grid = M.pop_grid(vsig, ssig)
    rows = []
    for code in ("G12", "G14"):
        points = M.greedy_feeder(source, code, e0, net0, walk_limit)
        if not points:
            continue
        feeder = dict(name=f"{code} 公平比較接駁線", station=code, points=[list(p) for p in points], loop=True)
        net1 = M.build_network(source, [], [feeder])
        e1 = M.evaluate(net1, walk_limit, conn)
        length = e1["length_km"]["FEEDER-0"]
        cycle = cycle_minutes(length, len(points) + 1, speed, road_factor, dwell, layover)
        count, used = allocation(cycle, mode, trips, hours)
        # Zero service cannot create coverage. Keep route geometry available as a candidate.
        changes = population_changes(e0, e1 if count > 0 else e0, code, grid["w"])
        profile = baseline_time(source, rsig, isig, vsig, ssig, schedule_sig, code,
                                walk_kmh, walk_limit, conn, speed, service_hours, rail_headway)
        times = time_changes(profile, feeder, length, count, walk_kmh, walk_limit, speed,
                             road_factor, dwell, service_hours, rail_headway)
        rows.append(dict(station=code, feeder=feeder, length=length, cycle_min=cycle,
                         trips=count, hours=used, unused_hours=max(0, hours-used) if mode == "相同工時上限" else 0,
                         headway=service_hours*60/count if count else None,
                         first_per_hour=changes["first"]/used if used else 0,
                         choice_per_hour=changes["choice"]/used if used else 0,
                         time_per_hour=times["improved"]/used if used else 0,
                         **changes, **times))
    return rows


def current_comparison(**kwargs):
    return compare("tdx", D.routes_sig("tdx"), D.sig("outputs/A2_isochrones.gpkg"),
                   D.sig("data/villages_pop65.gpkg"), D.sig("data/stations_green_north.csv"),
                   D.sig("data/tdx/Schedule_Taoyuan_800m_routes.json.gz"), **kwargs)
