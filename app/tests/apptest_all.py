import sys
from streamlit.testing.v1 import AppTest

pages = [
    "views/p0_home.py",
    "views/p1_overlap.py",
    "views/p2_access.py",
    "views/p3_scenario.py",
    "views/p4_before_after.py",
    "views/p5_about.py",
]
failed = False
for i, p in enumerate(pages):
    at = AppTest.from_file("../app.py", default_timeout=300)
    at.run()
    if i == 0:
        titles = [t.value for t in at.title]
        print("default titles:", titles)
        if not any("綠線通車後" in t for t in titles):
            print("FAIL: default page is not 首頁")
            failed = True
        home_text = "\n".join(
            [m.value for m in at.markdown]
            + [c.value for c in at.caption]
            + [x.value for x in at.info]
        )
        print("  home metrics:", [(m.label, m.value, m.delta) for m in at.metric])
        checks = {
            "driver value 133.8": any(m.value == "133.8" for m in at.metric),
            "driver delta -4.4 / 138.1": any(m.delta and "-4.4" in m.delta and "138.1" in m.delta for m in at.metric),
            "G14 2,332": any(str(m.value).startswith("2,332") for m in at.metric),
            "G14 delta 1,018": any(m.delta and "1,018" in m.delta and "1,313" in m.delta for m in at.metric),
            "GR 4.40": any("4.40" in str(m.value) for m in at.metric),
            "G12 tradeoff": "8,806" in home_text and "8,773" in home_text and "-33" in home_text,
            "G15b tradeoff": "873" in home_text and "845" in home_text and "-28" in home_text,
            "GR before lengths": "17.31" in home_text and "17.25" in home_text,
            "industrial 12 and 8 with a stop": "12 塊" in home_text and "8 塊" in home_text,
            "assumption label": "估算，含假設" in home_text,
            "disclaimer": "展示版" in home_text and "試行分析" in home_text,
        }
        for name, ok in checks.items():
            print(f"  {'OK' if ok else 'FAIL'} {name}")
            failed = failed or not ok
        if [e.value for e in at.exception]:
            failed = True
    at.switch_page(p)
    at.run()
    exc = [e.value for e in at.exception]
    err = [e.value for e in at.error]
    print(p, "exceptions:", exc[:3], "errors:", err[:3], "titles:", [t.value for t in at.title])
    if exc:
        failed = True
    if p.endswith("p3_scenario.py"):
        pre = [(m.label, m.value, m.delta) for m in at.metric]
        print("  before click metrics:", pre)
        if not any(m.value == "133.8" for m in at.metric):
            print("FAIL: A+B was not preselected")
            failed = True
        btn = [b for b in at.button if b.label.startswith("A＋B")][0]
        btn.click()
        at.run()
        exc = [e.value for e in at.exception]
        print("  after A+B exceptions:", exc[:3])
        print("  metrics:", [(m.label, m.value, m.delta) for m in at.metric])
        if exc:
            failed = True
    if p.endswith("p1_overlap.py"):
        at.sidebar.radio[0].set_value("pdf")
        at.run()
        exc = [e.value for e in at.exception]
        print("  pdf exceptions:", exc[:3])
        if exc:
            failed = True

sys.exit(1 if failed else 0)
