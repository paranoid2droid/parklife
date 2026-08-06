"""E2E for the About/landing overlay + first-visit greeting (real Chrome)."""
import os, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8091/")
errors = []
SUBS = {"ja": "公園の生きもの地図", "en": "A map of life in Japan",
        "zh": "日本公园的生物地图", "zhT": "日本公園的生物地圖"}


def check(page):
    # --- first visit: About auto-opens (fresh storage) ----------------------
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_selector("#about.on", timeout=8000)
    body = page.locator("#abody").inner_text()
    assert "Parklife" in body
    assert page.locator("#abody ol li").count() == 4, "expected 4 how-to steps"
    # stats line eventually shows real counts (meta.json fetched)
    page.wait_for_function(
        "() => { const s=document.querySelector('#abody .stat'); return s && /[0-9],?[0-9]/.test(s.textContent); }",
        timeout=8000)
    stat = page.locator("#abody .stat").inner_text()
    assert "park" in stat.lower() or "公園" in stat or "公园" in stat, f"stat line odd: {stat}"

    # close with Get started -> persists, overlay hidden
    page.click("#abody .start-btn")
    page.wait_for_timeout(120)
    assert not page.locator("#about").evaluate("e => e.classList.contains('on')")
    assert page.evaluate("() => localStorage.getItem('pl_seen_about')") == "1"

    # --- reload: About does NOT auto-open second time ------------------------
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(600)
    assert not page.locator("#about").evaluate("e => e.classList.contains('on')"), "About re-nagged on 2nd visit"

    # --- brand click re-opens it, in every language -------------------------
    for l, want in SUBS.items():
        page.evaluate(f"App.setLang('{l}')")
        page.click("#brand")
        page.wait_for_selector("#about.on")
        sub = page.locator("#abody .sub").inner_text()
        assert want in sub, f"lang {l}: sub {sub!r} lacks {want!r}"
        page.keyboard.press("Escape")
        page.wait_for_timeout(80)

    # --- credits link inside About opens the credits overlay ----------------
    page.click("#brand")
    page.wait_for_selector("#about.on")
    page.click("#abody .credits-link a")
    page.wait_for_selector("#credits.on", timeout=3000)
    assert not page.locator("#about").evaluate("e => e.classList.contains('on')"), "About should close when opening credits"
    assert "iNaturalist" in page.locator("#cbody").inner_text()

    print("ABOUT E2E: all assertions passed")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context()  # fresh storage => first-visit path
    page = ctx.new_page()
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
