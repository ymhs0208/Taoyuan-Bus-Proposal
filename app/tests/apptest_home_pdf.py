"""來源切換回歸：首頁主方案固定使用 TDX，其他來源必須提示不可混用。"""
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("../app.py", default_timeout=300)
at.session_state["source"] = "pdf"
at.run()
assert not at.exception, [e.value for e in at.exception]
assert any("主方案比較固定採交通部" in w.value and "不能混用" in w.value for w in at.warning)
assert not any("駕駛班次" in m.label for m in at.metric)
print("PASS: alternate map source does not change the TDX decision baseline")
