#!/usr/bin/env python3
"""Asserts STUDIO_CONTEXT.md §8 expected values through the ccreplay/
wrappers, before any UI is built on top of them. Exits 0 iff every
assertion passes; prints a readable report either way.
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ccreplay import traces as traces_mod
from ccreplay import controllers as controllers_mod
from ccreplay.diff import run_diff, run_all_decisions
from ccreplay.checkpoint import run_checkpoint

FAILURES = []
CREATED_PARAM_IDS = []   # cleaned up at the end -- never a blanket wipe of studio_data/param_variants.json
CREATED_USER_IDS = []    # cleaned up at the end -- never a blanket `rm controllers/user/user_*.py`


def expect(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def save_param(base, name, params):
    cid = controllers_mod.save_param_variant(base, name, params)
    CREATED_PARAM_IDS.append(cid)
    return cid


def save_user(name, abi_base, code):
    cid = controllers_mod.save_user_controller(name, abi_base, code)
    CREATED_USER_IDS.append(cid)
    return cid


def cleanup():
    """Removes exactly the controllers THIS RUN created -- never a blanket
    wipe, which would delete real owner data in any session that has some
    (see STUDIO_STATUS.md's note on this)."""
    if CREATED_PARAM_IDS:
        store = controllers_mod._param_store_load()
        for cid in CREATED_PARAM_IDS:
            store.pop(cid, None)
        controllers_mod._param_store_save(store)
    for cid in CREATED_USER_IDS:
        (controllers_mod.USER_DIR / f"{cid}.py").unlink(missing_ok=True)
        (controllers_mod.USER_DIR / f"{cid}.meta.json").unlink(missing_ok=True)


def main():
    cubic_rep1 = None
    for t in traces_mod.list_traces():
        if t.get("path") == "raw/cubic_replay/primary/rep1.ccr":
            cubic_rep1 = t["id"]
    expect("cubic_rep1 found in library", cubic_rep1 is not None, str(cubic_rep1))
    if cubic_rep1 is None:
        return 1

    t = traces_mod.get_trace(cubic_rep1)
    expect("cubic_rep1 n_dominant_events == 78688", t["n_dominant_events"] == 78688, str(t["n_dominant_events"]))

    r = run_diff(cubic_rep1, "cubic", "cubic")
    expect("negative control NO DIVERGENCE", r["result"] == "NO DIVERGENCE", r["result"])
    expect("negative control 78688 events", r["n_events_dominant"] == 78688, str(r["n_events_dominant"]))

    r = run_diff(cubic_rep1, "cubic", "cubic_bug_ssthresh")
    d = r.get("divergence") or {}
    seq = d.get("first_divergent_event", {}).get("seq")
    cb = d.get("callback")
    res = d.get("callback_result_diff", {}).get("result", {})
    expect("seeded bug seq == 1705", seq == 1705, str(seq))
    expect("seeded bug callback == ssthresh", cb == "ssthresh", str(cb))
    expect("seeded bug 145 vs 146", res.get("reference") == 145 and res.get("candidate") == 146, str(res))
    expect("seeded bug kind == result (M2 done-when)", r.get("kind") == "result", str(r.get("kind")))

    ck = run_checkpoint(cubic_rep1, "cubic", "cubic_bug_ssthresh", 500)
    expect("checkpoint @ event 1500", ck["nearest_checkpoint"]["event_index"] == 1500,
           str(ck.get("nearest_checkpoint")))
    expect("checkpoint suffix length 204", ck["suffix_length"] == 204, str(ck.get("suffix_length")))
    expect("checkpoint reproduced identical divergence", ck["reproduced_same_divergence"] is True,
           str(ck["reproduced_same_divergence"]))

    cid = save_param("cubic", "beta_default_check", {})
    r = run_diff(cubic_rep1, "cubic", cid)
    expect("default-param clone == NO DIVERGENCE", r["result"] == "NO DIVERGENCE", r["result"])

    cid2 = save_param("cubic", "beta_819", {"BETA": 819})
    r = run_diff(cubic_rep1, "cubic", cid2)
    d = r.get("divergence") or {}
    seq = d.get("first_divergent_event", {}).get("seq")
    expect("BETA=819 divergence seq == 742", seq == 742, str(seq))
    expect("BETA=819 callback == cong_avoid", d.get("callback") == "cong_avoid", str(d.get("callback")))
    expect("BETA=819 kind == private_state_only (M2 done-when)", r.get("kind") == "private_state_only",
           str(r.get("kind")))

    # Reno parameter variants (r0 rep1) -- the num/den retention-fraction path,
    # separate code from the CUBIC path above and never exercised until now.
    reno_rep1 = None
    for tr in traces_mod.list_traces():
        if tr.get("path") == "raw/r0/rep1.ccr":
            reno_rep1 = tr["id"]
    expect("reno r0 rep1 found", reno_rep1 is not None, str(reno_rep1))
    if reno_rep1:
        cid_std = save_param("reno", "reno_std_1_2", {"num": 1, "den": 2})
        r = run_diff(reno_rep1, "reno", cid_std)
        expect("reno 1/2 (standard) == NO DIVERGENCE", r["result"] == "NO DIVERGENCE", r["result"])

        cid_gentle = save_param("reno", "reno_3_4", {"num": 3, "den": 4})
        r = run_diff(reno_rep1, "reno", cid_gentle)
        expect("reno 3/4 (gentler) diverges", r["result"] == "DIVERGENCE", r["result"])

    # User-written controller path (the code editor): template unchanged must
    # be a no-op (NO DIVERGENCE), OFFSET=1 must reproduce STUDIO_CONTEXT.md
    # SS8's verified "User override" row exactly.
    template = controllers_mod.get_template("cubic")
    cid_unchanged = save_user("smoke_template_unchanged", "cubic", template)
    v = controllers_mod.validate_controller(cid_unchanged)
    expect("template-unchanged controller validates OK", v["ok"], str(v))
    r = run_diff(cubic_rep1, "cubic", cid_unchanged)
    expect("template unchanged (OFFSET=0) == NO DIVERGENCE", r["result"] == "NO DIVERGENCE", r["result"])

    offset1_code = template.replace("OFFSET = 0", "OFFSET = 1")
    expect("OFFSET=1 substitution actually changed the source", offset1_code != template)
    cid_offset1 = save_user("smoke_template_offset1", "cubic", offset1_code)
    r = run_diff(cubic_rep1, "cubic", cid_offset1)
    d = r.get("divergence") or {}
    seq = d.get("first_divergent_event", {}).get("seq")
    res = d.get("callback_result_diff", {}).get("result", {})
    expect("User override seq == 1705", seq == 1705, str(seq))
    expect("User override 145 vs 144", res.get("reference") == 145 and res.get("candidate") == 144, str(res))

    # Reno template path (separate code from CUBIC's above, never exercised until now).
    reno_template = controllers_mod.get_template("reno")
    expect("reno template contains the NUM/DEN no-op default", "NUM = 1" in reno_template and "DEN = 2" in reno_template,
           reno_template[:200])
    cid_reno_unchanged = save_user("smoke_reno_template_unchanged", "reno", reno_template)
    v = controllers_mod.validate_controller(cid_reno_unchanged)
    expect("reno template-unchanged validates OK", v["ok"], str(v))
    if reno_rep1:
        r = run_diff(reno_rep1, "reno", cid_reno_unchanged)
        expect("reno template unchanged (1/2) == NO DIVERGENCE", r["result"] == "NO DIVERGENCE", r["result"])

        reno_3_4_code = reno_template.replace("NUM = 1", "NUM = 3").replace("DEN = 2", "DEN = 4")
        cid_reno_3_4 = save_user("smoke_reno_template_3_4", "reno", reno_3_4_code)
        r = run_diff(reno_rep1, "reno", cid_reno_3_4)
        expect("reno template NUM=3,DEN=4 diverges", r["result"] == "DIVERGENCE", r["result"])

    # A controller file that doesn't define CONTROLLER must fail validation
    # with a readable reason (plan §3 A1 "missing CONTROLLER" done-when).
    cid_no_controller = save_user("smoke_no_controller", "cubic", "x = 1\n")
    v = controllers_mod.validate_controller(cid_no_controller)
    expect("missing-CONTROLLER module fails validation", v["ok"] is False, str(v))
    expect("missing-CONTROLLER reason names CONTROLLER",
           any("CONTROLLER" in c.get("detail", "") for c in v.get("checks", [])), str(v.get("checks")))

    # Broken Python must fail validation with a readable reason, never a fake PASS.
    cid_broken = save_user("smoke_broken", "cubic", "this is not valid python +++")
    v = controllers_mod.validate_controller(cid_broken)
    expect("broken controller validation ok == False", v["ok"] is False, str(v))
    expect("broken controller reason mentions syntax",
           any("syntax" in c.get("detail", "").lower() for c in v.get("checks", [])), str(v.get("checks")))

    # M7 all-decisions (ADR-026): precommitted predictions, each independently
    # verified against the real engine before being written here (see
    # STUDIO_STATUS.md's M7 section) -- not fitted to whatever the first run
    # happened to produce.
    r = run_all_decisions(cubic_rep1, "cubic", "cubic", mode="A")
    expect("all-decisions cubic vs cubic Mode A: 0 disagreements", r["n_disagree"] == 0, str(r["n_disagree"]))
    expect("all-decisions cubic vs cubic Mode A: all 78688 events checked", r["n_events"] == 78688, str(r["n_events"]))

    r = run_all_decisions(cubic_rep1, "cubic", "cubic_bug_dormant_undo", mode="A")
    expect("all-decisions dormant_undo vs cubic Mode A: 0 disagreements (rep1 has no undo_cwnd events)",
           r["n_disagree"] == 0, str(r["n_disagree"]))

    r = run_all_decisions(cubic_rep1, "cubic", "cubic_bug_ssthresh", mode="A")
    expect("all-decisions seeded ssthresh bug Mode A: exactly 14 disagreements (unconditional +1, "
           "rep1 has 14 ssthresh events -- verified via `diff user/cubic_model.py "
           "user/cubic_model_bug_ssthresh.py` before this assertion was written)",
           r["n_disagree"] == 14, str(r["n_disagree"]))
    expect("all-decisions seeded ssthresh bug: disagreements are ssthresh-only",
           r["per_callback_disagree"] == {"ssthresh": 14}, str(r["per_callback_disagree"]))
    expect("all-decisions seeded ssthresh bug: first disagreement matches diff_trace's seq 1705",
           r["first_disagreement_seq"] == 1705, str(r["first_disagreement_seq"]))

    r = run_all_decisions(cubic_rep1, "cubic", "cubic_bug_ssthresh", mode="B")
    expect("all-decisions seeded ssthresh bug Mode B: same first-divergence location as Mode A/diff_trace",
           r["first_disagreement_seq"] == 1705, str(r["first_disagreement_seq"]))
    expect("all-decisions seeded ssthresh bug Mode B: bug does not cascade into other callbacks",
           r["n_disagree"] == 14, str(r["n_disagree"]))

    cid_default = save_param("cubic", "sweep_default_check", {"BETA": 717})
    r = run_all_decisions(cubic_rep1, "cubic", cid_default, mode="A")
    expect("all-decisions BETA=717 (identical to the reference default): 0 disagreements",
           r["n_disagree"] == 0, str(r["n_disagree"]))

    covegas_rep4 = None
    for tr in traces_mod.list_traces():
        if tr.get("path") == "raw/covegas_campaign/rep4.ccr":
            covegas_rep4 = tr["id"]
    expect("covegas_campaign rep4 found", covegas_rep4 is not None, str(covegas_rep4))
    if covegas_rep4:
        r = run_diff(covegas_rep4, "covegas", "covegas_v3_latch")
        d = r.get("divergence") or {}
        seq = d.get("first_divergent_event", {}).get("seq")
        expect("historical divergence seq == 10421", seq == 10421, str(seq))
        mode_diff = d.get("private_state_diff", {}).get("priv_post_mode", {})
        expect("historical mode DELAY<->COMPETE", set(mode_diff.values()) == {0, 1}, str(mode_diff))

    print()
    if FAILURES:
        print(f"SMOKE TEST: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("SMOKE TEST: ALL PASS")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        cleanup()
    sys.exit(code)
