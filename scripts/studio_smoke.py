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
from ccreplay.diff import run_diff
from ccreplay.checkpoint import run_checkpoint

FAILURES = []


def expect(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    cubic_rep1 = None
    for t in traces_mod.list_traces():
        if t.get("path") == "raw/cubic_replay/primary/rep1.ccr":
            cubic_rep1 = t["id"]
    expect("cubic_rep1 found in library", cubic_rep1 is not None, str(cubic_rep1))
    if cubic_rep1 is None:
        sys.exit(1)

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

    ck = run_checkpoint(cubic_rep1, "cubic", "cubic_bug_ssthresh", 500)
    expect("checkpoint @ event 1500", ck["nearest_checkpoint"]["event_index"] == 1500,
           str(ck.get("nearest_checkpoint")))
    expect("checkpoint suffix length 204", ck["suffix_length"] == 204, str(ck.get("suffix_length")))
    expect("checkpoint reproduced identical divergence", ck["reproduced_same_divergence"] is True,
           str(ck["reproduced_same_divergence"]))

    cid = controllers_mod.save_param_variant("cubic", "beta_default_check", {})
    r = run_diff(cubic_rep1, "cubic", cid)
    expect("default-param clone == NO DIVERGENCE", r["result"] == "NO DIVERGENCE", r["result"])

    cid2 = controllers_mod.save_param_variant("cubic", "beta_819", {"BETA": 819})
    r = run_diff(cubic_rep1, "cubic", cid2)
    d = r.get("divergence") or {}
    seq = d.get("first_divergent_event", {}).get("seq")
    expect("BETA=819 divergence seq == 742", seq == 742, str(seq))
    expect("BETA=819 callback == cong_avoid", d.get("callback") == "cong_avoid", str(d.get("callback")))

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
        sys.exit(1)
    print("SMOKE TEST: ALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
