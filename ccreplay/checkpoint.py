"""Checkpoint + suffix reproducer wrapper (wraps user/ccreplay_checkpoint.py)."""
import ccreplay  # noqa: F401
from user.ccreplay_checkpoint import (
    run_with_checkpoints, nearest_checkpoint_at_or_before, replay_suffix_from_checkpoint,
)

from ccreplay import controllers as controllers_mod
from ccreplay import traces as traces_mod
from ccreplay.diff import AbiMismatchError


def run_checkpoint(trace_id: str, ref_id: str, cand_id: str, interval: int) -> dict:
    trace_path = traces_mod.resolve_id(trace_id)
    trace_abi = traces_mod.get_trace(trace_id)["abi"]
    ref_abi = controllers_mod.abi_of(ref_id)
    cand_abi = controllers_mod.abi_of(cand_id)
    if ref_abi != trace_abi or cand_abi != trace_abi:
        raise AbiMismatchError(
            f"ABI mismatch: trace is ABI v{trace_abi}, reference={ref_id} is v{ref_abi}, "
            f"candidate={cand_id} is v{cand_abi}.")

    ref_mod = controllers_mod.load_controller(ref_id)
    cand_mod = controllers_mod.load_controller(cand_id)

    checkpoints, first_divergence, dominant_events, CALLBACK_NAMES = run_with_checkpoints(
        str(trace_path), ref_mod, cand_mod, interval)

    result = {
        "trace_id": trace_id,
        "reference_id": ref_id,
        "candidate_id": cand_id,
        "interval": interval,
        "n_checkpoints": len(checkpoints),
        "first_divergence_full_run": first_divergence,
    }
    if first_divergence is None:
        result["result"] = "NO DIVERGENCE"
        return result

    D = first_divergence["event_index"]
    ckpt = nearest_checkpoint_at_or_before(checkpoints, D)
    suffix_divergence = replay_suffix_from_checkpoint(ckpt, dominant_events, ref_mod, cand_mod, D)
    reproduced = (
        suffix_divergence is not None
        and suffix_divergence["event_index"] == D
        and suffix_divergence["seq"] == first_divergence["seq"]
        and suffix_divergence["diff_fields"] == first_divergence["diff_fields"]
    )
    result.update({
        "result": "DIVERGENCE",
        "nearest_checkpoint": {"event_index": ckpt["event_index"], "seq": ckpt["seq"]},
        "suffix_length": D - ckpt["event_index"],
        "suffix_replay_divergence": suffix_divergence,
        "reproduced_same_divergence": reproduced,
    })
    return result
