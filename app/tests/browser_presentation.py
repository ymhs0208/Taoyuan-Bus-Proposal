"""Browser checks for presentation. Start the app on port 8601, then run from any directory."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screens"

with sync_playwright() as p:
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    browser = p.chromium.launch(executable_path=str(edge) if edge.exists() else None, headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    for route in ['scenario', 'overlap']:
        page.goto('http://localhost:8601/' + route)
        page.get_by_test_id('stMetric').first.wait_for(timeout=180000)
        page.wait_for_timeout(2500)
        assert page.get_by_test_id('stException').count() == 0
        if route == 'scenario':
            metrics = page.locator('[data-testid=stMetric]:visible')
            assert metrics.count() == 3, metrics.count()
            assert '+4.4' in metrics.nth(0).inner_text()
            assert '+1,313' in metrics.nth(1).inner_text()
            assert '2' in metrics.nth(2).inner_text()
            assert metrics.first.bounding_box()['y'] < page.get_by_role('button', name='A＋B 組合', exact=True).bounding_box()['y']
        page.screenshot(path=str(OUT / ('optimized_' + route + '.png')), full_page=True)
        print(route, 'visual smoke passed', flush=True)
        if route == 'overlap':
            frame = next(f for f in page.frames if f != page.main_frame and f.locator('.leaflet-container').count())
            assert frame.locator('path[stroke="#146b3a"]').count() > 0
            assert frame.locator('path[stroke="#7c8994"]').count() > 0
            assert frame.locator('.leaflet-tile-pane').evaluate('(el) => getComputedStyle(el).opacity') == '0.6'
    page.goto('http://localhost:8601/scenario')
    page.get_by_role('button', name='清除，回到 S0', exact=True).click()
    page.get_by_test_id('stMetric').first.filter(has_text='+0.0 班').wait_for(timeout=180000)
    assert '0 站' in page.get_by_test_id('stMetric').nth(2).inner_text()
    page.get_by_role('button', name='A＋B 組合', exact=True).click()
    page.get_by_test_id('stMetric').first.filter(has_text='+4.4 班').wait_for(timeout=180000)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto('http://localhost:8601/scenario')
    page.get_by_test_id('stMetric').first.wait_for(timeout=180000)
    page.screenshot(path=str(OUT / 'optimized_scenario_mobile.png'), full_page=True)
    assert page.get_by_test_id('stException').count() == 0
    assert page.locator('[data-testid=stMain]').evaluate('(el) => el.scrollWidth <= el.clientWidth')
    print('reset, restore, and mobile checks passed', flush=True)
    browser.close()
