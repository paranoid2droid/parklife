"""End-to-end smoke test for the thin-client SPA, via system Chrome.

Drives the real UI (playwright `channel="chrome"`, no browser download) against
a running `scripts.serve_api`. Asserts the full feature set and that the browser
console stays error-free.

Run:
    .venv/bin/python -m scripts.serve_api &        # start the stack
    .venv/bin/python webapp/e2e_test.py            # (BASE overridable via env)
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8787/")
errors: list[str] = []


def check(page) -> None:
    # --- map + park panel ----------------------------------------------------
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_selector(".marker-cluster, .leaflet-marker-icon", timeout=15000)

    page.evaluate("App.openPark(192)")               # 代々木公園 (~616 species)
    page.wait_for_selector(".controls", timeout=10000)
    assert page.locator(".grp-h").count() > 0
    assert page.locator(".card").count() > 0

    # --- sort / month / group toggle ----------------------------------------
    assert page.locator(".controls select").count() == 2
    h0 = page.locator(".park-meta").first.inner_text()
    page.select_option(".controls select >> nth=1", "4")     # April
    page.wait_for_timeout(250)
    assert page.locator(".park-meta").first.inner_text() != h0, "month filter no-op"
    page.select_option(".controls select >> nth=1", "0")
    page.select_option(".controls select >> nth=0", "name")  # sort by name
    page.wait_for_timeout(200)
    page.locator(".grp-h").first.click()                     # collapse a group
    page.wait_for_timeout(150)
    assert page.locator(".grp-h.off").count() >= 1
    page.locator(".grp-h").first.click()

    # --- pagination ----------------------------------------------------------
    page.evaluate("App.openPark(192)")
    page.wait_for_selector(".grid", timeout=10000)
    page.wait_for_timeout(200)
    n0 = page.locator(".card").count()
    assert page.locator(".more-btn").count() > 0, "no show-more on big park"
    page.locator(".more-btn").first.click()
    page.wait_for_timeout(200)
    assert page.locator(".card").count() > n0, "show-more added nothing"

    # --- species modal + park-local photos + zh i18n -------------------------
    page.evaluate("App.openPark(25)")
    page.wait_for_selector(".controls", timeout=10000)
    page.evaluate("App.openSpecies(4301, 25)")               # has park-local photos
    page.wait_for_selector("#modal.on", timeout=10000)
    page.wait_for_timeout(300)
    assert "📍" in page.locator(".mphoto .attr").inner_text(), "no park-local badge"
    assert page.locator(".mbody h2").inner_text()
    page.evaluate("App.setLang('zh')")
    assert page.locator(".mbody h2").inner_text()

    # --- species → map reverse view ------------------------------------------
    page.evaluate("App.setLang('en')")
    page.evaluate("App.openSpecies(198)")                    # Parus cinereus
    page.wait_for_selector("#modal.on", timeout=10000)
    page.locator(".mbody button.more-btn").click()
    page.wait_for_selector("#mapBanner", state="visible", timeout=8000)
    assert "parks with" in page.locator("#mapBanner").inner_text()
    page.locator("#mapBanner button").click()
    page.wait_for_timeout(200)
    assert not page.locator("#mapBanner").is_visible()

    # --- deep-linking --------------------------------------------------------
    page.goto(BASE + "#species/198", wait_until="networkidle")
    page.wait_for_selector("#modal.on", timeout=12000)
    page.goto(BASE + "#park/192", wait_until="networkidle")
    page.wait_for_selector(".park-name", timeout=12000)
    assert page.locator("#modal.on").count() == 0
    page.locator(".card").first.click()
    page.wait_for_selector("#modal.on", timeout=8000)
    assert page.evaluate("location.hash").startswith("#species/")
    page.go_back()
    page.wait_for_function("location.hash === '#park/192'", timeout=5000)
    assert page.locator("#modal.on").count() == 0, "Back should close the modal"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 820})
        # Skip the first-visit About greeting so its overlay doesn't intercept
        # clicks — this suite tests the steady-state map/panel/modal features
        # (the greeting itself is covered separately by about_e2e).
        page.add_init_script("try { localStorage.setItem('pl_seen_about','1'); } catch(e) {}")
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
    print("E2E PASS — all features OK, 0 console errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
