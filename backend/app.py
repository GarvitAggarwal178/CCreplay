"""CCReplay Studio backend. FastAPI app serving /api/* and the built
frontend (frontend/dist) at /. Binds 127.0.0.1 only, never runs as root
(see run_studio.sh). No made-up output: every value returned by /api comes
from a real call into ccreplay/*.py, which wraps the existing user/*.py
replay engine -- no hardcoded results."""
import json
import pathlib
import subprocess
import sys
import time

from fastapi import FastAPI, HTTPException, UploadFile, File
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
def get_events(trace_id: str, offset: int = 0, limit: int = 100, callback: str | None = None):
    try:
        return traces_mod.get_events(trace_id, offset=offset, limit=limit, callback=callback)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/traces/upload")
async def upload_trace(file: UploadFile = File(...), meta: UploadFile | None = File(None)):
    if not file.filename.endswith(".ccr"):
        raise HTTPException(status_code=400, detail="file must have .ccr extension")
    data = await file.read()
    if data[:8] != b"CCRPLAY0":
        raise HTTPException(status_code=400, detail="bad magic: not a CCReplay trace file")
    dest = traces_mod.UPLOADS_DIR / file.filename
    dest.write_bytes(data)
    if meta is not None:
        meta_data = await meta.read()
        try:
            json.loads(meta_data)
        except Exception:
            raise HTTPException(status_code=400, detail="meta file is not valid JSON")
        (traces_mod.UPLOADS_DIR / (dest.stem + ".meta.json")).write_bytes(meta_data)
    tid = traces_mod._slug(f"uploads/{file.filename}")
    try:
        info = traces_mod.get_trace(tid)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"uploaded file failed to parse: {exc}")
    return info


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
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid parameters: {exc}")
    cid = controllers_mod.save_param_variant(req.base, req.name, req.params)
    validation = jobs.run_validate_sync(cid)
    return {"id": cid, "validation": validation}


class UserControllerRequest(BaseModel):
    name: str
    abi_base: str
    code: str


@app.post("/api/controllers/user")
def create_user_controller(req: UserControllerRequest):
    cid = controllers_mod.save_user_controller(req.name, req.abi_base, req.code)
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


def _check_abi_compat(trace_id, reference, candidate):
    trace_abi = traces_mod.get_trace(trace_id)["abi"]
    ref_abi = controllers_mod.abi_of(reference)
    cand_abi = controllers_mod.abi_of(candidate)
    if ref_abi != trace_abi or cand_abi != trace_abi:
        raise HTTPException(status_code=400, detail=(
            f"ABI mismatch: trace is ABI v{trace_abi}, reference={reference} is v{ref_abi}, "
            f"candidate={candidate} is v{cand_abi}. All three must share the same Replay ABI."))


@app.post("/api/experiments")
def create_experiment(req: ExperimentRequest):
    if req.type not in ("diff", "checkpoint"):
        raise HTTPException(status_code=400, detail=f"unknown experiment type: {req.type}")
    _check_abi_compat(req.trace_id, req.reference, req.candidate)
    config = {"trace_id": req.trace_id, "reference": req.reference, "candidate": req.candidate}
    if req.type == "checkpoint":
        config["interval"] = req.interval or 500
    exp_id = jobs.create_experiment(req.type, config)
    return {"id": exp_id, "status": "queued"}


@app.get("/api/experiments/{exp_id}")
def get_experiment(exp_id: str):
    exp = jobs.get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="unknown experiment id")
    return exp


@app.get("/api/experiments")
def list_experiments():
    return jobs.list_experiments()


@app.post("/api/experiments/{exp_id}/rerun")
def rerun_experiment(exp_id: str):
    original = jobs.get_experiment(exp_id)
    if original is None:
        raise HTTPException(status_code=404, detail="unknown experiment id")
    new_id = jobs.create_experiment(original["type"], original["config"])
    deadline = time.time() + 130
    while time.time() < deadline:
        new_exp = jobs.get_experiment(new_id)
        if new_exp["status"] in ("done", "error"):
            break
        time.sleep(0.2)
    else:
        new_exp = jobs.get_experiment(new_id)
    same = (
        original["status"] == "done" and new_exp["status"] == "done"
        and original["result"] == new_exp["result"]
    )
    return {"id": new_id, "status": new_exp["status"], "same_as_original": same}


@app.get("/api/experiments/{exp_id}/export")
def export_experiment(exp_id: str, format: str = "json"):
    exp = jobs.get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="unknown experiment id")
    if format == "json":
        return JSONResponse(exp)
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
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")
    raise HTTPException(status_code=400, detail="format must be json or md")


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
