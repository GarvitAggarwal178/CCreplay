"""Experiment job store (SQLite) + child-process runner with timeout.

Each experiment (diff/checkpoint/validate) runs via
`python -m ccreplay.worker <job.json> <result.json>` as a real subprocess,
bounded by a wall-clock timeout. This isolates a slow/crashing run from the
API thread; it is not a security sandbox (plan/AUTORUN: trusted local tool).
"""
import json
import os
import signal
import pathlib
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
STUDIO_DATA = ROOT / "studio_data"
STUDIO_DATA.mkdir(exist_ok=True)
JOBS_DIR = STUDIO_DATA / "jobs"
JOBS_DIR.mkdir(exist_ok=True)
DB_PATH = STUDIO_DATA / "studio.db"

JOB_TIMEOUT_S = 120

_db_lock = threading.Lock()
_slots = threading.Semaphore(max(1, min(2, int(os.environ.get("CCREPLAY_WORKERS", "1")))))
_processes = {}
_cancelled = set()
_shutting_down = threading.Event()


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS experiments (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        config TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        error TEXT,
        created_at REAL NOT NULL,
        started_at REAL,
        finished_at REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS controllers (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        created_at REAL NOT NULL
    )""")
    return c


def _run_worker_subprocess(job: dict, timeout_s: int = JOB_TIMEOUT_S) -> dict:
    job_id = uuid.uuid4().hex
    job_path = JOBS_DIR / f"{job_id}.job.json"
    result_path = JOBS_DIR / f"{job_id}.result.json"
    job_path.write_text(json.dumps(job))
    python = sys.executable
    try:
        proc = subprocess.Popen(
            [python, "-m", "ccreplay.worker", str(job_path), str(result_path)],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        owner_id = job.get("_owner_id")
        if owner_id:
            _processes[owner_id] = proc
            if owner_id in _cancelled:
                os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        finally:
            _processes.pop(owner_id, None)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"job timed out after {timeout_s}s"}
    finally:
        try:
            job_path.unlink(missing_ok=True)
        except Exception:
            pass
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text())
        finally:
            try:
                result_path.unlink(missing_ok=True)
            except Exception:
                pass
        return result
    return {"ok": False, "error": f"worker produced no result (exit {proc.returncode}): {stderr[-2000:]}"}


def create_experiment(exp_type: str, config: dict) -> str:
    config = dict(config)
    if exp_type in ("diff", "checkpoint", "all_decisions") and "_capsule" not in config:
        from ccreplay import revisions, traces
        from ccreplay.storage import digest
        path = traces.resolve_id(config["trace_id"])
        config["_capsule"] = {"reference": revisions.snapshot(config["reference"]),
                              "candidate": revisions.snapshot(config["candidate"]),
                              "trace_path": str(path), "trace_sha256": digest(path)}
    exp_id = uuid.uuid4().hex[:12]
    with _db_lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO experiments (id, type, config, status, created_at) VALUES (?, ?, ?, 'queued', ?)",
            (exp_id, exp_type, json.dumps(config), time.time()),
        )
        conn.commit()
        conn.close()

    def _run():
        with _slots:
            _run_owned()

    def _run_owned():
        if exp_id in _cancelled or _shutting_down.is_set():
            return
        with _db_lock:
            conn = _conn()
            conn.execute("UPDATE experiments SET status='running', started_at=? WHERE id=?",
                         (time.time(), exp_id))
            conn.commit()
            conn.close()

        job = {"type": exp_type, **config, "_owner_id": exp_id}
        try:
            outcome = _run_worker_subprocess(job)
        except Exception as exc:
            outcome = {"ok": False, "error": str(exc)}

        with _db_lock:
            conn = _conn()
            if _shutting_down.is_set():
                conn.execute("UPDATE experiments SET status='interrupted', error='Server stopped during execution', finished_at=? WHERE id=?", (time.time(),exp_id))
            elif exp_id in _cancelled:
                conn.execute("UPDATE experiments SET status='cancelled', finished_at=? WHERE id=?", (time.time(),exp_id))
            elif outcome.get("ok"):
                conn.execute(
                    "UPDATE experiments SET status='done', result=?, finished_at=? WHERE id=?",
                    (json.dumps(outcome["result"]), time.time(), exp_id),
                )
            else:
                conn.execute(
                    "UPDATE experiments SET status='error', error=?, finished_at=? WHERE id=?",
                    (outcome.get("error", "unknown error"), time.time(), exp_id),
                )
            conn.commit()
            conn.close()

    threading.Thread(target=_run, daemon=True).start()
    return exp_id


def get_experiment(exp_id: str) -> dict | None:
    with _db_lock:
        conn = _conn()
        row = conn.execute(
            "SELECT id, type, config, status, result, error, created_at, started_at, finished_at "
            "FROM experiments WHERE id=?", (exp_id,)).fetchone()
        conn.close()
    if row is None:
        return None
    keys = ["id", "type", "config", "status", "result", "error", "created_at", "started_at", "finished_at"]
    d = dict(zip(keys, row))
    d["config"] = json.loads(d["config"])
    if d["result"]:
        d["result"] = json.loads(d["result"])
    return d


def list_experiments(limit: int = 100) -> list:
    with _db_lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT id, type, config, status, result, error, created_at, started_at, finished_at "
            "FROM experiments ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
    keys = ["id", "type", "config", "status", "result", "error", "created_at", "started_at", "finished_at"]
    out = []
    for row in rows:
        d = dict(zip(keys, row))
        d["config"] = json.loads(d["config"])
        if d["result"]:
            d["result"] = json.loads(d["result"])
        out.append(d)
    return out


def run_validate_sync(controller_id: str, timeout_s: int = 60) -> dict:
    """Returns the validate() report itself (`{ok, checks, ...}`), not the
    worker's outer `{ok, result}` envelope -- a caller that only checks the
    envelope's `ok` (true whenever the subprocess didn't crash) would report
    PASS for a controller whose own checks failed, which is exactly the kind
    of fake success this project must never produce."""
    job = {"type": "validate", "controller_id": controller_id}
    outcome = _run_worker_subprocess(job, timeout_s=timeout_s)
    if outcome.get("ok"):
        return outcome["result"]
    return {"ok": False, "checks": [], "error": outcome.get("error", "validation job failed")}


def cancel(exp_id):
    if get_experiment(exp_id) is None:
        raise KeyError(exp_id)
    _cancelled.add(exp_id)
    proc = _processes.get(exp_id)
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    with _db_lock:
        con = _conn()
        con.execute("UPDATE experiments SET status='cancelled', finished_at=? WHERE id=? AND status IN ('queued','running')", (time.time(),exp_id))
        con.commit(); con.close()
    return get_experiment(exp_id)


def reconcile():
    with _db_lock:
        con = _conn()
        con.execute("UPDATE experiments SET status='interrupted', error='Server restarted during execution', finished_at=? WHERE status IN ('queued','running')", (time.time(),))
        con.commit(); con.close()


def shutdown():
    _shutting_down.set()
    for proc in list(_processes.values()):
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=2)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
    reconcile()
