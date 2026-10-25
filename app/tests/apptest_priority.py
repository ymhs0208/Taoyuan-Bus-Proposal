from streamlit.testing.v1 import AppTest
at = AppTest.from_file('../app.py', default_timeout=300).run()
assert not at.exception, [e.value for e in at.exception]
at.switch_page('views/p12_priority.py').run()
assert not at.exception, [e.value for e in at.exception]
assert any('G12 社區接駁可優先' in x.value for x in at.info)
assert not at.success
resources=at.dataframe[0].value
assert list(resources['理想最少車數']) == ['2', '1']
assert any('不足 1 人' in m.value for m in at.markdown)
assert any('項目' in d.value.columns for d in at.dataframe)
at.number_input(key='priority_max_fleet').set_value(1).run()
assert any('沒有可優先推進' in x.value for x in at.warning)
at.number_input(key='priority_max_fleet').set_value(2).run()
at.radio(key='priority_mode').set_value('相同工時上限').run()
assert not at.exception, [e.value for e in at.exception]
assert any('沒有可優先推進' in x.value for x in at.warning)
assert all(at.dataframe[0].value['篩選結果'] == '未達自訂條件')
at.number_input(key='priority_hours').set_value(1.0).run()
assert not at.exception, [e.value for e in at.exception]
assert not at.success
print('PASS: conditional decision, fleet ceiling, low hours, readable precision and journey example')
