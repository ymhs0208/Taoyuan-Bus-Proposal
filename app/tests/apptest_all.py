import sys
from streamlit.testing.v1 import AppTest
pages=["views/p1_overlap.py","views/p2_access.py","views/p3_scenario.py","views/p4_before_after.py","views/p5_about.py"]
for p in pages:
    at=AppTest.from_file("../app.py", default_timeout=300)
    at.run()
    at.switch_page(p); at.run()
    print(p, "exceptions:", [e.value for e in at.exception][:3], "errors:", [e.value for e in at.error][:3], "titles:", [t.value for t in at.title])
    if p.endswith("p3_scenario.py"):
        btn=[b for b in at.button if b.label.startswith("A＋B")][0]; btn.click(); at.run()
        print("  after A+B exceptions:", [e.value for e in at.exception][:3]); print("  metrics:", [(m.label,m.value,m.delta) for m in at.metric])
        sb=[s for s in at.selectbox if s.label.startswith("公車") ]
    if p.endswith("p1_overlap.py"):
        at.sidebar.radio[0].set_value("pdf"); at.run(); print("  pdf exceptions:", [e.value for e in at.exception][:3])
