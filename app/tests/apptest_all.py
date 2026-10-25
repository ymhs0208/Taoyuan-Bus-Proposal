import sys
from streamlit.testing.v1 import AppTest

pages = [
    "views/p0_home.py",
    "views/p1_overlap.py",
    "views/p2_access.py",
    "views/p3_scenario.py",
    "views/p12_priority.py",
    "views/p4_before_after.py",
    "views/p5_about.py",
    "views/p6_reliability.py",
    "views/p7_plan1.py",
    "views/p8_plan2.py",
    "views/p9_plan3.py",
    "views/p10_plan4.py",
    "views/p11_plan5.py",
]
failed = False
for i, p in enumerate(pages):
    at = AppTest.from_file("../app.py", default_timeout=300)
    at.run()
    if i == 0:
        titles = [t.value for t in at.title]
        print("default titles:", titles)
        if not any("真正需要" in t for t in titles):
            print("FAIL: default page is not 首頁")
            failed = True
        home_text = "\n".join(
            [m.value for m in at.markdown]
            + [c.value for c in at.caption]
            + [x.value for x in at.info]
        )
        print("  home metrics:", [(m.label, m.value, m.delta) for m in at.metric])
        checks = {
            "conditional decision": "可先進一步驗證" in home_text,
            "fleet tradeoff": "至少 2 輛" in home_text and "至少 1 輛" in home_text,
            "not actual passengers": "不是實際乘客" in home_text,
            "no legacy headline": not any(m.value == "133.8" for m in at.metric),
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
