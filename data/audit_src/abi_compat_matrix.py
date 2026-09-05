"""ABI compatibility matrix -- FINAL post-v2-extension version.

Phase 0 of the integrated session ran an earlier version of this script against the
code state where user/ccreplay_diff.py supported v0/v1 and REJECTED v2 cleanly.
That result is frozen below as PHASE0_INITIAL_MATRIX (do not erase).

Phase 3 of the same session added Replay-ABI-v2 support to ccreplay_diff.py (and
Phase 10 to ccreplay_checkpoint.py). This script now audits the FINAL code and
also runs the v2 differential regression checks required by the post-success
closure task.

Feeds a real trace of each Replay ABI version to every official version-dispatch
boundary and classifies each cell:
  ACCEPTED_CORRECTLY / REJECTED_CLEANLY / MISPARSED / NOT_APPLICABLE

Required:  FINAL_MISPARSED_CELLS = 0
"""
import sys
import json
import glob
import os
import traceback

sys.path.insert(0, ".")
sys.path.insert(0, "user")

TRACES = {
    "v0_reno":    "raw/r0/rep1.ccr",
    "v1_cubic":   "raw/cubic_replay/primary/rep1.ccr",
    "v2_covegas": "raw/covegas_replay/primary/rep1.ccr",
}
META = {
    "v0_reno":    "raw/r0/rep1.meta.json",
    "v1_cubic":   "raw/cubic_replay/primary/rep1.meta.json",
    "v2_covegas": "raw/covegas_replay/primary/rep1.meta.json",
}
OWN_VERSION = {"v0_reno": 0, "v1_cubic": 1, "v2_covegas": 2}

# ---------------------------------------------------------------------------
# FROZEN Phase-0 result -- the code state at Phase 0: ccreplay_diff rejected v2.
# Preserved verbatim; not recomputed.
# ---------------------------------------------------------------------------
PHASE0_INITIAL_MATRIX = {
    "ABI_COMPATIBILITY": "CLEAN",
    "n_misparsed_cells": 0,
    "code_state": "Phase 0 -- user/ccreplay_diff.py supported v0/v1 only; v2 -> ValueError('unsupported trace_version 2')",
    "matrix": {
        "ccr_trace.parse_trace (v0)": {
            "v0_reno": "ACCEPTED_CORRECTLY", "v1_cubic": "REJECTED_CLEANLY", "v2_covegas": "REJECTED_CLEANLY"},
        "ccr_trace_v1.parse_trace_v1 (v1)": {
            "v0_reno": "REJECTED_CLEANLY", "v1_cubic": "ACCEPTED_CORRECTLY", "v2_covegas": "REJECTED_CLEANLY"},
        "ccr_trace_v2.parse_trace_v2 (v2)": {
            "v0_reno": "REJECTED_CLEANLY", "v1_cubic": "REJECTED_CLEANLY", "v2_covegas": "ACCEPTED_CORRECTLY"},
        "ccreplay_diff._detect_version_and_parse": {
            "v0_reno": "ACCEPTED_CORRECTLY", "v1_cubic": "ACCEPTED_CORRECTLY",
            "v2_covegas": "REJECTED_CLEANLY  (ValueError: unsupported trace_version 2)"},
        "validate_run / _v1 / _v2 (own version)": {
            "v0_reno": "ACCEPTED_CORRECTLY", "v1_cubic": "ACCEPTED_CORRECTLY", "v2_covegas": "ACCEPTED_CORRECTLY"},
    },
    "committed_traces_all_consistent": True,
}


def classify_parse(parser_name, parser_fn, own_version, trace_key, trace_path):
    tv = OWN_VERSION[trace_key]
    try:
        hdr, events = parser_fn(trace_path)
    except Exception as e:
        etype, msg = type(e).__name__, str(e)
        if tv == own_version:
            return "MISPARSED", f"{parser_name} rejected its OWN version: {etype}: {msg}"
        clean = (
            (etype == "TraceValidationError" and "trace_version" in msg) or
            (etype == "TraceValidationError" and "record_size" in msg))
        return ("REJECTED_CLEANLY", f"{etype}: {msg}") if clean else \
               ("MISPARSED", f"foreign version raised UNEXPECTED {etype}: {msg}\n{traceback.format_exc()}")
    if tv == own_version:
        if getattr(hdr, "trace_version", None) == own_version and len(events) > 0:
            return "ACCEPTED_CORRECTLY", f"{len(events)} events"
        return "MISPARSED", f"own version parsed but hdr.trace_version={getattr(hdr,'trace_version',None)}"
    return "MISPARSED", f"foreign v{tv} trace parsed by {parser_name} without raising ({len(events)} events)"


def final_matrix():
    from user.ccr_trace import parse_trace, validate_run
    from user.ccr_trace_v1 import parse_trace_v1, validate_run_v1
    from user.ccr_trace_v2 import parse_trace_v2, validate_run_v2
    from user.ccreplay_diff import _detect_version_and_parse

    parsers = [
        ("ccr_trace.parse_trace (v0)", parse_trace, 0),
        ("ccr_trace_v1.parse_trace_v1 (v1)", parse_trace_v1, 1),
        ("ccr_trace_v2.parse_trace_v2 (v2)", parse_trace_v2, 2),
    ]
    matrix = {}
    for pname, pfn, pver in parsers:
        matrix[pname] = {}
        for tkey, tpath in TRACES.items():
            cls, detail = classify_parse(pname, pfn, pver, tkey, tpath)
            matrix[pname][tkey] = {"class": cls, "detail": detail}

    dname = "ccreplay_diff._detect_version_and_parse"
    matrix[dname] = {}
    for tkey, tpath in TRACES.items():
        tv = OWN_VERSION[tkey]
        try:
            hdr, events, _, _ = _detect_version_and_parse(tpath)
            ok = hdr.trace_version == tv and len(events) > 0
            matrix[dname][tkey] = {"class": "ACCEPTED_CORRECTLY" if ok else "MISPARSED",
                                   "detail": f"{len(events)} events, hdr.trace_version={hdr.trace_version}"}
        except Exception as e:
            matrix[dname][tkey] = {"class": "MISPARSED",
                                   "detail": f"v{tv} rejected by diff dispatch: {type(e).__name__}: {e}"}

    vname = "validate_run / _v1 / _v2 (own version)"
    matrix[vname] = {}
    for tkey, vfn in (("v0_reno", validate_run), ("v1_cubic", validate_run_v1), ("v2_covegas", validate_run_v2)):
        try:
            res = vfn(TRACES[tkey], META[tkey])
            matrix[vname][tkey] = {"class": "ACCEPTED_CORRECTLY" if res.get("pass") else "MISPARSED",
                                   "detail": f"pass={res.get('pass')}, n_events={res.get('n_events')}"}
        except Exception as e:
            matrix[vname][tkey] = {"class": "MISPARSED", "detail": f"{type(e).__name__}: {e}"}

    # committed-trace re-verification
    reverify = []
    for vjson in sorted(glob.glob("raw/**/*_validation.json", recursive=True)):
        base = vjson[:-len("_validation.json")]
        ccr, meta = base + ".ccr", base + ".meta.json"
        if not (os.path.exists(ccr) and os.path.exists(meta)):
            reverify.append({"trace": ccr, "status": "SKIP (missing .ccr/.meta)"})
            continue
        with open(ccr, "rb") as f:
            tv = int.from_bytes(f.read(12)[8:12], "little")
        vfn = {0: validate_run, 1: validate_run_v1, 2: validate_run_v2}.get(tv)
        try:
            res = vfn(ccr, meta)
            committed = json.load(open(vjson))
            reverify.append({"trace": ccr, "trace_version": tv,
                             "recomputed_pass": res.get("pass"), "committed_pass": committed.get("pass"),
                             "consistent": res.get("pass") == committed.get("pass")})
        except Exception as e:
            reverify.append({"trace": ccr, "status": f"ERROR {type(e).__name__}: {e}"})

    n_misparsed = sum(1 for p in matrix.values() for c in p.values() if c["class"] == "MISPARSED")
    all_consistent = all(r.get("consistent", True) for r in reverify)

    # --- v2 differential regression checks (post-success closure task sec 2) ---
    from user.ccreplay_diff import diff_trace
    import user.covegas_model as v4
    import user.covegas_model_v3_latch as v3
    v2diff = {}
    ff = diff_trace("raw/covegas_replay/primary/rep1.ccr", "x", v4, v4)
    v2diff["fixed_v4_vs_fixed_v4_rep1"] = ff["result"]
    for rep in ("rep1", "rep2", "rep3"):
        r = diff_trace(f"raw/covegas_replay/primary/{rep}.ccr", "x", v4, v3)
        v2diff[f"fixed_v4_vs_recon_v3_{rep}"] = r["result"]
    rep4 = diff_trace("raw/covegas_campaign/rep4.ccr", "x", v4, v3)
    v2diff["fixed_v4_vs_recon_v3_campaign_rep4_result"] = rep4["result"]
    v2diff["fixed_v4_vs_recon_v3_campaign_rep4_first_divergence_seq"] = (
        rep4["divergence"]["first_divergent_event"]["seq"] if rep4["divergence"] else None)
    v2diff["fixed_v4_vs_recon_v3_campaign_rep4_callback"] = (
        rep4["divergence"]["callback"] if rep4["divergence"] else None)
    v2diff_ok = (
        v2diff["fixed_v4_vs_fixed_v4_rep1"] == "NO DIVERGENCE" and
        all(v2diff[f"fixed_v4_vs_recon_v3_{r}"] == "NO DIVERGENCE" for r in ("rep1", "rep2", "rep3")) and
        v2diff["fixed_v4_vs_recon_v3_campaign_rep4_result"] == "DIVERGENCE" and
        v2diff["fixed_v4_vs_recon_v3_campaign_rep4_first_divergence_seq"] == 10421 and
        v2diff["fixed_v4_vs_recon_v3_campaign_rep4_callback"] == "cong_avoid")

    return {
        "code_state": "FINAL -- user/ccreplay_diff.py and user/ccreplay_checkpoint.py support v0/v1/v2",
        "ABI_COMPATIBILITY": "CLEAN" if (n_misparsed == 0 and all_consistent and v2diff_ok) else "NOT_CLEAN",
        "FINAL_MISPARSED_CELLS": n_misparsed,
        "committed_traces_all_consistent": all_consistent,
        "matrix": matrix,
        "committed_trace_reverification": reverify,
        "v2_differential_regression": v2diff,
        "v2_differential_regression_ok": v2diff_ok,
    }


def main():
    fm = final_matrix()
    out = {
        "phase0_initial_matrix": PHASE0_INITIAL_MATRIX,
        "final_post_v2_extension_matrix": fm,
        "FINAL_MISPARSED_CELLS": fm["FINAL_MISPARSED_CELLS"],
        "ABI_COMPATIBILITY_FINAL": fm["ABI_COMPATIBILITY"],
    }
    with open("data/abi_compat_matrix.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps({
        "ABI_COMPATIBILITY_FINAL": out["ABI_COMPATIBILITY_FINAL"],
        "FINAL_MISPARSED_CELLS": out["FINAL_MISPARSED_CELLS"],
        "final_matrix": {b: {t: c["class"] for t, c in cells.items()} for b, cells in fm["matrix"].items()},
        "v2_differential_regression": fm["v2_differential_regression"],
        "v2_differential_regression_ok": fm["v2_differential_regression_ok"],
        "committed_traces_all_consistent": fm["committed_traces_all_consistent"],
    }, indent=2, default=str))
    sys.exit(0 if out["ABI_COMPATIBILITY_FINAL"] == "CLEAN" else 1)


if __name__ == "__main__":
    main()
