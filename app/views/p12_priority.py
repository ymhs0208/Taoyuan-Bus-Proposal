"""同資源比較與乘客效益。"""
import pandas as pd
import streamlit as st

from lib import passenger as B, plans as P

src, rts, stations = P.need()
st.title("先做哪一站？G12 與 G14 公平比較")
st.markdown("**先選主方案，再談裁切。** 兩站皆保留現有公車，各新增一條最多六個既有站牌的循環接駁，對照同一份現況。")
st.caption("比較的是候選路線與潛在人口；未預測實際搭乘人數。新線以點間直線乘繞行係數估計，待現地與排班驗證。")

mode = st.radio("公平比較條件", ["相同班次", "相同工時上限"], horizontal=True, key="priority_mode")
with st.expander("資源、步行與時間假設（可調）"):
    a, b, c = st.columns(3)
    trips = a.number_input("兩站各自每日整圈班次", 1, 150, 30, key="priority_trips")
    hours = b.number_input("兩站各自每日工時上限", 1.0, 48.0, 8.0, 0.5, key="priority_hours")
    service_hours = c.number_input("每日服務時段長度（小時）", 4.0, 24.0, 16.0, 1.0)
    speed = a.number_input("公車平均時速【假設】", 8.0, 40.0, 18.0, 0.5)
    factor = b.number_input("新線道路繞行係數【假設】", 1.0, 2.5, 1.3, 0.1)
    walk = c.number_input("步行時速【假設】", 2.0, 6.0, 3.0, 0.5)
    dwell = a.number_input("每站停靠分鐘【假設】", 0.0, 3.0, 0.5, 0.1)
    layover = b.number_input("每圈端點休息分鐘【假設】", 0.0, 30.0, 5.0, 1.0)
    rail = c.number_input("捷運班距分鐘【假設，非已公布班表】", 2.0, 30.0, 8.0, 1.0)
    st.caption("相同工時以完整整圈班次向下取整，列出未使用工時。此為含端點休息的車輛服務工時，尚非合法可執行的駕駛班表。")

params = dict(trips=trips, hours=hours, speed=speed, road_factor=factor, dwell=dwell,
              layover=layover, service_hours=service_hours, walk_kmh=walk, rail_headway=rail)
rows = B.current_comparison(mode=mode, **params)
if len(rows) != 2:
    st.warning("候選線或資料不齊，無法公平比較。")
    st.stop()
priority = B.recommend(rows, "補服務空白優先")
time_priority = B.recommend(rows, "改善到站時間優先")
selected = next((r for r in rows if r["station"] == priority), None)
if selected:
    st.success(f"**優先驗證主方案：{priority} 社區接駁。** 以「每服務工時新增多少原本不能一車到任一綠線站的長者」優先，"
               f"目前幾何估計為 {selected['first_per_hour']:.1f} 人／工時。此為模型排序，不是核定試辦路線。")
else:
    st.info("目前參數下無法明確區分主方案，應先補現地與需求資料。")
if time_priority:
    st.info(f"以每工時增加的「到站時間至少改善 1 分鐘」潛在人口排序：{time_priority} 優先。")
else:
    st.warning("目前條件下，時間效益沒有明確勝者；不能只憑人口覆蓋增加就宣稱更快。")

st.subheader("新增服務，還是增加到站選擇？")
comparison = []
for row in rows:
    comparison.append({"方案": row["station"], "每日整圈班次": row["trips"], "服務工時／日": round(row["hours"], 2),
                       "整圈估計分鐘": round(row["cycle_min"], 1), "估計班距分鐘": round(row["headway"], 1) if row["headway"] else None,
                       "首次可一車到任一站（人）": round(row["first"]), "已有服務、增加本站選擇（人）": round(row["choice"]),
                       "新增本站覆蓋合計（人）": round(row["target_gain"]),
                       "首次服務／工時": round(row["first_per_hour"], 1),
                       "時間改善至少1分（人）": round(row["improved"]), "改善者平均省下分鐘": round(row["mean_saved"], 1) if row["improved"] else None})
table = pd.DataFrame(comparison).set_index("方案").T
st.dataframe(table, width="stretch", column_config={"G12": st.column_config.NumberColumn(format="%.1f"),
                                                    "G14": st.column_config.NumberColumn(format="%.1f")})
st.caption("兩類人互斥：首次服務＋已有服務但增加本站選擇＝新增本站覆蓋。人口以格點去重、村里面積均分估計；有站牌或直達其他站，不等於已能直達本站。")
if mode == "相同工時上限":
    st.caption("未使用工時：" + "；".join(f"{r['station']} {r['unused_hours']:.2f} 小時" for r in rows)
               + "。班距以整日均勻發車推算，不代表尖峰班距。")

st.subheader("步行、候車與轉乘：同一群人前後比較")
st.markdown("每站固定比較本站 1.5 公里內的長者，目的地固定為該站；現況可選全程步行或有方向、可到站的既有公車，新增後再多一個接駁選項。保留較快的選擇。")
for row in rows:
    with st.expander(f"{row['station']}｜時間至少改善 1 分鐘：約 {row['improved']:,.0f} 人", expanded=True):
        if row["improved"]:
            st.dataframe(pd.DataFrame(row["components"]).round(2), hide_index=True, width="stretch")
            st.caption("現況與改後為同一批「至少改善 1 分鐘」的格點人口加權平均；變化負值代表省下時間。兩站族群不同，不以兩站的原始平均時間互相比快。")
        else:
            st.info("本模型下沒有達到 1 分鐘改善的長者；不把新增覆蓋直接換成節省時間，也不將無改善者平均節省寫成正值。")
        with st.expander("接駁各站的候車、車內與轉乘步行估計"):
            st.dataframe(pd.DataFrame(row["feeder_components"]).round(2), hide_index=True, width="stretch")

with st.expander("兩種資源條件下，優先順序是否一致？"):
    checks = []
    for compare_mode in ["相同班次", "相同工時上限"]:
        scenarios = B.current_comparison(mode=compare_mode, **params)
        checks.append({"條件": compare_mode, "補服務空白優先": B.recommend(scenarios, "補服務空白優先") or "無明確差異",
                       "時間效益優先": B.recommend(scenarios, "改善到站時間優先") or "無明確差異"})
    st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch")
    st.caption("同班次不等於同工時。排序以每實際服務工時的效益比較；人口覆蓋只表示是否存在服務，不反映班次充足性。")

with st.expander("方法、限制與下一步驗證"):
    st.markdown(f"""
- **候選線**：相同演算法、每站最多六個既有站牌、距目標站 300–1,500 公尺；各自最大化本站長者覆蓋。不是全路網最適解。
- **工時**：整圈直線公里 × 繞行係數 {factor:g} ÷ 時速 {speed:g}，另加每站停靠 {dwell:g} 分鐘及端點休息 {layover:g} 分鐘；兩站採同一組假設。未含場站空車與跨班調度。
- **人口分類**：沿用既有幾何覆蓋模型（站牌直線 300 公尺、車站步行等時圈 500 公尺）；未納入方向、時段與需求。時間模型另檢查上車後能依站序到站，故時間受益人口與覆蓋人口不相等。
- **步行**：採直線距離 ÷ 時速 {walk:g} 公里，是距離下限；不是已驗證無障礙步行路徑。
- **候車**：既有線以週三班次、新線以分配整圈班次，皆假設分布在 {service_hours:g} 小時內、等間隔且乘客隨機到站，期望候車＝服務分鐘 ÷ 班次 ÷ 2。未合併不同路線頻率、未使用站點實際到站班表，未計首末班邊界及脫班。
- **車內**：既有線使用實際線型里程與站序，新線用直線里程乘繞行係數；新線按單向循環線剩餘路程回站。不是直線到站即下車。
- **轉乘**：下車點至車站採直線步行；捷運候車以假設班距 {rail:g} 分鐘的一半估計，前後相同，改善量為零。未知出入口、月台內步行及銜接時刻尚未計入，不能聲稱省下轉乘次數。
- **時間終點**：到本站並等待捷運，不含捷運車程、最終目的地或票價。因此是到站時間估計，不是完整旅次時間或因果效益。
- **排序**：優先比較每工時首次服務人口；若兩線皆不足 0.5 人，才比較增加本站選擇人口／工時。分數相差不足 0.5 人／工時視為無明確差異。時間排序另列，不混成任意加權總分。
- **下一步**：先實查優先線道路及折返、測各站步行與行車時間、確認需求與班表，再做時速／繞行／班次敏感度分析與試辦。主方案是優先驗證，不能據此直接裁切 GR。
""")

export = pd.DataFrame([{**record, "比較條件": mode, **params} for record in comparison])
st.download_button("下載本次比較數據與假設", export.to_csv(index=False).encode("utf-8-sig"),
                   file_name="G12_G14_同資源比較.csv", mime="text/csv")
st.page_link("views/p3_scenario.py", label="再到情境模擬，檢查裁切與接駁組合", icon="🧪")
