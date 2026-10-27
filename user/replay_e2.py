"""E2 -- CoVegas event-local exact semantic self-replay (Mode A).

Same shape as user/replay_r3a.py, adapted for ADR-023's mode-dependent
comparison schema: PRE-arm fields are irrelevant to the oracle (private
state for Mode A always comes fresh from the event's own recorded PRE,
which already reflects the real PRE mode); POST-arm fields are compared
only for the arm the model's own computed POST mode selects.

Usage: replay_e2.py <trace.ccr> <meta.json> [...]
"""
import sys
import json

sys.path.insert(0, ".")
from user.ccr_trace_v2 import (
    parse_trace_v2, select_dominant_connection, CALLBACK_NAMES,
    jiffies_clock_classification, ktime_clock_classification,
)
from user.covegas_model import transition, comparison_fields, private_pre_from_event


def diagnose_mismatch(trace_path, events, idx, expected, actual, diff_fields):
    e = events[idx]
    lo = max(0, idx - 5)
    hi = min(len(events), idx + 6)
    out = sys.stderr
    print("=" * 70, file=out)
    print(f"MISMATCH  trace={trace_path}  seq={e['seq']}  "
          f"callback={CALLBACK_NAMES.get(e['callback_id'], e['callback_id'])}  "
          f"jiffies_clock={jiffies_clock_classification(e)} ktime_clock={ktime_clock_classification(e)}",
          file=out)
    print(f"  pre_mode={e['priv_pre_mode']}  shared PRE: snd_cwnd={e['pre_snd_cwnd']} "
          f"snd_ssthresh={e['pre_snd_ssthresh']} snd_cwnd_cnt={e['pre_snd_cwnd_cnt']}", file=out)
    print(f"  private PRE: {private_pre_from_event(e)}", file=out)
    print(f"  expected: {expected}", file=out)
    print(f"  actual (recorded): {actual}", file=out)
    print(f"  differing fields: {diff_fields}", file=out)
    print(f"  context [{lo}:{hi}):", file=out)
    for j in range(lo, hi):
        marker = ">>" if j == idx else "  "
        ej = events[j]
        print(f"  {marker} seq={ej['seq']} cb={CALLBACK_NAMES.get(ej['callback_id'])} "
              f"pre_mode={ej['priv_pre_mode']} post_mode={ej['priv_post_mode']} "
              f"pre_cwnd={ej['pre_snd_cwnd']} post_cwnd={ej['post_snd_cwnd']}", file=out)
    print("=" * 70, file=out)


def run_e2_on_trace(trace_path, meta_path):
    hdr, events = parse_trace_v2(trace_path)
    dominant_cookie, dominant_events, other_events = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    n_checked = 0
    n_fields_compared = 0
    first_mismatch = None
    mismatch_count = 0
    per_callback_checked = {}
    per_callback_mismatched = {}
    jiffies_stable_checked = jiffies_stable_mismatched = 0
    jiffies_ambiguous_checked = jiffies_ambiguous_mismatched = 0
    ktime_stable_checked = ktime_stable_mismatched = 0
    ktime_ambiguous_checked = ktime_ambiguous_mismatched = 0

    for idx, e in enumerate(dominant_events):
        cb = e["callback_id"]
        ca = private_pre_from_event(e)
        computed, _ = transition(e, ca)
        fields = comparison_fields(cb, e["priv_pre_mode"], computed["priv_post_mode"])

        diffs = [f for f in fields if computed.get(f) != e.get(f)]
        n_checked += 1
        n_fields_compared += len(fields)
        per_callback_checked[cb] = per_callback_checked.get(cb, 0) + 1

        j_stable = jiffies_clock_classification(e) == "CLOCK_STABLE"
        k_stable = ktime_clock_classification(e) == "CLOCK_STABLE"
        if j_stable:
            jiffies_stable_checked += 1
        else:
            jiffies_ambiguous_checked += 1
        if k_stable:
            ktime_stable_checked += 1
        else:
            ktime_ambiguous_checked += 1

        if diffs:
            mismatch_count += 1
            per_callback_mismatched[cb] = per_callback_mismatched.get(cb, 0) + 1
            if j_stable:
                jiffies_stable_mismatched += 1
            else:
                jiffies_ambiguous_mismatched += 1
            if k_stable:
                ktime_stable_mismatched += 1
            else:
                ktime_ambiguous_mismatched += 1
            expected = {f: computed.get(f) for f in fields}
            actual = {f: e.get(f) for f in fields}
            if first_mismatch is None:
                first_mismatch = {
                    "trace": trace_path, "seq": e["seq"], "callback": CALLBACK_NAMES.get(cb),
                    "jiffies_clock": jiffies_clock_classification(e),
                    "ktime_clock": ktime_clock_classification(e),
                    "expected": expected, "actual": actual, "diff_fields": diffs,
                }
                diagnose_mismatch(trace_path, dominant_events, idx, expected, actual, diffs)

    return {
        "trace": trace_path,
        "n_events_total": len(events),
        "n_events_dominant": len(dominant_events),
        "n_checked": n_checked,
        "n_fields_compared": n_fields_compared,
        "mismatch_count": mismatch_count,
        "per_callback_checked": {CALLBACK_NAMES.get(k, k): v for k, v in per_callback_checked.items()},
        "per_callback_mismatched": {CALLBACK_NAMES.get(k, k): v for k, v in per_callback_mismatched.items()},
        "jiffies_stable_checked": jiffies_stable_checked, "jiffies_stable_mismatched": jiffies_stable_mismatched,
        "jiffies_ambiguous_checked": jiffies_ambiguous_checked, "jiffies_ambiguous_mismatched": jiffies_ambiguous_mismatched,
        "ktime_stable_checked": ktime_stable_checked, "ktime_stable_mismatched": ktime_stable_mismatched,
        "ktime_ambiguous_checked": ktime_ambiguous_checked, "ktime_ambiguous_mismatched": ktime_ambiguous_mismatched,
        "first_mismatch": first_mismatch,
    }


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json> [...]", file=sys.stderr)
        sys.exit(2)

    from replay_scope import validation_scope
    scope = validation_scope(args, 'covegas_replay/primary')

    results = [run_e2_on_trace(args[i], args[i + 1]) for i in range(0, len(args), 2)]

    total_checked = sum(r["n_checked"] for r in results)
    total_fields = sum(r["n_fields_compared"] for r in results)
    total_mismatches = sum(r["mismatch_count"] for r in results)
    overall_first_mismatch = next((r["first_mismatch"] for r in results if r["first_mismatch"]), None)
    total_jiffies_stable = sum(r["jiffies_stable_checked"] for r in results)
    total_jiffies_stable_mismatched = sum(r["jiffies_stable_mismatched"] for r in results)
    total_ktime_stable = sum(r["ktime_stable_checked"] for r in results)
    total_ktime_stable_mismatched = sum(r["ktime_stable_mismatched"] for r in results)

    summary = {
        "scope": scope,
        "gate": "E2",
        "pass": total_mismatches == 0,
        "pass_jiffies_stable_only": total_jiffies_stable_mismatched == 0,
        "pass_ktime_stable_only": total_ktime_stable_mismatched == 0,
        "traces": [r["trace"] for r in results],
        "total_events_checked": total_checked,
        "total_fields_compared": total_fields,
        "total_mismatches": total_mismatches,
        "jiffies_stable_checked": total_jiffies_stable,
        "jiffies_stable_mismatched": total_jiffies_stable_mismatched,
        "ktime_stable_checked": total_ktime_stable,
        "ktime_stable_mismatched": total_ktime_stable_mismatched,
        "first_mismatch": overall_first_mismatch,
        "per_trace": results,
    }
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
