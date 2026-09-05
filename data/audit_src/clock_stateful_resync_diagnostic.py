"""Part C, addendum item 3: stateful resynchronization diagnostic.

Diagnostic-only Mode-B variant: at every divergence, instead of stopping (as production R3B does),
replace the replay-private state with the EVENT'S OWN RECORDED semantic private POST state and
continue from the next event. Shared TCP state is already re-injected from the recording at every
event in Mode B (unchanged). The production replay algorithm (user/cubic_model.py, user/replay_r3b.py)
is not modified by this script.

Answers: does one clock-ambiguous divergence merely introduce a local, self-contained state error
(replay is exact again immediately after resyncing), or does unexplained drift continue afterward
even on CLOCK_STABLE events?
"""
import sys
import json

sys.path.insert(0, ".")
sys.path.insert(0, "user")
from user.ccr_trace_v1 import parse_trace_v1, select_dominant_connection, CALLBACK_NAMES, clock_classification
from user.cubic_model import transition, COMPARISON_FIELDS, PRIVATE_FIELDS, INITIAL_PRIVATE_STATE

TRACES = [
    "raw/cubic_replay/primary/rep1.ccr",
    "raw/cubic_replay/primary/rep2.ccr",
    "raw/cubic_replay/primary/rep3.ccr",
]


def private_post_from_event(e):
    return {f: e[f"priv_post_{f}"] for f in PRIVATE_FIELDS}


def run_resync_diagnostic(trace_path):
    meta_path = trace_path.replace(".ccr", ".meta.json")
    hdr, events = parse_trace_v1(trace_path)
    _, dominant_events, _ = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    ca = dict(INITIAL_PRIVATE_STATE)
    divergences = []
    exact_since_last_resync = 0
    unexplained_stable_divergence = None

    for idx, e in enumerate(dominant_events):
        cb = e["callback_id"]
        fields = COMPARISON_FIELDS[cb]
        computed, next_ca = transition(e, ca)
        diffs = [f for f in fields if computed[f] != e[f]]

        if diffs:
            clock = clock_classification(e)
            divergences.append({
                "event_index": idx, "seq": e["seq"], "callback": CALLBACK_NAMES.get(cb, cb),
                "clock": clock, "diff_fields": diffs,
                "exact_events_since_previous_resync_or_start": exact_since_last_resync,
            })
            if clock != "CLOCK_AMBIGUOUS" and unexplained_stable_divergence is None:
                unexplained_stable_divergence = divergences[-1]
                # Per addendum: STOP -- additional state-propagation problem. We keep scanning
                # (diagnostic-only, informational) but flag it clearly rather than silently
                # continuing as if nothing happened.
            # Resync: replace replay-private state with this event's own RECORDED private POST.
            ca = private_post_from_event(e)
            exact_since_last_resync = 0
        else:
            ca = next_ca
            exact_since_last_resync += 1

    return {
        "trace": trace_path,
        "n_events": len(dominant_events),
        "n_divergences": len(divergences),
        "divergences": divergences,
        "unexplained_clock_stable_divergence": unexplained_stable_divergence,
        "all_divergences_clock_ambiguous": all(d["clock"] == "CLOCK_AMBIGUOUS" for d in divergences),
        "min_exact_events_between_divergences": (
            min(d["exact_events_since_previous_resync_or_start"] for d in divergences)
            if divergences else None
        ),
    }


def main():
    results = [run_resync_diagnostic(t) for t in TRACES]
    overall = {
        "per_trace": results,
        "any_unexplained_clock_stable_divergence": any(
            r["unexplained_clock_stable_divergence"] is not None for r in results),
        "all_divergences_are_clock_ambiguous_in_every_trace": all(
            r["all_divergences_clock_ambiguous"] for r in results),
    }
    with open("data/cubic_clock_stateful_resync_diagnostic.json", "w") as f:
        json.dump(overall, f, indent=2, default=str)

    for r in results:
        print(f"=== {r['trace']} ===")
        print(f"  n_events={r['n_events']} n_divergences={r['n_divergences']}")
        print(f"  all_divergences_clock_ambiguous={r['all_divergences_clock_ambiguous']}")
        print(f"  unexplained_clock_stable_divergence={r['unexplained_clock_stable_divergence']}")
        for d in r["divergences"]:
            print(f"    seq={d['seq']} cb={d['callback']} clock={d['clock']} "
                  f"exact_since_prev={d['exact_events_since_previous_resync_or_start']} "
                  f"diffs={d['diff_fields']}")
    print()
    print("any_unexplained_clock_stable_divergence:", overall["any_unexplained_clock_stable_divergence"])
    print("all_divergences_are_clock_ambiguous_in_every_trace:",
          overall["all_divergences_are_clock_ambiguous_in_every_trace"])


if __name__ == "__main__":
    main()
