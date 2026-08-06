"""E2E for #3b: 'in season this month' discovery (real Chrome)."""
import os, sys, datetime
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8091/")
errors = []
CUR_MONTH = datetime.date.today().month


def check(page):
    page.goto(BASE, wait_until="networkidle")
    # empty-state has both discovery buttons
    page.wait_for_selector(".near-btn.alt", timeout=8000)

    # open season (no arg -> auto-load current month)
    page.evaluate("App.discoverSeason()")
    page.wait_for_selector(".grid .card", timeout=8000)
    # month <select> defaults to the current month
    sel = int(page.locator(".controls select").input_value())
    assert sel == CUR_MONTH, f"season did not auto-load current month: got {sel}, want {CUR_MONTH}"
    n_cards = page.locator(".grid .card").count()
    assert n_cards > 0, "no season cards"
    hdr = page.locator(".park-name").inner_text()
    assert "🌸" in hdr

    # show-more grows the list
    if page.locator(".more-btn").count():
        before = page.locator(".grid .card").count()
        page.locator(".more-btn").click()
        page.wait_for_timeout(150)
        assert page.locator(".grid .card").count() > before, "show-more did not add cards"

    # switching month re-loads a different shard
    other = 6 if CUR_MONTH != 6 else 12
    page.select_option(".controls select", str(other))
    page.wait_for_timeout(300)
    assert int(page.locator(".controls select").input_value()) == other
    assert page.locator(".grid .card").count() > 0

    # a card opens the species modal (no park context)
    page.locator(".grid .card").first.click()
    page.wait_for_selector("#modal.on", timeout=8000)
    assert page.locator("#mbody h2").count() > 0, "species modal did not open"
    page.keyboard.press("Escape")

    # language switch re-renders the season view (header localizes)
    page.evaluate("App.discoverSeason()")
    page.wait_for_selector(".grid .card")
    page.evaluate("App.setLang('en')")
    page.wait_for_timeout(150)
    assert "in season" in page.locator(".park-name").inner_text().lower(), "season header did not re-localize"

    print(f"SEASON E2E: auto-loaded month {CUR_MONTH}, {n_cards}+ cards, month-switch + card modal + i18n — OK")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context()
    ctx.add_init_script("try { localStorage.setItem('pl_seen_about','1'); } catch(e) {}")
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
