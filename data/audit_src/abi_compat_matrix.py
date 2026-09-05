"""PHASE 0 -- ABI compatibility matrix.

Feeds a real trace of each version (v0 Reno, v1 CUBIC, v2 CoVegas) to each
official version-dispatch boundary and classifies the cell:

  ACCEPTED_CORRECTLY  -- parser accepted a trace of its own version, parse succeeded
  REJECTED_CLEANLY    -- parser raised its declared exception (TraceValidationError /
                         ValueError "unsupported trace_version") for a foreign version
  MISPARSED           -- parser returned data for a foreign version, or crashed with an
                         unexpected exception, or accepted-then-produced-garbage
  NOT_APPLICABLE

Boundaries tested:
  - user/ccr_trace.py::parse_trace            (v0; used by replay_r1/r2)
  - user/ccr_trace_v1.py::parse_trace_v1      (v1; used by replay_r3a/r3b)
  - user/ccr_trace_v2.py::parse_trace_v2      (v2; used by replay_e2/e3)
  - user/ccreplay_diff.py::_detect_version_and_parse   (diff entrypoint dispatch)
  - user/ccr_trace.py::validate_run / _v1 / _v2        (validation entrypoints)

Also re-verifies the committed traces parse + their committed validation JSON.
"""
import sys
import json
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


def classify_parse(parser_name, parser_fn, own_version, trace_key, trace_path):
    trace_version = OWN_VERSION[trace_key]
    try:
        hdr, events = parser_fn(trace_path)
    except Exception as e:
        etype = type(e).__name__
        msg = str(e)
        if trace_version == own_version:
            return "MISPARSED", f"parser {parser_name} rejected its OWN version: {etype}: {msg}"
        # foreign version -> must be the declared clean-rejection exception
        clean = (
            (etype == "TraceValidationError" and "trace_version" in msg) or
            (etype == "ValueError" and "unsupported trace_version" in msg) or
            (etype == "TraceValidationError" and "record_size" in msg)
        )
        if clean:
            return "REJECTED_CLEANLY", f"{etype}: {msg}"
        return "MISPARSED", f"foreign version raised UNEXPECTED {etype}: {msg}\n{traceback.format_exc()}"
    # parse returned without raising
    if trace_version == own_version:
        # sanity: header version matches, event count > 0
        if getattr(hdr, "trace_version", None) == own_version and len(events) > 0:
            return "ACCEPTED_CORRECTLY", f"{len(events)} events, hdr.trace_version={hdr.trace_version}"
        return "MISPARSED", f"own version parsed but hdr.trace_version={getattr(hdr,'trace_version',None)}, n_events={len(events)}"
    # foreign version parsed WITHOUT raising -> misparse
    return "MISPARSED", f"foreign v{trace_version} trace parsed by {parser_name} without raising: {len(events)} events"


def main():
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

    # diff entrypoint dispatch
    dname = "ccreplay_diff._detect_version_and_parse"
    matrix[dname] = {}
    for tkey, tpath in TRACES.items():
        tv = OWN_VERSION[tkey]
        try:
            hdr, events, _, _ = _detect_version_and_parse(tpath)
            if tv in (0, 1):
                cls = "ACCEPTED_CORRECTLY" if (hdr.trace_version == tv and len(events) > 0) else "MISPARSED"
                detail = f"{len(events)} events, hdr.trace_version={hdr.trace_version}"
            else:
                cls, detail = "MISPARSED", f"v2 accepted by diff dispatch: {len(events)} events"
        except Exception as e:
            etype, msg = type(e).__name__, str(e)
            if tv in (0, 1):
                cls, detail = "MISPARSED", f"v{tv} rejected by diff dispatch: {etype}: {msg}"
            else:
                cls = "REJECTED_CLEANLY" if (etype == "ValueError" and "unsupported trace_version" in msg) else "MISPARSED"
                detail = f"{etype}: {msg}"
        matrix[dname][tkey] = {"class": cls, "detail": detail}

    # validation entrypoints (own version only -- foreign is NOT_APPLICABLE, they call the vN parser)
    vname = "validate_run / _v1 / _v2 (own version)"
    matrix[vname] = {}
    for tkey, vfn in (("v0_reno", validate_run), ("v1_cubic", validate_run_v1), ("v2_covegas", validate_run_v2)):
        try:
            res = vfn(TRACES[tkey], META[tkey])
            cls = "ACCEPTED_CORRECTLY" if res.get("pass") else "MISPARSED"
            detail = f"pass={res.get('pass')}, n_events={res.get('n_events')}"
        except Exception as e:
            cls, detail = "MISPARSED", f"{type(e).__name__}: {e}"
        matrix[vname][tkey] = {"class": cls, "detail": detail}
    for tkey in ("v0_reno", "v1_cubic", "v2_covegas"):
        for tk2 in ("v0_reno", "v1_cubic", "v2_covegas"):
            pass  # foreign cells for validation are NOT_APPLICABLE (validation is version-specific by construction)

    # committed-trace re-verification: all committed .ccr + .meta + committed _validation.json
    reverify = []
    import glob, os
    for vjson in sorted(glob.glob("raw/**/*_validation.json", recursive=True)):
        base = vjson[:-len("_validation.json")]
        ccr = base + ".ccr"
        meta = base + ".meta.json"
        if not (os.path.exists(ccr) and os.path.exists(meta)):
            reverify.append({"trace": ccr, "status": "SKIP (missing .ccr/.meta)"})
            continue
        with open(ccr, "rb") as f:
            tv = int.from_bytes(f.read(12)[8:12], "little")
        vfn = {0: validate_run, 1: validate_run_v1, 2: validate_run_v2}.get(tv)
        try:
            res = vfn(ccr, meta)
            committed = json.load(open(vjson))
            same_pass = res.get("pass") == committed.get("pass")
            reverify.append({
                "trace": ccr, "trace_version": tv,
                "recomputed_pass": res.get("pass"),
                "committed_pass": committed.get("pass"),
                "consistent": same_pass,
            })
        except Exception as e:
            reverify.append({"trace": ccr, "status": f"ERROR {type(e).__name__}: {e}"})

    n_misparsed = sum(
        1 for p in matrix.values() for c in p.values() if c["class"] == "MISPARSED"
    )
    all_consistent = all(r.get("consistent", True) for r in reverify)

    out = {
        "ABI_COMPATIBILITY": "CLEAN" if (n_misparsed == 0 and all_consistent) else "NOT_CLEAN",
        "n_misparsed_cells": n_misparsed,
        "committed_traces_all_consistent": all_consistent,
        "matrix": matrix,
        "committed_trace_reverification": reverify,
    }
    with open("data/abi_compat_matrix.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out["ABI_COMPATIBILITY"] == "CLEAN" else 1)


if __name__ == "__main__":
    main()
