"""C6 mutation campaign runner (SPEC.md sections 4-6).

Steps:
  1. Harness controls (SPEC.md section 5). If any fails: write controls.json,
     stop, exit 2. No mutant runs.
  2. Every live mutant x every trace x Mode A and Mode B, through the
     existing, unmodified ccreplay.diff.all_decisions_core (reference = the
     unmutated built-in model, candidate = the mutant). Rows are appended to
     results.jsonl as they finish, so a stopped run keeps its evidence.
  3. For mutants that survive a primary trace in Mode A: a full-output pass
     comparing every key of transition()'s output dict, including keys outside
     the comparison schema (PREDICTIONS.md S4).
  4. Analysis (analysis.json): scores, survivor coverage labels, and the
     automatic S1/S2/S3/S4 checks. E-proof vs E-obs attribution of executed
     survivors is done by hand in summary.md, never inferred here.

Usage:
  python results/c6_mutation_campaign/run.py [--workers 6] [--limit N] [--out DIR]
  python results/c6_mutation_campaign/run.py --analyze-only
"""
import argparse
import ast
import csv
import datetime
import importlib
import json
import multiprocessing as mp
import os
import pathlib
import platform
import subprocess
import sys
import time

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from experiments.c6_mutation_campaign.complete import c6_common as common
from experiments.c6_mutation_campaign.complete import mutate
from ccreplay import controllers as controllers_mod
from ccreplay.diff import all_decisions_core

TIMEOUT_S = 120  # the Studio worker's per-job limit (SPEC.md section 4)


# --------------------------------------------------------------------------
# Running one comparison
# --------------------------------------------------------------------------

class MutantTimeout(Exception):
    pass


def _with_deadline(mod, seconds):
    """Enforce the per-run limit at callback granularity: the candidate's
    transition() raises once the deadline passes. (The models contain no
    loops, so a single callback cannot run unbounded; growth across Mode-B
    events is what this guards against.)"""
    inner = mod.transition
    deadline = time.monotonic() + seconds

    def transition(event, state):
        if time.monotonic() > deadline:
            raise MutantTimeout(f"exceeded {seconds}s")
        return inner(event, state)

    mod.transition = transition
    return mod


def compare(controller, cand_src, cand_name, rel_path, mode, ref_mod=None):
    """One all_decisions_core run. Returns a result row (without mutant metadata)."""
    ref_mod = ref_mod or controllers_mod.load_controller(controller)
    t0 = time.monotonic()
    row = {"trace": rel_path, "mode": mode}
    try:
        cand_mod = mutate.build_module(cand_name, cand_src, controller)
        _with_deadline(cand_mod, TIMEOUT_S)
        r = all_decisions_core(common.ROOT / rel_path, common.ABI[controller], ref_mod, cand_mod, mode)
    except MutantTimeout as exc:
        row.update(outcome="KILLED-TIMEOUT", error=str(exc))
    except Exception as exc:  # noqa: BLE001 -- any candidate exception is a crash-kill
        row.update(outcome="KILLED-CRASH", error=f"{type(exc).__name__}: {exc}")
    else:
        first_cb = r["disagreements"][0]["callback"] if r["disagreements"] else None
        row.update(
            outcome="KILLED" if r["n_disagree"] else "SURVIVED",
            n_events=r["n_events"], n_disagree=r["n_disagree"],
            first_index=r["first_disagreement_index"], first_seq=r["first_disagreement_seq"],
            first_callback=first_cb, per_callback_disagree=r["per_callback_disagree"],
            n_runs=len(r["disagree_runs"]),
        )
    row["elapsed_s"] = round(time.monotonic() - t0, 3)
    return row


def full_output_pass(controller, cand_src, cand_name, rel_path):
    """PREDICTIONS.md S4: Mode A over every event, diffing the FULL
    transition() output dicts (schema and non-schema keys)."""
    ref_mod = controllers_mod.load_controller(controller)
    cand_mod = mutate.build_module(cand_name, cand_src, controller)
    events, callback_names = common.load_events(rel_path)
    pre_fn = common.base_pre_fn(controller)
    schema_fn = ref_mod.COMPARISON_FIELDS
    out_of_schema, in_schema = {}, 0
    for e in events:
        pre = pre_fn(e) if pre_fn else None
        rc, _ = ref_mod.transition(e, pre)
        cc, _ = cand_mod.transition(e, pre_fn(e) if pre_fn else None)
        schema = set(schema_fn[e["callback_id"]])
        for k in set(rc) | set(cc):
            if rc.get(k) != cc.get(k):
                if k in schema:
                    in_schema += 1
                else:
                    out_of_schema[k] = out_of_schema.get(k, 0) + 1
    return {"trace": rel_path, "out_of_schema_diffs": out_of_schema, "in_schema_diffs": in_schema}


def run_mutant(task):
    """Pool worker: every trace x mode for one mutant, then the S4 pass for
    each primary trace it survived in Mode A."""
    rec, src = task
    controller = rec["controller"]
    ref_mod = controllers_mod.load_controller(controller)
    meta = {k: rec[k] for k in ("id", "controller", "operator", "function", "line", "end_line")}
    rows = []
    for rel_path, role in common.traces_for(controller):
        for mode in common.MODES:
            row = compare(controller, src, rec["id"], rel_path, mode, ref_mod)
            rows.append({**meta, "role": role, **row})
    s4 = []
    for row in rows:
        if row["role"] == "primary" and row["mode"] == "A" and row["outcome"] == "SURVIVED":
            s4.append(full_output_pass(controller, src, rec["id"], row["trace"]))
    return rec["id"], rows, s4


# --------------------------------------------------------------------------
# Controls (SPEC.md section 5)
# --------------------------------------------------------------------------

def run_controls():
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # 1. Identity control: the unparsed reference, built exactly like a mutant.
    for controller in ("reno", "cubic"):
        src = mutate.reference_source(controller)
        for rel_path, _ in common.traces_for(controller):
            for mode in common.MODES:
                r = compare(controller, src, f"{controller}-identity", rel_path, mode)
                check(f"identity {controller} {rel_path} mode {mode}",
                      r.get("outcome") == "SURVIVED", {k: r.get(k) for k in ("outcome", "n_disagree", "error")})

    # 2. Known seeded bugs through the same harness (CURRENT_STATE section 14, results/c5).
    rep1 = common.PRIMARY["cubic"][0]
    ref = controllers_mod.load_controller("cubic")

    def seeded(bug, rel_path, mode):
        cand = controllers_mod.load_controller(bug)
        r = all_decisions_core(common.ROOT / rel_path, 1, ref, cand, mode)
        cb = r["disagreements"][0]["callback"] if r["disagreements"] else None
        return {"n_disagree": r["n_disagree"], "first_seq": r["first_disagreement_seq"], "first_callback": cb}

    a = seeded("cubic_bug_ssthresh", rep1, "A")
    check("bug_ssthresh rep1 mode A: 14 disagreements, first seq 1705, ssthresh",
          (a["n_disagree"], a["first_seq"], a["first_callback"]) == (14, 1705, "ssthresh"), a)
    b = seeded("cubic_bug_ssthresh", rep1, "B")
    check("bug_ssthresh rep1 mode B: first seq 1705, ssthresh",
          (b["first_seq"], b["first_callback"]) == (1705, "ssthresh"), b)
    b = seeded("cubic_bug_epoch_reset", rep1, "B")
    check("bug_epoch_reset rep1 mode B: first seq 1705, ssthresh",
          (b["first_seq"], b["first_callback"]) == (1705, "ssthresh"), b)
    b = seeded("cubic_bug_ack_accounting", rep1, "B")
    check("bug_ack_accounting rep1 mode B: first seq 588, cong_avoid",
          (b["first_seq"], b["first_callback"]) == (588, "cong_avoid"), b)
    for rel_path in common.PRIMARY["cubic"]:
        for mode in common.MODES:
            r = seeded("cubic_bug_dormant_undo", rel_path, mode)
            check(f"bug_dormant_undo {rel_path} mode {mode}: 0 disagreements", r["n_disagree"] == 0, r)

    # 3. Generator determinism.
    same = mutate.MUTANTS_PATH.exists() and mutate.MUTANTS_PATH.read_bytes() == mutate.jsonl_bytes()
    check("generator determinism (mutants.jsonl byte-identical on regeneration)", same, same)
    return checks


# --------------------------------------------------------------------------
# Static call graph (PREDICTIONS.md S1)
# --------------------------------------------------------------------------

def _static_graph(controller):
    """Return (reach, names, module_assign_lines):
    reach[callback_name]  = model functions transition() can reach for that callback;
    names[callback_name]  = module-level names those functions read, closed over
                            module-level constant dependencies;
    module_assign_lines   = [(start, end, target_name)] for module-level assigns."""
    tree = ast.parse(mutate.MODEL_SOURCES[controller].read_text())
    ref = importlib.import_module(controllers_mod.BUILTINS[controller]["module"])
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    calls = {f: {c.func.id for c in ast.walk(n) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
             for f, n in funcs.items()}
    loads = {f: {x.id for x in ast.walk(n) if isinstance(x, ast.Name)} for f, n in funcs.items()}
    module_deps, assign_lines = {}, []
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    module_deps[t.id] = {x.id for x in ast.walk(n.value) if isinstance(x, ast.Name)}
                    assign_lines.append((n.lineno, n.end_lineno, t.id))

    def close(start, graph):
        seen, todo = set(), list(start)
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            todo.extend(graph.get(x, ()))
        return seen

    reach, names = {}, {}
    for node in ast.walk(funcs["transition"]):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "cb"
                and isinstance(t.comparators[0], ast.Name)):
            cb_name = ref.CALLBACK_NAMES[getattr(ref, t.comparators[0].id)]
            direct = {c.func.id for b in node.body for c in ast.walk(b)
                      if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in funcs}
            r = close(direct, {f: calls[f] & set(funcs) for f in funcs})
            reach[cb_name] = r
            read = set().union(*(loads[f] for f in r)) if r else set()
            names[cb_name] = close(read & set(module_deps), module_deps)
    return reach, names, assign_lines


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

KILL = ("KILLED", "KILLED-CRASH", "KILLED-TIMEOUT")


def analyze(out_dir):
    rows = [json.loads(x) for x in (out_dir / "results.jsonl").read_text().splitlines() if x.strip()]
    s4_rows = [json.loads(x) for x in (out_dir / "s4.jsonl").read_text().splitlines() if x.strip()] \
        if (out_dir / "s4.jsonl").exists() else []
    coverage = json.loads((common.HERE / "coverage.json").read_text())
    by_mutant = {}
    for r in rows:
        by_mutant.setdefault(r["id"], []).append(r)

    analysis = {"controllers": {}, "S1_violations": [], "S2_violations": [], "S3_exceptions": [],
                "S4_out_of_schema": [], "S4_in_schema_on_survivor": []}
    graphs = {c: _static_graph(c) for c in {r["controller"] for r in rows}}

    for controller in sorted({r["controller"] for r in rows}):
        reach, names, assign_lines = graphs[controller]
        primary = common.PRIMARY[controller]
        covered = set()
        for p in primary:
            covered |= set(coverage[controller][p]["lines"])
        mids = sorted(m for m, rs in by_mutant.items() if rs[0]["controller"] == controller)
        per_op, survivors, killed_list = {}, [], []
        crash = timeout = 0
        aux = {}
        for mid in mids:
            rs = by_mutant[mid]
            op = rs[0]["operator"]
            prim_a = [r for r in rs if r["role"] == "primary" and r["mode"] == "A"]
            killed = any(r["outcome"] in KILL for r in prim_a)
            d = per_op.setdefault(op, {"total": 0, "killed": 0})
            d["total"] += 1
            d["killed"] += killed
            crash += any(r["outcome"] == "KILLED-CRASH" for r in prim_a)
            timeout += any(r["outcome"] == "KILLED-TIMEOUT" for r in prim_a)
            for r in rs:
                if r["role"] == "auxiliary" and r["mode"] == "A":
                    aux.setdefault(r["trace"], {"killed": 0, "total": 0})
                    aux[r["trace"]]["total"] += 1
                    aux[r["trace"]]["killed"] += r["outcome"] in KILL
            if killed:
                killed_list.append(mid)
            else:
                fn = rs[0]["function"]
                span = set(range(rs[0]["line"], rs[0]["end_line"] + 1))
                label = "executed" if fn == "<module>" or (span & covered) else "U"
                survivors.append({"id": mid, "operator": op, "function": fn,
                                  "line": rs[0]["line"], "coverage_label": label})

            # S1: localization of the first Mode-A disagreement, per trace.
            for r in rs:
                if r["mode"] != "A" or r["outcome"] != "KILLED":
                    continue
                cb = r["first_callback"]
                fn = r["function"]
                if fn == "<module>":
                    tgt = [n for (a, b, n) in assign_lines if a <= r["line"] <= b]
                    ok = bool(tgt) and tgt[0] in names.get(cb, set())
                else:
                    ok = fn in reach.get(cb, set())
                if not ok:
                    analysis["S1_violations"].append({"id": mid, "trace": r["trace"], "first_callback": cb,
                                                      "function": fn, "line": r["line"]})

            # S2/S3: Mode A vs Mode B per trace.
            for rel_path in {r["trace"] for r in rs}:
                ra = next((r for r in rs if r["trace"] == rel_path and r["mode"] == "A"), None)
                rb = next((r for r in rs if r["trace"] == rel_path and r["mode"] == "B"), None)
                if not ra or not rb or ra["outcome"] != "KILLED" and rb["outcome"] != "KILLED":
                    continue
                if "KILLED-" in ra["outcome"] or "KILLED-" in rb["outcome"]:
                    continue  # crash/timeout: no first-disagreement index to compare
                n = ra.get("n_events") or rb.get("n_events")
                prefix = common.R3B_EXACT_PREFIX.get(rel_path, n)
                fa, fb = ra.get("first_index"), rb.get("first_index")
                firsts = [x for x in (fa, fb) if x is not None]
                if firsts and min(firsts) < prefix and fa != fb:
                    analysis["S2_violations"].append({"id": mid, "trace": rel_path, "first_index_A": fa,
                                                      "first_index_B": fb, "prefix": prefix})
                if ra["outcome"] == "KILLED" and rb["outcome"] != "KILLED":
                    analysis["S3_exceptions"].append({"id": mid, "trace": rel_path, "first_index_A": fa,
                                                      "after_prefix": fa is not None and fa >= prefix})

        live = len(mids)
        n_killed = len(killed_list)
        analysis["controllers"][controller] = {
            "live_mutants": live, "killed_primary": n_killed,
            "raw_score": round(n_killed / live, 4) if live else None,
            "killed_by_crash": crash, "killed_by_timeout": timeout,
            "per_operator": {op: {**d, "rate": round(d["killed"] / d["total"], 4)} for op, d in sorted(per_op.items())},
            "survivors": survivors,
            "survivor_labels": {lab: sum(s["coverage_label"] == lab for s in survivors) for lab in ("U", "executed")},
            "auxiliary_mode_A": aux,
        }
    for s in s4_rows:
        if s["out_of_schema_diffs"]:
            analysis["S4_out_of_schema"].append(s)
        if s["in_schema_diffs"]:
            analysis["S4_in_schema_on_survivor"].append(s)
    (out_dir / "analysis.json").write_text(json.dumps(analysis, indent=1, sort_keys=True) + "\n")

    fields = ["id", "controller", "operator", "function", "line", "trace", "role", "mode", "outcome",
              "n_events", "n_disagree", "first_index", "first_seq", "first_callback", "elapsed_s", "error"]
    with open(out_dir / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["id"], r["trace"], r["mode"])):
            w.writerow(r)
    (out_dir / "results.json").write_text(json.dumps(
        sorted(rows, key=lambda r: (r["id"], r["trace"], r["mode"])), indent=1) + "\n")
    return analysis


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def _git(*args):
    return subprocess.run(["git", *args], cwd=common.ROOT, capture_output=True, text=True).stdout.strip()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser(description="C6 mutation campaign runner")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--limit", type=int, default=None,
                    help="only the first N live mutants per controller (harness check, not evidence)")
    ap.add_argument("--controllers", nargs="+", default=["reno", "cubic"])
    ap.add_argument("--out", default=str(common.HERE / _now().replace(":", "") / __import__("uuid").uuid4().hex[:8]))
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args(argv)
    out_dir = pathlib.Path(args.out)
    if not args.analyze_only:
        missing = [p for c in args.controllers for p, _ in common.traces_for(c) if not (common.ROOT / p).exists()]
        if missing: ap.error("Restore the complete friend ZIP inputs first: " + ", ".join(missing))
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.analyze_only:
        print(json.dumps({c: {k: v for k, v in d.items() if k != "survivors"}
                          for c, d in analyze(out_dir)["controllers"].items()}, indent=1))
        return 0

    manifest = {
        "command": "python " + " ".join([pathlib.Path(sys.argv[0]).as_posix(), *sys.argv[1:]]),
        "git_commit": _git("rev-parse", "HEAD"),
        "dirty": _git("status", "--porcelain"),
        "host": {"platform": platform.platform(), "python": platform.python_version(),
                 "cpu_count": os.cpu_count()},
        "workers": args.workers, "limit": args.limit, "controllers": args.controllers,
        "timeout_s": TIMEOUT_S, "started": _now(),
    }

    checks = run_controls()
    (out_dir / "controls.json").write_text(json.dumps(checks, indent=1) + "\n")
    if not all(c["ok"] for c in checks):
        manifest.update(finished=_now(), status="STOPPED: harness control failed")
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        print("Harness control failed -- no mutant was run (SPEC.md section 5).")
        return 2

    tasks = []
    for controller in args.controllers:
        live = [r for r in mutate.generate(controller) if r["status"] == "live"]
        if args.limit:
            live = live[:args.limit]
        tasks += [({k: v for k, v in r.items() if k != "source"}, r["source"]) for r in live]
    manifest["n_mutants_run"] = len(tasks)
    print(f"running {len(tasks)} mutants on {args.workers} workers")

    for name in ("results.jsonl", "s4.jsonl"):
        (out_dir / name).write_text("")
    done = 0
    t0 = time.monotonic()
    ctx = mp.get_context("spawn")
    with ctx.Pool(args.workers, maxtasksperchild=25) as pool, \
            open(out_dir / "results.jsonl", "a") as fr, open(out_dir / "s4.jsonl", "a") as fs:
        for mid, rows, s4 in pool.imap_unordered(run_mutant, tasks):
            for r in rows:
                fr.write(json.dumps(r, sort_keys=True) + "\n")
            for s in s4:
                fs.write(json.dumps({"id": mid, **s}, sort_keys=True) + "\n")
            fr.flush()
            fs.flush()
            done += 1
            if done % 10 == 0 or done == len(tasks):
                el = time.monotonic() - t0
                print(f"{done}/{len(tasks)} mutants, {el:.0f}s elapsed, "
                      f"~{el / done * (len(tasks) - done):.0f}s left", flush=True)

    manifest.update(finished=_now(), status="COMPLETE")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    a = analyze(out_dir)
    print(json.dumps({c: {k: v for k, v in d.items() if k != "survivors"} for c, d in a["controllers"].items()},
                     indent=1))
    print({k: len(v) for k, v in a.items() if k != "controllers"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
