"""情境模擬：規則檢查、S2a、S2b。執行：在 app/tests 內 python apptest_rules.py"""
import sys
from streamlit.testing.v1 import AppTest

fail = False
def check(name, ok, info=""):
    global fail
    fail |= not ok; print(("PASS " if ok else "FAIL ") + name, info)
def ex(at): return [e.value for e in at.exception]
def dfs(at): return [d.value for d in at.dataframe]
def find(at, col):
    return [d for d in dfs(at) if col in d.columns]

at = AppTest.from_file("../app.py", default_timeout=300); at.run(); at.switch_page("views/p3_scenario.py"); at.run()
check("載入無例外", not ex(at), ex(at))
r1 = find(at, "檢查")
check("預設 A+B 有規則一表", bool(r1))
if r1:
    print(r1[0].to_string(index=False))
    check("GR 兩方向各一列＋G14 新線一列", len(r1[0]) == 3, len(r1[0]))
cap = find(at, "每小時單向載客上限")
check("預設 A+B 有容量與長度表", bool(cap))
if cap:
    print(cap[0].to_string(index=False))
check("規則二寫明無法檢查", any("無法檢查" in i.value for i in at.info))

# S2b：G12
[b for b in at.button if b.label.startswith("S2b｜G12")][0].click(); at.run()
check("S2b G12 無例外", not ex(at), ex(at))
cap = find(at, "每小時單向載客上限")
check("S2b G12 後容量表含 G12 接駁線", bool(cap) and any("G12" in str(x) for x in cap[0]["接駁線"]))
if cap: print(cap[0].to_string(index=False))

# 改車型為桃小巴，載客上限應變小
before = int(cap[0]["每小時單向載客上限"].iloc[0])
at.radio(key="rl_veh").set_value("桃小巴"); at.run()
after = int(find(at, "每小時單向載客上限")[0]["每小時單向載客上限"].iloc[0])
check("改桃小巴後載客上限下降", after < before, f"{before}->{after}")

# S2a：選一條有鐵路端的路線套用
reset = [b for b in at.button if b.label.startswith("清除")][0]; reset.click(); at.run()
opts = at.selectbox(key="s2a_route").options
print("S2a 候選路線數", len(opts))
check("S2a 有候選路線", len(opts) > 0)
at.selectbox(key="s2a_code").set_value("G11"); at.run()
go = [b for b in at.button if b.key == "s2a_go"]
check("S2a 可套用", bool(go))
if go:
    go[0].click(); at.run()
    check("S2a 套用無例外", not ex(at), ex(at))
    r1 = find(at, "檢查")
    if r1:
        print(r1[0].to_string(index=False))
        check("S2a 列有轉乘步行距離", "轉乘步行(下限 m)" in r1[0].columns)
print("FAIL" if fail else "ALL PASS"); sys.exit(1 if fail else 0)
