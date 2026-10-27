"""N6 -- replay-private-state checkpoint + suffix reproducer.

Extends user/ccreplay_diff.py's model-vs-model replay with periodic
checkpointing of both models' private state, and a resume-from-checkpoint
path that replays only the SUFFIX of events from a checkpoint boundary K
through the first divergence D inclusive, verifying it reproduces the exact
same first divergence (position, fields, computed values and post-event
private state) the full from-scratch run found.

Boundary convention (schema_version=2): a checkpoint stores
`next_event_index` K and both models' private state immediately BEFORE
event K. Resuming executes events K..D inclusive, i.e. D-K+1 transitions
(K=1500, D=1704 gives 205, including the failing event). Schema 1 stored the
same pre-event state but resumed at K+1, silently skipping event K; it is
rejected on load rather than reinterpreted.

This is a reproducer, not minimization: events [0..K-1] are captured by the
checkpoint's saved state (nothing is deleted), and the suffix [K..D] is
replayed in full and in order. It must never be described as arbitrary
event minimization.

Checkpoint format (JSON): trace identity, reference/candidate module
names, `next_event_index`, `next_seq`, and both models' full private-state
dicts at that point. Serialization
is deterministic (`json.dumps(..., sort_keys=True)`), so re-running a
checkpoint save at the same event index against the same trace/models
byte-for-byte reproduces the same checkpoint file.
"""
import sys
import json
from copy import deepcopy

sys.path.insert(0, ".")
from user.ccreplay_diff import _detect_version_and_parse, _initial_state


def _fields_for(reference_module, cb, event, ref_computed):
    """v2 (CoVegas, ADR-023) uses a mode-dependent comparison schema
    `comparison_fields(callback_id, pre_mode, post_mode)`; v0/v1 use a flat
    `COMPARISON_FIELDS` dict. `priv_post_mode` is always in the dedicated
    field set, so a mode disagreement is always caught."""
    if hasattr(reference_module, "COMPARISON_FIELDS"):
        return reference_module.COMPARISON_FIELDS[cb]
    return reference_module.comparison_fields(
        cb, event.get("priv_pre_mode"), ref_computed.get("priv_post_mode"))

CHECKPOINT_SCHEMA_VERSION = 2


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
                "next_event_index": idx,
                "next_seq": e["seq"],
                "ref_state": deepcopy(ref_state),
                "cand_state": deepcopy(cand_state),
            })

        cb = e["callback_id"]
        ref_computed, ref_state = reference_module.transition(e, ref_state)
        cand_computed, cand_state = candidate_module.transition(e, cand_state)
        fields = _fields_for(reference_module, cb, e, ref_computed)
        diffs = [f for f in fields if ref_computed.get(f) != cand_computed.get(f)]
        if diffs:
            first_divergence = {
                "event_index": idx, "seq": e["seq"],
                "callback": CALLBACK_NAMES.get(cb, cb), "diff_fields": diffs,
                "ref_computed": deepcopy(ref_computed), "cand_computed": deepcopy(cand_computed),
                "ref_post_state": deepcopy(ref_state), "cand_post_state": deepcopy(cand_state),
            }
            break

    return checkpoints, first_divergence, dominant_events, CALLBACK_NAMES


def nearest_checkpoint_at_or_before(checkpoints, event_index):
    """Latest checkpoint whose next event is <= event_index (equality means
    the failing event itself is the first resumed transition)."""
    candidates = [c for c in checkpoints if c["next_event_index"] <= event_index]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["next_event_index"])


def replay_suffix_from_checkpoint(checkpoint, dominant_events, reference_module,
                                   candidate_module, stop_at_index):
    """Resumes from `checkpoint`'s pre-event state and replays events
    [checkpoint['next_event_index'], stop_at_index] INCLUSIVE, in full, in
    order. Returns the divergence found (or None), including computed values
    and post-event private states for comparison against the from-scratch
    divergence."""
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported checkpoint schema_version {checkpoint.get('schema_version')!r}; "
            f"expected {CHECKPOINT_SCHEMA_VERSION} (schema 1 resumed one event late)")
    ref_state = deepcopy(checkpoint["ref_state"])
    cand_state = deepcopy(checkpoint["cand_state"])

    divergence = None
    for idx in range(checkpoint["next_event_index"], stop_at_index + 1):
        e = dominant_events[idx]
        cb = e["callback_id"]
        ref_computed, ref_state = reference_module.transition(e, ref_state)
        cand_computed, cand_state = candidate_module.transition(e, cand_state)
        fields = _fields_for(reference_module, cb, e, ref_computed)
        diffs = [f for f in fields if ref_computed.get(f) != cand_computed.get(f)]
        if diffs:
            divergence = {"event_index": idx, "seq": e["seq"], "diff_fields": diffs,
                          "ref_computed": deepcopy(ref_computed), "cand_computed": deepcopy(cand_computed),
                          "ref_post_state": deepcopy(ref_state), "cand_post_state": deepcopy(cand_state)}
            break
    return divergence


def same_divergence(full, resumed):
    """Exact reproduction: position, fields, computed values and post-event
    private states all equal (not just the event index and field names)."""
    if full is None or resumed is None:
        return False
    keys = ("event_index", "seq", "diff_fields", "ref_computed", "cand_computed",
            "ref_post_state", "cand_post_state")
    return all(full.get(k) == resumed.get(k) for k in keys)


def suffix_length(checkpoint, divergence_index):
    return divergence_index - checkpoint["next_event_index"] + 1


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
        result["nearest_checkpoint"] = {"next_event_index": ckpt["next_event_index"], "next_seq": ckpt["next_seq"]}
        suffix_divergence = replay_suffix_from_checkpoint(ckpt, dominant_events, ref_mod, cand_mod, D)
        result["suffix_replay_divergence"] = suffix_divergence
        result["reproduced_same_divergence"] = same_divergence(first_divergence, suffix_divergence)
        result["suffix_length"] = suffix_length(ckpt, D)

    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if first_divergence is None or result.get("reproduced_same_divergence") else 1)


if __name__ == "__main__":
    main()
