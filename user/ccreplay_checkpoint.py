"""N6 -- replay-private-state checkpoint + suffix reproducer.

Extends user/ccreplay_diff.py's model-vs-model replay with periodic
checkpointing of both models' private state, and a resume-from-checkpoint
path that replays only the SUFFIX of events from a checkpoint boundary K+1
through the first divergence D, verifying it reproduces the exact same
first divergence the full from-scratch run found.

This is a reproducer, not minimization: the checkpoint's very purpose is
that events [0..K] are already fully accounted for by the checkpoint's
saved state (nothing before K is skipped or deleted -- it is captured, not
discarded), and the suffix [K+1..D] is replayed in full, in order, with no
events removed from that range. Per the pipeline's explicit prohibition,
this must never be described as arbitrary event minimization.

Checkpoint format (JSON, schema_version=1): trace identity, reference/
candidate module names, the event index and seq the checkpoint was taken
at, and both models' full private-state dicts at that point. Serialization
is deterministic (`json.dumps(..., sort_keys=True)`), so re-running a
checkpoint save at the same event index against the same trace/models
byte-for-byte reproduces the same checkpoint file.
"""
import sys
import json

sys.path.insert(0, ".")
from user.ccreplay_diff import _detect_version_and_parse, _initial_state

CHECKPOINT_SCHEMA_VERSION = 1


def run_with_checkpoints(trace_path, reference_module, candidate_module, interval):
    """Replays the full dominant-connection event sequence (model vs
    model, same shape as ccreplay_diff.diff_trace), saving a checkpoint
    every `interval` events, and returns (checkpoints, first_divergence,
    dominant_events) so a caller can pick the nearest checkpoint at or
    before any divergence index."""
    hdr, events, select_dominant_connection, CALLBACK_NAMES = _detect_version_and_parse(trace_path)
    _, dominant_events, _ = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    ref_state = _initial_state(reference_module)
    cand_state = _initial_state(candidate_module)

    checkpoints = []
    first_divergence = None

    for idx, e in enumerate(dominant_events):
        if idx % interval == 0:
            checkpoints.append({
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "trace": trace_path,
                "reference": reference_module.__name__,
                "candidate": candidate_module.__name__,
                "event_index": idx,
                "seq": e["seq"],
                "ref_state": dict(ref_state) if ref_state is not None else None,
                "cand_state": dict(cand_state) if cand_state is not None else None,
            })

        cb = e["callback_id"]
        fields = reference_module.COMPARISON_FIELDS[cb]
        ref_computed, ref_state = reference_module.transition(e, ref_state)
        cand_computed, cand_state = candidate_module.transition(e, cand_state)
        diffs = [f for f in fields if ref_computed.get(f) != cand_computed.get(f)]
        if diffs:
            first_divergence = {
                "event_index": idx, "seq": e["seq"],
                "callback": CALLBACK_NAMES.get(cb, cb), "diff_fields": diffs,
            }
            break

    return checkpoints, first_divergence, dominant_events, CALLBACK_NAMES


def nearest_checkpoint_at_or_before(checkpoints, event_index):
    candidates = [c for c in checkpoints if c["event_index"] <= event_index]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["event_index"])


def replay_suffix_from_checkpoint(checkpoint, dominant_events, reference_module,
                                   candidate_module, stop_at_index):
    """Resumes from `checkpoint`'s saved state and replays ONLY events
    (checkpoint['event_index'], stop_at_index] -- the suffix K+1..D, in
    full, in order, nothing skipped within that range. Returns the
    divergence found (or None), for comparison against the original
    from-scratch divergence at the same index."""
    ref_state = dict(checkpoint["ref_state"]) if checkpoint["ref_state"] is not None else None
    cand_state = dict(checkpoint["cand_state"]) if checkpoint["cand_state"] is not None else None

    divergence = None
    for idx in range(checkpoint["event_index"] + 1, stop_at_index + 1):
        e = dominant_events[idx]
        cb = e["callback_id"]
        fields = reference_module.COMPARISON_FIELDS[cb]
        ref_computed, ref_state = reference_module.transition(e, ref_state)
        cand_computed, cand_state = candidate_module.transition(e, cand_state)
        diffs = [f for f in fields if ref_computed.get(f) != cand_computed.get(f)]
        if diffs:
            divergence = {"event_index": idx, "seq": e["seq"], "diff_fields": diffs}
            break
    return divergence


def main():
    import argparse
    import importlib

    p = argparse.ArgumentParser(description="N6 checkpoint + suffix reproducer demo")
    p.add_argument("trace")
    p.add_argument("--reference", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--interval", type=int, default=500)
    p.add_argument("--save-checkpoints-to", default=None)
    args = p.parse_args()

    ref_mod = importlib.import_module(args.reference)
    cand_mod = importlib.import_module(args.candidate)

    checkpoints, first_divergence, dominant_events, CALLBACK_NAMES = run_with_checkpoints(
        args.trace, ref_mod, cand_mod, args.interval)

    if args.save_checkpoints_to:
        with open(args.save_checkpoints_to, "w") as f:
            json.dump(checkpoints, f, indent=2, sort_keys=True, default=str)

    result = {"n_checkpoints": len(checkpoints), "first_divergence_full_run": first_divergence}

    if first_divergence:
        D = first_divergence["event_index"]
        ckpt = nearest_checkpoint_at_or_before(checkpoints, D)
        result["nearest_checkpoint"] = {"event_index": ckpt["event_index"], "seq": ckpt["seq"]}
        suffix_divergence = replay_suffix_from_checkpoint(ckpt, dominant_events, ref_mod, cand_mod, D)
        result["suffix_replay_divergence"] = suffix_divergence
        result["reproduced_same_divergence"] = (
            suffix_divergence is not None and
            suffix_divergence["event_index"] == D and
            suffix_divergence["seq"] == first_divergence["seq"] and
            suffix_divergence["diff_fields"] == first_divergence["diff_fields"]
        )
        result["suffix_length"] = D - ckpt["event_index"]

    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if first_divergence is None or result.get("reproduced_same_divergence") else 1)


if __name__ == "__main__":
    main()
