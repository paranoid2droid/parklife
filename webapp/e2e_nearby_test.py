"""E2E for #3 discovery: 'parks near me' list + geo-denied fallback (real Chrome)."""
import os, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8091/")
errors = []
# mock near 代々木公園 / central Tokyo
TOKYO = {"latitude": 35.6717, "longitude": 139.6949}


def check_geo(page):
    page.goto(BASE, wait_until="networkidle")
    # trigger the near-me discovery directly (autoLocate may have opened a park)
    page.evaluate("App.discoverNearby()")
    page.wait_for_selector(".near-list", timeout=8000)
    n = page.locator(".near-item").count()
    assert n > 0, "no near-items rendered"
    # each item has a distance
    assert page.locator(".near-item .near-km").count() == n, "missing distance on some items"
    # distances are ascending (nearest first)
    kms = []
    for t in page.locator(".near-item .near-km").all_inner_texts():
        kms.append(float(t.replace("km", "").strip()))
    assert kms == sorted(kms), f"near list not sorted by distance: {kms}"
    assert kms[0] < 50, f"nearest park implausibly far: {kms[0]}"
    # header shows the count
    hdr = page.locator(".park-name").inner_text()
    assert str(n) in hdr, f"header {hdr!r} lacks count {n}"
    # clicking an item opens that park
    page.locator(".near-item").first.click()
    page.wait_for_selector(".controls", timeout=8000)
    assert page.locator(".card").count() > 0, "park did not open from near-me item"
    print(f"NEARBY E2E (geo): {n} parks listed, nearest {kms[0]} km, click opens park — OK")


def check_denied(page):
    # no geolocation permission -> discoverNearby shows the denied message,
    # and the empty-state near-me button is present.
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_selector(".near-btn", timeout=8000)  # empty-state CTA rendered
    page.evaluate("App.discoverNearby()")
    page.wait_for_function(
        "() => { const p=document.querySelector('#panel .placeholder'); return p && /location|位置|定位/.test(p.textContent); }",
        timeout=8000)
    print("NEARBY E2E (denied): empty-state button present + geo-denied fallback shown — OK")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)

    ctx = browser.new_context(geolocation=TOKYO, permissions=["geolocation"])
    ctx.add_init_script("try { localStorage.setItem('pl_seen_about','1'); } catch(e) {}")
    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        check_geo(pg)
    finally:
        ctx.close()

    ctx2 = browser.new_context()  # no geolocation permission
    ctx2.add_init_script("try { localStorage.setItem('pl_seen_about','1'); } catch(e) {}")
    pg2 = ctx2.new_page()
    pg2.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg2.on("pageerror", lambda e: errors.append(str(e)))
    try:
        check_denied(pg2)
    finally:
        ctx2.close()
        browser.close()

if errors:
    print("CONSOLE ERRORS:", *errors, sep="\n  ")
    sys.exit(1)
print("0 console errors — PASS")
