"""Part C, addendum item 2: two-sided clock attribution diagnostic.

For every event in the three primary CUBIC traces that is CLOCK_AMBIGUOUS AND currently mismatches
under the production `_before` convention (R3A, event-local Mode A), test two DIAGNOSTIC-ONLY
substitutions on that event in isolation:

  Diagnostic A: use clock_jiffies32_before (== the production convention, already known to mismatch
                by construction of this event set -- included for completeness/table symmetry)
  Diagnostic B: use clock_jiffies32_after

Classify each event MATCHES_BEFORE_ONLY / MATCHES_AFTER_ONLY / MATCHES_BOTH / MATCHES_NEITHER.

This is diagnostic-only: it does NOT alter user/cubic_model.py, the production Replay Contract, the
selected clock convention, or the R3 verdict. Never used to dynamically pick a clock during normal
replay.

Writes data/cubic_clock_boundary_attribution.json.
"""
import sys
import json

sys.path.insert(0, ".")
sys.path.insert(0, "user")
from user.ccr_trace_v1 import parse_trace_v1, select_dominant_connection, CALLBACK_NAMES, clock_classification
from user.cubic_model import transition, COMPARISON_FIELDS, private_pre_from_event

TRACES = [
    ("raw/cubic_replay/primary/rep1.ccr", "raw/cubic_replay/primary/rep1.meta.json"),
    ("raw/cubic_replay/primary/rep2.ccr", "raw/cubic_replay/primary/rep2.meta.json"),
    ("raw/cubic_replay/primary/rep3.ccr", "raw/cubic_replay/primary/rep3.meta.json"),
]


def classify_event(e, fields):
    ca = private_pre_from_event(e)

    computed_before, _ = transition(e, dict(ca))  # production convention (clock_jiffies32_before)

    e_after = dict(e)
    e_after["clock_jiffies32_before"] = e["clock_jiffies32_after"]
    computed_after, _ = transition(e_after, dict(ca))

    matches_before = all(computed_before[f] == e[f] for f in fields)
    matches_after = all(computed_after[f] == e[f] for f in fields)

    if matches_before and matches_after:
        return "MATCHES_BOTH", computed_before, computed_after
    if matches_before:
        return "MATCHES_BEFORE_ONLY", computed_before, computed_after
    if matches_after:
        return "MATCHES_AFTER_ONLY", computed_before, computed_after
    return "MATCHES_NEITHER", computed_before, computed_after


def main():
    rows = []
    counts = {"MATCHES_BEFORE_ONLY": 0, "MATCHES_AFTER_ONLY": 0, "MATCHES_BOTH": 0, "MATCHES_NEITHER": 0}

    for trace_path, meta_path in TRACES:
        hdr, events = parse_trace_v1(trace_path)
        _, dominant_events, _ = select_dominant_connection(events)
        dominant_events.sort(key=lambda e: e["seq"])

        for e in dominant_events:
            if clock_classification(e) != "CLOCK_AMBIGUOUS":
                continue
            cb = e["callback_id"]
            fields = COMPARISON_FIELDS[cb]
            ca = private_pre_from_event(e)
            computed_before, _ = transition(e, dict(ca))
            currently_mismatches = any(computed_before[f] != e[f] for f in fields)
            if not currently_mismatches:
                continue  # scope per addendum item 2: only currently-mismatching events

            classification, computed_before, computed_after = classify_event(e, fields)
            counts[classification] += 1
            rows.append({
                "trace": trace_path,
                "seq": e["seq"],
                "callback": CALLBACK_NAMES.get(cb, cb),
                "clock_before": e["clock_jiffies32_before"],
                "clock_after": e["clock_jiffies32_after"],
                "classification": classification,
                "diff_fields_under_before": [f for f in fields if computed_before[f] != e[f]],
                "diff_fields_under_after": [f for f in fields if computed_after[f] != e[f]],
            })

    result = {
        "scope": "CLOCK_AMBIGUOUS events that currently mismatch under the production "
                 "clock_jiffies32_before convention, across all three primary traces",
        "n_events_classified": len(rows),
        "counts": counts,
        "attribution_closed": counts["MATCHES_NEITHER"] == 0,
        "rows": rows,
    }
    with open("data/cubic_clock_boundary_attribution.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    print()
    print(f"{'trace':<45} {'seq':>8} {'callback':<12} {'before':>12} {'after':>12} {'classification'}")
    for r in rows:
        print(f"{r['trace']:<45} {r['seq']:>8} {r['callback']:<12} {r['clock_before']:>12} "
              f"{r['clock_after']:>12} {r['classification']}")


if __name__ == "__main__":
    main()
