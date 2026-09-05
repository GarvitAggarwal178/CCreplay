"""E3 -- CoVegas stateful-controller exact semantic self-replay (Mode B).

Same shape as user/replay_r3b.py, adapted for ADR-023's mode-dependent
comparison schema and ADR-024's two independent clocks. Private state
initialized once (all-zero, matching a freshly allocated icsk_ca_priv);
the trace's own `init` event is transition #1, not skipped. Per the
pipeline's explicit instruction: "Do not silently inherit CUBIC's clock
exception. Prove whether it applies." -- this engine classifies every
divergence by BOTH clocks independently rather than assuming either
clock's CUBIC-established behavior transfers.

Usage: replay_e3.py <trace.ccr> <meta.json> [...]
"""
import sys
import json

sys.path.insert(0, ".")
from user.ccr_trace_v2 import (
    parse_trace_v2, select_dominant_connection, CALLBACK_NAMES,
    jiffies_clock_classification, ktime_clock_classification,
)
from user.covegas_model import transition, comparison_fields, ALL_PRIVATE_FIELDS, INITIAL_PRIVATE_STATE, CCR_CB_INIT

ZERO_PRIVATE_STATE = INITIAL_PRIVATE_STATE


def run_e3_on_trace(trace_path, meta_path):
    hdr, events = parse_trace_v2(trace_path)
    _, dominant_events, _ = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    if not dominant_events:
        return {
            "trace": trace_path, "n_events_dominant": 0,
            "n_checked_before_stop": 0, "first_divergence": None,
            "final_private_state": None, "fields_that_changed": [],
        }

    if dominant_events[0]["callback_id"] != CCR_CB_INIT:
        return {
            "trace": trace_path, "n_events_dominant": len(dominant_events),
            "n_checked_before_stop": 0,
            "first_divergence": {
                "error": f"first dominant-connection event is not CCR_CB_INIT "
                         f"(got {dominant_events[0]['callback_id']})"
            },
            "final_private_state": None, "fields_that_changed": [],
        }

    ca = dict(ZERO_PRIVATE_STATE)
    first_divergence = None
    n_checked = 0
    private_state_history = [dict(ca)]

    for idx, e in enumerate(dominant_events):
        cb = e["callback_id"]
        computed, ca = transition(e, ca)
        fields = comparison_fields(cb, e["priv_pre_mode"], computed["priv_post_mode"])
        private_state_history.append(dict(ca))

        n_checked += 1
        diffs = [f for f in fields if computed.get(f) != e.get(f)]
        if diffs:
            first_divergence = {
                "trace": trace_path, "seq": e["seq"], "callback": CALLBACK_NAMES.get(cb),
                "event_index": idx,
                "jiffies_clock": jiffies_clock_classification(e),
                "ktime_clock": ktime_clock_classification(e),
                "expected": {f: computed.get(f) for f in fields},
                "actual": {f: e.get(f) for f in fields},
                "diff_fields": diffs,
                "private_state_at_divergence": ca,
            }
            break

    fields_that_changed = [
        f for f in ALL_PRIVATE_FIELDS
        if len({s[f] for s in private_state_history}) > 1
    ]

    return {
        "trace": trace_path,
        "n_events_dominant": len(dominant_events),
        "n_checked_before_stop": n_checked,
        "first_divergence": first_divergence,
        "final_private_state": ca,
        "fields_that_changed": fields_that_changed,
        "fields_that_never_changed": [f for f in ALL_PRIVATE_FIELDS if f not in fields_that_changed],
    }


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json> [...]", file=sys.stderr)
        sys.exit(2)

    results = [run_e3_on_trace(args[i], args[i + 1]) for i in range(0, len(args), 2)]

    overall_first_divergence = next((r["first_divergence"] for r in results if r["first_divergence"]), None)
    all_fields_changed = set()
    for r in results:
        all_fields_changed |= set(r.get("fields_that_changed", []))

    # "Do not silently inherit CUBIC's clock exception. Prove whether it
    # applies." -- classify explicitly whether the (if any) divergence is
    # attributable to either clock, both, or neither.
    clock_attribution = None
    if overall_first_divergence and "jiffies_clock" in overall_first_divergence:
        j = overall_first_divergence["jiffies_clock"]
        k = overall_first_divergence["ktime_clock"]
        if j == "CLOCK_AMBIGUOUS" and k == "CLOCK_STABLE":
            clock_attribution = "JIFFIES_AMBIGUOUS_ONLY"
        elif j == "CLOCK_STABLE" and k == "CLOCK_AMBIGUOUS":
            clock_attribution = "KTIME_AMBIGUOUS_ONLY"
        elif j == "CLOCK_AMBIGUOUS" and k == "CLOCK_AMBIGUOUS":
            clock_attribution = "BOTH_AMBIGUOUS"
        else:
            clock_attribution = "NEITHER_AMBIGUOUS_UNEXPLAINED"

    summary = {
        "gate": "E3",
        "pass": overall_first_divergence is None,
        "traces": [r["trace"] for r in results],
        "total_events_replayed_sequentially": sum(r["n_checked_before_stop"] for r in results),
        "first_divergence": overall_first_divergence,
        "clock_attribution_of_first_divergence": clock_attribution,
        "nontrivial_private_state_propagation": bool(all_fields_changed),
        "fields_that_changed_across_any_trace": sorted(all_fields_changed),
        "fields_that_never_changed_in_any_trace": sorted(set(ALL_PRIVATE_FIELDS) - all_fields_changed),
        "per_trace": results,
        "note": "Private state seeded as all-zero once per trace (fresh icsk_ca_priv), "
                "never re-injected from the recording after that.",
    }
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
