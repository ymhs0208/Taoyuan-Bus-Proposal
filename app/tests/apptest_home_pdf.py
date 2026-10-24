"""回歸：路線來源選「市府站牌表（pdf）」時，首頁不可顯示 0.0 駕駛班次，且須有來源警示。執行：python apptest_home_pdf.py（在 app/tests 內）"""
import sys
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("../app.py", default_timeout=300)
at.session_state["source"] = "pdf"
at.run()
assert not at.exception, at.exception
drv = [m for m in at.metric if m.label == "平日約當駕駛班次"]
warn = [w.value for w in at.warning]
ok = bool(drv) and drv[0].value == "—" and any("站牌表" in w for w in warn)
print("driver metric:", [(m.label, m.value) for m in drv], "| warnings:", len(warn))
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
