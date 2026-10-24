"""首頁：給非專家的 30 秒說明。數字全部來自與各頁相同的演算法或已提交的衍生檔。"""
import streamlit as st

from lib import brief as B, data as D, ui

ui.banner()
st.title("🚌 綠線通車後，公車可以怎麼改？")
st.markdown(
    "**這頁在回答：** 桃園捷運綠線北段（G11 藝文特區到 G15b 坑口）通車之後，"
    "要怎麼改公車，才能把不夠用的駕駛從「跟捷運走同一條路」的路段挪去補車站，讓長者更容易到站。"
)

if not ui.require_data():
    st.stop()
src = D.current_source()
if src is None:
    st.stop()


@st.cache_data(show_spinner="正在整理三個重點（與情境模擬用同一套算法）…")
def _load(source, _rsig, _isig, _vsig, _schedsig, _indsig):
    return B.scenario_ab(source)


_ind = D.APP_DIR / "derived" / "A4_industrial_reach.csv"
H = _load(src, D.routes_sig(src), D.sig("outputs/A2_isochrones.gpkg"), D.sig("data/villages_pop65.gpkg"),
          D.sig("data/tdx/Schedule_Taoyuan_800m_routes.json.gz"),
          _ind.stat().st_mtime if _ind.exists() else 0)
if not H:
    st.warning("車站、步行範圍或人口資料還不齊，首頁無法算出重點。請到「關於資料」看缺了什麼。")
    st.stop()

st.markdown("**三個可以先記住的結果**（示意方案，不是市府的決定）")
st.caption(f"路線形狀來源：{D.SOURCES[src]}。左側可切換；兩個來源的數字不同，引用時請註明來源。")
if src == "pdf":
    st.warning("目前用市府站牌表（站和站用直線連），路線長度會偏短、也沒有班表；提案書與正式分析以「交通部公開資料」為準。")
c1, c2, c3 = st.columns(3)

s0 = H["s0_h"] / H["shift_h"]
s1 = H["s1_h"] / H["shift_h"]
has_sched = H["s0_h"] > 0  # 站牌表（pdf）來源沒有班表，無法換算駕駛班次；不可顯示成 0.0
with c1:
    if has_sched:
        st.metric("平日約當駕駛班次", f"{s1:.1f}", f"{s1 - s0:+.1f}（現況 {s0:.1f}）", delta_color="inverse")
        st.caption(
            f"估算，含假設：平均時速 {H['speed']:g} 公里、一位駕駛一班 {H['shift_h']:g} 小時。"
            + ("有路線改用實測速度。" if H["a1_routes"] else "目前實測樣本不夠，全部用這個假設時速。")
            + " 方案是縮短 GR，並幫 G14 加一條接駁。"
        )
    else:
        st.metric("平日約當駕駛班次", "—")
        st.caption("目前選的路線來源（市府站牌表）沒有班表，算不出駕駛班次。請在左側改選「交通部公開資料」。")
    if st.button("看駕駛人力怎麼換算", key="go_driver", use_container_width=True):
        st.switch_page("views/p3_scenario.py")

def _pair(code):
    a, b = H["people"].get(code) or (None, None)
    if a is None or b is None:
        return None
    return int(round(a)), int(round(b)), b - a

g14, g12, g15b = _pair("G14"), _pair("G12"), _pair("G15b")
with c2:
    if g14:
        a, b, d = g14
        st.metric("G14 能一車到站的 65 歲以上", f"{b:,} 人", f"{d:+,.0f} 人（現況 {a:,}）")
    else:
        st.metric("G14 能一車到站的 65 歲以上", "—")
    bits = []
    if g12:
        a, b, d = g12
        bits.append(f"G12 {a:,}→{b:,}（{d:+,.0f} 人）")
    if g15b:
        a, b, d = g15b
        bits.append(f"G15b {a:,}→{b:,}（{d:+,.0f} 人，車站位置是估計）")
    st.caption("同一方案的代價：" + ("；".join(bits) if bits else "—")
               + "。各站只算車站 1.5 公里內、走路直線 300 公尺能搭到「可一車到該站」公車的長者，是估計值。")
    if st.button("看長者到站怎麼變", key="go_people", use_container_width=True):
        st.switch_page("views/p3_scenario.py")

with c3:
    gr = H["gr"]
    afters = {f"{g['after']:.2f}" for g in gr}
    st.metric("GR 裁掉平行段後，每個方向大約",
              f"{next(iter(afters))} 公里" if len(afters) == 1 else "見下方")
    if gr:
        st.caption(
            "全長→剩下：" + "、".join(f"{g['label']} {g['before']:.2f}→{g['after']:.2f} 公里" for g in gr) + "。"
            "會看 GR，是因為它在捷運站 500 公尺內的長度最多："
            + "、".join(f"{g['label']} {g['overlap_km']:.2f} 公里（{g['share']:.0%}）" for g in gr if g["overlap_km"] is not None)
            + "。"
        )
    if st.button("看哪些公車跟綠線重疊", key="go_overlap", use_container_width=True):
        st.switch_page("views/p1_overlap.py")

st.info("**先看這句：** 上面三格是同一個示意改法。平日駕駛班次變少，G14 能一車到站的長者變多，G12 和 G15b 會少一點；GR 跟綠線走在一起的那一段被縮短。")

if H["ind_n"] is not None:
    anystop = H.get("ind_anystop")
    stop_bit = f"其中 {anystop} 塊在 300 公尺內有公車站，但 " if anystop is not None else ""
    st.info(
        f"**代理指標，不是移工人數：** G12 蘆興埤附近 {H['ind_n']} 塊產業用地，"
        f"{stop_bit}{H['ind_nodirect']} 塊都沒有「不用轉車就能到 G12」的站牌。"
        "只代表「可能有人要去上班的地方」，不知道實際有多少移工。"
    )
    if st.button("看各站接駁與產業用地", key="go_access"):
        st.switch_page("views/p2_access.py")

st.divider()
st.markdown("**怎麼看這個網站**")
st.page_link("views/p1_overlap.py", label="1. 路線重疊地圖 — 哪些公車跟綠線走同一條路，可以考慮縮短。")
st.page_link("views/p2_access.py", label="2. 接駁缺口 — 哪一站附近的長者比較難走到公車站，班次夠不夠。")
st.page_link("views/p3_scenario.py", label="3. 情境模擬 — 試著縮短平行路段、幫弱的站加接駁，看駕駛和長者會怎樣。")
st.page_link("views/p4_before_after.py", label="4. 通車前後比較 — 通車後才能比快慢；現在只有很短的通車前樣本。")
st.markdown("**改良方案（左側選單「改良方案」，每個方案一頁）**")
st.page_link("views/p7_plan1.py", label="方案一｜GR 縮短成接駁")
st.page_link("views/p8_plan2.py", label="方案二｜G14 社區接駁線")
st.page_link("views/p9_plan3.py", label="方案三｜G12 補強")
st.page_link("views/p10_plan4.py", label="方案四｜長路線切短、站內轉乘")
st.page_link("views/p11_plan5.py", label="方案五｜班次改善")
st.caption("想查數字從哪來、哪些還不能當結論，打開「關於資料」。")
st.caption("名詞：班次＝時刻表一天開幾班；車公里＝班次數 × 路程；一車到站＝不用轉車就能到那座捷運站；約當駕駛班次＝把開車總時數換成「幾個人的一個班」（含假設）。")
