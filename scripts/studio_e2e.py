#!/usr/bin/env python3
"""Playwright e2e check of CCReplay Studio, driving the real running app
(not calling the API directly) at http://127.0.0.1:8765 by default. Clicks
through the guided demo, creates a controller variant through the UI, and
asserts the expected values appear on screen. Saves screenshots to
studio_data/screens/.
"""
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
ROOT = pathlib.Path(__file__).resolve().parents[1]
SCREENS = ROOT / "studio_data" / "screens"
SCREENS.mkdir(parents=True, exist_ok=True)

FAILURES = []


def expect(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))

        page.goto(BASE_URL + "/")
        page.wait_for_selector("text=CCReplay Studio")
        # Wait for the trace/controller library fetch to finish before interacting --
        # clicking Run before /api/traces resolves races the step against an empty list.
        page.wait_for_function(
            "() => { const m = document.body.innerText.match(/library: (\\d+) traces/); return m && Number(m[1]) > 0; }",
            timeout=15000,
        )
        expect("overview page loads", True)
        page.screenshot(path=str(SCREENS / "m6-overview.png"))

        # Guided demo steps 1-5
        run_buttons = page.locator(".panel:has-text('Guided demo') button:has-text('Run')")
        n_steps = run_buttons.count()
        expect("5 guided demo steps present", n_steps == 5, str(n_steps))
        for i in range(n_steps):
            run_buttons.nth(i).click()
            # wait for THIS step's row to leave the running state (poll up to 30s)
            deadline = time.time() + 30
            while time.time() < deadline:
                text = page.locator(".panel:has-text('Guided demo')").inner_text()
                if text.count("matches expected value") + text.count("unexpected result") > i:
                    break
                page.wait_for_timeout(300)
        page.wait_for_timeout(500)
        demo_text = page.locator(".panel:has-text('Guided demo')").inner_text()
        expect("step 1 NO DIVERGENCE shown", "NO DIVERGENCE" in demo_text)
        expect("step 2 seq=1705 shown", "seq=1705" in demo_text)
        expect("step 3 suffix=204 shown", "suffix=204" in demo_text)
        expect("step 4 seq=742 shown", "seq=742" in demo_text)
        expect("step 5 seq=10421 shown", "seq=10421" in demo_text)
        expect("no 'unexpected result' badges", "unexpected result" not in demo_text)
        page.screenshot(path=str(SCREENS / "m5-overview-guided-demo.png"), full_page=True)

        # Traces page
        page.goto(BASE_URL + "/#/traces")
        page.wait_for_selector("text=Traces")
        page.wait_for_timeout(500)
        expect("traces table has rows", page.locator("table tbody tr").count() > 0)
        page.screenshot(path=str(SCREENS / "m3-traces.png"), full_page=True)

        first_explore = page.locator("a:has-text('Explore')").first
        first_explore.click()
        page.wait_for_timeout(1500)
        expect("trace detail page has charts (svg present)", page.locator("svg.main-svg").count() > 0)
        page.screenshot(path=str(SCREENS / "m3-trace-detail.png"), full_page=True)

        # Controllers page: create a param variant through the UI
        page.goto(BASE_URL + "/#/controllers")
        page.wait_for_selector("text=Controllers")
        page.fill(".panel:has-text('Create a parameter variant') input[placeholder='my_variant']", f"e2e_beta_{int(time.time())}")
        page.fill(".panel:has-text('Create a parameter variant') input[type=number] >> nth=0", "819")
        page.click(".panel:has-text('Create a parameter variant') button:has-text('Create')")
        page.wait_for_selector("text=Validation:", timeout=30000)
        page.wait_for_timeout(500)
        param_panel_text = page.locator(".panel:has-text('Create a parameter variant')").inner_text()
        expect("param variant validation PASS shown in UI", "PASS" in param_panel_text)
        page.screenshot(path=str(SCREENS / "m2-controllers-param.png"), full_page=True)

        # Controllers page: write a one-line custom controller
        editor = page.locator(".cm-content").last
        editor.click()
        page.keyboard.press("Control+A")
        custom_code = (
            "from ccreplay.controllers import clone_base\n"
            "base = clone_base('cubic', name='e2e_custom')\n"
            "CCREPLAY_ABI_BASE = 'cubic'\n"
            "base.CCREPLAY_ABI_BASE = 'cubic'\n"
            "_orig = base.transition\n"
            "def my_transition(event, ca):\n"
            "    computed, next_ca = _orig(event, ca)\n"
            "    if event['callback_id'] == 1:\n"
            "        computed = dict(computed)\n"
            "        computed['result'] = computed['result'] - 1\n"
            "    return computed, next_ca\n"
            "base.transition = my_transition\n"
            "CONTROLLER = base\n"
        )
        page.keyboard.insert_text(custom_code)
        page.fill(".panel:has-text('Write a controller') input[placeholder='my_controller']", f"e2e_custom_{int(time.time())}")
        page.click(".panel:has-text('Write a controller') button:has-text('Save')")
        page.wait_for_timeout(15000)
        code_panel_text = page.locator(".panel:has-text('Write a controller')").inner_text()
        expect("custom controller validation ran", "Validation:" in code_panel_text)
        page.screenshot(path=str(SCREENS / "m4-controllers-code.png"), full_page=True)

        # History page
        page.goto(BASE_URL + "/#/history")
        page.wait_for_selector("text=History")
        page.wait_for_timeout(500)
        expect("history has rows", page.locator("table tbody tr").count() > 0)
        page.screenshot(path=str(SCREENS / "m5-history.png"), full_page=True)

        expect("no browser console errors", len(console_errors) == 0, str(console_errors[:5]))

        browser.close()

    print()
    if FAILURES:
        print(f"E2E: {len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("E2E: ALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
