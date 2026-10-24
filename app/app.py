"""綠線接駁決策平台（展示版）— 入口。執行：streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="綠線接駁決策平台（展示版）", page_icon="🚌", layout="wide")

from lib import data as D  # noqa: E402

pages = [
    st.Page("views/p0_home.py", title="首頁", icon="🚌", default=True, url_path="home"),
    st.Page("views/p1_overlap.py", title="路線重疊地圖", icon="🗺️", url_path="overlap"),
    st.Page("views/p2_access.py", title="接駁缺口", icon="🚶", url_path="access"),
    st.Page("views/p3_scenario.py", title="情境模擬", icon="🧪", url_path="scenario"),
    st.Page("views/p4_before_after.py", title="通車前後比較", icon="⏱️", url_path="before-after"),
    st.Page("views/p5_about.py", title="關於資料", icon="ℹ️", url_path="about"),
]
nav = st.navigation(pages)

with st.sidebar:
    st.markdown("### 綠線接駁決策平台（展示版）")
    st.caption("捷運綠線北段 G11–G15b 通車後的公車路網重整｜115年度 為桃園做研究・研究實作組")
    av = D.available_sources()
    if av:
        if st.session_state.get("source") not in av:
            st.session_state["source"] = av[0]
        st.radio("路線形狀用哪一份", av, format_func=lambda s: D.SOURCES[s], key="source",
                 help="預設用交通部公開的、車子實際走的路線。可改成市府站牌表（站和站用直線連，比較粗），用來對照提案初稿。")
    pdir = D.pilot_dir()
    st.caption("試行分析，數字可再核對。出處在「關於資料」。" if pdir else "⚠️ 找不到資料夾，請看「關於資料」。")
    if st.button("🔄 重新讀取最新資料", help="另一個程序更新檔案後，按此清除快取"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
    st.divider()

nav.run()
