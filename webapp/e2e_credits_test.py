"""Focused e2e for the credits / data-source attribution overlay (real Chrome)."""
import os, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8091/")
errors = []

EXPECT_SOURCES = ["iNaturalist", "GBIF", "eBird", "Wikimedia Commons",
                  "Catalogue of Life", "国土数値情報", "OpenStreetMap", "Nominatim"]
TITLES = {"ja": "データ出典", "en": "Data sources & credits",
          "zh": "数据来源与致谢", "zhT": "資料來源與致謝"}


def check(page):
    page.goto(BASE, wait_until="networkidle")
    # overlay hidden initially
    assert not page.locator("#credits").evaluate("e => e.classList.contains('on')"), "credits open on load"

    # open it
    page.click("#creditsBtn")
    page.wait_for_selector("#credits.on", timeout=5000)
    body = page.locator("#cbody").inner_text()
    for s in EXPECT_SOURCES:
        assert s in body, f"missing source credit: {s}"
    # per-source license chips present
    assert page.locator("#cbody .lic").count() >= 8, "license chips missing"
    # feedback link
    fb = page.locator("#cbody .fb a")
    assert "github.com" in (fb.get_attribute("href") or ""), "feedback link wrong"
    # 4 section headings
    assert page.locator("#cbody h3").count() == 4, "expected 4 source sections"

    # language switching re-renders the open overlay
    for l, want in TITLES.items():
        page.evaluate(f"App.setLang('{l}')")
        page.wait_for_timeout(120)
        h2 = page.locator("#cbody h2").inner_text()
        assert want in h2, f"lang {l}: title {h2!r} lacks {want!r}"
        # sources are language-neutral, still present
        assert "iNaturalist" in page.locator("#cbody").inner_text()

    # close via Escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(120)
    assert not page.locator("#credits").evaluate("e => e.classList.contains('on')"), "Escape did not close"

    # re-open + close via backdrop click
    page.click("#creditsBtn")
    page.wait_for_selector("#credits.on")
    page.mouse.click(5, 5)  # backdrop
    page.wait_for_timeout(120)
    assert not page.locator("#credits").evaluate("e => e.classList.contains('on')"), "backdrop did not close"

    print("CREDITS E2E: all assertions passed")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page()
    page.add_init_script("try { localStorage.setItem('pl_seen_about','1'); } catch(e) {}")  # skip first-visit greeting
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        check(page)
    finally:
        browser.close()

if errors:
    print("CONSOLE ERRORS:", *errors, sep="\n  ")
    sys.exit(1)
print("0 console errors — PASS")
