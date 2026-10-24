"""以 headless Chrome 截圖每一頁（1280 寬）。用法：先 streamlit run app.py --server.port 8601，再執行本檔。"""
import sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8601"
OUT = Path(__file__).resolve().parent.parent / "screens"
OUT.mkdir(exist_ok=True)


def wait_ready(page, extra=4):
    page.wait_for_selector('[data-testid="stApp"]', timeout=120000)
    time.sleep(1.5)
    for _ in range(240):
        if page.locator('[data-testid="stStatusWidget"]').count() == 0 and page.locator('[data-testid="stSpinner"]').count() == 0:
            break
        time.sleep(0.5)
    time.sleep(extra)  # 地圖圖磚載入


def shot(page, path):
    """Streamlit 內容在內部捲動容器裡：先把視窗拉高到內容高度再截圖。"""
    h = page.evaluate("() => { const m = document.querySelector('[data-testid=stMain]') || document.body; return Math.max(m.scrollHeight, 900); }")
    page.set_viewport_size({"width": 1280, "height": min(int(h) + 40, 6000)})
    time.sleep(3)
    page.screenshot(path=str(path), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


def errors(page):
    return page.locator('[data-testid="stException"]').count()


with sync_playwright() as p:
    exe = "/usr/bin/google-chrome"
    b = p.chromium.launch(executable_path=exe if Path(exe).exists() else None, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
    shots = [("", "1_路線重疊地圖"), ("access", "2_接駁缺口"), ("scenario", "3_情境模擬_S0"),
             ("before-after", "4_通車前後比較"), ("about", "5_關於資料")]
    for path, name in shots:
        pg.goto(f"{BASE}/{path}")
        wait_ready(pg)
        shot(pg, OUT / f"{name}.png")
        print(name, "exceptions:", errors(pg))
    # 情境：載入 A＋B
    pg.goto(f"{BASE}/scenario")
    wait_ready(pg)
    pg.get_by_role("button", name="A＋B 組合").click()
    wait_ready(pg, extra=6)
    shot(pg, OUT / "3_情境模擬_A+B.png")
    print("3_情境模擬_A+B exceptions:", errors(pg))
    b.close()
