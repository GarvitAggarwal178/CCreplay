"""N4 -- CCReplay differential debugger core.

Conceptual command (docs/session pipeline): `ccreplay diff TRACE --reference
REF --candidate CANDIDATE`. This is the smallest useful implementation of
that idea: REF and CANDIDATE are Python modules exposing the same
model-module interface as user/reno_model.py (v0) / user/cubic_model.py
(v1) -- a `transition(event, private_state)` function returning
`(computed_dict, next_private_state)`, a `COMPARISON_FIELDS` dict keyed by
callback_id, and either `NONE_PRIVATE_STATE` or `INITIAL_PRIVATE_STATE` as
the Mode-B seed. Both modules are replayed statefully (Mode B shape --
shared TCP state injected from the recording at every event, each module's
OWN private state carried forward independently) against the SAME recorded
TRACE, and the first callback at which their declared results or
controller-owned/private state transitions differ is reported
(CLAUDE.md: "Two implementations replayed against the same recorded
contract can be compared to identify the first callback at which their
declared results or state transitions differ").

This does NOT compare either module against the recording itself (that is
R1/R2/R3A/R3B's job) -- it compares two IMPLEMENTATIONS against each other,
which is the actual regression-debugging use case: a known-good reference
model vs. a candidate model with a suspected or seeded defect.

Usage:
    ccreplay_diff.py <trace.ccr> <meta.json> --reference <module> --candidate <module>

<module> is a dotted Python module path, e.g. `user.cubic_model` or
`user.reno_model`, or a path to a variant module placed alongside one of
those (e.g. for N5's seeded-bug case study).
"""
import sys
import json
import argparse
import importlib

sys.path.insert(0, ".")


def _detect_version_and_parse(trace_path):
    """Peek at the trace header's magic+trace_version to choose the right
    parser/CALLBACK_NAMES/select_dominant_connection, without assuming
    either module the caller passes in matches a particular version --
    the trace itself is authoritative."""
    import struct
    from user.ccr_trace import HEADER_FMT, HEADER_SIZE, CCR_TRACE_MAGIC

    with open(trace_path, "rb") as f:
        raw_hdr = f.read(HEADER_SIZE)
    vals = struct.unpack(HEADER_FMT, raw_hdr)
    magic, trace_version = vals[0], vals[1]
    if magic != CCR_TRACE_MAGIC:
        raise ValueError(f"bad magic: {magic!r}")

    if trace_version == 0:
        from user.ccr_trace import parse_trace, select_dominant_connection, CALLBACK_NAMES
        hdr, events = parse_trace(trace_path)
        return hdr, events, select_dominant_connection, CALLBACK_NAMES
    elif trace_version == 1:
        from user.ccr_trace_v1 import parse_trace_v1, select_dominant_connection, CALLBACK_NAMES
        hdr, events = parse_trace_v1(trace_path)
        return hdr, events, select_dominant_connection, CALLBACK_NAMES
    else:
        raise ValueError(f"unsupported trace_version {trace_version}")


def _initial_state(module):
    # INITIAL_PRIVATE_STATE (a real, non-None seed) takes priority over
    # NONE_PRIVATE_STATE where a module defines both (cubic_model.py keeps
    # NONE_PRIVATE_STATE only as a documented sentinel for "no init has run
    # yet"; its actual Mode-B seed is INITIAL_PRIVATE_STATE). A module
    # with genuinely no private state (reno_model.py) defines only
    # NONE_PRIVATE_STATE.
    if hasattr(module, "INITIAL_PRIVATE_STATE"):
        return dict(module.INITIAL_PRIVATE_STATE)
    if hasattr(module, "NONE_PRIVATE_STATE"):
        return module.NONE_PRIVATE_STATE
    raise AttributeError(
        f"{module.__name__} exposes neither NONE_PRIVATE_STATE nor INITIAL_PRIVATE_STATE")


def diff_trace(trace_path, meta_path, reference_module, candidate_module):
    del meta_path  # not required for a pure model-vs-model diff; kept in
    # the CLI for symmetry with R1/R2/R3A/R3B's argument shape.
    hdr, events, select_dominant_connection, CALLBACK_NAMES = _detect_version_and_parse(trace_path)
    _, dominant_events, _ = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    ref_state = _initial_state(reference_module)
    cand_state = _initial_state(candidate_module)

    matched_before_divergence = 0
    first_divergence = None

    for idx, e in enumerate(dominant_events):
        cb = e["callback_id"]
        fields = reference_module.COMPARISON_FIELDS[cb]

        ref_computed, ref_state = reference_module.transition(e, ref_state)
        cand_computed, cand_state = candidate_module.transition(e, cand_state)

        diffs = [f for f in fields if ref_computed.get(f) != cand_computed.get(f)]
        if diffs:
            first_divergence = {
                "matched_event_count_before_divergence": matched_before_divergence,
                "first_divergent_event": {"seq": e["seq"], "event_index": idx},
                "callback": CALLBACK_NAMES.get(cb, cb),
                "callback_result_diff": {
                    f: {"reference": ref_computed.get(f), "candidate": cand_computed.get(f)}
                    for f in diffs if f in ("result", "result_valid")
                },
                "controller_owned_state_diff": {
                    f: {"reference": ref_computed.get(f), "candidate": cand_computed.get(f)}
                    for f in diffs if f.startswith("post_")
                },
                "private_state_diff": {
                    f: {"reference": ref_computed.get(f), "candidate": cand_computed.get(f)}
                    for f in diffs if f.startswith("priv_post_")
                },
                "shared_pre": {k: v for k, v in e.items() if k.startswith("pre_")},
                "inputs_and_time": {k: v for k, v in e.items()
                                    if k.startswith("in_") or "clock" in k or k == "ts_ns"},
                "all_diff_fields": diffs,
            }
            break
        matched_before_divergence += 1

    lo = max(0, (first_divergence["first_divergent_event"]["event_index"] - 5)
             if first_divergence else len(dominant_events) - 5)
    hi = min(len(dominant_events), lo + 11)
    event_context = [
        {"seq": dominant_events[j]["seq"], "callback": CALLBACK_NAMES.get(dominant_events[j]["callback_id"])}
        for j in range(lo, hi)
    ] if dominant_events else []

    return {
        "trace": trace_path,
        "reference": reference_module.__name__,
        "candidate": candidate_module.__name__,
        "n_events_dominant": len(dominant_events),
        "matched_event_count_before_divergence": matched_before_divergence,
        "divergence": first_divergence,
        "event_context": event_context if first_divergence else None,
        "result": "NO DIVERGENCE" if first_divergence is None else "DIVERGENCE",
    }


def main():
    p = argparse.ArgumentParser(description="CCReplay differential debugger (N4)")
    p.add_argument("trace")
    p.add_argument("meta", nargs="?", default=None)
    p.add_argument("--reference", required=True)
    p.add_argument("--candidate", required=True)
    args = p.parse_args()

    ref_mod = importlib.import_module(args.reference)
    cand_mod = importlib.import_module(args.candidate)

    result = diff_trace(args.trace, args.meta, ref_mod, cand_mod)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["result"] == "NO DIVERGENCE" else 1)


if __name__ == "__main__":
    main()
