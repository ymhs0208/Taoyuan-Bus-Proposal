"""把產業用地代理指標存成快照 CSV（供提案引用）：derived/A4_industrial_by_station.csv、A4_industrial_reach.csv、A4_industrial_summary.csv。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import datetime, pandas as pd
from lib import data as D, metrics as M, proxy as X
ind = X.load_industrial()
net0 = M.build_network("tdx", [], []); e0 = M.evaluate(net0, 300)
T1 = X.station_table(ind, D.isochrones())
T2, summ = X.reach_table(ind, D.stations(), D.stop_positions(D.routes("tdx")), e0["conn_by_station"], 300)
ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M (UTC+8)")
for df in (T1, T2):
    df["computed_at"] = ts
T1.to_csv(X.DERIVED / "A4_industrial_by_station.csv", index=False, encoding="utf-8-sig")
T2.to_csv(X.DERIVED / "A4_industrial_reach.csv", index=False, encoding="utf-8-sig")
pd.DataFrame([dict(summ, computed_at=ts)]).round(2).to_csv(X.DERIVED / "A4_industrial_summary.csv", index=False, encoding="utf-8-sig")
print(T1.pivot(index="code", columns="dist_m", values="ind_ha")); print(summ)
print(T2.groupby("nearest_station").agg(n=("area_ha", "size"), ha=("area_ha", "sum"), any=("stop_within_R", "sum"), direct=("direct_within_R", "sum")))
