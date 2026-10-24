"""班距可靠度頁：可載入、有表格與指標、調門檻會改變結果。執行：在 app/tests 內 python apptest_reliability.py"""
import os, sys
sys.path.insert(0, os.path.abspath('..'))
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("../views/p6_reliability.py", default_timeout=300)
at.run()
assert not at.exception, at.exception
m = {x.label: x.value for x in at.metric}
print("metrics:", m, "| dataframes:", len(at.dataframe), "| titles:", [t.value for t in at.title])
ok = len(at.dataframe) >= 1 and int(m["可檢查的路線方向"]) > 0 and int(m["在門檻內"]) + int(m["超過門檻"]) == int(m["可檢查的路線方向"])
at.sidebar.slider[0].set_value(1.5); at.sidebar.slider[1].set_value(0.6); at.sidebar.slider[2].set_value(0.6).run()
m2 = {x.label: x.value for x in at.metric}
ok &= int(m2["在門檻內"]) == int(m2["可檢查的路線方向"])   # 門檻放到最寬，全部應通過
print("loose thresholds:", m2)
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
