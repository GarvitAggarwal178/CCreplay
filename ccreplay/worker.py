"""Child-process entry point. Runs one job (diff / checkpoint / validate)
read from a JSON file and writes the result (or error) to another JSON
file. Invoked as `python -m ccreplay.worker <job_path> <result_path>` from
backend/jobs.py with a wall-clock timeout -- this isolation is for
responsiveness and crash containment, not a security sandbox (user
controller code runs with the same privileges as the backend process).
"""
import json
import sys
import traceback


def main():
    if len(sys.argv) != 3:
        print("usage: worker.py <job.json> <result.json>", file=sys.stderr)
        sys.exit(2)
    job_path, result_path = sys.argv[1], sys.argv[2]
    with open(job_path) as f:
        job = json.load(f)

    try:
        kind = job["type"]
        if job.get("_capsule"):
            from ccreplay import controllers, revisions
            from ccreplay.storage import digest
            cap = job["_capsule"]
            if digest(cap["trace_path"]) != cap["trace_sha256"]:
                raise ValueError("Recording hash changed since submission")
            previous_loader = controllers.load_controller
            frozen = {job[side]: cap[side] for side in ("reference","candidate")}
            controllers.load_controller = lambda cid: revisions.load(frozen[cid]) if cid in frozen else previous_loader(cid)
        if kind == "algorithm_workbench":
            from ccreplay.teaching_workbench import run_job
            result = run_job(job)
        elif kind == "replay":
            from ccreplay.replay_session import run
            result = run(job["session_id"])
        elif kind == "session_checkpoint":
            from ccreplay.replay_session import checkpoint
            result = checkpoint(job["session_id"], job["interval"])
        elif kind == "diff":
            from ccreplay.diff import run_diff
            result = run_diff(job["trace_id"], job["reference"], job["candidate"])
        elif kind == "all_decisions":
            from ccreplay.diff import run_all_decisions
            result = run_all_decisions(job["trace_id"], job["reference"], job["candidate"], job.get("mode", "A"))
        elif kind == "sweep":
            from ccreplay.sweep import run_sweep
            result = run_sweep(job["base"], job["param"], job["values"], job["trace_ids"], job.get("reference_id"))
        elif kind == "checkpoint":
            from ccreplay.checkpoint import run_checkpoint
            result = run_checkpoint(job["trace_id"], job["reference"], job["candidate"], job["interval"])
        elif kind == "validate":
            from ccreplay.controllers import validate_controller
            result = validate_controller(job["controller_id"])
        else:
            raise ValueError(f"unknown job type: {kind}")
        with open(result_path, "w") as f:
            json.dump({"ok": True, "result": result}, f, default=str)
    except Exception as exc:
        with open(result_path, "w") as f:
            json.dump({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc()}, f)
        sys.exit(1)


if __name__ == "__main__":
    main()
