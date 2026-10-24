"""Generate the research note from the same calculations as the comparison page."""
import json
import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from lib import data as D, passenger as B


def markdown_table(rows):
    headers = list(rows[0])
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"]*len(headers)) + " |"]
    lines += ["| " + " | ".join(str(r[h]) for h in headers) + " |" for r in rows]
    return "\n".join(lines)


def build():
    sections, output = [], []
    for mode in ["相同班次", "相同工時上限"]:
        rows = B.current_comparison(mode=mode)
        records = []
        for r in rows:
            records.append({"方案": r["station"], "每日整圈班次": r["trips"], "服務工時": round(r["hours"], 2),
                            "首次直達任一站長者": round(r["first"]), "增加本站選擇長者": round(r["choice"]),
                            "首次直達人口每工時": round(r["first_per_hour"], 1),
                            "到站改善至少1分鐘長者": round(r["improved"]),
                            "改善者平均省下分鐘": round(r["mean_saved"], 2) if r["improved"] else "無改善族群"})
            output.append(dict(mode=mode, **{k:v for k,v in r.items() if k not in ["feeder", "components", "feeder_components"]}))
        sections.append(f"## {mode}\n\n" + markdown_table(records))
        sections.append("補服務空白優先：" + str(B.recommend(rows, "補服務空白優先") or "無明確差異") + "。時間效益優先："
                        + str(B.recommend(rows, "改善到站時間優先") or "無明確差異") + "。")
        for r in rows:
            if r["improved"]:
                comp = [{k:round(v, 2) if isinstance(v,float) else v for k,v in a.items()} for a in r["components"]]
                sections.append(f"### {r['station']} 同一改善族群的時間分解\n\n" + markdown_table(comp))
    sensitivity = []
    for factor, walking in [(1.1, 3.0), (1.6, 3.0), (1.3, 2.5), (1.3, 4.0)]:
        rows = B.current_comparison(road_factor=factor, walk_kmh=walking)
        sensitivity.append({"條件": "每日各30班", "繞行係數": factor, "步行時速": walking,
                            "覆蓋優先": B.recommend(rows, "補服務空白優先") or "無明確差異",
                            "時間優先": B.recommend(rows, "改善到站時間優先") or "無明確差異",
                            "G12時間改善人口": round(rows[0]["improved"]), "G14時間改善人口": round(rows[1]["improved"])})
    text = """# G12／G14 主方案比較與乘客效益（模型試行）

本報告由平台相同計算流程產生；資料為目前已提交快照，並非現地量測或實際乘客旅次。兩方案各自新增一條接駁線，不裁切 GR、不強迫原乘客改搭。

## 共同條件

- 既有服務、300 公尺站牌接近門檻、500 公尺車站步行等時圈、每站 1.5 公里研究範圍一致；最多選六個既有站牌。
- 同班次比較：各每日30整圈。工時上限比較：各每日8小時，完整班次向下取整，未使用工時留白。
- 公車時速18公里、新線繞行係數1.3、每站停靠0.5分鐘、每圈端點休息5分鐘，全部為假設；既有線行駛使用實際線型。
- 服務時段16小時且等間隔發車，步行時速3公里，捷運班距8分鐘，全部為假設。捷運候車前後相同，不能宣稱改善。
- 每工時是每車輛服務工時，不是已驗證的駕駛班表；仍缺空車、輪休與跨班調度。

## 人口與時間口徑

首次直達：現況不能一車到任一研究車站，新增線後可到目標站的長者。
增加選擇：現況已有任一研究車站直達服務，新增線後多了目標站的長者。兩類互斥；均非新乘客人數。

覆蓋沿用幾何模型，尚未核對方向及發車時段；時間估計另檢查既有路線上車後能按站序到達目標站，循環接駁依剩餘圈長回站。
每站固定同一目的站與居住人口，現況可選步行或既有直達公車，新增後多一個接駁選項，保留較快選擇。沒有強迫轉乘，也不假設既有兩車轉乘旅程。
時間效益人口是模型中至少改善1分鐘者，前後平均固定使用這一群人。人口按村里面積均分；不是實際旅次、因果效益或完整門到門時間。

""" + "\n\n".join(sections) + "\n\n## 假設敏感度（每日各30班）\n\n" + markdown_table(sensitivity) + """

## 主方案與實作順序

在現有資料與預設模型下，以每服務工時首次直達人口為優先，選 G12 社區接駁作為優先現地驗證主方案，G14 保留為備選。這是兩條貪婪法候選線的比較，不是全路網最適解，也不是核定營運方案。

若僅有8小時工時卻分散服務16小時，覆蓋增加不代表候車時間改善。應進一步比較集中服務時段或增加資源；不能直接把30班的時間效益移用到8小時情境。

優先實查 G12 候選站牌、道路可通行性及折返；記錄尖離峰行車、停站、步行與轉乘時間，以實測替代假設。再確認需求、上下車量及排班可行性，才提出是否裁切 GR 的組合方案。

## 仍不能宣稱的效益

不能把增加到站選擇說成新增搭乘者；不能將兩站人數相加；不能宣稱省下實際轉乘次數；不能以模型車輛工時宣稱已能移轉同量駕駛人力。
步行為直線下限，未知出入口與月台動線未納入；候車以起點班次推估整日均勻班距，未處理脫班與首末班；未納入票價、最終目的地或實際搭乘意願。
"""
    report = APP.parent / "docs" / "scenario" / "G12_G14_主方案與乘客效益.md"
    report.write_text(text, encoding="utf-8")
    pd.DataFrame(output).to_csv(APP / "derived" / "G12_G14_passenger_comparison.csv", index=False, encoding="utf-8-sig")
    (APP / "derived" / "G12_G14_passenger_assumptions.json").write_text(json.dumps(
        dict(speed=18, road_factor=1.3, dwell_min=0.5, layover_min=5, service_hours=16,
             walk_kmh=3, rail_headway_min=8, trips=30, hours_cap=8, sensitivity=sensitivity,
             data_signatures={rel: D.sig(rel) for rel in ["outputs/A2_isochrones.gpkg", "data/villages_pop65.gpkg",
                  "data/stations_green_north.csv", "data/tdx/stop_of_route.csv", "data/tdx/Shape_Taoyuan.json.gz",
                  "data/tdx/Schedule_Taoyuan_800m_routes.json.gz"]}), ensure_ascii=False, indent=2), encoding="utf-8")
    print(report, flush=True)


if __name__ == "__main__":
    build()
