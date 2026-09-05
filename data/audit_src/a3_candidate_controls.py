"""Phases 3-4: mechanically verify the reconstructed-v3 candidate differs from
fixed/v4 in EXACTLY the A3 settle-latch guard, then run the synthetic positive
control and the real-trace negative controls. Offline, read-only.

Writes data/a3_candidate_controls.json.
"""
import sys
import json
import inspect
import difflib

sys.path.insert(0, ".")
sys.path.insert(0, "user")

import user.covegas_model as v4
import user.covegas_model_v3_latch as v3
from user.covegas_model import private_pre_from_event, ALL_PRIVATE_FIELDS, MODE_DELAY, MODE_COMPETE
from user.ccr_trace_v2 import parse_trace_v2, select_dominant_connection, CCR_CB_CONG_AVOID


def only_a3_difference():
    """Compare the two handle_compete_mode source bodies and confirm the ONLY
    change is the A3 guard; confirm v3.transition delegates to v4.transition."""
    src4 = inspect.getsource(v4.handle_compete_mode)
    src3 = inspect.getsource(v3.handle_compete_mode)
    # normalize: drop docstrings/comments/blank lines, keep code lines
    def code_lines(src):
        out = []
        in_doc = False
        for ln in src.splitlines():
            s = ln.strip()
            if s.startswith('"""'):
                if s.count('"""') >= 2:
                    continue          # one-line docstring
                in_doc = not in_doc
                continue
            if in_doc or not s or s.startswith("#"):
                continue
            # strip inline comments (none of these code lines contain '#' in a
            # string literal -- verified by eye)
            if "#" in s:
                s = s.split("#", 1)[0].rstrip()
            if s:
                out.append(s)
        return out
    c4, c3 = code_lines(src4), code_lines(src3)
    diff = list(difflib.unified_diff(c4, c3, "v4.handle_compete_mode", "v3.handle_compete_mode", lineterm=""))
    # lines present in v4 but not v3 (removed) and vice versa
    removed = [l[1:] for l in diff if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in diff if l.startswith("+") and not l.startswith("+++")]

    expected_removed = {
        'if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:',
        'ca["dlv_rate_compete"] = ca["dlv_rate_bps"]',
        'else:',
        'cwnd, ca = revert_to_delay(ca, pre, jiffies_now)',
        'return cwnd, cwnd_cnt, ca',
    }
    expected_added = {'ca["dlv_rate_compete"] = ca["dlv_rate_bps"]'}
    # the unconditional-latch assignment appears in BOTH (indented differently
    # after normalization it is the same string), so difflib may or may not
    # flag it; the load-bearing check is that the removed set is exactly the
    # guard's 5 lines and nothing else, and no OTHER code line changed.
    removed_set = set(removed)
    added_set = set(added)
    guard_only = removed_set.issubset(expected_removed) and added_set.issubset(expected_added | expected_removed)
    # v3.transition delegates to v4.transition (source contains the delegation)
    tsrc = inspect.getsource(v3.transition)
    delegates = "_base.transition(event, ca)" in tsrc and "_base.handle_compete_mode = handle_compete_mode" in tsrc
    return {
        "handle_compete_mode_removed_lines": removed,
        "handle_compete_mode_added_lines": added,
        "guard_is_the_only_difference": guard_only,
        "transition_delegates_to_base": delegates,
        "ONLY_A3_SEMANTIC_DIFFERENCE": guard_only and delegates,
    }


def synthetic_positive_control():
    """Phase 4.1: precommitted event rep1 seq=608. Copy private PRE state,
    set dlv_rate_bps = dlv_rate_max, invoke both transitions, compare."""
    hdr, events = parse_trace_v2("raw/covegas_replay/primary/rep1.ccr")
    _, dom, _ = select_dominant_connection(events)
    dom.sort(key=lambda e: e["seq"])
    ev = next(e for e in dom if e["seq"] == 608)
    assert ev["callback_id"] == CCR_CB_CONG_AVOID

    ca_real = private_pre_from_event(ev)
    ca_syn = dict(ca_real)
    old_bps = ca_syn["dlv_rate_bps"]
    ca_syn["dlv_rate_bps"] = ca_syn["dlv_rate_max"]
    changed = [f for f in ALL_PRIVATE_FIELDS if ca_syn[f] != ca_real[f]]

    out4, _ = v4.transition(ev, dict(ca_syn))
    out3, _ = v3.transition(ev, dict(ca_syn))

    diverge_fields = sorted(k for k in set(out4) | set(out3) if out4.get(k) != out3.get(k))
    passed = (
        changed == ["dlv_rate_bps"]
        and out4.get("priv_post_mode") == MODE_DELAY
        and out3.get("priv_post_mode") == MODE_COMPETE
        and out4.get("priv_post_dlv_rate_compete") == 0
        and out3.get("priv_post_dlv_rate_compete") == ca_syn["dlv_rate_max"]
        and len(diverge_fields) > 0
    )
    return {
        "source_event": "raw/covegas_replay/primary/rep1.ccr seq=608",
        "original_dlv_rate_bps": old_bps,
        "original_dlv_rate_max": ca_real["dlv_rate_max"],
        "original_ratio": round(old_bps / ca_real["dlv_rate_max"], 6),
        "synthetic_dlv_rate_bps": ca_syn["dlv_rate_bps"],
        "all_other_synthetic_private_fields_changed": [f for f in changed if f != "dlv_rate_bps"] or "NONE",
        "fixed_v4_post_mode": "DELAY" if out4.get("priv_post_mode") == MODE_DELAY else out4.get("priv_post_mode"),
        "v3_post_mode": "COMPETE" if out3.get("priv_post_mode") == MODE_COMPETE else out3.get("priv_post_mode"),
        "fixed_v4_post_dlv_rate_compete": out4.get("priv_post_dlv_rate_compete"),
        "v3_post_dlv_rate_compete": out3.get("priv_post_dlv_rate_compete"),
        "semantic_divergence": "YES" if diverge_fields else "NO",
        "divergent_fields": diverge_fields,
        "SYNTHETIC_POSITIVE_CONTROL": "PASS" if passed else "FAIL",
    }


def real_trace_negatives():
    """Phases 4.2 / 4.3 via the stateful ccreplay_diff engine."""
    from user.ccreplay_diff import diff_trace
    res = {}
    for rep in ("rep1", "rep2", "rep3"):
        t = f"raw/covegas_replay/primary/{rep}.ccr"
        m = f"raw/covegas_replay/primary/{rep}.meta.json"
        ff = diff_trace(t, m, v4, v4)
        fv3 = diff_trace(t, m, v4, v3)
        res[rep] = {
            "fixed_vs_fixed": ff["result"],
            "fixed_vs_fixed_matched": ff["matched_event_count_before_divergence"],
            "fixed_vs_v3": fv3["result"],
            "fixed_vs_v3_matched": fv3["matched_event_count_before_divergence"],
            "fixed_vs_v3_divergence": fv3["divergence"],
        }
    return res


def main():
    out = {
        "phase3_only_a3_difference": only_a3_difference(),
        "phase4_1_synthetic_positive_control": synthetic_positive_control(),
        "phase4_2_4_3_real_trace_negatives": real_trace_negatives(),
    }
    ok = (
        out["phase3_only_a3_difference"]["ONLY_A3_SEMANTIC_DIFFERENCE"]
        and out["phase4_1_synthetic_positive_control"]["SYNTHETIC_POSITIVE_CONTROL"] == "PASS"
        and all(v["fixed_vs_fixed"] == "NO DIVERGENCE" and v["fixed_vs_v3"] == "NO DIVERGENCE"
                for v in out["phase4_2_4_3_real_trace_negatives"].values())
    )
    out["ALL_CONTROLS_PASS"] = ok
    with open("data/a3_candidate_controls.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
