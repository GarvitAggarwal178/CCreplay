"""Parameter sweep (plan §4 / M7): one tunable, several values, several
traces -> a table + chart of disagreement rate and median delta vs value.
Every point is a real all_decisions_core(mode="A") call (CLAUDE.md: never a
made-up or interpolated number); nothing claims a throughput/RTT/queue
outcome -- "computed on identical recorded inputs" only (see ADR-026).

Sweep variants are built via ccreplay.controllers.make_param and used
in-process; they are NEVER passed to save_param_variant, so a sweep never
writes to studio_data/param_variants.json or appears in the Controllers
registry -- the registry stays exactly what the user explicitly created,
run after run (this was explicit review guidance before M7 began).
"""
import statistics

import ccreplay  # noqa: F401
from ccreplay import controllers as controllers_mod
from ccreplay import traces as traces_mod
from ccreplay.diff import all_decisions_core, UnknownEntityError

TUNABLES_BY_BASE = {"cubic": controllers_mod.CUBIC_TUNABLES, "reno": controllers_mod.RENO_TUNABLES}


def _median_abs_delta(delta_samples: list):
    deltas = [abs(d["delta"]) for d in delta_samples]
    return statistics.median(deltas) if deltas else None


def run_sweep(base: str, param: str, values: list, trace_ids: list, reference_id: str | None = None) -> dict:
    if base not in TUNABLES_BY_BASE:
        raise ValueError(f"no tunables defined for base {base!r}")
    spec = TUNABLES_BY_BASE[base].get(param)
    if spec is None:
        raise ValueError(f"unknown parameter {param!r} for base {base!r}")
    out_of_range = [v for v in values if not (spec["min"] <= v <= spec["max"])]
    if out_of_range:
        raise ValueError(f"values {out_of_range} out of range [{spec['min']}, {spec['max']}] for {param}")
    if not values:
        raise ValueError("values must be non-empty")
    if not trace_ids:
        raise ValueError("trace_ids must be non-empty")

    reference_id = reference_id or base
    try:
        ref_abi = controllers_mod.abi_of(reference_id)
    except KeyError:
        raise UnknownEntityError(f"unknown controller: {reference_id}")
    ref_mod = controllers_mod.load_controller(reference_id)

    points = []
    for value in values:
        # Fresh module per value, in-process only -- never written to
        # controllers/user/ or param_variants.json (see module docstring).
        cand_mod = controllers_mod.make_param(base, f"sweep_{param}_{value}", {param: value})
        for trace_id in trace_ids:
            try:
                trace_path = traces_mod.resolve_id(trace_id)
                trace_abi = traces_mod.get_abi(trace_id)
            except KeyError:
                points.append({"param": param, "value": value, "trace_id": trace_id,
                               "error": f"unknown trace: {trace_id}"})
                continue
            if trace_abi != ref_abi:
                points.append({"param": param, "value": value, "trace_id": trace_id,
                               "error": f"ABI mismatch: trace is v{trace_abi}, reference is v{ref_abi}"})
                continue

            result = all_decisions_core(trace_path, trace_abi, ref_mod, cand_mod, "A")
            points.append({
                "param": param,
                "value": value,
                "trace_id": trace_id,
                "n_events": result["n_events"],
                "n_disagree": result["n_disagree"],
                "disagreement_rate": result["disagreement_rate"],
                "median_abs_delta": _median_abs_delta(result["delta_samples"]),
                "first_disagreement_seq": result["first_disagreement_seq"],
            })

    return {
        "base": base,
        "param": param,
        "reference_id": reference_id,
        "default_value": spec["default"],
        "values": values,
        "trace_ids": trace_ids,
        "points": points,
    }
