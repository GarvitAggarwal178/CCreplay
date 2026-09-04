"""R2 -- Reno stateful-controller exact semantic self-replay (Mode B).

Controller-private replay state is initialized ONCE per trace and
propagated across the recorded callback stream; recorded shared TCP
boundary state is injected from the trace at EVERY event (never derived
from the previous event's replay output -- docs/SEMANTICS.md, ADR-004).
Comparison finds the first divergence, not merely a per-event mismatch
count (docs/GATES.md R2 PASS = "first divergence = NONE").

Reno has no controller-private state (ADR-014): `private_state` is
initialized to reno_model.NONE_PRIVATE_STATE once, threaded through every
call to `transition()` in event order, and (correctly) never changes,
since nothing in the Reno transition writes to it. This is not a
shortcut around Mode B -- it is Mode B's actual, honestly-reported
behavior for a controller that carries no private history: initialization
is trivial and propagation is vacuous, and this is stated explicitly
rather than silently treated as "the same as R1" (see
docs/REPORT_GATES_R0_R1_R2.md discussion). The per-event computation is
identical to Mode A's because the only stateful ingredient Mode B could
have changed here does not exist for this controller; what R2 additionally
exercises that R1 does not is genuinely sequential replay: each event's
model call is fed the *actual* private_state carried out of the previous
event's call (not a fresh NONE_PRIVATE_STATE every time), so if a future
controller's model forgot to thread state correctly this harness would
still catch it.

Usage: replay_r2.py <trace1.ccr> <meta1.json> [<trace2.ccr> <meta2.json> ...]
"""
import sys
import json

sys.path.insert(0, ".")
from user.ccr_trace import parse_trace, select_dominant_connection, CALLBACK_NAMES
from user.reno_model import transition, COMPARISON_FIELDS, NONE_PRIVATE_STATE


def run_r2_on_trace(trace_path, meta_path):
    hdr, events = parse_trace(trace_path)
    dominant_cookie, dominant_events, other_events = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    private_state = NONE_PRIVATE_STATE  # initialized ONCE, before the loop
    first_divergence = None
    n_checked = 0

    for idx, e in enumerate(dominant_events):
        cb = e["callback_id"]
        fields = COMPARISON_FIELDS[cb]

        # Shared TCP boundary state for THIS event comes from the
        # recording (transition() reads pre_* directly off `e`), never
        # from the previous iteration's computed post-state.
        computed, private_state = transition(e, private_state)

        n_checked += 1
        diffs = [f for f in fields if computed[f] != e[f]]
        if diffs:
            first_divergence = {
                "trace": trace_path, "seq": e["seq"], "callback": CALLBACK_NAMES.get(cb),
                "event_index": idx,
                "expected": {f: computed[f] for f in fields},
                "actual": {f: e[f] for f in fields},
                "diff_fields": diffs,
                "private_state_at_divergence": private_state,
            }
            break

    return {
        "trace": trace_path,
        "n_events_dominant": len(dominant_events),
        "n_checked_before_stop": n_checked,
        "first_divergence": first_divergence,
        "final_private_state": private_state,
    }


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json> [...]", file=sys.stderr)
        sys.exit(2)

    results = []
    for i in range(0, len(args), 2):
        results.append(run_r2_on_trace(args[i], args[i + 1]))

    overall_first_divergence = next((r["first_divergence"] for r in results if r["first_divergence"]), None)

    summary = {
        "gate": "R2",
        "pass": overall_first_divergence is None,
        "traces": [r["trace"] for r in results],
        "total_events_replayed_sequentially": sum(r["n_checked_before_stop"] for r in results),
        "first_divergence": overall_first_divergence,
        "per_trace": results,
        "note": "Reno has no controller-private state (ADR-014); private_state is NONE "
                "throughout by construction, not by omission -- see module docstring.",
    }
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
