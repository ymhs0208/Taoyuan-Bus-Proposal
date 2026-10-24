from streamlit.testing.v1 import AppTest
def ex(at): return [e.value for e in at.exception]
at=AppTest.from_file("../app.py", default_timeout=300); at.run(); at.switch_page("views/p3_scenario.py"); at.run()
# 截短
at.radio(key="md_op").set_value("截短（只保留部分站序）"); at.run(); print("keep_range ui", ex(at))
[b for b in at.button if b.key=="md_add"][0].click(); at.run(); print("keep_range add", ex(at), [m.value for m in at.metric][-1])
at.radio(key="md_op").set_value("整條停駛"); at.run(); at.selectbox(key="md_route").set_value(at.selectbox(key="md_route").options[5] if False else at.selectbox(key="md_route").value); at.run()
[b for b in at.button if b.key=="md_add"][0].click(); at.run(); print("remove add", ex(at), [m.value for m in at.metric])
# 自訂接駁 G13
at.selectbox(key="fd_station").set_value("G13"); at.run()
[b for b in at.button if b.label.startswith("🤖")][0].click(); at.run(); print("auto pick", ex(at), at.multiselect(key="fd_stops").value)
[b for b in at.button if b.key=="fd_add"][0].click(); at.run(); print("feeder add", ex(at), [(m.label[:12],m.value,m.delta) for m in at.metric])
# PDF 來源
at.sidebar.radio[0].set_value("pdf"); at.run(); print("pdf scenario", ex(at))
[b for b in at.button if b.label.startswith("A＋B")][0].click(); at.run(); print("pdf A+B", ex(at), [(m.value,m.delta) for m in at.metric])
at2=AppTest.from_file("../app.py", default_timeout=300); at2.run(); at2.select_slider[0].set_value(800); at2.run(); print("p1 800", ex(at2))
