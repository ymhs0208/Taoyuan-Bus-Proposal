"""改良方案五頁：關鍵數字、互動。執行：在 app/tests 內 python apptest_plans.py"""
import sys
from streamlit.testing.v1 import AppTest

fail = False
def check(name, ok, info=""):
    global fail
    fail |= not ok; print(("PASS " if ok else "FAIL ") + name, info)
def ex(at): return [e.value for e in at.exception]
def mets(at): return {m.label: (m.value, m.delta) for m in at.metric}

at = AppTest.from_file("../app.py", default_timeout=300); at.run()
def go(p):
    at.switch_page(p); at.run(); assert not ex(at), (p, ex(at))

go("views/p7_plan1.py"); m = mets(at); print(m)
check("方案一 駕駛班次 138.1→132.8", m["平日約當駕駛班次"][0] == "132.8" and "138.1" in m["平日約當駕駛班次"][1])
check("方案一 有長者表與規則表", len(at.dataframe) >= 2)

go("views/p8_plan2.py"); m = mets(at); print(m)
check("方案二 G14 長者 2,332（+1,313）", m["可一車直達 G14 的 65 歲以上"][0].startswith("2,332") and "1,313" in m["可一車直達 G14 的 65 歲以上"][1])
at.sidebar.slider[0].set_value(3).run()
check("方案二 調站數無例外", not ex(at), ex(at))
v3 = mets(at)["可一車直達 G14 的 65 歲以上"][0]
check("方案二 站數 3 時人數 ≤ 站數 6 時", int(v3.split()[0].replace(",", "")) <= 2332, v3)
[r for r in at.sidebar.radio if r.label == "車型"][0].set_value("桃小巴").run()
check("方案二 改桃小巴無例外", not ex(at), ex(at))

go("views/p9_plan3.py"); m = mets(at); print(m)
check("方案三 800 m 長者約 1,379", any(v[0].startswith("1,379") for v in m.values()))
check("方案三 500 m 尖峰 4.2 班", any(v[0].startswith("4.2") for v in m.values()))
check("方案三 有候選地點表", len(at.dataframe) >= 1)

go("views/p10_plan4.py"); m = mets(at); print(m)
check("方案四 預設 703 有三個長度指標", len(m) >= 3)
at.selectbox(key="p4_code").set_value("G11").run()
check("方案四 換站無例外", not ex(at), ex(at))

go("views/p11_plan5.py"); m = mets(at); print(m)
check("方案五 有班距與成本指標", any("實際平均班距" in k for k in m) and any("車公里" in k for k in m))
at.slider[0].set_value(10).run()
check("方案五 調目標班距無例外", not ex(at), ex(at))
print("FAIL" if fail else "ALL PASS"); sys.exit(1 if fail else 0)
