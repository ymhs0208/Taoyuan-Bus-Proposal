"""Start Streamlit on 8601, then run this browser check from any directory."""
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parents[1] / "screens"
with sync_playwright() as p:
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser = p.chromium.launch(executable_path=str(edge) if edge.exists() else None, headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    page.goto("http://localhost:8601/priority")
    page.get_by_text("進階：再探索裁切與接駁組合", exact=True).wait_for(timeout=180000)
    assert page.get_by_test_id("stException").count() == 0
    page.get_by_text("G12 社區接駁可優先進一步驗證。", exact=False).first.wait_for()
    page.locator('[data-testid="stSpinner"]').wait_for(state="hidden", timeout=180000)
    page.wait_for_timeout(1500)  # Let Streamlit finish applying responsive element widths.
    page.screenshot(path=str(out / "priority_same_trips.png"), full_page=True)
    page.get_by_text("相同工時上限", exact=True).click()
    page.get_by_text("目前沒有可優先推進的主方案", exact=False).first.wait_for(timeout=180000)
    assert page.get_by_test_id("stException").count() == 0
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "priority_same_hours.png"), full_page=True)
    page.goto("http://localhost:8601/scenario")
    page.get_by_test_id("stMetric").first.wait_for(timeout=180000)
    page.get_by_text("G14 新增到站服務：哪些是首次服務", exact=False).click()
    page.locator('[data-testid=stDataFrame]:visible').first.wait_for()
    assert page.get_by_test_id("stException").count() == 0
    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.goto("http://localhost:8601/priority")
    mobile.get_by_text("進階：再探索裁切與接駁組合", exact=True).wait_for(timeout=180000)
    mobile.wait_for_timeout(1500)
    mobile.screenshot(path=str(out / "priority_mobile.png"), full_page=True)
    assert mobile.locator('[data-testid=stMain]').evaluate('(el) => el.scrollWidth <= el.clientWidth')
    page.goto("http://localhost:8601/")
    page.get_by_text("進階探索與資料核對", exact=True).wait_for(timeout=180000)
    assert page.get_by_test_id("stException").count() == 0
    assert page.get_by_text("Page not found", exact=True).count() == 0
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "home_decision.png"), full_page=True)
    print("PASS: priority page, capped resource warning, mobile layout, scenario population breakdown")
    browser.close()
