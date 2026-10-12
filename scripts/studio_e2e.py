#!/usr/bin/env python3
"""Playwright e2e check of CCReplay Studio, driving the real running app
(not calling the API directly) at http://127.0.0.1:8765 by default. Clicks
through the guided demo, creates controller variants through the UI and
actually diffs them, exercises validation failure/ABI refusal/rerun/export,
and asserts the expected values appear on screen. Saves screenshots (light
theme, per AUTORUN) to studio_data/screens/ and copies the key ones to
.autorun/evidence/.
"""
import pathlib
import shutil
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
ROOT = pathlib.Path(__file__).resolve().parents[1]
SCREENS = ROOT / "studio_data" / "screens"
EVIDENCE = ROOT / ".autorun" / "evidence"
SCREENS.mkdir(parents=True, exist_ok=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)

FAILURES = []


def expect(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def shot(page, name, full_page=True):
    path = SCREENS / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    shutil.copy(path, EVIDENCE / f"{name}.png")


def fetch_text(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode()


def fetch_status(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script("try { localStorage.setItem('ccr-theme', 'light'); } catch (e) {}")
        page = context.new_page()
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
        shot(page, "m6-overview")

        # Guided demo steps 1-5
        run_buttons = page.locator(".panel:has-text('Guided demo') button:has-text('Run')")
        n_steps = run_buttons.count()
        expect("5 guided demo steps present", n_steps == 5, str(n_steps))
        for i in range(n_steps):
            run_buttons.nth(i).click()
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
        expect("step 5 shows mode names not a hardcoded string", "priv_post_mode: DELAY <-> COMPETE" in demo_text, demo_text)
        expect("no 'unexpected result' badges", "unexpected result" not in demo_text)
        shot(page, "m5-overview-guided-demo")

        # Traces page
        page.goto(BASE_URL + "/#/traces")
        page.wait_for_selector("text=Traces")
        page.wait_for_timeout(500)
        expect("traces table has rows", page.locator("table tbody tr").count() > 0)
        shot(page, "m3-traces")

        # cubic rep1 specifically (has W_max/bic_K + RTT charts + callback bar)
        page.click("tr:has-text('cubic_replay/primary/rep1') a:has-text('Explore')")
        page.wait_for_timeout(2500)
        n_charts = page.locator("svg.main-svg").count()
        expect("trace detail page has charts (svg present)", n_charts > 0, str(n_charts))
        # CUBIC trace detail renders 4 Plotly charts: callback-mix bar, cwnd/ssthresh,
        # W_max/bic_K, RTT samples -- fewer than that means the bar chart regressed
        # back to a table-only callback mix.
        expect("callback mix renders as a bar chart (4 charts total on a CUBIC trace)", n_charts >= 4, str(n_charts))
        shot(page, "m3-trace-detail")

        # Controllers page: create a param variant through the UI, THEN diff it (M2 done-when)
        page.goto(BASE_URL + "/#/controllers")
        page.wait_for_selector("text=Controllers")
        variant_name = f"e2e_beta_{int(time.time())}"
        page.fill(".panel:has-text('Create a parameter variant') input[placeholder='my_variant']", variant_name)
        page.fill(".panel:has-text('Create a parameter variant') input[type=number] >> nth=0", "819")
        page.click(".panel:has-text('Create a parameter variant') button:has-text('Create')")
        page.wait_for_selector("text=Validation:", timeout=30000)
        page.wait_for_timeout(500)
        param_panel_text = page.locator(".panel:has-text('Create a parameter variant')").inner_text()
        expect("param variant validation PASS shown in UI", "PASS" in param_panel_text)
        shot(page, "m2-controllers-param")

        page.goto(BASE_URL + "/#/diff")
        page.wait_for_selector("text=Diff Workbench")
        page.wait_for_timeout(500)
        # pick the cubic rep1 trace and the just-created variant as candidate
        trace_select = page.locator("select").nth(0)
        trace_options = trace_select.locator("option").all_inner_texts()
        cubic_rep1_label = next((o for o in trace_options if "cubic_replay/primary/rep1" in o), None)
        expect("cubic rep1 present in Diff trace picker", cubic_rep1_label is not None)
        if cubic_rep1_label:
            trace_select.select_option(label=cubic_rep1_label)
        ref_select = page.locator("select").nth(1)
        ref_options = ref_select.locator("option").all_inner_texts()
        cubic_ref_label = next((o for o in ref_options if o.startswith("cubic ")), None)
        if cubic_ref_label:
            ref_select.select_option(label=cubic_ref_label)
        cand_select = page.locator("select").nth(2)
        cand_options = cand_select.locator("option").all_inner_texts()
        variant_label = next((o for o in cand_options if variant_name in o), None)
        expect("UI-created param variant appears in the Diff candidate picker", variant_label is not None, str(cand_options))
        if variant_label:
            cand_select.select_option(label=variant_label)
        page.click("button:has-text('Run diff')")
        page.wait_for_selector("text=DIVERGENCE", timeout=30000)
        page.wait_for_timeout(500)
        diff_text = page.locator("body").inner_text()
        expect("UI-created variant diffed against reference -> seq 742 (M2 done-when, not just validated)",
               "742" in diff_text)
        shot(page, "m2-diff-from-ui-variant")

        # ABI-incompatible pairing refused with an explanation
        page.goto(BASE_URL + "/#/diff")
        page.wait_for_timeout(500)
        trace_select = page.locator("select").nth(0)
        reno_label = next((o for o in trace_select.locator("option").all_inner_texts() if "r0/rep1" in o), None)
        if reno_label:
            trace_select.select_option(label=reno_label)
            page.wait_for_timeout(300)
            ref_select = page.locator("select").nth(1)
            cubic_opt = next((o for o in ref_select.locator("option").all_inner_texts() if o.startswith("cubic ")), None)
            # cubic should be rendered disabled for a Reno trace
            disabled = page.locator("select >> nth=1 >> option", has_text="cubic ").first.is_disabled() if cubic_opt else None
            expect("incompatible-ABI controller option is disabled in the Diff picker", disabled is True, str(disabled))
        shot(page, "m3-diff-abi-refusal")

        # Controllers page: write a controller from the template, verify the
        # no-op default, then flip OFFSET and verify a real divergence (M4 done-when).
        page.goto(BASE_URL + "/#/controllers")
        page.wait_for_selector("text=Controllers")
        page.wait_for_timeout(800)
        template = fetch_text(BASE_URL + "/api/controllers/templates/cubic")
        expect("cubic template contains the OFFSET no-op knob", "OFFSET = 0" in template, template[:200])

        unchanged_name = f"e2e_tmpl_unchanged_{int(time.time())}"
        page.fill(".panel:has-text('Write a controller') input[placeholder='my_controller']", unchanged_name)
        page.click(".panel:has-text('Write a controller') button:has-text('Save')")
        page.wait_for_selector(".panel:has-text('Write a controller') >> text=Validation:", timeout=30000)
        code_panel_text = page.locator(".panel:has-text('Write a controller')").inner_text()
        expect("template-unchanged controller validates PASS", "PASS" in code_panel_text, code_panel_text[-300:])
        shot(page, "m4-controllers-code-unchanged")

        offset1_name = f"e2e_tmpl_offset1_{int(time.time())}"
        editor = page.locator(".cm-content").last
        editor.click()
        page.keyboard.press("Control+A")
        page.keyboard.insert_text(template.replace("OFFSET = 0", "OFFSET = 1"))
        page.fill(".panel:has-text('Write a controller') input[placeholder='my_controller']", offset1_name)
        page.click(".panel:has-text('Write a controller') button:has-text('Save')")
        page.wait_for_timeout(15000)

        page.goto(BASE_URL + "/#/diff")
        page.wait_for_timeout(500)
        trace_select = page.locator("select").nth(0)
        trace_select.select_option(label=cubic_rep1_label)
        page.wait_for_timeout(300)
        ref_select = page.locator("select").nth(1)
        cubic_ref_label2 = next((o for o in ref_select.locator("option").all_inner_texts() if o.startswith("cubic ")), None)
        ref_select.select_option(label=cubic_ref_label2)
        cand_select = page.locator("select").nth(2)
        cand_label = next((o for o in cand_select.locator("option").all_inner_texts() if offset1_name in o), None)
        expect("OFFSET=1 user controller appears in Diff candidate picker", cand_label is not None)
        if cand_label:
            cand_select.select_option(label=cand_label)
        page.click("button:has-text('Run diff')")
        page.wait_for_selector("text=DIVERGENCE", timeout=30000)
        page.wait_for_timeout(500)
        divergence_text = page.locator("body").inner_text()
        expect("user-written OFFSET=1 controller -> seq 1705 (verified 'User override' row)", "1,705" in divergence_text or "1705" in divergence_text)
        shot(page, "m4-controllers-code-offset1-diff")

        # Broken code must fail validation visibly, never show a fake PASS.
        page.goto(BASE_URL + "/#/controllers")
        page.wait_for_timeout(500)
        broken_name = f"e2e_broken_{int(time.time())}"
        editor = page.locator(".cm-content").last
        editor.click()
        page.keyboard.press("Control+A")
        page.keyboard.insert_text("this is not valid python +++")
        page.fill(".panel:has-text('Write a controller') input[placeholder='my_controller']", broken_name)
        page.click(".panel:has-text('Write a controller') button:has-text('Save')")
        page.wait_for_selector(".panel:has-text('Write a controller') >> text=Validation:", timeout=30000)
        broken_panel_text = page.locator(".panel:has-text('Write a controller')").inner_text()
        expect("broken controller shows FAIL, not PASS", "FAIL" in broken_panel_text and "PASS" not in broken_panel_text.split("Validation:")[-1][:50], broken_panel_text[-300:])
        expect("broken controller shows the real syntax error", "syntax" in broken_panel_text.lower(), broken_panel_text[-300:])
        shot(page, "m4-controllers-code-broken")

        # History page: rerun + export
        page.goto(BASE_URL + "/#/history")
        page.wait_for_selector("text=History")
        page.wait_for_timeout(500)
        expect("history has rows", page.locator("table tbody tr").count() > 0)
        first_rerun = page.locator("table tbody tr button:has-text('Rerun')").first
        first_rerun.click()
        page.wait_for_function(
            "() => document.body.innerText.includes('identical to original') || document.body.innerText.includes('differs from original')",
            timeout=30000,
        )
        rerun_text = page.locator("body").inner_text()
        expect("rerun reports identical to original", "identical to original" in rerun_text, rerun_text[:300])

        page.locator("table tbody tr button:has-text('Open')").first.click()
        page.wait_for_selector("a:has-text('Export JSON')", timeout=10000)
        shot(page, "m5-history")

        export_link = page.locator("a:has-text('Export JSON')").first
        export_href = export_link.get_attribute("href")
        export_url = BASE_URL + export_href if export_href and export_href.startswith("/") else export_href
        expect("export JSON link returns 200", fetch_status(export_url) == 200, export_url)

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
