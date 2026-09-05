"""R3B -- CUBIC stateful-controller exact semantic self-replay (Mode B).

Controller-private replay state is initialized ONCE per trace (seeded as
all-zero, matching a freshly allocated `icsk_ca_priv` -- real sockets are
zeroed at creation, before the CC implementation's `.init` ever runs) and
propagated across the recorded callback stream; recorded SHARED TCP
boundary state is injected from the trace at every event, but PRIVATE state
is never re-seeded from the recording after the initial zero state (CLAUDE.md
Mode B definition). The dominant connection's first event is always
`init` (CCR_CB_INIT fires exactly once per connection, N1.5 manifest) --
so `init`'s own transition IS the seeding step, and its recorded POST state
is the first thing compared, not skipped (this directly demonstrates the
private-state propagation the pipeline requires "nontrivial": every
subsequent event's `ca` argument is what THIS model computed for the
previous event, never what the recorder captured).

Comparison finds the FIRST divergence, not merely a per-event mismatch
count (R2/R3B PASS = "first divergence = NONE"). Per the clock-window
hazard investigation (data/cubic_replay_capability_audit.md), a divergence
on a CLOCK_AMBIGUOUS event is reported and classified separately rather
than silently treated the same as a CLOCK_STABLE divergence -- the pipeline
requires PASS to demonstrate central-path exactness, and stopping the
sequential replay AT a clock-ambiguous divergence (rather than skipping
past it) is the honest behavior: Mode B's private state genuinely does
diverge from that point forward once a CLOCK_AMBIGUOUS mismatch occurs,
since (unlike R3A) there is no fresh recorded PRE to resynchronize from on
the next event.

Usage: replay_r3b.py <trace1.ccr> <meta1.json> [<trace2.ccr> <meta2.json> ...]
"""
import sys
import json

sys.path.insert(0, ".")
from user.ccr_trace_v1 import parse_trace_v1, select_dominant_connection, CALLBACK_NAMES, clock_classification
from user.cubic_model import transition, COMPARISON_FIELDS, PRIVATE_FIELDS, CCR_CB_INIT, INITIAL_PRIVATE_STATE

ZERO_PRIVATE_STATE = INITIAL_PRIVATE_STATE


def run_r3b_on_trace(trace_path, meta_path):
    hdr, events = parse_trace_v1(trace_path)
    dominant_cookie, dominant_events, other_events = select_dominant_connection(events)
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
                "error": "first dominant-connection event is not callback_id=CCR_CB_INIT "
                         f"(got {dominant_events[0]['callback_id']}) -- Mode B's zero-state "
                         "seeding assumption does not hold for this trace"
            },
            "final_private_state": None, "fields_that_changed": [],
        }

    ca = ZERO_PRIVATE_STATE  # initialized ONCE, before the loop (fresh icsk_ca_priv)
    first_divergence = None
    n_checked = 0
    private_state_history = [dict(ca)]

    for idx, e in enumerate(dominant_events):
        cb = e["callback_id"]
        fields = COMPARISON_FIELDS[cb]

        # Shared TCP boundary state for THIS event comes from the
        # recording; private state (`ca`) is whatever THIS model computed
        # for the previous event.
        computed, ca = transition(e, ca)
        private_state_history.append(dict(ca))

        n_checked += 1
        diffs = [f for f in fields if computed[f] != e[f]]
        if diffs:
            first_divergence = {
                "trace": trace_path, "seq": e["seq"], "callback": CALLBACK_NAMES.get(cb),
                "event_index": idx, "clock": clock_classification(e),
                "expected": {f: computed[f] for f in fields},
                "actual": {f: e[f] for f in fields},
                "diff_fields": diffs,
                "private_state_at_divergence": ca,
            }
            break

    # "demonstrate that private state evolved NONTRIVIALLY" -- report which
    # of the 16 semantic fields actually took more than one distinct value
    # across the whole (possibly stopped-early) replayed prefix.
    fields_that_changed = [
        f for f in PRIVATE_FIELDS
        if len({s[f] for s in private_state_history}) > 1
    ]

    return {
        "trace": trace_path,
        "n_events_dominant": len(dominant_events),
        "n_checked_before_stop": n_checked,
        "first_divergence": first_divergence,
        "final_private_state": ca,
        "fields_that_changed": fields_that_changed,
        "fields_that_never_changed": [f for f in PRIVATE_FIELDS if f not in fields_that_changed],
    }


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json> [...]", file=sys.stderr)
        sys.exit(2)

    results = []
    for i in range(0, len(args), 2):
        results.append(run_r3b_on_trace(args[i], args[i + 1]))

    overall_first_divergence = next((r["first_divergence"] for r in results if r["first_divergence"]), None)
    overall_first_divergence_is_clock_ambiguous = (
        overall_first_divergence is not None and
        overall_first_divergence.get("clock") == "CLOCK_AMBIGUOUS"
    )
    all_fields_changed = set()
    for r in results:
        all_fields_changed |= set(r.get("fields_that_changed", []))

    summary = {
        "gate": "R3B",
        "pass": overall_first_divergence is None,
        "pass_first_divergence_is_only_clock_ambiguous": overall_first_divergence_is_clock_ambiguous,
        "traces": [r["trace"] for r in results],
        "total_events_replayed_sequentially": sum(r["n_checked_before_stop"] for r in results),
        "first_divergence": overall_first_divergence,
        "nontrivial_private_state_propagation": bool(all_fields_changed),
        "fields_that_changed_across_any_trace": sorted(all_fields_changed),
        "fields_that_never_changed_in_any_trace": sorted(set(PRIVATE_FIELDS) - all_fields_changed),
        "per_trace": results,
        "note": "Private state seeded as all-zero once per trace (fresh icsk_ca_priv), "
                "never re-injected from the recording after that -- only shared TCP "
                "state is re-injected per event, per CLAUDE.md's Mode B definition.",
    }
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
