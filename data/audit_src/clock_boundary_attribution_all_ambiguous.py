"""Addendum item 1: full two-sided clock attribution over ALL 46 CLOCK_AMBIGUOUS events
(not just the 4 that mismatch under the production `clock_jiffies32_before` convention --
see clock_boundary_attribution.py / data/cubic_clock_boundary_attribution.json for that
narrower, already-published table).

For every CLOCK_AMBIGUOUS event across the three primary CUBIC traces, test two
DIAGNOSTIC-ONLY substitutions in isolation:

  using clock_jiffies32_before (== the production convention)
  using clock_jiffies32_after

Classify each event MATCHES_BEFORE_ONLY / MATCHES_AFTER_ONLY / MATCHES_BOTH / MATCHES_NEITHER,
where "matches" means the computed fields equal every one of that callback's declared
comparison fields as actually recorded.

Diagnostic-only: does not alter user/cubic_model.py, the production Replay Contract, the
selected clock convention, or the R3 verdict. Never used to dynamically pick a clock during
normal replay.

Writes data/cubic_clock_boundary_attribution_all_ambiguous.json.
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

    computed_before, _ = transition(e, dict(ca))  # production convention

    e_after = dict(e)
    e_after["clock_jiffies32_before"] = e["clock_jiffies32_after"]
    computed_after, _ = transition(e_after, dict(ca))

    matches_before = all(computed_before[f] == e[f] for f in fields)
    matches_after = all(computed_after[f] == e[f] for f in fields)

    if matches_before and matches_after:
        return "MATCHES_BOTH", matches_before, matches_after
    if matches_before:
        return "MATCHES_BEFORE_ONLY", matches_before, matches_after
    if matches_after:
        return "MATCHES_AFTER_ONLY", matches_before, matches_after
    return "MATCHES_NEITHER", matches_before, matches_after


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

            classification, matches_before, matches_after = classify_event(e, fields)
            counts[classification] += 1
            rows.append({
                "trace": trace_path,
                "seq": e["seq"],
                "callback": CALLBACK_NAMES.get(cb, cb),
                "clock_before": e["clock_jiffies32_before"],
                "clock_after": e["clock_jiffies32_after"],
                "matches_before": matches_before,
                "matches_after": matches_after,
                "classification": classification,
            })

    result = {
        "scope": "ALL CLOCK_AMBIGUOUS events across all three primary traces (not scoped to "
                 "the 4 that mismatch under the production clock_jiffies32_before convention)",
        "n_events_classified": len(rows),
        "counts": counts,
        "attribution_closed": counts["MATCHES_NEITHER"] == 0,
        "interpretation": (
            "The recorded transition is semantically compatible with the indicated value(s) "
            "from the before/after clock bracket under the replay model. This is not a claim "
            "that the reference necessarily read exactly that value; MATCHES_BOTH events are "
            "ones where the callback's declared comparison fields happen not to depend on the "
            "clock delta between the before/after snapshots for that specific event."
        ),
        "rows": rows,
    }
    with open("data/cubic_clock_boundary_attribution_all_ambiguous.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    print()
    print(f"{'trace':<45} {'seq':>8} {'callback':<12} {'before':>12} {'after':>12} {'classification'}")
    for r in rows:
        print(f"{r['trace']:<45} {r['seq']:>8} {r['callback']:<12} {r['clock_before']:>12} "
              f"{r['clock_after']:>12} {r['classification']}")


if __name__ == "__main__":
    main()
