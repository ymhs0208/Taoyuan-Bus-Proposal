"""情境模擬：A＋B 預設的駕駛人力與各項指標（印出供報告使用）。"""
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("../app.py", default_timeout=300); at.run()
at.switch_page("views/p3_scenario.py"); at.run()
[b for b in at.button if b.label.startswith("A＋B")][0].click(); at.run()
print("exceptions:", [e.value for e in at.exception])
for m in at.metric: print("METRIC|", m.label, "|", m.value, "|", m.delta)
for md in at.markdown:
    if "可移轉駕駛人力" in md.value: print("HEADLINE|", " ".join(md.value.split())[:600])
for df in at.dataframe:
    d = df.value
    if "速率來源" in getattr(d, "columns", []): print(d.to_string())
