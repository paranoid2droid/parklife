"""E2E for geolocation: auto-locate on load + the "my location" button.

Separate from e2e_test.py because it needs a geolocation-granted context with a
mocked position. Drives real Chrome (playwright channel="chrome") against a
static build served over http (geolocation needs a secure context; localhost
qualifies).

Run:
    cd site && python -m http.server 8094 &     # serve a fresh export_static build
    BASE=http://127.0.0.1:8094/ .venv/bin/python webapp/e2e_geo_test.py
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8094/")
# Mock position near Tokyo Station: inside Japan, many parks within 30 km.
GEO = {"latitude": 35.681, "longitude": 139.767}
errors: list[str] = []


def check(page) -> None:
    # --- auto-locate on first load ------------------------------------------
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_selector(".leaflet-marker-icon, .marker-cluster", timeout=15000)
    # autoLocate is async (getCurrentPosition); it recentres from the national
    # default (36.2,138.2) to the user and opens the nearest park.
    page.wait_for_function(
        "() => Math.abs(map.getCenter().lat - 35.681) < 0.6 "
        "&& Math.abs(map.getCenter().lng - 139.767) < 0.6",
        timeout=8000)
    assert page.evaluate("!!userLayer && userLayer.getLayers().length > 0"), \
        "no user-location marker after auto-locate"
    assert page.locator(".park-name").count() > 0, "auto-locate did not open nearest park"

    # --- the "my location" button -------------------------------------------
    assert page.locator("#locateBtn").count() == 1, "locate button missing"
    page.wait_for_timeout(400)
    # drag the map away (real interaction), then the button recentres on the user
    page.mouse.move(600, 400); page.mouse.down()
    page.mouse.move(280, 180, steps=8); page.mouse.up()
    page.wait_for_timeout(250)
    page.locator("#locateBtn").click()
    page.wait_for_function(
        "() => Math.abs(map.getCenter().lat - 35.681) < 0.6 "
        "&& Math.abs(map.getCenter().lng - 139.767) < 0.6",
        timeout=8000)

    # --- button title is i18n ------------------------------------------------
    page.evaluate("App.setLang('en')")
    assert page.get_attribute("#locateBtn", "title") == "My location"
    page.evaluate("App.setLang('ja')")
    assert page.get_attribute("#locateBtn", "title") == "現在地に移動"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(
            viewport={"width": 1200, "height": 820},
            geolocation=GEO, permissions=["geolocation"], locale="ja-JP")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        try:
            check(page)
        finally:
            browser.close()
    if errors:
        print("FAIL — console/page errors:")
        for e in errors[:20]:
            print("  ", e)
        return 1
    print("GEO E2E PASS — auto-locate + my-location button OK, 0 console errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
