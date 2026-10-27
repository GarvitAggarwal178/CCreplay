"""Differential-debugger wrapper (wraps user/ccreplay_diff.diff_trace)."""
import importlib
import statistics

import ccreplay  # noqa: F401
from user.ccreplay_diff import diff_trace, _detect_version_and_parse, _initial_state

from ccreplay import traces as traces_mod
from ccreplay import controllers as controllers_mod

RESULT_FIELDS = ("result", "result_valid", "post_snd_cwnd", "post_snd_cwnd_cnt", "post_snd_ssthresh")
BASE_MODULE_BY_ABI = {0: "reno", 1: "cubic", 2: "covegas"}
# Capped so a controller that disagrees on nearly every event of a 236k-event
# trace doesn't blow up the API response -- the strip/rate/per-callback
# numbers below are exact over the FULL trace regardless of this cap; only
# the per-event detail list (used for the table view) is capped.
MAX_DETAILED_DISAGREEMENTS = 2000


def _classify_kind(divergence) -> str:
    if divergence is None:
        return "none"
    diffs = divergence.get("all_diff_fields", [])
    if any(f in RESULT_FIELDS for f in diffs):
        return "result"
    return "private_state_only"


class AbiMismatchError(ValueError):
    pass


class UnknownEntityError(ValueError):
    pass


def _resolve_and_check_abi(trace_id: str, ref_id: str, cand_id: str):
    # Runs inside the worker subprocess (ccreplay.worker), reached both from
    # a fresh POST /api/experiments (behind backend/app.py's own
    # _check_abi_compat, which gives a 404 before the job is even queued)
    # and from POST /api/experiments/{id}/rerun (which does NOT go through
    # that check -- a rerun whose controller was deleted since the original
    # run must still fail with a readable reason here, not a bare KeyError
    # str() that doesn't say which entity is missing or why).
    try:
        trace_path = traces_mod.resolve_id(trace_id)
        trace_abi = traces_mod.get_abi(trace_id)
    except KeyError:
        raise UnknownEntityError(f"unknown trace: {trace_id}")
    try:
        ref_abi = controllers_mod.abi_of(ref_id)
    except KeyError:
        raise UnknownEntityError(f"unknown controller: {ref_id}")
    try:
        cand_abi = controllers_mod.abi_of(cand_id)
    except KeyError:
        raise UnknownEntityError(f"unknown controller: {cand_id}")
    if ref_abi != trace_abi or cand_abi != trace_abi:
        raise AbiMismatchError(
            f"ABI mismatch: trace is ABI v{trace_abi}, reference={ref_id} is v{ref_abi}, "
            f"candidate={cand_id} is v{cand_abi}. All three must share the same Replay ABI.")
    return trace_path, trace_abi


def run_diff(trace_id: str, ref_id: str, cand_id: str) -> dict:
    trace_path, trace_abi = _resolve_and_check_abi(trace_id, ref_id, cand_id)
    ref_mod = controllers_mod.load_controller(ref_id)
    cand_mod = controllers_mod.load_controller(cand_id)
    result = diff_trace(str(trace_path), None, ref_mod, cand_mod)
    result["kind"] = _classify_kind(result.get("divergence"))
    result["reference_id"] = ref_id
    result["candidate_id"] = cand_id
    result["trace_id"] = trace_id
    return result


def _fields_for(ref_mod, v2_schema, cb, event, ref_computed):
    if v2_schema:
        return ref_mod.comparison_fields(cb, event.get("priv_pre_mode"), ref_computed.get("priv_post_mode"))
    return ref_mod.COMPARISON_FIELDS[cb]


def all_decisions_core(trace_path, trace_abi: int, ref_mod, cand_mod, mode: str) -> dict:
    """The actual all-decisions event loop (M7, ADR-026): every event is
    compared, not only up to the first divergence. Mode "A" (event-local):
    both ref and cand run from the SAME recorded private PRE state for
    every event, taken from the trace's ABI's built-in base module (not
    from either controller's own copy -- see ADR-026). Mode "B" (stateful):
    each controller's private state evolves from its own prior computed
    output, same shape as diff_trace; every disagreement after the first is
    labelled "cascaded" since Mode B does not reset state at a divergence.

    Takes already-resolved/loaded `ref_mod`/`cand_mod` module objects
    rather than controller ids, so it can be shared verbatim by
    run_all_decisions (id-based, the normal path) and ccreplay.sweep
    (which builds unregistered in-memory variants that have no id --
    ADR-026/the sweep design explicitly keeps sweep variants out of the
    controller registry, so there is nothing to look up by id).
    """
    if mode not in ("A", "B"):
        raise ValueError(f"mode must be 'A' or 'B', got {mode!r}")

    hdr, events, select_dominant_connection, CALLBACK_NAMES = _detect_version_and_parse(str(trace_path))
    _, dominant_events, _ = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    base_id = BASE_MODULE_BY_ABI[trace_abi]
    base_mod = importlib.import_module(controllers_mod.BUILTINS[base_id]["module"])
    base_pre_fn = getattr(base_mod, "private_pre_from_event", None)  # None for Reno (ADR-014)

    v2_schema = not hasattr(ref_mod, "COMPARISON_FIELDS") and hasattr(ref_mod, "comparison_fields")

    ref_state = _initial_state(ref_mod) if mode == "B" else None
    cand_state = _initial_state(cand_mod) if mode == "B" else None

    n_events = len(dominant_events)
    n_disagree = 0
    per_callback_checked = {}
    per_callback_disagree = {}
    first_disagreement_index = None
    detailed = []
    delta_samples = []  # [{field, reference, candidate, delta}], numeric fields only, capped -- histogram only
    field_deltas = {}  # field -> list[signed delta], UNCAPPED -- exact stats, not an estimate
    disagree_runs = []  # [[start_index, length], ...], UNCAPPED -- RLE over the full trace. Cheap even
    # for a long Mode-B cascade (one run can cover tens of thousands of
    # events in a single [start, length] pair); for isolated Mode-A
    # disagreements each run is length 1, no worse than a flat list.
    run_start = None

    # Mode B "cascaded" means the PRIVATE STATE the two sides carry into this
    # event already differs (a consequence of an earlier disagreement), not
    # merely "some earlier event disagreed" -- a bug can disagree on every
    # recurrence of one callback (e.g. the seeded ssthresh +1) without ever
    # touching private state, in which case none of its recurrences are
    # cascades of each other.
    def _states_differ(a, b):
        return a != b

    from ccreplay.transitions import iterate
    for idx, e, ref_computed, cand_computed, ref_pre, cand_pre, ref_next, cand_next, fields, diffs, pre_state_diverged in iterate(dominant_events, ref_mod, cand_mod, base_mod, mode):
        cb = e["callback_id"]
        cb_name = CALLBACK_NAMES.get(cb, str(cb))

        per_callback_checked[cb_name] = per_callback_checked.get(cb_name, 0) + 1
        if diffs:
            n_disagree += 1
            per_callback_disagree[cb_name] = per_callback_disagree.get(cb_name, 0) + 1
            cascaded = pre_state_diverged
            if first_disagreement_index is None:
                first_disagreement_index = idx
            if run_start is None:
                run_start = idx
            if len(detailed) < MAX_DETAILED_DISAGREEMENTS:
                detailed.append({
                    "event_index": idx, "seq": e["seq"], "callback": cb_name, "cascaded": cascaded,
                    "diff_fields": diffs,
                })
            for f in diffs:
                rv, cv = ref_computed.get(f), cand_computed.get(f)
                if isinstance(rv, (int, float)) and isinstance(cv, (int, float)) and not isinstance(rv, bool):
                    delta = cv - rv
                    field_deltas.setdefault(f, []).append(delta)
                    if len(delta_samples) < MAX_DETAILED_DISAGREEMENTS:
                        delta_samples.append({"field": f, "reference": rv, "candidate": cv, "delta": delta})
        else:
            if run_start is not None:
                disagree_runs.append([run_start, idx - run_start])
                run_start = None
    if run_start is not None:
        disagree_runs.append([run_start, n_events - run_start])

    delta_stats = {}
    for field, deltas in field_deltas.items():
        delta_stats[field] = {
            "count": len(deltas),
            "median": statistics.median(deltas),
            "mean": statistics.fmean(deltas),
            "min": min(deltas),
            "max": max(deltas),
        }

    return {
        "mode": mode,
        "n_events": n_events,
        "n_disagree": n_disagree,
        "disagreement_rate": (n_disagree / n_events) if n_events else 0.0,
        "per_callback_checked": per_callback_checked,
        "per_callback_disagree": per_callback_disagree,
        "first_disagreement_index": first_disagreement_index,
        "first_disagreement_seq": dominant_events[first_disagreement_index]["seq"] if first_disagreement_index is not None else None,
        # Sparse (capped) per-event detail for the table view, plus an
        # UNCAPPED run-length-encoded [start, length] list for the strip
        # chart -- a long Mode-B cascade compresses to one or a few runs
        # instead of tens of thousands of per-event entries.
        "disagreements": detailed,
        "disagreements_truncated": n_disagree > MAX_DETAILED_DISAGREEMENTS,
        "disagree_runs": disagree_runs,
        "delta_samples": delta_samples,
        # Exact per-field signed-delta statistics over EVERY disagreement,
        # never just the capped sample above (plan §4: "Δ statistics").
        "delta_stats": delta_stats,
    }


def run_all_decisions(trace_id: str, ref_id: str, cand_id: str, mode: str = "A") -> dict:
    """Id-based entry point: resolves trace/reference/candidate ids, checks
    ABI compatibility, loads both controllers, then delegates to
    all_decisions_core for the actual comparison (see its docstring)."""
    trace_path, trace_abi = _resolve_and_check_abi(trace_id, ref_id, cand_id)
    ref_mod = controllers_mod.load_controller(ref_id)
    cand_mod = controllers_mod.load_controller(cand_id)
    result = all_decisions_core(trace_path, trace_abi, ref_mod, cand_mod, mode)
    result["trace_id"] = trace_id
    result["reference_id"] = ref_id
    result["candidate_id"] = cand_id
    return result
