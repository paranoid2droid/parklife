"""E2E for #3b: 'in season this month' — grouped + checkbox-filtered (real Chrome)."""
import os, sys, datetime
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8091/")
errors = []
CUR_MONTH = datetime.date.today().month


def check(page):
    page.goto(BASE, wait_until="networkidle")

    # header discovery buttons carry readable text labels (not hover-only tooltips)
    assert len(page.locator("#nearBtn").inner_text()) > 2, "near button lacks a text label"
    assert len(page.locator("#seasonBtn").inner_text()) > 2, "season button lacks a text label"

    # open season -> auto-loads the current month, grouped with a checkbox filter row
    page.evaluate("App.discoverSeason()")
    page.wait_for_selector(".grp-filter", timeout=8000)
    assert int(page.locator(".controls select").input_value()) == CUR_MONTH, "did not auto-load current month"
    headers = page.locator(".grp-h.static").count()
    groups = page.locator(".grp-filter .gcb:not(.all)").count()
    assert headers >= 2 and groups == headers, f"not grouped by taxon: {headers} headers / {groups} chips"
    assert page.locator(".grid .card").count() > 0, "no season cards"
    assert "🌸" in page.locator(".park-name").inner_text()

    # unchecking a group hides its section
    page.locator(".grp-filter .gcb:not(.all) input").first.uncheck()
    page.wait_for_timeout(150)
    assert page.locator(".grp-h.static").count() == headers - 1, "uncheck did not hide a group"

    # 'All' checkbox: on -> all sections, off -> none
    page.locator(".gcb.all input").check(); page.wait_for_timeout(120)
    assert page.locator(".grp-h.static").count() == headers, "All-on did not restore all groups"
    page.locator(".gcb.all input").uncheck(); page.wait_for_timeout(120)
    assert page.locator(".grp-h.static").count() == 0, "All-off did not clear sections"
    page.locator(".gcb.all input").check(); page.wait_for_timeout(120)

    # per-group show-more grows that group
    if page.locator(".more-btn").count():
        before = page.locator(".grid .card").count()
        page.locator(".more-btn").first.click()
        page.wait_for_timeout(150)
        assert page.locator(".grid .card").count() > before, "show-more added no cards"

    # switching month reloads a different shard (and resets groups to all)
    other = 6 if CUR_MONTH != 6 else 12
    page.select_option(".controls select", str(other))
    page.wait_for_timeout(300)
    assert int(page.locator(".controls select").input_value()) == other
    assert page.locator(".grid .card").count() > 0

    # a card opens the species modal
    page.locator(".grid .card").first.click()
    page.wait_for_selector("#modal.on", timeout=8000)
    assert page.locator("#mbody h2").count() > 0
    page.keyboard.press("Escape")

    # language switch re-renders the season view (header localizes)
    page.evaluate("App.discoverSeason()")
    page.wait_for_selector(".grid .card")
    page.evaluate("App.setLang('en')")
    page.wait_for_timeout(150)
    assert "in season" in page.locator(".park-name").inner_text().lower(), "season header did not re-localize"

    print(f"SEASON E2E: month {CUR_MONTH} auto-loaded, {groups} groups, checkbox filter + show-more + modal + i18n — OK")


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
