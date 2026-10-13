#!/usr/bin/env python3
"""Playwright e2e check of CCReplay Studio, driving the real running app
(not calling the API directly) at http://127.0.0.1:8765 by default. Clicks
through the guided demo, creates controller variants through the UI and
actually diffs them, exercises validation failure/ABI refusal/rerun/export,
and asserts the expected values appear on screen. Saves screenshots (light
theme, per AUTORUN) to studio_data/screens/ and copies the key ones to
.autorun/evidence/.
"""
import json
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


def post_json(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_status(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


CREATED_PARAM_NAMES = []  # bare names passed to createParamController, e.g. "e2e_beta_123"
CREATED_USER_NAMES = []   # bare names passed to createUserController, e.g. "e2e_broken_123"


def cleanup_e2e_artifacts():
    """Removes exactly the controllers and experiment rows THIS RUN
    created -- never a blanket wipe or prefix sweep (an earlier version of
    this function swept every `param_e2e_*`/`user_e2e_*` entry, which is
    still a blanket pattern match, not an exact-id delete, and could catch
    a real owner's similarly-named controller). The fixed-name
    param_beta_0_8_demo entry (guided demo step 4) is never touched here --
    it's meant to persist and be reused, not cleaned up per run."""
    import sqlite3

    param_cids = [f"param_{n}" for n in CREATED_PARAM_NAMES]
    user_cids = [f"user_{n}" for n in CREATED_USER_NAMES]

    user_dir = ROOT / "controllers" / "user"
    for cid in user_cids:
        (user_dir / f"{cid}.py").unlink(missing_ok=True)
        (user_dir / f"{cid}.meta.json").unlink(missing_ok=True)

    store_path = ROOT / "studio_data" / "param_variants.json"
    if store_path.exists() and param_cids:
        store = json.loads(store_path.read_text())
        for cid in param_cids:
            store.pop(cid, None)
        store_path.write_text(json.dumps(store, indent=2, sort_keys=True))

    # Experiment rows referencing a now-deleted controller would otherwise
    # sit in History pointing at nothing -- opening or rerunning one is
    # exactly the "unknown controller" case this round's review flagged.
    all_cids = set(param_cids) | set(user_cids)
    db_path = ROOT / "studio_data" / "studio.db"
    if all_cids and db_path.exists():
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id, config FROM experiments").fetchall()
        to_delete = [rid for rid, cfg in rows
                     if json.loads(cfg).get("reference") in all_cids or json.loads(cfg).get("candidate") in all_cids]
        if to_delete:
            conn.executemany("DELETE FROM experiments WHERE id = ?", [(rid,) for rid in to_delete])
            conn.commit()
        conn.close()


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
        expect("overview page loads", True)

        # Cold-start race check: a presenter clicking Run before the library
        # has loaded must never see "trace not found" -- the button must
        # either be disabled until the library loads, or the click must
        # succeed (found as a REAL failure during earlier e2e development:
        # clicking immediately raced an empty `traces` array in Overview.tsx
        # and showed "unexpected result ... trace not found" on screen).
        first_run_button = page.locator(".panel:has-text('Guided demo') button:has-text('Run'), "
                                         ".panel:has-text('Guided demo') button:has-text('Loading')").first
        was_disabled_at_click_time = first_run_button.is_disabled()
        first_run_button.click(force=True)  # force: clicking a disabled button is itself part of what we're checking
        page.wait_for_timeout(2000)
        cold_click_text = page.locator(".panel:has-text('Guided demo')").inner_text()
        expect(
            "clicking Run immediately on a cold page never shows 'trace not found'",
            "trace not found" not in cold_click_text,
            f"was_disabled_at_click_time={was_disabled_at_click_time}; {cold_click_text[:400]}",
        )

        # Wait for the trace/controller library fetch to finish before the
        # rest of this script interacts with it.
        page.wait_for_function(
            "() => { const m = document.body.innerText.match(/library: (\\d+) traces/); return m && Number(m[1]) > 0; }",
            timeout=15000,
        )
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

        # All three ABIs must render their detail page without console errors
        # (plan §3 A3.2 done-when: "all three ABIs render without console
        # errors ... screenshot per ABI"), not only CUBIC.
        # NOTE: this Plotly build renders 3 <svg class="main-svg"> elements per
        # chart, so `svg.main-svg` count is not usable as a per-chart count
        # (found by actually inspecting the DOM: .js-plotly-plot is the real
        # one-per-chart container).
        abi_pages = [
            ("r0/rep1", "reno", 2),           # callback-mix bar, cwnd/ssthresh only (no RTT/W_max for Reno)
            ("cubic_replay/primary/rep1", "cubic", 4),   # + W_max/bic_K, RTT
            ("covegas_campaign/rep4", "covegas", 3),     # + RTT (no W_max/bic_K)
        ]
        for path_fragment, abi_name, n_expected_charts in abi_pages:
            console_errors.clear()
            page.click(f"tr:has-text('{path_fragment}') a:has-text('Explore')")
            page.wait_for_timeout(2500)
            n_charts = page.locator(".js-plotly-plot").count()
            expect(f"{abi_name} trace detail renders exactly {n_expected_charts} charts",
                   n_charts == n_expected_charts, str(n_charts))
            n_bars = page.locator(".barlayer .trace.bars").count()
            expect(f"{abi_name} callback-mix is a real bar chart (not a regressed table)", n_bars >= 1, str(n_bars))
            expect(f"{abi_name} trace detail has 0 console errors", len(console_errors) == 0, str(console_errors[:5]))
            shot(page, f"m3-trace-detail-{abi_name}")
            page.go_back()
            page.wait_for_timeout(500)
        console_errors.clear()  # reset so the final whole-run check only reflects the rest of the run

        # Controllers page: create a param variant through the UI, THEN diff it (M2 done-when)
        page.goto(BASE_URL + "/#/controllers")
        page.wait_for_selector("text=Controllers")
        variant_name = f"e2e_beta_{int(time.time())}"
        CREATED_PARAM_NAMES.append(variant_name)
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
        page.wait_for_timeout(300)
        ref_select = page.locator("select").nth(1)
        ref_options = ref_select.locator("option").all_inner_texts()
        cubic_ref_label = next((o for o in ref_options if o.startswith("cubic ")), None)
        if cubic_ref_label:
            ref_select.select_option(label=cubic_ref_label)
        page.wait_for_timeout(300)
        cand_select = page.locator("select").nth(2)
        cand_options = cand_select.locator("option").all_inner_texts()
        variant_label = next((o for o in cand_options if variant_name in o), None)
        expect("UI-created param variant appears in the Diff candidate picker", variant_label is not None, str(cand_options))
        if variant_label:
            cand_select.select_option(label=variant_label)
        page.wait_for_timeout(300)
        expect("Run diff button is enabled before clicking",
               page.locator("button:has-text('Run diff')").is_enabled())
        page.click("button:has-text('Run diff')")
        page.wait_for_selector(".verdict-banner", timeout=30000)
        page.wait_for_timeout(500)
        # Scope to the First-divergence panel specifically (data-testid, not a
        # text match) -- a whole-page text search for "742" would also match
        # picker option names containing a Date.now() timestamp, and
        # "DIVERGENCE" matches "NO DIVERGENCE" too.
        verdict_text = page.locator(".verdict-banner").inner_text()
        divergence_panel_text = (
            page.locator("[data-testid=first-divergence-panel]").inner_text(timeout=5000)
            if "DIVERGENCE" in verdict_text and "NO DIVERGENCE" not in verdict_text
            else ""
        )
        expect("verdict banner shows DIVERGENCE (not NO DIVERGENCE)",
               verdict_text.startswith("DIVERGENCE"), verdict_text)
        expect("UI-created variant diffed against reference -> seq 742 (M2 done-when, not just validated)",
               "742" in divergence_panel_text, divergence_panel_text)
        expect("UI-created variant divergence kind == private_state_only",
               "only internal controller state differs" in divergence_panel_text, divergence_panel_text)
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
        CREATED_USER_NAMES.append(unchanged_name)
        page.fill(".panel:has-text('Write a controller') input[placeholder='my_controller']", unchanged_name)
        page.click(".panel:has-text('Write a controller') button:has-text('Save')")
        page.wait_for_selector(".panel:has-text('Write a controller') >> text=Validation:", timeout=30000)
        code_panel_text = page.locator(".panel:has-text('Write a controller')").inner_text()
        expect("template-unchanged controller validates PASS", "PASS" in code_panel_text, code_panel_text[-300:])
        shot(page, "m4-controllers-code-unchanged")

        # Validation passing is not the same claim as "diffs as NO DIVERGENCE"
        # -- actually run it through the Diff page too, the same way the
        # OFFSET=1 variant is diffed below.
        page.goto(BASE_URL + "/#/diff")
        page.wait_for_timeout(500)
        trace_select = page.locator("select").nth(0)
        trace_select.select_option(label=cubic_rep1_label)
        page.wait_for_timeout(300)
        ref_select = page.locator("select").nth(1)
        cubic_ref_label_u = next((o for o in ref_select.locator("option").all_inner_texts() if o.startswith("cubic ")), None)
        ref_select.select_option(label=cubic_ref_label_u)
        page.wait_for_timeout(300)
        cand_select = page.locator("select").nth(2)
        unchanged_label = next((o for o in cand_select.locator("option").all_inner_texts() if unchanged_name in o), None)
        expect("template-unchanged controller appears in Diff candidate picker", unchanged_label is not None)
        if unchanged_label:
            cand_select.select_option(label=unchanged_label)
        page.wait_for_timeout(300)
        page.click("button:has-text('Run diff')")
        page.wait_for_selector(".verdict-banner", timeout=30000)
        page.wait_for_timeout(500)
        unchanged_verdict = page.locator(".verdict-banner").inner_text()
        expect("template unchanged diffs as NO DIVERGENCE through the real Diff page",
               unchanged_verdict.startswith("NO DIVERGENCE"), unchanged_verdict)

        offset1_name = f"e2e_tmpl_offset1_{int(time.time())}"
        CREATED_USER_NAMES.append(offset1_name)
        page.goto(BASE_URL + "/#/controllers")
        page.wait_for_selector("text=Controllers")
        page.wait_for_timeout(500)
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
        page.wait_for_timeout(300)
        cand_select = page.locator("select").nth(2)
        cand_label = next((o for o in cand_select.locator("option").all_inner_texts() if offset1_name in o), None)
        expect("OFFSET=1 user controller appears in Diff candidate picker", cand_label is not None)
        if cand_label:
            cand_select.select_option(label=cand_label)
        page.wait_for_timeout(300)
        expect("Run diff button is enabled before clicking (OFFSET=1)",
               page.locator("button:has-text('Run diff')").is_enabled())
        page.click("button:has-text('Run diff')")
        page.wait_for_selector(".verdict-banner", timeout=30000)
        page.wait_for_timeout(500)
        verdict_text = page.locator(".verdict-banner").inner_text()
        divergence_panel_text = page.locator("[data-testid=first-divergence-panel]").inner_text()
        fields_table_text = page.locator("[data-testid=diff-fields-table]").inner_text()
        expect("verdict banner shows DIVERGENCE", verdict_text.startswith("DIVERGENCE"), verdict_text)
        expect("user-written OFFSET=1 controller -> seq 1705 (verified 'User override' row)",
               "1,705" in divergence_panel_text or "1705" in divergence_panel_text, divergence_panel_text)
        expect("differing-fields table shows 145 (reference) vs 144 (candidate)",
               "145" in fields_table_text and "144" in fields_table_text, fields_table_text)
        shot(page, "m4-controllers-code-offset1-diff")

        # Broken code must fail validation visibly, never show a fake PASS.
        page.goto(BASE_URL + "/#/controllers")
        page.wait_for_timeout(500)
        broken_name = f"e2e_broken_{int(time.time())}"
        CREATED_USER_NAMES.append(broken_name)
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

        # A controller file that doesn't define CONTROLLER must also fail
        # validation visibly through the real editor, not just at the smoke-
        # test (ccreplay-wrapper) level.
        no_controller_name = f"e2e_no_controller_{int(time.time())}"
        CREATED_USER_NAMES.append(no_controller_name)
        editor = page.locator(".cm-content").last
        editor.click()
        page.keyboard.press("Control+A")
        page.keyboard.insert_text("x = 1\n")
        page.fill(".panel:has-text('Write a controller') input[placeholder='my_controller']", no_controller_name)
        page.click(".panel:has-text('Write a controller') button:has-text('Save')")
        page.wait_for_selector(".panel:has-text('Write a controller') >> text=Validation:", timeout=30000)
        no_controller_panel_text = page.locator(".panel:has-text('Write a controller')").inner_text()
        expect("missing-CONTROLLER module shows FAIL in the real editor",
               "FAIL" in no_controller_panel_text, no_controller_panel_text[-300:])
        expect("missing-CONTROLLER reason mentions CONTROLLER",
               "CONTROLLER" in no_controller_panel_text, no_controller_panel_text[-300:])
        shot(page, "m4-controllers-code-no-controller")

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

        # Both export formats should actually download (Content-Disposition:
        # attachment), not just return 200 while opening in a tab.
        with page.expect_download() as dl_info:
            page.click("a:has-text('Export JSON')")
        json_download = dl_info.value
        expect("export JSON triggers a real download", json_download.suggested_filename.endswith(".json"),
               json_download.suggested_filename)

        with page.expect_download() as dl_info2:
            page.click("a:has-text('Export Markdown')")
        md_download = dl_info2.value
        expect("export Markdown triggers a real download", md_download.suggested_filename.endswith(".md"),
               md_download.suggested_filename)

        # Trace upload: a renamed copy of an existing small library trace is a
        # real .ccr file with a real magic/header, not manufactured evidence --
        # it exercises the actual upload-parse-register path end to end. The
        # source copy lives OUTSIDE uploads/ (in a scratch dir) so the test
        # proves the endpoint writes the file, rather than finding a copy
        # that was already sitting in uploads/ before the upload happened.
        src = ROOT / "raw" / "r0" / "rep1.ccr"
        scratch_dir = ROOT / "studio_data" / "e2e_tmp"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        upload_src = scratch_dir / "e2e_upload_test.ccr"
        upload_src.write_bytes(src.read_bytes())
        uploaded_dest = ROOT / "uploads" / "e2e_upload_test.ccr"
        uploaded_dest.unlink(missing_ok=True)
        expect("upload destination does not exist before uploading", not uploaded_dest.exists())

        page.goto(BASE_URL + "/#/traces")
        page.wait_for_selector("text=Traces")
        page.wait_for_timeout(500)
        page.locator("input[type=file]").first.set_input_files(str(upload_src))
        page.click("button:has-text('Upload')")
        page.wait_for_function(
            "() => document.body.innerText.includes('uploaded:') || document.body.innerText.includes('failed:')",
            timeout=15000,
        )
        upload_msg = page.locator("body").inner_text()
        expect("upload reports success with correct ABI and event count",
               "uploaded:" in upload_msg and "Reno" in upload_msg and "37260" in upload_msg.replace(",", ""),
               [l for l in upload_msg.splitlines() if "uploaded" in l or "failed" in l])
        expect("upload endpoint actually wrote the file to uploads/", uploaded_dest.exists())
        shot(page, "m3-traces-upload")
        upload_src.unlink(missing_ok=True)
        uploaded_dest.unlink(missing_ok=True)
        (ROOT / "uploads" / "e2e_upload_test.meta.json").unlink(missing_ok=True)

        # Bad-magic upload must fail with a readable error, not a fake success.
        bad_file = scratch_dir / "e2e_upload_bad.ccr"
        bad_file.write_bytes(b"not a real trace file")
        page.locator("input[type=file]").first.set_input_files(str(bad_file))
        page.click("button:has-text('Upload')")
        page.wait_for_function("() => document.body.innerText.includes('failed:')", timeout=15000)
        bad_upload_msg = page.locator("body").inner_text()
        expect("bad-magic upload fails with a readable error", "failed:" in bad_upload_msg)
        bad_file.unlink(missing_ok=True)
        (ROOT / "uploads" / "e2e_upload_bad.ccr").unlink(missing_ok=True)
        # The bad-magic upload above deliberately triggers a 400 response,
        # which Chromium logs as a console error of its own accord (the fetch
        # network layer, not application code) -- that is the expected
        # behavior of this negative-path test, not a real app bug, so it is
        # excluded from the overall console-cleanliness check below.
        console_errors.clear()

        # Invariant check (BEFORE the deliberately-orphaning test below):
        # every experiment in History must reference controllers that still
        # exist. A violation here would mean some EARLIER run (a prior
        # session, or an earlier step in this one) left orphaned experiment
        # rows -- exactly the state that made rerun/"Diff Workbench" show a
        # misleading "failed" or raise a bare 500 before this round's fixes.
        known_ids = {c["id"] for c in json.loads(fetch_text(BASE_URL + "/api/controllers"))}
        experiments = json.loads(fetch_text(BASE_URL + "/api/experiments"))
        dangling = [
            e["id"] for e in experiments
            if e["config"].get("reference") not in known_ids or e["config"].get("candidate") not in known_ids
        ]
        expect("no pre-existing experiment references a deleted controller", len(dangling) == 0, str(dangling[:5]))

        # A rerun whose controller was deleted since the original run must be
        # reported as failed, never as "result differs from original" -- the
        # same fake-signal failure mode as the validation-envelope bug fixed
        # earlier. Exercised at the API level (backend/app.py's rerun +
        # _check_abi_compat), since this is backend behavior, not a UI click.
        # This test deliberately creates exactly the orphaned-reference state
        # the invariant above checks for, so it cleans up its OWN experiment
        # row immediately afterward rather than leaving it for the final
        # cleanup -- the invariant must hold again once this block finishes.
        doomed_name = f"e2e_doomed_{int(time.time())}"
        CREATED_USER_NAMES.append(doomed_name)
        post_json(BASE_URL + "/api/controllers/user",
                  {"name": doomed_name, "abi_base": "cubic", "code": fetch_text(BASE_URL + "/api/controllers/templates/cubic")})
        cubic_trace_id = next(t["id"] for t in json.loads(fetch_text(BASE_URL + "/api/traces"))
                               if t["path"] == "raw/cubic_replay/primary/rep1.ccr")
        doomed_exp = post_json(BASE_URL + "/api/experiments",
                                {"type": "diff", "trace_id": cubic_trace_id, "reference": "cubic", "candidate": f"user_{doomed_name}"})
        deadline = time.time() + 30
        while time.time() < deadline:
            exp = json.loads(fetch_text(BASE_URL + f"/api/experiments/{doomed_exp['id']}"))
            if exp["status"] in ("done", "error"):
                break
            time.sleep(0.3)
        expect("doomed-controller experiment completed before deleting its controller", exp["status"] == "done", exp["status"])
        (ROOT / "controllers" / "user" / f"user_{doomed_name}.py").unlink(missing_ok=True)
        (ROOT / "controllers" / "user" / f"user_{doomed_name}.meta.json").unlink(missing_ok=True)

        # Drive the actual failure message through the real History page, not
        # only the API -- the API-level check above proves the backend logic;
        # this proves History.tsx actually renders the "failed" branch rather
        # than the old "differs" text for this exact case.
        page.goto(BASE_URL + "/#/history")
        page.wait_for_selector("text=History")
        page.wait_for_timeout(500)
        doomed_row = page.locator(f"tr:has-text('user_{doomed_name}')").first
        doomed_row.locator("button:has-text('Rerun')").click()
        page.wait_for_function(
            "() => { const t = document.body.innerText; return t.includes('rerun') && (t.includes('failed') || t.includes('identical') || t.includes('differs')); }",
            timeout=30000,
        )
        ui_rerun_text = page.locator("p.hint").first.inner_text()
        expect("UI rerun of a deleted controller shows 'failed', not 'differs'",
               "failed" in ui_rerun_text and "differs" not in ui_rerun_text, ui_rerun_text)
        expect("UI rerun failure message names the real reason",
               "unknown controller" in ui_rerun_text.lower(), ui_rerun_text)
        shot(page, "m5-history-rerun-failed")

        rerun_result = post_json(BASE_URL + f"/api/experiments/{doomed_exp['id']}/rerun")
        expect("rerun of a deleted controller reports status=error, not same_as_original=false-as-differs",
               rerun_result["status"] == "error" and rerun_result["same_as_original"] is False, str(rerun_result))
        expect("rerun error message is present and readable",
               bool(rerun_result.get("error")) and "unknown controller" in rerun_result["error"].lower(),
               str(rerun_result.get("error")))

        # Clean up every experiment row this block created (the API rerun
        # above, plus whatever id(s) the UI rerun click produced) by exact
        # candidate id -- not by parsing an id out of rendered text.
        import sqlite3
        conn = sqlite3.connect(str(ROOT / "studio_data" / "studio.db"))
        rows = conn.execute("SELECT id, config FROM experiments").fetchall()
        doomed_cid = f"user_{doomed_name}"
        doomed_exp_ids = [rid for rid, cfg in rows if json.loads(cfg).get("candidate") == doomed_cid]
        conn.executemany("DELETE FROM experiments WHERE id = ?", [(rid,) for rid in doomed_exp_ids])
        conn.commit()
        conn.close()

        # Post-cleanup invariant: the doomed-controller test above must not
        # have left a dangling reference behind once it cleaned up after
        # itself.
        known_ids = {c["id"] for c in json.loads(fetch_text(BASE_URL + "/api/controllers"))}
        experiments = json.loads(fetch_text(BASE_URL + "/api/experiments"))
        dangling = [
            e["id"] for e in experiments
            if e["config"].get("reference") not in known_ids or e["config"].get("candidate") not in known_ids
        ]
        expect("no experiment references a deleted controller", len(dangling) == 0, str(dangling[:5]))

        expect("no browser console errors", len(console_errors) == 0, str(console_errors[:5]))

        browser.close()

    print()
    if FAILURES:
        print(f"E2E: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("E2E: ALL PASS")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        cleanup_e2e_artifacts()
    sys.exit(code)
