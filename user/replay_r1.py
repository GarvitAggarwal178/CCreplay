"""R1 -- Reno event-local exact semantic self-replay (Mode A).

For each event independently: load recorded shared PRE state + callback
inputs, run the transition, compare declared callback result and
controller-owned POST state against what was recorded. No replay state
carries to the next event (docs/SEMANTICS.md Mode A;
private_state is always reno_model.NONE_PRIVATE_STATE since Mode A never
threads anything between events, private or otherwise).

PASS requires 100% exact equality on every declared exact field of every
valid event, across all R0 traces (docs/GATES.md R1).

Usage: replay_r1.py <trace1.ccr> <meta1.json> [<trace2.ccr> <meta2.json> ...]
"""
import sys
import json

sys.path.insert(0, ".")
from user.ccr_trace import parse_trace, select_dominant_connection, CALLBACK_NAMES
from user.reno_model import transition, COMPARISON_FIELDS, NONE_PRIVATE_STATE


def diagnose_mismatch(trace_path, events, idx, expected, actual, diff_fields):
    e = events[idx]
    lo = max(0, idx - 5)
    hi = min(len(events), idx + 6)
    print("=" * 70)
    print(f"MISMATCH  trace={trace_path}  seq={e['seq']}  "
          f"callback={CALLBACK_NAMES.get(e['callback_id'], e['callback_id'])}  "
          f"ts_ns={e['ts_ns']}")
    print(f"  shared PRE: snd_cwnd={e['pre_snd_cwnd']} snd_ssthresh={e['pre_snd_ssthresh']} "
          f"snd_cwnd_cnt={e['pre_snd_cwnd_cnt']} snd_cwnd_clamp={e['pre_snd_cwnd_clamp']} "
          f"prior_cwnd={e['pre_prior_cwnd']} max_packets_out={e['pre_max_packets_out']} "
          f"is_cwnd_limited={e['pre_is_cwnd_limited']}")
    print(f"  callback inputs: ack={e['in_ack']} acked={e['in_acked']}")
    print(f"  expected: {expected}")
    print(f"  actual (recorded): {actual}")
    print(f"  differing fields: {diff_fields}")
    print(f"  context [{lo}:{hi}):")
    for j in range(lo, hi):
        marker = ">>" if j == idx else "  "
        ej = events[j]
        print(f"  {marker} seq={ej['seq']} cb={CALLBACK_NAMES.get(ej['callback_id'])} "
              f"pre_cwnd={ej['pre_snd_cwnd']} post_cwnd={ej['post_snd_cwnd']} "
              f"result={ej['result']}")
    print("=" * 70)


def run_r1_on_trace(trace_path, meta_path):
    hdr, events = parse_trace(trace_path)
    dominant_cookie, dominant_events, other_events = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    n_checked = 0
    n_fields_compared = 0
    first_mismatch = None
    mismatch_count = 0

    for idx, e in enumerate(dominant_events):
        cb = e["callback_id"]
        fields = COMPARISON_FIELDS[cb]
        computed, _ = transition(e, NONE_PRIVATE_STATE)

        diffs = [f for f in fields if computed[f] != e[f]]
        n_checked += 1
        n_fields_compared += len(fields)

        if diffs:
            mismatch_count += 1
            expected = {f: computed[f] for f in fields}
            actual = {f: e[f] for f in fields}
            if first_mismatch is None:
                first_mismatch = {
                    "trace": trace_path, "seq": e["seq"], "callback": CALLBACK_NAMES.get(cb),
                    "expected": expected, "actual": actual, "diff_fields": diffs,
                }
                diagnose_mismatch(trace_path, dominant_events, idx, expected, actual, diffs)

    return {
        "trace": trace_path,
        "n_events_total": len(events),
        "n_events_dominant": len(dominant_events),
        "n_events_other": len(other_events),
        "n_checked": n_checked,
        "n_fields_compared": n_fields_compared,
        "mismatch_count": mismatch_count,
        "first_mismatch": first_mismatch,
    }


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json> [...]", file=sys.stderr)
        sys.exit(2)

    results = []
    for i in range(0, len(args), 2):
        results.append(run_r1_on_trace(args[i], args[i + 1]))

    total_checked = sum(r["n_checked"] for r in results)
    total_fields = sum(r["n_fields_compared"] for r in results)
    total_mismatches = sum(r["mismatch_count"] for r in results)
    overall_first_mismatch = next((r["first_mismatch"] for r in results if r["first_mismatch"]), None)

    summary = {
        "gate": "R1",
        "pass": total_mismatches == 0,
        "traces": [r["trace"] for r in results],
        "total_events_checked": total_checked,
        "total_fields_compared": total_fields,
        "total_mismatches": total_mismatches,
        "first_mismatch": overall_first_mismatch,
        "per_trace": results,
    }
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
