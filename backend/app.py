"""CCReplay Studio backend. FastAPI app serving /api/* and the built
frontend (frontend/dist) at /. Binds 127.0.0.1 only; intended to run as a
non-root user (this file does not itself enforce or check that -- see the
README's "Run CCReplay Studio" section). No made-up output: every value
returned by /api comes from a real call into ccreplay/*.py, which wraps the
existing user/*.py replay engine -- no hardcoded results."""
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ccreplay import traces as traces_mod
from ccreplay import controllers as controllers_mod
from ccreplay.diff import AbiMismatchError
import backend.jobs as jobs

app = FastAPI(title="CCReplay Studio")


@app.on_event("startup")
def _warm_trace_summary_cache():
    """Parses every library trace once, in a background thread, right after
    the server binds -- so the FIRST real request (a presenter's or a
    visitor's) doesn't pay the ~4-5 s cold-parse cost measured in
    STUDIO_STATUS.md. This only populates the lightweight summary cache
    (ccreplay.traces._summary_cached), never the bounded full-event LRU, so
    it does not reintroduce the memory problem that cache split fixed."""
    def _warm():
        try:
            traces_mod.list_traces()
        except Exception:
            pass  # best-effort warmup; a real request will retry and surface any real error
    threading.Thread(target=_warm, daemon=True).start()

SEMANTIC_RULE = (
    "CCReplay answers what a congestion-control implementation computes at a "
    "recorded Linux congestion-control callback boundary. It does not claim "
    "what network trajectory or performance that implementation would have produced."
)

ABI_VALIDATION_TABLE = [
    {"abi": "v0 Reno", "verdict": "PASS",
     "caveat": "strongest reference: real kernel tcp_reno_* functions"},
    {"abi": "v1 CUBIC", "verdict": "PARTIAL",
     "caveat": "46 of 236,088 events are CLOCK_AMBIGUOUS (jiffies bracket), 4 mismatches; everything else exact"},
    {"abi": "v2 CoVegas", "verdict": "PASS",
     "caveat": "no independent kernel reference; validates replay fidelity, not the algorithm"},
]


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                               capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return "unknown"


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "semantic_rule": SEMANTIC_RULE,
        "abi_validation_table": ABI_VALIDATION_TABLE,
    }


@app.get("/api/traces")
def list_traces():
    return traces_mod.list_traces()


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str):
    try:
        return traces_mod.get_trace(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/traces/{trace_id}/series")
def get_series(trace_id: str, fields: str, max_points: int = 4000,
                t0: float | None = None, t1: float | None = None):
    field_list = [f for f in fields.split(",") if f]
    try:
        return traces_mod.get_series(trace_id, field_list, max_points=max_points, t0=t0, t1=t1)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/traces/{trace_id}/events")
def get_events(trace_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), callback: str | None = None):
    try:
        return traces_mod.get_events(trace_id, offset=offset, limit=limit, callback=callback)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/traces/upload")
async def upload_trace(file: UploadFile = File(...), meta: UploadFile | None = File(None)):
    if not file.filename.endswith(".ccr"):
        raise HTTPException(status_code=400, detail="file must have .ccr extension")
    from ccreplay.recordings import import_bytes, MAX_UPLOAD
    data = await file.read(MAX_UPLOAD + 1)
    meta_data = await meta.read(131073) if meta else None
    try:
        if meta_data is not None and len(meta_data) > 131072:
            raise ValueError("Metadata exceeds 128 KiB")
        entry = import_bytes(data, meta_data, name=pathlib.Path(file.filename).name)
        info = traces_mod.get_trace(entry["id"])
        info.update(entry)
        return info
    except Exception as exc:
        raise HTTPException(400, f"Upload rejected atomically: {exc}")


@app.get("/api/controllers")
def list_controllers():
    return controllers_mod.list_controllers()


@app.get("/api/controllers/{controller_id}/source")
def get_controller_source(controller_id: str):
    try:
        return PlainTextResponse(controllers_mod.get_source(controller_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown controller: {controller_id}")


@app.get("/api/controllers/templates/{base}")
def get_template(base: str):
    try:
        return PlainTextResponse(controllers_mod.get_template(base))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no template for base: {base}")


class ParamRequest(BaseModel):
    base: str
    name: str
    params: dict


@app.post("/api/controllers/param")
def create_param_controller(req: ParamRequest):
    try:
        controllers_mod.make_param(req.base, req.name, req.params)  # validate it builds
        cid = controllers_mod.save_param_variant(req.base, req.name, req.params)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid request: {exc}")
    validation = jobs.run_validate_sync(cid)
    return {"id": cid, "validation": validation}


class UserControllerRequest(BaseModel):
    name: str
    abi_base: str
    code: str


@app.post("/api/controllers/user")
def create_user_controller(req: UserControllerRequest):
    try:
        cid = controllers_mod.save_user_controller(req.name, req.abi_base, req.code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid request: {exc}")
    validation = jobs.run_validate_sync(cid)
    return {"id": cid, "validation": validation}


@app.post("/api/controllers/{controller_id}/validate")
def validate_controller_endpoint(controller_id: str):
    return jobs.run_validate_sync(controller_id)


class ExperimentRequest(BaseModel):
    type: str
    trace_id: str
    reference: str
    candidate: str
    interval: int | None = None
    mode: str | None = None  # "A" (event-local) or "B" (stateful) -- all_decisions only


def _check_abi_compat(trace_id, reference, candidate):
    # A rerun (or a stale History/Diff-Workbench link) can reference a trace
    # or controller that no longer exists (e.g. an e2e-created controller
    # that's since been cleaned up) -- that must surface as a readable 404,
    # not a bare 500 from an uncaught KeyError deep in resolve_id/abi_of.
    try:
        trace_abi = traces_mod.get_abi(trace_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown trace: {trace_id}")
    try:
        ref_abi = controllers_mod.abi_of(reference)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown controller: {reference}")
    try:
        cand_abi = controllers_mod.abi_of(candidate)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown controller: {candidate}")
    if ref_abi != trace_abi or cand_abi != trace_abi:
        raise HTTPException(status_code=400, detail=(
            f"ABI mismatch: trace is ABI v{trace_abi}, reference={reference} is v{ref_abi}, "
            f"candidate={candidate} is v{cand_abi}. All three must share the same Replay ABI."))


@app.post("/api/experiments")
def create_experiment(req: ExperimentRequest):
    if req.type not in ("diff", "checkpoint", "all_decisions"):
        raise HTTPException(status_code=400, detail=f"unknown experiment type: {req.type}")
    _check_abi_compat(req.trace_id, req.reference, req.candidate)
    config = {"trace_id": req.trace_id, "reference": req.reference, "candidate": req.candidate}
    if req.type == "checkpoint":
        config["interval"] = req.interval or 500
    if req.type == "all_decisions":
        mode = req.mode or "A"
        if mode not in ("A", "B"):
            raise HTTPException(status_code=400, detail=f"mode must be 'A' or 'B', got {mode!r}")
        config["mode"] = mode
    exp_id = jobs.create_experiment(req.type, config)
    return {"id": exp_id, "status": "queued"}


@app.get("/api/experiments/{exp_id}")
def get_experiment(exp_id: str):
    exp = jobs.get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="unknown experiment id")
    return exp


@app.get("/api/tunables/{base}")
def get_tunables(base: str):
    from ccreplay.sweep import TUNABLES_BY_BASE
    spec = TUNABLES_BY_BASE.get(base)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"no tunables for base: {base}")
    return spec


class SweepRequest(BaseModel):
    base: str
    param: str
    values: list[int]
    trace_ids: list[str]
    reference_id: str | None = None


@app.post("/api/sweeps")
def create_sweep(req: SweepRequest):
    from ccreplay.sweep import TUNABLES_BY_BASE
    spec = TUNABLES_BY_BASE.get(req.base, {}).get(req.param)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"unknown parameter {req.param!r} for base {req.base!r}")
    out_of_range = [v for v in req.values if not (spec["min"] <= v <= spec["max"])]
    if out_of_range:
        raise HTTPException(status_code=400,
                             detail=f"values {out_of_range} out of range [{spec['min']}, {spec['max']}] for {req.param}")
    if not req.values:
        raise HTTPException(status_code=400, detail="values must be non-empty")
    if not req.trace_ids:
        raise HTTPException(status_code=400, detail="trace_ids must be non-empty")
    # A sweep is one worker job with a 120 s budget; measured ~1 s per
    # (value, trace) pair on a CUBIC-size trace, so an unbounded combination
    # count can time out and lose the whole sweep, not just the slow part.
    n_combinations = len(req.values) * len(req.trace_ids)
    if n_combinations > 60:
        raise HTTPException(status_code=400, detail=(
            f"{len(req.values)} values x {len(req.trace_ids)} traces = {n_combinations} combinations "
            f"exceeds the 60-combination limit for a single sweep (one worker job, 120 s budget) -- "
            f"reduce the number of values or traces."))
    for tid in req.trace_ids:
        try:
            trace_abi = traces_mod.get_abi(tid)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown trace: {tid}")
        ref_id = req.reference_id or req.base
        try:
            ref_abi = controllers_mod.abi_of(ref_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown controller: {ref_id}")
        if trace_abi != ref_abi:
            raise HTTPException(status_code=400, detail=(
                f"ABI mismatch: trace {tid} is v{trace_abi}, reference={ref_id} is v{ref_abi}."))
    config = {"base": req.base, "param": req.param, "values": req.values, "trace_ids": req.trace_ids,
              "reference_id": req.reference_id}
    exp_id = jobs.create_experiment("sweep", config)
    return {"id": exp_id, "status": "queued"}


@app.get("/api/experiments")
def list_experiments():
    return jobs.list_experiments()


@app.post("/api/experiments/{exp_id}/rerun")
def rerun_experiment(exp_id: str):
    original = jobs.get_experiment(exp_id)
    if original is None:
        raise HTTPException(status_code=404, detail="unknown experiment id")
    if original["type"] == "algorithm_workbench" and os.environ.get("CCREPLAY_DEMO_MODE") == "1":
        raise HTTPException(403, "Custom algorithm execution requires the local application")
    config = dict(original["config"])
    if original["type"] == "algorithm_workbench" and original.get("result"):
        config['_initialization_json'] = original['result'].get('initialization_json')
    new_id = jobs.create_experiment(original["type"], config)
    return {"id": new_id, "status": "queued", "same_as_original": None, "error": None}


@app.get("/api/experiments/{exp_id}/export")
def export_experiment(exp_id: str, format: str = "json"):
    exp = jobs.get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="unknown experiment id")
    if format == "json":
        return JSONResponse(exp, headers={"Content-Disposition": f'attachment; filename="ccreplay_{exp_id}.json"'})
    if format == "md":
        lines = [
            f"# CCReplay Studio experiment {exp_id}",
            "",
            f"**Type:** {exp['type']}  **Status:** {exp['status']}",
            f"**Config:** `{json.dumps(exp['config'])}`",
            "",
            f"> {SEMANTIC_RULE}",
            "",
        ]
        if exp.get("result"):
            lines.append("```json")
            lines.append(json.dumps(exp["result"], indent=2, default=str))
            lines.append("```")
        if exp.get("error"):
            lines.append(f"**Error:** {exp['error']}")
        return PlainTextResponse(
            "\n".join(lines), media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="ccreplay_{exp_id}.md"'},
        )
    raise HTTPException(status_code=400, detail="format must be json or md")


from backend.algorithm_workbench import router as algorithm_workbench_router
app.include_router(algorithm_workbench_router)
from backend.replay import router as replay_router
app.include_router(replay_router)
from backend.lab import router as lab_router
app.include_router(lab_router)

@app.on_event("startup")
def reconcile_jobs():
    if os.geteuid() == 0:
        raise RuntimeError("Studio must run as a normal user; only the separate lab agent runs as root")
    jobs.reconcile()

@app.on_event("shutdown")
def stop_workers():
    jobs.shutdown()

# --- static frontend (built by frontend/) -----------------------------------
DIST_DIR = ROOT / "frontend" / "dist"
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = DIST_DIR / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(DIST_DIR / "index.html"))
