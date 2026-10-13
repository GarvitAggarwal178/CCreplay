"""Differential-debugger wrapper (wraps user/ccreplay_diff.diff_trace)."""
import ccreplay  # noqa: F401
from user.ccreplay_diff import diff_trace, _detect_version_and_parse

from ccreplay import traces as traces_mod
from ccreplay import controllers as controllers_mod

RESULT_FIELDS = ("result", "result_valid", "post_snd_cwnd", "post_snd_cwnd_cnt", "post_snd_ssthresh")


def _classify_kind(divergence) -> str:
    if divergence is None:
        return "none"
    diffs = divergence.get("all_diff_fields", [])
    if any(f in RESULT_FIELDS for f in diffs):
        return "result"
    return "private_state_only"


class AbiMismatchError(ValueError):
    pass


def run_diff(trace_id: str, ref_id: str, cand_id: str) -> dict:
    trace_path = traces_mod.resolve_id(trace_id)
    trace_abi = traces_mod.get_abi(trace_id)
    ref_abi = controllers_mod.abi_of(ref_id)
    cand_abi = controllers_mod.abi_of(cand_id)
    if ref_abi != trace_abi or cand_abi != trace_abi:
        raise AbiMismatchError(
            f"ABI mismatch: trace is ABI v{trace_abi}, reference={ref_id} is v{ref_abi}, "
            f"candidate={cand_id} is v{cand_abi}. All three must share the same Replay ABI.")

    ref_mod = controllers_mod.load_controller(ref_id)
    cand_mod = controllers_mod.load_controller(cand_id)
    result = diff_trace(str(trace_path), None, ref_mod, cand_mod)
    result["kind"] = _classify_kind(result.get("divergence"))
    result["reference_id"] = ref_id
    result["candidate_id"] = cand_id
    result["trace_id"] = trace_id
    return result
