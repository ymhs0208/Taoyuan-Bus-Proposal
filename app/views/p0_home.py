"""研究入口：先說清楚決策與證據邊界。"""
import streamlit as st
from lib import passenger as B, data as D, ui

ui.banner()
st.title("把接駁資源，放在真正需要的地方")
st.markdown("桃園捷運綠線北段 G11–G15b 通車後，哪些公車值得調整？本研究先比較 G12、G14 新增接駁的乘客效益，再檢查有限資源能否支持服務。")
if not ui.require_data():
    st.stop()
if D.current_source() != 'tdx':
    st.warning("主方案比較固定採交通部公開路線與班表；左側其他來源僅供地圖及探索頁對照，不能混用數字。")
rows = B.current_comparison()
if len(rows) != 2:
    st.warning("資料尚不完整，無法產生主方案比較。請先查閱關於資料。")
    st.stop()
selected = B.screened_priority(rows)
st.info(f"**目前判斷：{selected} 可先進一步驗證。** 每線每日 30 圈、服務 16 小時，並以最長班距 40 分鐘、最多 2 輛為示範門檻；這是候選線比較，尚非開線建議。" if selected else "目前預設條件沒有可優先推進的主方案，請先檢查資源與效益。")
a, b, c = st.columns(3)
with a:
    st.markdown("### ① 看問題")
    st.write("重疊里程只是線索；真正要問的是，哪些地方仍缺少可用的到站選擇。")
    st.page_link('views/p2_access.py', label='查看接駁缺口', icon='🚶')
    st.page_link('views/p1_overlap.py', label='查看路線重疊', icon='🗺️')
with b:
    st.markdown("### ② 比方案")
    st.write("分開看首次覆蓋、增加到站選擇與時間改善，並用相同班次或工時比較兩線。")
    st.page_link('views/p12_priority.py', label='比較 G12、G14', icon='⚖️')
with c:
    st.markdown("### ③ 看驗證條件")
    st.write("班距與車數未達條件時先不推進；道路、需求及駕駛排班仍須現地確認。")
    st.page_link('views/p12_priority.py', label='檢查資源及旅程示例', icon='📋')
st.subheader("相同班次的代價，先攤開看")
for r in rows:
    gate = B.screen(r)
    first = '不足 1 人' if 0 < r['first'] < 1 else f"約 {r['first']:,.0f} 人"
    st.write(f"**{r['station']}**：首次幾何覆蓋 {first}；約 {r['hours']:.1f} 車輛服務工時／日；理想均勻排班至少 {gate['fleet']} 輛。")
st.caption("人口為村里面積均分的估計，不是實際乘客；車數尚未含備援與空車調度。同班次不等於同工時。")
limited = B.current_comparison(mode='相同工時上限')
if B.screened_priority(limited) is None:
    st.warning("資源縮成每線每日 8 車輛服務工時、仍服務 16 小時時，預設兩線皆無至少 1 分鐘的模型時間改善，不能沿用同班次的優先結論。")
st.markdown("**證據還缺什麼？** 真實搭乘需求、無障礙步行、道路與折返可行性、可執行班表，以及通車後成效。目前沒有足夠證據宣稱已省下人力或完整旅次時間。")
with st.expander('進階探索與資料核對'):
    st.page_link('views/p3_scenario.py', label='情境模擬：裁切與接駁組合（探索用途）')
    st.page_link('views/p6_reliability.py', label='班距可靠度：查看樣本與限制')
    st.page_link('views/p4_before_after.py', label='通車前後：查看尚待補足的證據')
    st.page_link('views/p5_about.py', label='關於資料與計算方法')
    st.caption('GR 裁切與 G14 接駁是另一組探索情境，不能與本頁保留既有路線的 G12／G14 比較混用效益。')
