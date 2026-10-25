"""同資源比較：區分相對效益、自訂門檻與尚待驗證事項。"""
import pandas as pd
import streamlit as st
from lib import passenger as B, plans as P

src, rts, stations = P.need()
st.title("G12、G14，哪一條值得先驗證？")
st.markdown("保留現有公車，兩站各新增一條候選循環接駁。先比較乘客效益，再檢查資源是否支持服務。")
st.caption("人口是村里面積均分的幾何估計，並非實際乘客；車速、繞行與班距均含假設。")
mode = st.radio("公平比較條件", ["相同班次", "相同工時上限"], horizontal=True, key="priority_mode")
with st.expander("調整資源、時間與篩選條件"):
    a, b, c = st.columns(3)
    trips = a.number_input("兩站各自每日整圈班次", 1, 150, 30, key="priority_trips")
    hours = b.number_input("兩站各自每日車輛服務工時上限", 1.0, 48.0, 8.0, 0.5, key="priority_hours")
    service_hours = c.number_input("每日服務時段長度（小時）", 4.0, 24.0, 16.0, 1.0)
    speed = a.number_input("公車平均時速【假設】", 8.0, 40.0, 18.0, 0.5)
    factor = b.number_input("新線道路繞行係數【假設】", 1.0, 2.5, 1.3, 0.1)
    walk = c.number_input("步行時速【假設】", 2.0, 6.0, 3.0, 0.5)
    dwell = a.number_input("每站停靠分鐘【假設】", 0.0, 3.0, 0.5, 0.1)
    layover = b.number_input("每圈端點休息分鐘【假設】", 0.0, 30.0, 5.0, 1.0)
    rail = c.number_input("捷運班距分鐘【假設，非已公布班表】", 2.0, 30.0, 8.0, 1.0)
    max_headway = a.number_input("可接受最長班距（分鐘，自訂）", 10, 120, 40, 5, key="priority_max_headway")
    max_fleet = b.number_input("每條候選線可投入車數（自訂）", 1, 10, 2, key="priority_max_fleet")
    st.caption("40 分鐘、2 輛為本頁可調的示範門檻，不是官方標準或已承諾資源。車輛服務工時包含端點休息，尚非駕駛班表。")
params = dict(trips=trips, hours=hours, speed=speed, road_factor=factor, dwell=dwell,
              layover=layover, service_hours=service_hours, walk_kmh=walk, rail_headway=rail)
rows = B.current_comparison(mode=mode, **params)
if len(rows) != 2:
    st.warning("候選線或資料不齊，無法公平比較。")
    st.stop()
priority = B.screened_priority(rows, max_headway, max_fleet)
spatial_rank = B.recommend(rows, "補服務空白優先")
screens = {r["station"]: B.screen(r, max_headway, max_fleet) for r in rows}
if priority:
    st.info(f"**{priority} 社區接駁可優先進一步驗證。** 每工時首次覆蓋人口排序較前，且通過本頁自訂的班距、車數及正時間效益條件；尚不能據此開線。")
else:
    st.warning("**目前沒有可優先推進的主方案。** 相對效益較高，不代表資源或時間效益已達條件；請先調整服務配置或補足證據。")
st.caption(f"幾何補空白排序：{spatial_rank or '無明確差異'}。候選線先以「本站覆蓋」產生，再以「首次覆蓋／工時」比較，目標不同，因此只比較這兩條候選線，不能聲稱找到最優路線。")
st.warning("兩線道路可通行性、實際需求、無障礙步行、車輛及合法駕駛排班均待查證；通過自訂條件也不等於已通過現地驗證。")

st.subheader("先看三個乘客效益")
def people(value):
    return "不足 1 人" if 0 < value < 1 else f"約 {value:,.0f} 人"
a, b, c = st.columns(3)
for col, field, label in [(a, "first", "首次覆蓋任一站"), (b, "choice", "已有服務、增加本站選擇"), (c, "improved", "到站時間至少改善 1 分鐘")]:
    with col:
        st.markdown(f"**{label}**")
        for row in rows:
            st.write(f"{row['station']}：{people(row[field])}")
st.caption("前兩類互斥，合計為新增本站覆蓋；時間改善另用方向與時間模型計算，與前兩類可能重疊，不能相加。小數反映人口分配方法，不代表可識別的實際人數。")

st.subheader("資源夠不夠？")
resources = []
for row in rows:
    gate = screens[row["station"]]
    resources.append({"方案": row["station"], "每日整圈": row["trips"],
        "車輛服務工時／日": f"{row['hours']:.1f}", "估計班距": f"約 {row['headway']:.0f} 分鐘" if row['headway'] else "無服務",
        "理想最少車數": str(gate['fleet']) if gate['fleet'] else "無服務", "篩選結果": gate['status'],
        "未達原因": "；".join(gate['reasons']) or "仍須現地、需求及排班驗證"})
st.dataframe(pd.DataFrame(resources), hide_index=True, width="stretch")
st.caption("理想最少車數＝整圈含休息時間／均勻發車班距，向上取整；未含備援、空車調度及尖峰壅塞，不能當成採購或人力結論。同班次不等於同工時。")
if mode == "相同工時上限":
    st.caption("完整班次向下取整，未使用工時：" + "；".join(f"{r['station']} 約 {r['unused_hours']:.1f} 小時" for r in rows))

st.subheader("到站旅程示例：真的比較快嗎？")
st.markdown("選一個候選站牌附近的模型格點，比較前後同一起點到同一車站。起點固定，不挑選省時最多的人。")
code = st.selectbox("目的車站", [r['station'] for r in rows], key="journey_station")
row = next(r for r in rows if r['station'] == code)
examples = row.get('examples', [])
if examples:
    index = st.selectbox("起點示例", range(len(examples)), format_func=lambda i: examples[i]['stop'] + "附近格點", key=f"journey_stop_{code}")
    example = examples[index]
    st.caption(f"起點為 {code} 研究範圍內、距該站牌最近的正人口 25 公尺格點，直線距站牌約 {example['distance']:.0f} 公尺；不是住戶、受訪者或實測旅次。")
    st.dataframe(pd.DataFrame(example['parts']).round(1), hide_index=True, width="stretch")
    st.info("新增後模型選用接駁。" if example['feeder'] else "新增後仍選現況較快的方式；此起點不能用來宣稱接駁省時。")
else:
    st.info("本次沒有可展示的有效班次或起點。")
st.caption("時間終點僅到本站並等待捷運；不含月台內步行、捷運車程、最終目的地、票價。模型容許全程步行到站，因此不適用於無法長距離步行者；不是完整長者旅次可及性證據。")

with st.expander("完整人口、時間比較與計算明細"):
    comparison = []
    for r in rows:
        comparison.append({"方案": r['station'], "每日整圈班次": r['trips'], "服務工時／日": r['hours'],
            "整圈估計分鐘": r['cycle_min'], "估計班距分鐘": r['headway'],
            "首次覆蓋任一站（人）": r['first'], "已有服務、增加本站選擇（人）": r['choice'],
            "新增本站覆蓋合計（人）": r['target_gain'], "首次覆蓋／工時": r['first_per_hour'],
            "時間改善至少1分（人）": r['improved'], "改善者平均省下分鐘": r['mean_saved'] if r['improved'] else None})
    display = []
    for record in comparison:
        item = {}
        for key, value in record.items():
            if key == '方案': item[key] = value
            elif value is None: item[key] = '無改善／無服務'
            elif '（人）' in key: item[key] = people(value)
            elif key == '每日整圈班次': item[key] = str(value)
            else: item[key] = f'{value:.1f}'
        display.append(item)
    st.dataframe(pd.DataFrame(display).set_index('方案').T, width="stretch")
    st.caption("顯示值經四捨五入，合計可能有尾差；下載保留模型原始數值以利重算，不代表同等測量精度。")
    for r in rows:
        st.markdown(f"**{r['station']}：同一批至少改善 1 分鐘的格點人口**")
        if r['improved']:
            st.dataframe(pd.DataFrame(r['components']).round(1), hide_index=True, width="stretch")
        else:
            st.write("沒有達門檻的改善人口，平均省時不適用。")

with st.expander("兩種資源條件是否得到相同結論？"):
    checks = []
    for compare_mode in ["相同班次", "相同工時上限"]:
        scenarios = B.current_comparison(mode=compare_mode, **params)
        checks.append({"條件": compare_mode, "幾何補空白排序": B.recommend(scenarios, "補服務空白優先") or "無明確差異",
                       "通過自訂條件後可先驗證": B.screened_priority(scenarios, max_headway, max_fleet) or "無",
                       "時間效益排序": B.recommend(scenarios, "改善到站時間優先") or "無明確差異"})
    st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch")

with st.expander("方法、限制與停止條件"):
    st.markdown(f"""
- **候選產生**：相同貪婪演算法，各站最多六個既有站牌、距目標站 300–1,500 公尺，逐次增加本站覆蓋；沒有同時最佳化工時、首次覆蓋或實際搭乘需求。
- **人口覆蓋**：站牌直線 300 公尺、車站步行等時圈 500 公尺，人口以村里面積均分格點去重。存在服務不等於方向、營運時段與頻率都能使用。
- **工時**：整圈直線里程乘繞行係數 {factor:g}、除時速 {speed:g}，加每站停靠 {dwell:g} 分鐘與端點休息 {layover:g} 分鐘。未含空車、跨班調度與備援。
- **時間**：步行用直線距離，既有車內用線型及可到站的站序，新線用循環剩餘路程乘繞行係數。既有線依週三班次、新線依分配班次，假設在 {service_hours:g} 小時均勻發車，候車為班距一半；未合併多線頻率或使用真實站點到站時刻。
- **轉乘**：另加下車至站點直線步行、假設捷運候車 {rail:g}／2 分鐘；未知出入口與站內步行未計，不聲稱減少轉乘次數。
- **相對排序**：首次覆蓋／實際服務工時優先；兩線首次覆蓋皆不足 0.5 人，改比增加本站選擇／工時。差距不足 0.5 人／工時視為無明確差異；時間效益另列。
- **先不推進**：相對排序第一者若超過自訂班距、車數，或沒有至少 1 分鐘時間改善人口，本頁不列優先驗證方案，也不自動改推第二名。道路、需求、步行或排班未通過現地驗證時，不應直接開線或裁切 GR。
- **下一步**：道路與折返實查 → 步行及乘車計時 → 需求訪談與排班 → 重新校準模型 → 小規模試辦並量測。現在尚無完整旅次或通車後成效證據。
""")
export = pd.DataFrame([{**record, "比較條件": mode, **params, "自訂最長班距": max_headway,
                       "自訂可投入車數": max_fleet, "篩選結果": screens[record['方案']]['status'],
                       "資料性質": "幾何人口及假設時間估計；非實際乘客或實測成效"} for record in comparison])
st.download_button("下載本次比較數據與假設", export.to_csv(index=False).encode('utf-8-sig'), file_name='G12_G14_同資源比較.csv', mime='text/csv')
st.page_link('views/p3_scenario.py', label='進階：再探索裁切與接駁組合', icon='🧪')
