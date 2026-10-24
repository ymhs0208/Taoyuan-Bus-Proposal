from streamlit.testing.v1 import AppTest

at = AppTest.from_file("../app.py", default_timeout=300).run()
at.switch_page("views/p12_priority.py").run()
assert not at.exception, [e.value for e in at.exception]
assert any("G12 社區接駁" in item.value for item in at.success)
table = at.dataframe[0].value
assert table.loc["首次可一車到任一站（人）", "G12"] > table.loc["首次可一車到任一站（人）", "G14"]
assert table.loc["每日整圈班次", "G12"] == table.loc["每日整圈班次", "G14"] == 30
for c in ["G12", "G14"]:
    assert abs(table.loc["首次可一車到任一站（人）", c] + table.loc["已有服務、增加本站選擇（人）", c]
               - table.loc["新增本站覆蓋合計（人）", c]) <= 1
at.radio(key="priority_mode").set_value("相同工時上限").run()
assert not at.exception, [e.value for e in at.exception]
table = at.dataframe[0].value
assert all(table.loc["服務工時／日"] <= 8)
assert all(table.loc["時間改善至少1分（人）"] == 0)
at.number_input(key="priority_hours").set_value(1.0).run()
assert not at.exception, [e.value for e in at.exception]
assert all(at.dataframe[0].value.loc["服務工時／日"] <= 1)
print("PASS: same trips, same capped hours, population categories, no invented time gains, low-resource case")
