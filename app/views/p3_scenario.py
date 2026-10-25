import json

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import shapely
import streamlit as st
from streamlit_folium import st_folium

from lib import data as D, driver as DR, metrics as M, passenger as PB, proxy as X, rules as RU, ui

ui.banner()
st.title("🧪 情境模擬：現況和改法差在哪")
st.markdown("**這頁在回答：** 如果把跟捷運走同一條路的公車縮短，改開接到車站的路線，駕駛夠不夠、長者會不會比較容易到站？")
st.caption("所有改法都是研究示意，不是市府或業者的方案。下面的駕駛人力是估算，含假設。")
st.warning("此頁為進階探索：預設 GR 裁切＋G14 接駁，與主方案頁保留現有路線的 G12／G14 比較不同。約當駕駛班次只換算行車時數，未含休息、待命與排班，不能解讀為實際可減少的人力；新增幾何覆蓋也不代表更快或已有搭乘需求。")
if not ui.require_data():
    st.stop()
src = D.current_source()
rts = D.routes(src)
stg = D.stations()
if D.isochrones() is None or D.villages() is None:
    st.warning("還沒有「沿人行道走得到的範圍」或村里人口，這頁沒辦法模擬。檔名在「關於資料」。")
    st.stop()
CODES = list(stg.code)
NAMES = dict(zip(stg.code, stg.name))

ss = st.session_state
ss.setdefault("scn_mods", [])
ss.setdefault("scn_feeders", [])
ss.setdefault("fd_custom", [])
ss.setdefault("fd_stops", [])
# 切換資料來源時，既有路線代碼不同 → 清掉修改
if ss.get("scn_src") != src:
    ss.scn_mods, ss.scn_src = [], src
    ss.scn_autoload = None

with st.sidebar.expander("模擬參數與人力假設"):
    st.markdown("**模擬參數**")
    R = st.select_slider("長者願意走到站牌的距離（直線，公尺）", [200, 300, 400, 500], value=300,
                         help="這裡用直線距離，不是沿人行道走。")
    CONN = st.select_slider("怎樣算「一車到站」：站牌在車站步行範圍內（公尺）", [300, 500, 800], value=500,
                            help="步行範圍是沿人行道走得到的範圍，不是直線。有一個站牌在這個範圍裡，就算這條路線可以一車到該站。")
    st.markdown("**駕駛人力換算（都是假設，可改）**")
    SPEED = st.number_input("假設平均時速（公里）【假設，可調整】", 8.0, 40.0, 18.0, 0.5,
                            help="時刻表只有發車時間、沒有站和站要開多久，所以時速先用這個假設。不是官方數字。實測樣本夠的路線可以改用實際速度。")
    USE_A1 = st.checkbox("樣本夠的路線改用實際速度", value=True,
                         help=f"同一輛車、同一條路線，相鄰兩次回報（間隔 30–180 秒）的位移 ÷ 時間。每個方向至少 {DR.MIN_PAIRS} 筆才採用。")
    SHIFT_H = st.number_input("一位駕駛一班算幾小時【假設，可調整】", 4.0, 12.0, 8.0, 0.5,
                              help="用來把開車總時數換成「約當幾個人的一個班」。沒有算休息、待命、輪休。")


@st.cache_resource(max_entries=40, show_spinner="重新計算情境指標…")
def run(source, rsig, R, conn, mods_json, feeders_json):
    mods, feeders = json.loads(mods_json), json.loads(feeders_json)
    net = M.build_network(source, mods, feeders)
    return net, M.evaluate(net, R, conn)


RS = D.routes_sig(src)
net0, e0 = run(src, RS, R, CONN, "[]", "[]")

ov = M.overlap_table(src, 500, RS)
rank_keys = list(ov.key) if not ov.empty else []
all_keys = rank_keys + sorted(k for k in rts if k not in set(rank_keys))
gr_keys = [k for k in rank_keys if rts[k]["sub"] == "GR"]
TRIPS = D.weekday_trips() if src == "tdx" else {}
_gr_trips = [TRIPS[k] for k in gr_keys if TRIPS.get(k)]
with st.sidebar.expander("新接駁線班次假設"):
    FT = st.number_input("新接駁線一天開幾班【假設，可調整】", 0, 200, int(max(_gr_trips)) if _gr_trips else 0, 1,
                         help=("預設先用 GR 現在平日單方向的班次數（時刻表）當比較基準" if _gr_trips else "沒有 GR 的班表，請自己填") +
                              "。用在預設接駁線，以及有勾「使用預設班次」的自訂接駁線。")


# ---------------------------------------------------------------- 預設情境（callbacks）
def preset_gr():
    ss.scn_mods = [m for m in ss.scn_mods if m["key"] not in gr_keys] + [
        dict(type="drop_parallel", key=k, radius=500, stations=CODES, desc=f"{rts[k]['short']}：刪除 7 站 500 m 間的平行區段") for k in gr_keys]


def preset_feeder(code="G14"):
    pts = M.greedy_feeder(src, code, e0, net0, R)
    if pts:
        ss.scn_feeders = [f for f in ss.scn_feeders if f.get("preset") != code] + [
            dict(name=f"{code} 接駁線（演算法示意）", station=code, points=[list(p) for p in pts], loop=True, preset=code, trips_default=True)]
        ss.focus = code
    else:
        ss["_msg"] = f"{code} 周邊 300–1,500 m 內找不到能增加直達覆蓋的既有站牌。"


def preset_ab():
    preset_gr()
    preset_feeder("G14")


def reset():
    ss.scn_mods, ss.scn_feeders, ss.fd_custom, ss.fd_stops = [], [], [], []


# 第一次進來就載入 A＋B，評審不用先按按鈕。按「清除」之後停留在現況，換資料來源才會重載。
if gr_keys and ss.get("scn_autoload") != src:
    preset_ab()
    ss.scn_autoload = src

if ss.get("scn_autoload") == src and gr_keys and ss.scn_feeders and ss.scn_mods:
    only_gr = all(m.get("type") == "drop_parallel" and m.get("key") in set(gr_keys) for m in ss.scn_mods)
    only_g14 = len(ss.scn_feeders) == 1 and ss.scn_feeders[0].get("preset") == "G14"
    is_ab = only_gr and {m["key"] for m in ss.scn_mods} == set(gr_keys) and only_g14
else:
    is_ab = False
summary_slot = st.container()
status_slot = st.container()
if is_ab:
    st.caption("目前比較：A＋B 組合＝縮短 GR 平行路段＋新增 G14 接駁線。")
elif ss.scn_mods or ss.scn_feeders:
    st.caption("目前比較：現況與你選擇的改法。下方可切換或調整方案。")
else:
    st.caption("目前是現況，尚未調整路線。選擇下方示意方案即可比較。")

st.markdown("**快速載入示意方案**（由資料算出，還可以再改）")
st.page_link("views/p12_priority.py", label="先比較 G12／G14：首次服務人口、到站選擇與時間效益", icon="⚖️")
b1, b2, b3, b4 = st.columns(4)
b1.button("A｜GR 平行段裁切", on_click=preset_gr, width="stretch", disabled=not gr_keys,
          help="把 GR 兩個方向裡、夾在綠線車站中間的那一段拿掉，兩端還留著。")
b2.button("B｜G14 接駁線", on_click=preset_feeder, args=("G14",), width="stretch",
          help="在 G14 周圍 300–1,500 公尺的現有站牌裡，挑最多 6 個，讓「能一車到 G14」的長者增加最多，再排成一圈。")
b3.button("A＋B 組合", on_click=preset_ab, width="stretch", type="primary")
b4.button("清除，回到 S0", on_click=reset, width="stretch")
if ss.get("_msg"):
    st.warning(ss.pop("_msg"))

with st.expander("調整方案與查看地圖", expanded=False):
    # ---- S2b：站出發的社區接駁（補弱站）
    st.markdown("**其他情境**")
    sb1, sb2 = st.columns(2)
    sb1.button("S2b｜G12 社區接駁線", on_click=preset_feeder, args=("G12",), width="stretch",
               help="G12 長者多、接駁弱。從 G12 往周邊既有站牌挑最多 6 個，讓可一車到 G12 的長者增加最多，排成一圈。")
    sb2.button("S2b｜G14 社區接駁線", on_click=preset_feeder, args=("G14",), width="stretch",
               help="與 B 相同，單獨加載（不含 A）。")


    # ---- S2a：切短＋接鐵路站
    def apply_s2a(k, code, a, b, rail, cut, walk):
        ss.scn_mods = [m for m in ss.scn_mods if m["key"] != k] + [
            dict(type="keep_range", key=k, **{"from": a, "to": b}, rail=rail, cut=cut, walk_m=walk, s2a=True,
                 desc=f"{rts[k]['short']}：切短，只保留 {rail}→{cut}（接鐵路站，於 {code} 轉乘綠線）")]


    with st.expander("S2a｜切短＋接鐵路站：選一條長路線，只保留『鐵路站端』到某座綠線站"):
        rail_keys = [k for k in all_keys if RU.rail_end(rts[k]["stops"]) is not None]
        if not rail_keys:
            st.caption("這個資料來源找不到兩端是火車站／總站／轉運站的路線。")
        else:
            c1_, c2_ = st.columns(2)
            k_ = c1_.selectbox("路線（兩端有鐵路站或轉運站者；依與綠線重疊排序）", rail_keys, key="s2a_route",
                               index=rail_keys.index(gr_keys[0]) if gr_keys and gr_keys[0] in rail_keys else 0,
                               format_func=lambda k: f"{rts[k]['label']}｜{RU.rail_end(rts[k]['stops'])[1]}")
            code_ = c2_.selectbox("在哪一座綠線站轉乘", CODES, key="s2a_code", format_func=lambda c: f"{c} {NAMES[c]}")
            sr_ = stg[stg.code == code_].iloc[0]
            rg_ = RU.s2a_range(rts[k_]["stops"], sr_.geometry.x, sr_.geometry.y)
            if rg_ is None:
                st.caption("這條路線的鐵路端就是最靠近該站的站牌，無法切短。")
            else:
                st.caption(f"保留：{rg_['rail']} → {rg_['cut_name']}（第 {rg_['from'] + 1}–{rg_['to'] + 1} 站）；切點站牌距 {code_} 直線 {rg_['walk_m']:.0f} m（轉乘步行距離下限）。")
                st.button("➕ 套用 S2a", key="s2a_go", type="primary", on_click=apply_s2a,
                          args=(k_, code_, rg_["from"], rg_["to"], rg_["rail"], rg_["cut_name"], rg_["walk_m"]))

    left, right = st.columns([2, 3])

    # ---------------------------------------------------------------- 控制區
    with left:
        t1, t2, t3 = st.tabs(["① 調整既有路線", "② 新增接駁線", f"③ 目前情境（{len(ss.scn_mods) + len(ss.scn_feeders)}）"])
        with t1:
            default_idx = all_keys.index(gr_keys[0]) if gr_keys else 0
            k = st.selectbox("路線（依與綠線重疊程度排序）", all_keys, index=default_idx, format_func=lambda k: rts[k]["label"], key="md_route")
            op = st.radio("調整方式", ["刪除與綠線平行的區段", "截短（只保留部分站序）", "整條停駛"], key="md_op")
            s = rts[k]["stops"].reset_index(drop=True)
            mod = None
            if op == "刪除與綠線平行的區段":
                rad = st.slider("站牌距車站多少公尺內算「平行」（直線）", 200, 1000, 500, 50, key="md_rad")
                sts = st.multiselect("參考車站", CODES, default=CODES, format_func=lambda c: f"{c} {NAMES[c]}", key="md_sts")
                mod = dict(type="drop_parallel", key=k, radius=rad, stations=sts, desc=f"{rts[k]['short']}：刪除 {'、'.join(sts)} {rad} m 間的平行區段")
            elif op == "截短（只保留部分站序）":
                a, b = st.select_slider("保留的站序範圍", options=list(range(len(s))), value=(0, len(s) - 1),
                                        format_func=lambda i: f"{i + 1}. {s.name[i]}", key=f"md_rng_{k}")
                mod = dict(type="keep_range", key=k, **{"from": a, "to": b}, desc=f"{rts[k]['short']}：只保留第 {a + 1}–{b + 1} 站（{s.name[a]}→{s.name[b]}）")
            else:
                mod = dict(type="remove", key=k, desc=f"{rts[k]['short']}：整條停駛")
            prev = M.apply_mod(rts[k], mod, stg)
            if prev is None:
                st.caption(f"預覽：刪除全部 {len(s)} 站、{rts[k]['line'].length / 1000:.2f} km")
            else:
                L1 = sum(l.length for l in prev["lines"]) / 1000
                st.caption(f"預覽：保留 {len(prev['stops'])}／{len(s)} 站；長度 {rts[k]['line'].length / 1000:.2f} → {L1:.2f} km；分成 {len(prev['lines'])} 段")
            if st.button("➕ 加入情境", key="md_add", type="primary"):
                ss.scn_mods = [m for m in ss.scn_mods if m["key"] != k] + [mod]
                st.rerun()
            same_route = [kk for kk in rts if rts[kk]["sub"] == rts[k]["sub"] and kk != k]
            if same_route:
                st.caption(f"提示：{rts[k]['sub']} 另有 {len(same_route)} 個方向，需分別加入。")

        with t2:
            fst = st.selectbox("接駁車站", CODES, index=CODES.index("G14") if "G14" in CODES else 0, format_func=lambda c: f"{c} {NAMES[c]}", key="fd_station")
            rr = st.slider("候選既有站牌範圍（距車站直線 m）", 300, 3000, (300, 1500), 100, key="fd_rr")
            srow = stg[stg.code == fst].iloc[0]
            SP = D.stop_positions({kk: dict(sub=v["sub"], stops=v["stops"]) for kk, v in rts.items()})
            grp = SP.groupby(["kx", "ky"]).agg(name=("name", "first"), x=("x", "first"), y=("y", "first"),
                                              routes=("route", lambda x: " ".join(sorted(set(map(str, x)))))).reset_index()
            grp["d"] = np.hypot(grp.x - srow.geometry.x, grp.y - srow.geometry.y)
            cand = grp[(grp.d >= rr[0]) & (grp.d <= rr[1])].sort_values("d")
            cand["id"] = cand.kx.astype(str) + "_" + cand.ky.astype(str)
            cmap = cand.set_index("id")
            ss.fd_stops = [i for i in ss.fd_stops if i in cmap.index]

            def auto_pick():
                pts = M.greedy_feeder(src, fst, e0, net0, R, rr[0], rr[1])
                ids = []
                for x, y, _ in pts:
                    kx, ky = int(round(x / 5)), int(round(y / 5))
                    ids.append(f"{kx}_{ky}")
                ss.fd_stops = [i for i in ids if i in cmap.index]
                if not ids:
                    ss["_msg"] = "此範圍內沒有能增加直達覆蓋的既有站牌。"

            st.button("🤖 自動挑選站牌（貪婪法：最大化可直達本站的 65+ 人口）", on_click=auto_pick, width="stretch")
            st.multiselect(f"經過的既有站牌（{len(cand)} 個候選）", list(cand.id), key="fd_stops",
                           format_func=lambda i: f"{cmap.name[i]}（{cmap.d[i]:.0f} m｜{cmap.routes[i][:30]}）")
            st.checkbox("在右側地圖點一下即新增自訂停靠點", key="fd_click")
            if ss.fd_custom:
                st.caption("自訂點：" + "、".join(p[2] for p in ss.fd_custom))
                if st.button("清除自訂點"):
                    ss.fd_custom = []
                    st.rerun()
            loop = st.checkbox("循環線（最後回到車站）", value=True, key="fd_loop")
            order = st.radio("停靠順序", ["自動（最近鄰＋2-opt 縮短路線）", "依選取順序"], key="fd_order", horizontal=True)
            name = st.text_input("路線名稱", value=f"{fst} 接駁線（自訂）", key="fd_name")
            use_ft = st.checkbox(f"使用側欄的預設接駁線班次（目前 {FT} 班）", value=True, key="fd_use_ft")
            ftrips = FT if use_ft else st.number_input("此接駁線平日班次（整圈）【假設，可調整】", 0, 200, int(FT), 1, key="fd_trips",
                                                        help="這是使用者自行輸入的假設值，不是資料。")
            pts = [(float(cmap.x[i]), float(cmap.y[i]), str(cmap.name[i])) for i in ss.fd_stops] + [tuple(p) for p in ss.fd_custom]
            if order.startswith("自動"):
                pts = M.two_opt(srow.geometry.x, srow.geometry.y, M.nn_order(srow.geometry.x, srow.geometry.y, pts), loop=loop)
            draft = dict(name=name, station=fst, points=[list(p) for p in pts], loop=loop, trips=int(ftrips) or None, trips_default=bool(use_ft))
            if pts:
                dl = M.feeder_route(draft, stg)["lines"][0].length / 1000
                st.caption(f"草稿：{len(pts)} 個停靠點＋車站端點，直線長度 {dl:.2f} km（實際道路距離會更長）")
            ss["_draft"] = draft

            def add_feeder():
                d = ss.get("_draft")
                if d and d["points"]:
                    ss.scn_feeders = ss.scn_feeders + [d]
                    ss.fd_stops, ss.fd_custom = [], []
                    ss.focus = d["station"]

            st.button("➕ 加入情境", key="fd_add", type="primary", disabled=not pts, on_click=add_feeder)

        with t3:
            if not ss.scn_mods and not ss.scn_feeders:
                st.info("目前是現況，還沒有改路線。")
            for i, m in enumerate(list(ss.scn_mods)):
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"✂️ {m['desc']}")
                if c2.button("刪除", key=f"delm{i}"):
                    ss.scn_mods.pop(i)
                    st.rerun()
            for i, f in enumerate(list(ss.scn_feeders)):
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"🟣 **{f['name']}**：{f['station']} → " + "→".join(p[2] for p in f["points"]) + (" → 回車站" if f.get("loop") else ""))
                if c2.button("刪除", key=f"delf{i}"):
                    ss.scn_feeders.pop(i)
                    st.rerun()

    # ---------------------------------------------------------------- 計算 S1
    FEEDERS = [dict(f, trips=(FT or None)) if f.get("trips_default") else f for f in ss.scn_feeders]
    mods_json = json.dumps(ss.scn_mods, ensure_ascii=False, sort_keys=True)
    feed_json = json.dumps([{k: v for k, v in f.items() if k != "trips"} for f in FEEDERS], ensure_ascii=False, sort_keys=True)
    net1, e1 = run(src, RS, R, CONN, mods_json, feed_json)

    feeder_codes = [f["station"] for f in ss.scn_feeders]
    with right:
        _def = feeder_codes[-1] if feeder_codes else ss.get("fd_station", "G14")
        if ss.get("focus") not in CODES:
            ss.focus = _def if _def in CODES else CODES[0]
        focus = st.selectbox("地圖與重點指標聚焦車站", CODES, format_func=lambda c: f"{c} {NAMES[c]}", key="focus")
        grid = M.pop_grid(D.sig("data/villages_pop65.gpkg"), D.sig("data/stations_green_north.csv"))
        m0 = e0["coverage"]["per_station"][focus]["mask"]
        m1 = e1["coverage"]["per_station"][focus]["mask"]

        def cells(mask):
            if not mask.any():
                return None
            h = M.GRID / 2
            bx = shapely.box(grid["x"][mask] - h, grid["y"][mask] - h, grid["x"][mask] + h, grid["y"][mask] + h)
            return shapely.union_all(bx)

        fm = ui.base_map(zoom=14)
        srow = stg[stg.code == focus].iloc[0]
        fm.location = [srow.lat, srow.lon]
        for poly, col, lab in [(cells(m1 & ~m0), "#2ca02c", "新增：可一車直達本站的 65+ 居住範圍"),
                               (cells(m0 & ~m1), "#d62728", "失去：原可一車直達本站的 65+ 居住範圍"),
                               (cells(m0 & m1), "#9e9ac8", "維持")]:
            if poly is not None:
                folium.GeoJson(ui.to_ll(poly).__geo_interface__, style_function=lambda f, c=col: dict(fillColor=c, color=c, weight=0, fillOpacity=0.45 if c != "#9e9ac8" else 0.2),
                               tooltip=lab).add_to(fm)
        folium.Circle([srow.lat, srow.lon], radius=M.STUDY_R, color="#555", weight=1, fill=False, dash_array="6 6",
                      tooltip=f"{focus} 人口分析範圍 {M.STUDY_R} m").add_to(fm)
        for k in {m["key"] for m in ss.scn_mods}:
            for part in ui.line_coords(rts[k]["line"]):
                folium.PolyLine(part, color="#888", weight=3, dash_array="6 6", opacity=0.8, tooltip=f"S0：{rts[k]['label']}").add_to(fm)
            new = net1.get(k)
            if new:
                for ln in new["lines"]:
                    for part in ui.line_coords(ln):
                        folium.PolyLine(part, color="#ff7f0e", weight=5, opacity=0.9, tooltip=f"情境：{rts[k]['label']}").add_to(fm)
            kept = set(zip(new["stops"].x.round(1), new["stops"].y.round(1))) if new else set()
            for _, p in rts[k]["stops"].iterrows():
                if (round(p.x, 1), round(p.y, 1)) not in kept:
                    folium.CircleMarker([p.lat, p.lon], radius=4, color="#d62728", fill=True, fill_opacity=1,
                                        tooltip=f"取消停靠：{p['name']}").add_to(fm)
        allf = list(ss.scn_feeders) + ([draft] if draft["points"] else [])
        for j, f in enumerate(allf):
            is_draft = j == len(allf) - 1 and draft["points"] and f is draft
            fr = M.feeder_route(f, stg)
            for ln in fr["lines"]:
                for part in ui.line_coords(ln, simplify=0):
                    folium.PolyLine(part, color="#6a3d9a", weight=4, opacity=0.9, dash_array="8 6" if is_draft else None,
                                    tooltip=("草稿：" if is_draft else "") + f["name"]).add_to(fm)
            for _, p in fr["stops"].iterrows():
                la, lo = ui.xy_to_ll(p.x, p.y)
                folium.CircleMarker([la, lo], radius=5, color="#6a3d9a", fill=True, fill_color="white", fill_opacity=1, weight=2,
                                    tooltip=p["name"]).add_to(fm)
        ui.add_stations(fm)
        out = st_folium(fm, height=560, use_container_width=True, returned_objects=["last_clicked"], key="scn_map")
        st.caption("綠色＝改完之後新增加、可以一車到這站的長者住的地方；紅色＝反而搭不到了；紫灰＝沒變。灰虛線＝原來的路線；橘色＝改完的路線；紅點＝取消停靠；紫色＝新的接駁線。")
        if ss.get("fd_click") and out and out.get("last_clicked"):
            lc = out["last_clicked"]
            tag = (round(lc["lat"], 6), round(lc["lng"], 6))
            if ss.get("_last_click") != tag:
                ss["_last_click"] = tag
                x, y = ui.ll_to_xy(lc["lat"], lc["lng"])
                ss.fd_custom = ss.fd_custom + [[float(x), float(y), f"自訂點{len(ss.fd_custom) + 1}"]]
                st.rerun()

with st.expander("完整比較、規則檢查與計算方法", expanded=False):
    # ---------------------------------------------------------------- 結果
    st.divider()
    st.subheader("現況和這個改法的差別")
    # ---- 駕駛人力（頭條指標）
    SPEEDS = DR.a1_speeds() if USE_A1 else {}
    DT = DR.driver_table(rts, net1, ss.scn_mods, FEEDERS, TRIPS, SPEEDS, SPEED, SHIFT_H, USE_A1, e1["length_km"])
    CT = DR.corridor_totals(rts, net1, TRIPS, SPEEDS, SPEED, USE_A1, e1["length_km"], FEEDERS)
    if TRIPS:
        mod_part = DT[DT.類型 == "調整既有路線"] if not DT.empty else DT
        fd_part = DT[DT.類型 == "新增接駁線"] if not DT.empty else DT
        saved = float((mod_part.S0_班次 - mod_part.情境_班次).sum()) if len(mod_part) else 0.0
        need = float(fd_part.情境_班次.sum()) if len(fd_part) else 0.0
        no_tt = int(mod_part.平日班次.isna().sum()) if len(mod_part) else 0
        no_fd = int(fd_part.平日班次.isna().sum()) if len(fd_part) else 0
        st.markdown(
            f"""<div style="background:#eef7ee;border:2px solid #1a7f37;border-radius:10px;padding:12px 18px;margin:6px 0 12px 0">
            <div style="font-size:0.95rem;color:#1a5f2a">👷 <b>可移轉駕駛人力</b>（平日，約當駕駛班次；估算，含假設）＝ 縮短路線省下的 − 新接駁需要的</div>
            <div style="font-size:2.3rem;font-weight:800;color:#145a24">{saved - need:+.1f} 班</div>
            <div style="font-size:0.9rem;color:#333">縮短省下 {saved:.1f} 班 − 接駁需要 {need:.1f} 班｜一班 {SHIFT_H:g} 小時【假設】、
            假設時速 {SPEED:g} 公里【假設】{('、' + str(len(SPEEDS) - (1 if '_ALL' in SPEEDS else 0)) + ' 個方向用實測速度') if SPEEDS else '（實測樣本還不夠，全部用假設時速）'}</div></div>""",
            unsafe_allow_html=True)
        if no_tt or no_fd:
            st.warning(f"{no_tt} 條調整路線沒有 TDX 班表、{no_fd} 條接駁線未設定班次，這些未計入人力換算。")
        d1, d2, d3 = st.columns(3)
        d1.metric("平日車公里（有班表的路線＋新接駁）", f"{CT['s1_km']:,.0f}", f"{CT['s1_km'] - CT['s0_km']:+,.0f}（現況 {CT['s0_km']:,.0f}）", delta_color="inverse",
                  help="車公里＝一天開幾班 × 路線長度（公里）。班次來自時刻表。")
        d2.metric("平日車輛小時", f"{CT['s1_h']:,.1f}", f"{CT['s1_h'] - CT['s0_h']:+,.1f}（現況 {CT['s0_h']:,.1f}）", delta_color="inverse",
                  help="車輛小時＝車公里 ÷ 時速。只算車子在開的時間。")
        d3.metric("約當駕駛班次", f"{CT['s1_h'] / SHIFT_H:,.1f}", f"{(CT['s1_h'] - CT['s0_h']) / SHIFT_H:+,.1f}（現況 {CT['s0_h'] / SHIFT_H:,.1f}）", delta_color="inverse",
                  help="約當駕駛班次＝車輛小時 ÷ 一班幾小時。估算，含假設，不是實際能裁掉的人數。")
        st.caption(f"計算範圍：有時刻表的 {sum(1 for k in TRIPS if k in rts)} 個路線方向（捷運站步行 800 公尺內會經過的路線）加上新接駁線。")
    else:
        st.info("駕駛人力要有時刻表才算得出來。請改用左側的「交通部公開資料」。")
    c0, c1 = e0["coverage"], e1["coverage"]
    p0, p1 = c0["per_station"][focus], c1["per_station"][focus]

    # ---------------------------------------------------------------- 規則檢查
    st.subheader("三條設計規則檢查")
    st.caption("研究的核心主張是「可靠度與容量達標才裁切」。下面三項把規則落成檢查；門檻、車型容量都是【假設，可調】，不是標準；缺資料時會寫「無法檢查」，不猜數字。")
    RELS = RU.reliability()
    TH0 = RU.reliability_thresholds_default(RELS)
    with st.expander("門檻與車型假設（可調）", expanded=False):
        t1c, t2c, t3c = st.columns(3)
        TH = dict(cv=t1c.slider("班距變異係數 cv 上限", 0.1, 1.5, TH0["cv"], 0.05, key="rl_cv", help="預設為目前樣本的中位數，不是標準。"),
                  gap=t2c.slider("大間隔比例上限", 0.0, 0.6, TH0["gap"], 0.05, key="rl_gap"),
                  bunch=t3c.slider("併班比例上限", 0.0, 0.6, TH0["bunch"], 0.05, key="rl_bun"))
        v1c, v2c, v3c = st.columns(3)
        VEH = v1c.radio("接駁線車型", ["大型公車", "桃小巴"], key="rl_veh", horizontal=True)
        CAP_BUS = v2c.number_input("大型公車載客數（座＋站）【假設】", 10, 120, 60, 5, key="rl_capbus", help="請以業者實際規格取代。")
        CAP_MINI = v3c.number_input("桃小巴載客數（座＋站）【假設】", 5, 40, 25, 1, key="rl_capmini", help="請以業者實際規格取代。")
        w1c, w2c = st.columns(2)
        PEAK_TPH = w1c.number_input("接駁線尖峰每小時班次【假設】", 1.0, 20.0, 4.0, 0.5, key="rl_tph", help="4 班＝約 15 分鐘一班。")
        LEN_CAP = w2c.number_input("新接駁線整圈長度上限（公里）【假設】", 2.0, 30.0, 8.0, 0.5, key="rl_lencap",
                                   help="背景規則：新線不可過長。上限值待與市府排班規則確認；此處用點間直線長度，是下限值。")
    if RELS is None:
        st.info("沒有班距結果檔（outputs/A3_headway_summary.csv），規則一無法檢查。")

    st.markdown("**規則一：班距穩定才裁切**（被裁切或截短的路線，其保留部分會被依賴）")
    rule_rows, any_bad = [], False
    for m in ss.scn_mods:
        r_ = rts[m["key"]]
        gt = RU.route_gate(RELS, r_["sub"], r_["dir"], TH)
        any_bad |= gt["status"] != "ok"
        ico = {"ok": "✅", "fail": "⚠️", "nodata": "❔"}[gt["status"]]
        row = {"對象": r_["label"], "改法": m["desc"].split("：", 1)[-1][:40], "檢查": f"{ico} {gt['why']}"}
        if gt["status"] != "nodata":
            row.update({"cv": round(gt["cv"], 2), "大間隔": round(gt["gap"], 2), "併班": round(gt["bunch"], 2),
                        "班距班數": gt["n"]})
        if m.get("s2a"):
            row["轉乘步行(下限 m)"] = round(m.get("walk_m", 0))
            if gt["status"] != "nodata":
                row["預估轉乘等候(分)"] = round(gt["mean_min"] / 2, 1)
        rule_rows.append(row)
    for f in FEEDERS:
        rule_rows.append({"對象": f["name"], "改法": "新增接駁線", "檢查": "❔ 新線沒有歷史班距，須通車後監測才能確認"})
        any_bad = True
    if rule_rows:
        RT = pd.DataFrame(rule_rows)
        for c_ in RT.columns:
            if c_ not in ("對象", "改法", "檢查"):
                RT[c_] = RT[c_].map(lambda v: "—" if pd.isna(v) else f"{v:g}")   # 無資料顯示「—」，不顯示 None／NaN
        st.dataframe(RT, hide_index=True, width="stretch")
        if any_bad:
            st.warning("至少有一項被依賴的路線或新線班距不穩、或缺資料。依設計原則，這個改法**現在還不能算「可裁切」**；只是示意，需要更多天的資料才能判斷。")
        else:
            st.success("目前樣本下，被裁切路線的班距都在門檻內（單日示意，不代表常態）。")
    else:
        st.caption("目前是現況，沒有被調整的路線。")
    if any(m.get("s2a") for m in ss.scn_mods):
        st.caption("轉乘等候＝實際平均班距 ÷ 2（隨機到站的期望值，未含班距不穩造成的額外等待；單日樣本）。轉乘步行距離為直線，是下限。")

    st.markdown("**規則二：載客高的路線不降為桃小巴**")
    st.info("**無法檢查。** 要知道哪些路線載客高，需要各路線各站上下車量，這項資料沒有公開，列為市府資料媒合需求。"
            "目前只在下面「容量」檢查接駁線本身會不會一個車型就裝不下。")
    if FEEDERS:
        st.markdown("**接駁線的容量與長度（規則二的替代檢查、規則三）**")
        cap_v = int(CAP_MINI if VEH == "桃小巴" else CAP_BUS)
        cap_rows = []
        for i, f in enumerate(FEEDERS):
            ben = c1["per_station"][f["station"]]["direct"] - c0["per_station"][f["station"]]["direct"]
            cp = RU.capacity(cap_v, PEAK_TPH, max(ben, 0))
            L = e1["length_km"].get(f"FEEDER-{i}", 0.0)
            lg = RU.length_gate(L, LEN_CAP)
            cap_rows.append({"接駁線": f["name"], "車型": f"{VEH}（{cap_v} 人）", "每小時單向載客上限": int(cp["per_hr"]),
                             "新增可一車到站的長者": int(round(max(ben, 0))),
                             "載客上限相當於這群長者的": (f"{cp['share']:.0%}" if cp["share"] is not None else "—（沒有新增）"),
                             "整圈直線長度(km)": round(L, 2), "長度": "✅ 在上限內" if lg["ok"] else f"⚠️ 超過 {LEN_CAP:g} km"})
        st.dataframe(pd.DataFrame(cap_rows), hide_index=True, width="stretch")
        st.caption("**怎麼讀：** 這裡不假設有多少人會搭。「載客上限相當於這群長者的 X%」意思是：同一小時只要這群長者有 X% 搭乘，車就滿了；"
                   "X 越小，越容易擠不上。號誌路口數沒有資料，未檢查；長度是點間直線（實際會更長）。尖峰班次、車型容量都是假設。")

    base_len = sum(rts[m["key"]]["line"].length for m in ss.scn_mods) / 1000
    new_len = sum(e1["length_km"].get(m["key"], 0.0) for m in ss.scn_mods)
    feed_len = sum(v for k, v in e1["length_km"].items() if k.startswith("FEEDER"))
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"{focus} 附近 1.5 公里、能一車到本站的 65 歲以上", ui.fmt_int(p1["direct"]), f"{p1['direct'] - p0['direct']:+,.0f} 人",
              help=f"{focus} 周圍 {M.STUDY_R} 公尺內，走路直線 {R} 公尺就到「能一車到本站」的公車站牌的 65 歲以上人數（估計）。這個範圍裡的 65 歲以上大約 {p0['total']:,.0f} 人。")
    k2.metric("七站附近、能一車到任一站的 65 歲以上", ui.fmt_int(c1["conn"]), f"{c1['conn'] - c0['conn']:+,.0f} 人",
              help=f"範圍是 7 站各 {M.STUDY_R} 公尺圓圈加在一起，65 歲以上大約 {c0['total']:,.0f} 人。相鄰站會重疊，不要把各站人數相加。")
    k3.metric(f"七站附近、走路 {R} 公尺內有公車站的 65 歲以上", ui.fmt_int(c1["any"]), f"{c1['any'] - c0['any']:+,.0f} 人")
    k4.metric("路線長度變化（改過的＋新接駁）", f"{new_len - base_len + feed_len:+.2f} km",
              f"原來的 {base_len:.2f}→{new_len:.2f} 公里；新線 +{feed_len:.2f} 公里", delta_color="off",
              help="新接駁線用點和點的直線，實際沿路會更長。")



    @st.cache_resource(show_spinner=False)
    def ind_corridor(isig):
        ind = X.load_industrial()
        if ind is None:
            return None
        from shapely.ops import unary_union
        corr = unary_union([g.buffer(X.NEAR_R) for g in stg.geometry])
        return unary_union(list(ind.geometry)).intersection(corr)


    def conn_xy(net, ev):
        xs = [np.column_stack([net[k]["stops"].x.values, net[k]["stops"].y.values]) for k in ev["conn_keys"] if k in net and len(net[k]["stops"])]
        return np.unique(np.round(np.vstack(xs), 0), axis=0) if xs else np.zeros((0, 2))


    IC = ind_corridor(X.industrial_sig())
    if IC is not None and not IC.is_empty:
        a0 = X.direct_area_ha(IC, conn_xy(net0, e0), R)
        a1 = X.direct_area_ha(IC, conn_xy(net1, e1), R)
        st.metric(f"產業用地（代理指標，不是移工人數）：七站各 1.5 公里內，{R} 公尺內能搭到可一車進站的公車",
                  f"{a1:,.1f} 公頃", f"{a1 - a0:+,.1f} 公頃（現況 {a0:,.1f}／範圍內共 {IC.area / 1e4:,.1f} 公頃）",
                  help="產業用地來自開放街圖標成工業的範圍，加上經濟部產業園區範圍。只算七座車站各 1.5 公里以內。這不是移工人數。")

    s0 = pd.DataFrame(e0["station"]).set_index(["code", "dist_m"])
    s1 = pd.DataFrame(e1["station"]).set_index(["code", "dist_m"])
    rows = []
    for c in CODES:
        row = {"車站": f"{c} {NAMES[c]}"}
        for d in [300, 500, 800]:
            if (c, d) in s0.index:
                a, b = s0.loc[(c, d), "stops"], s1.loc[(c, d), "stops"]
                row[f"站牌 {d} m"] = f"{a} → {b}" + (f"（{b - a:+d}）" if b != a else "")
        if (c, CONN) in s0.index:
            a, b = s0.loc[(c, CONN), "routes"], s1.loc[(c, CONN), "routes"]
            row[f"路線數 {CONN} m"] = f"{a} → {b}" + (f"（{b - a:+d}）" if b != a else "")
        a, b = c0["per_station"][c]["direct"], c1["per_station"][c]["direct"]
        row["能一車到本站的 65 歲以上"] = f"{a:,.0f} → {b:,.0f}" + (f"（{b - a:+,.0f}）" if round(b) != round(a) else "")
        row["_chg"] = round(b) != round(a) or any("（" in str(v) for v in row.values())
        rows.append(row)
    T = pd.DataFrame(rows)
    st.dataframe(T.drop(columns="_chg").style.apply(lambda r: ["background-color:#fff3cd" if T.loc[r.name, "_chg"] else ""] * len(r), axis=1),
                 hide_index=True, width="stretch")
    st.caption(f"「站牌 N 公尺」＝沿人行道走到捷運站 N 公尺以內，這個改法還有停靠的公車站（5 公尺以內算同一個站）。「路線數」用 {CONN} 公尺的步行範圍。")

    g1, g2 = st.columns(2)
    with g1:
        fig = go.Figure([go.Bar(name="現況", x=CODES, y=[c0["per_station"][c]["direct"] for c in CODES], marker_color="#9ecae1"),
                         go.Bar(name="自訂情境", x=CODES, y=[c1["per_station"][c]["direct"] for c in CODES], marker_color="#6a3d9a")])
        fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=40, b=10),
                          title=f"各站 1.5 公里內，能一車到本站的 65 歲以上人數", legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")
    with g2:
        fig = go.Figure([go.Bar(name="現況", x=CODES, y=[s0.loc[(c, 500), "stops"] if (c, 500) in s0.index else 0 for c in CODES], marker_color="#9ecae1"),
                         go.Bar(name="自訂情境", x=CODES, y=[s1.loc[(c, 500), "stops"] if (c, 500) in s1.index else 0 for c in CODES], marker_color="#6a3d9a")])
        fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=40, b=10), title="各站步行 500 公尺內，還有公車停的站牌數", legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")

    if ss.scn_mods or ss.scn_feeders:
        st.markdown("**駕駛人力明細（平日）**")
        if DT.empty:
            st.info("尚無可換算的路線。")
        else:
            show = DT.copy()
            for c in ["S0_車公里", "情境_車公里", "S0_車小時", "情境_車小時"]:
                show[c] = show[c].round(1)
            for c in ["S0_班次", "情境_班次"]:
                show[c] = show[c].round(2)
            show["平日班次"] = [f"{int(t)}" if t == t and t else "—" for t in show.平日班次]
            show["長度變化_km"] = [round(e1["length_km"].get(m["key"], 0.0) - rts[m["key"]]["line"].length / 1000, 2) for m in ss.scn_mods] + \
                                [round(e1["length_km"].get(f"FEEDER-{i}", 0.0), 2) for i, f in enumerate(FEEDERS)]
            st.dataframe(show[["路線", "類型", "長度變化_km", "平日班次", "速率_kmh", "速率來源", "S0_車公里", "情境_車公里", "S0_車小時", "情境_車小時", "S0_班次", "情境_班次"]].rename(columns={
                "長度變化_km": "長度變化（公里）", "速率_kmh": "時速（公里）",
                "S0_車公里": "現況車公里", "情境_車公里": "改後車公里",
                "S0_車小時": "現況車輛小時", "情境_車小時": "改後車輛小時",
                "S0_班次": "現況約當班次", "情境_班次": "改後約當班次",
            }), hide_index=True, width="stretch")
            st.caption("車公里＝一天的班次數 × 單程長度；車輛小時＝車公里 ÷ 時速；約當駕駛班次＝車輛小時 ÷ 一班幾小時。"
                       "既有路線的班次來自時刻表（用星期三有開的班，去程和回程分開算）；接駁線的班次是側欄或自己填的**假設**。"
                       "只算車子在開的時間，沒有算休息、空車調度、待命和輪休，所以實際需要的人會更多。「可移轉」只是換算，不代表可以裁員。")

    with st.expander("計算方法與限制（簡報時請一併說明）"):
        st.markdown(f"""
    - **有幾個站牌**：用沿人行道走得到的範圍來算（技術檔是步行等時圈）。5 公尺以內的站牌算同一個位置。
    - **一車到本站**：某條路線只要有一個站牌在該捷運站 {CONN} 公尺步行範圍內，就算「不用轉車就能到」。還沒有考慮班次、方向和幾點開。
    - **65 歲以上人數**：內政部 115 年 9 月的村里人口，依面積比例分到 {M.GRID} 公尺的格子（假設人在村里裡平均分布）。走到站牌用**直線** {R} 公尺，不是沿路走。
    - **範圍**：7 站各 {M.STUDY_R} 公尺的圓圈；每一站只算自己這圈（隔壁站會重疊，各站人數不能相加）。
    - **路線長度**：現有路線用{'車子實際走的形狀' if src == 'tdx' else '站和站之間的直線（會比實際路短）'}；新接駁是點和點的直線，實際沿路會更長。拿掉平行段時，假設車在剩下的兩端掉頭，沒有把掉頭和空車算進去。
    - **駕駛人力**：班次來自時刻表。時速預設 {SPEED:g} 公里是【假設，可調整】（樣本夠的路線可改用實測）。一班 {SHIFT_H:g} 小時是【假設，可調整】。沒有算休息、空車、待命和輪休。
    - **產業用地（移工通勤的代理指標）**：工廠或產業園區的範圍，只代表可能有人要去上班，不等於移工人數。
    - **還沒算**：旅行時間、要轉幾次車、路能不能開公車、場站夠不夠、轉乘票價。
    - **預設接駁線**是演算法挑的現有站牌，只是起點，不代表真的開得成。
    """)

with summary_slot:
    st.subheader("這個改法，帶來什麼變化？")
    h1, h2, h3 = st.columns(3)
    with h1:
        st.metric("可移轉約當駕駛班次", f"{saved - need:+.1f} 班" if TRIPS else "待補班表",
                  help="平日縮短路線省下的班次，扣除新增接駁需要的班次；負值表示需要增加人力。估算，含假設。")
        st.caption(f"省下 {saved:.1f} 班 − 接駁需要 {need:.1f} 班" if TRIPS else "請切換至交通部公開資料，才能換算人力。")
    g0, g1 = c0["per_station"].get("G14"), c1["per_station"].get("G14")
    with h2:
        st.metric("G14 可一車到站的長者", f"{g1['direct'] - g0['direct']:+,.0f} 人" if g0 and g1 else "待補資料")
        st.caption(f"現況 {g0['direct']:,.0f} → 改後 {g1['direct']:,.0f} 人（估計）" if g0 and g1 else "缺少 G14 的覆蓋資料。")
    losses = [(c, c0["per_station"][c]["direct"], c1["per_station"][c]["direct"]) for c in CODES
              if round(c1["per_station"][c]["direct"]) < round(c0["per_station"][c]["direct"])]
    with h3:
        st.metric("直達服務減少的車站", f"{len(losses)} 站", delta_color="off")
        st.caption("、".join(c for c, _, _ in losses) if losses else "目前估計未有車站減少。")
    if losses:
        st.warning("**需要補救的服務缺口：** " + "；".join(
            f"{c} {NAMES[c]}：{a:,.0f} → {b:,.0f} 人（{b-a:+,.0f}）" for c, a, b in losses)
            + "。各站分析範圍重疊，人數不可相加。")
    st.caption(f"估算，含假設：平均時速 {SPEED:g} 公里、每班 {SHIFT_H:g} 小時；長者走到站牌以直線 {R} 公尺估計。"
               "可服務人數不等於實際搭乘人數。完整計算與未納入班表的項目見下方明細。")
    with st.expander(f"{focus} 新增到站服務：哪些是首次服務、哪些只是多一個選擇？"):
        changes = PB.population_changes(e0, e1, focus, grid["w"])
        st.dataframe(pd.DataFrame([
            {"分類": "原本不能一車到任一綠線站，現在可到本站", "長者估計人數": round(changes["first"])},
            {"分類": "原本已能到其他綠線站，現在多了本站選擇", "長者估計人數": round(changes["choice"])},
            {"分類": "全研究範圍首次取得直達服務（去重）", "長者估計人數": round(changes["new_any"])},
            {"分類": "全研究範圍失去全部直達服務（去重）", "長者估計人數": round(changes["lost_any"])},
        ]), hide_index=True, width="stretch")
        st.caption("前兩列為新增本站覆蓋的互斥分類；後兩列為全廊帶服務得失，範圍不同，不可四列相加。"
                   f"全廊帶直達覆蓋淨變化為 {changes['net_any']:+,.0f} 人，不代表相同人數的新乘客或旅次。")


with status_slot:
    if any_bad and rule_rows:
        st.warning("方案尚待驗證：被調整路線或新接駁線仍有班距資料不足或未達門檻的項目。請展開完整比較查看規則檢查。")
