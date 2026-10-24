"""打包：app/ ＋ pilot 資料快照（複製，不移動），輸出 ../綠線接駁決策平台_展示版.zip。
排除：.venv、__pycache__、金鑰／環境檔（.env*、*secret*、*token*、*.pid、.tdx_last_call）、logs/、原始 PDF、HTML 暫存、app/derived/raw（產管局原始 SHP，可用 tools/build_official_parks.py 重新下載）。
A1 即時收集檔：總量 ≤ 30 MB 才放入（只放當下快照）。"""
import fnmatch, os, shutil, sys, tempfile, zipfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
ROOT = APP.parent
PILOT = ROOT / "pilot"
OUT = ROOT / "綠線接駁決策平台_展示版.zip"
TOP = "綠線接駁決策平台_展示版"
EXCL = [".venv", "__pycache__", ".env", ".env.*", "*.env", "*secret*", "*token*", "*.pid", ".tdx_last_call", "*.pyc", ".DS_Store"]
PILOT_FILES = [
    "README.md",
    "data/stations_green_north.csv", "data/stations_retrieved_at.txt",
    "data/villages_pop65.gpkg", "data/taoyuan_village_pop65_11509.csv",
    "data/route_stops_parsed.csv", "data/parse_report.csv",
    "data/tdx/stop_of_route.csv", "data/tdx/Shape_Taoyuan.json.gz", "data/tdx/Shape_retrieved_at.txt",
    "data/tdx/StopOfRoute_retrieved_at.txt", "data/tdx/Schedule_retrieved_at.txt",
    "config/collector_routes.txt",
]
PILOT_GLOBS = ["outputs/*", "data/tdx/Schedule_*.json.gz"]
A1_MAX = 30e6


def bad(name):
    return any(fnmatch.fnmatch(name.lower(), p) for p in EXCL)


def main():
    files = []
    for dp, dns, fns in os.walk(APP):
        dns[:] = [d for d in dns if not bad(d) and not (Path(dp).name == "derived" and d == "raw")]
        for f in fns:
            if not bad(f):
                p = Path(dp) / f
                files.append((p, Path(TOP) / "app" / p.relative_to(APP)))
    sel = set(PILOT_FILES)
    for g in PILOT_GLOBS:
        sel |= {str(p.relative_to(PILOT)) for p in PILOT.glob(g) if p.is_file()}
    a1 = sorted(PILOT.glob("data/a1/a1_*.csv*"))
    if a1 and sum(p.stat().st_size for p in a1) <= A1_MAX:
        sel |= {str(p.relative_to(PILOT)) for p in a1}
    for rel in sorted(sel):
        p = PILOT / rel
        if p.is_file() and not bad(p.name):
            files.append((p, Path(TOP) / "pilot" / rel))
    with tempfile.TemporaryDirectory() as td:  # 先複製成快照（避免收集器寫入中途被打包）
        tmp = Path(td) / "out.zip"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for src, arc in files:
                c = Path(td) / "snap"
                shutil.copy2(src, c)
                z.write(c, str(arc))
        shutil.copy2(tmp, OUT)
    print(OUT, round(OUT.stat().st_size / 1e6, 2), "MB", len(files), "files")


if __name__ == "__main__":
    main()
