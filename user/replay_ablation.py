"""Replay ABI ablation (data/abi_ablation/SPEC.md, CURRENT_STATE section 11 Priority B).

Masks one recorded INPUT field class (or one field) to 0 in a copy of every
event, reruns exact semantic self-replay -- the R1/R2 loops for Reno, the
E2/E3 loops for CoVegas, mirrored here unchanged except for the mask -- and
compares against the UNMASKED recording with the gates' own comparison
schema. Reports the first failing event with full evidence (INSTRUCTIONS.md
section 10).

The gate scripts user/replay_r1.py, replay_r2.py, replay_e2.py, replay_e3.py
are not modified; control 1 (the unmasked baseline must reproduce the
CURRENT_STATE section 14 ledger exactly) is what ties this loop to them.

Usage:
  python user/replay_ablation.py [--workers 6]   # writes data/abi_ablation/{results,manifest,analysis}.json
  python user/replay_ablation.py --analyze-only
"""
import argparse
import datetime
import json
import multiprocessing as mp
import os
import pathlib
import platform
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
# user/ too: ccr_trace_v1/v2 import their sibling `ccr_trace` as a top-level
# module (same sys.path setup as ccreplay/__init__.py).
for _p in (str(ROOT), str(ROOT / "user")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_DIR = ROOT / "runtime" / "experiments" / "abi_ablation"

TRACES = {
    "reno": ["raw/r0/rep1.ccr", "raw/r0/rep2.ccr", "raw/r0/rep3.ccr"],
    "covegas": ["raw/covegas_replay/primary/rep1.ccr", "raw/covegas_replay/primary/rep2.ccr",
                "raw/covegas_replay/primary/rep3.ccr"],
}

# SPEC.md section 3. Only fields the replay reads as input; never an oracle field.
_SPS = ["pre_snd_cwnd", "pre_snd_ssthresh", "pre_snd_cwnd_cnt", "pre_snd_cwnd_clamp", "pre_prior_cwnd"]
RENO_CLASSES = {
    "CI": ["in_ack", "in_acked"],
    "SPS": _SPS,
    "OBS": ["pre_max_packets_out", "pre_is_cwnd_limited"],
    "DIAG": ["ts_ns"],
}


def _covegas_classes():
    from user.covegas_model import DEDICATED_FIELDS, DELAY_ARM_FIELDS, CUBIC_ARM_FIELDS
    return {
        "CI": ["in_ack", "in_acked", "in_sample_rtt_us"],
        "SPS": _SPS,
        "OBS": ["pre_max_packets_out", "pre_is_cwnd_limited", "pre_snd_nxt", "pre_mss_cache",
                "pre_rate_delivered", "pre_rate_interval_us", "pre_rate_app_limited", "pre_srtt_us"],
        "TIME-J": ["clock_jiffies32_before"],
        "TIME-K": ["clock_ktime_ns_before"],
        "DIAG": ["clock_jiffies32_after", "clock_ktime_ns_after"],
        "PRIV-DED": [f"priv_pre_{f}" for f in DEDICATED_FIELDS if f != "mode"],
        "PRIV-MODE": ["priv_pre_mode"],
        "PRIV-DELAY": [f"priv_pre_{f}" for f in DELAY_ARM_FIELDS],
        "PRIV-CUBIC": [f"priv_pre_{f}" for f in CUBIC_ARM_FIELDS],
    }


def classes_for(controller):
    return RENO_CLASSES if controller == "reno" else _covegas_classes()


def masks_for(controller):
    """[(mask_id, kind, fields)]: baseline, identity, every class, every field."""
    classes = classes_for(controller)
    out = [("BASELINE", "control", []), ("IDENTITY", "control", None)]
    out += [(f"class:{c}", "class", fs) for c, fs in classes.items()]
    out += [(f"field:{f}", "field", [f]) for fs in classes.values() for f in fs]
    return out


# --------------------------------------------------------------------------
# Controller adapters: exactly the gate scripts' calls.
# --------------------------------------------------------------------------

class Adapter:
    def __init__(self, controller):
        self.controller = controller
        if controller == "reno":
            import user.reno_model as m
            self.m = m
            self.seed = m.NONE_PRIVATE_STATE  # R2 threads NONE (ADR-014)
        else:
            import user.covegas_model as m
            self.m = m
            self.seed = m.INITIAL_PRIVATE_STATE  # E3's ZERO_PRIVATE_STATE

    def mode_a_state(self, e):
        # R1: NONE_PRIVATE_STATE; E2: private_pre_from_event(e)
        return self.m.NONE_PRIVATE_STATE if self.controller == "reno" else self.m.private_pre_from_event(e)

    def fields(self, original, computed):
        if self.controller == "reno":
            return self.m.COMPARISON_FIELDS[original["callback_id"]]
        # E2/E3: PRE mode from the RECORDING (oracle, never masked), POST mode computed.
        return self.m.comparison_fields(original["callback_id"], original["priv_pre_mode"],
                                        computed["priv_post_mode"])


def _masked(e, fields):
    if fields is None:  # IDENTITY control: a copy with every field set to its own value
        return {k: v for k, v in e.items()}
    c = dict(e)
    for f in fields:
        c[f] = 0
    return c


def run_mask(ad, events, names, mask_fields, mode):
    """One masked self-replay. Mode A: count every mismatch. Mode B: carry state;
    first divergence is the result (later ones are cascades, only counted)."""
    state = dict(ad.seed) if isinstance(ad.seed, dict) else ad.seed
    first = None
    mismatches = 0
    exceptions = 0
    field_comparisons = 0
    for idx, e in enumerate(events):
        me = _masked(e, mask_fields)
        try:
            if mode == "A":
                computed, _ = ad.m.transition(me, ad.mode_a_state(me))
            else:
                computed, state = ad.m.transition(me, state)
        except Exception as exc:  # noqa: BLE001
            # A masked input can make the model itself fail (e.g. cwnd = 0 as a
            # divisor). Self-replay cannot reproduce the recorded result at this
            # event, so it is a failure here. Mode A continues event by event;
            # Mode B stops, since there is no state to carry forward.
            mismatches += 1
            exceptions += 1
            if first is None:
                first = {"index": idx, "seq": e["seq"], "callback": names.get(e["callback_id"], e["callback_id"]),
                         "diff_fields": [], "exception": f"{type(exc).__name__}: {exc}",
                         "masked_inputs_recorded": {f: e.get(f) for f in (mask_fields or [])}}
            if mode == "B":
                break
            continue
        fields = ad.fields(e, computed)
        field_comparisons += len(fields)
        diffs = [f for f in fields if computed.get(f) != e.get(f)]
        if diffs:
            mismatches += 1
            if first is None:
                first = {
                    "index": idx, "seq": e["seq"], "callback": names.get(e["callback_id"], e["callback_id"]),
                    "diff_fields": diffs,
                    "expected_computed": {f: computed.get(f) for f in diffs},
                    "actual_recorded": {f: e.get(f) for f in diffs},
                    "masked_inputs_recorded": {f: e.get(f) for f in (mask_fields or [])},
                }
    return {"mismatch_events": mismatches, "exception_events": exceptions,
            "field_comparisons": field_comparisons, "first_failure": first}


def trace_facts(events, controller, mask_fields):
    first_nonzero = next((i for i, e in enumerate(events) if any(e.get(f, 0) != 0 for f in mask_fields or [])), None)
    inert = sum(1 for e in events if all(e.get(f, 0) == 0 for f in mask_fields or []))
    return first_nonzero, inert


def reference_facts(events, controller):
    """Facts the predictions reference, computed from the recording alone."""
    facts = {}
    if controller == "reno":
        facts["G_first_growth_index"] = next(
            (i for i, e in enumerate(events) if e["callback_id"] == 2 and
             (e["post_snd_cwnd"] != e["pre_snd_cwnd"] or e["post_snd_cwnd_cnt"] != e["pre_snd_cwnd_cnt"])), None)
        facts["first_ssthresh_index"] = next((i for i, e in enumerate(events) if e["callback_id"] == 1), None)
    else:
        facts["first_compete_pre_index"] = next((i for i, e in enumerate(events) if e["priv_pre_mode"] == 1), None)
    return facts


def run_trace(task):
    """Pool worker: parse one trace once, run every mask in both modes."""
    controller, rel_path = task
    from user.ccreplay_diff import _detect_version_and_parse
    _, raw, select_dominant_connection, names = _detect_version_and_parse(str(ROOT / rel_path))
    _, events, _ = select_dominant_connection(raw)
    events.sort(key=lambda e: e["seq"])
    ad = Adapter(controller)
    rows = []
    for mask_id, kind, fields in masks_for(controller):
        first_nonzero, inert = trace_facts(events, controller, fields)
        for mode in ("A", "B"):
            t0 = time.monotonic()
            r = run_mask(ad, events, names, fields, mode)
            rows.append({
                "controller": controller, "trace": rel_path, "mask": mask_id, "kind": kind,
                "fields": fields, "mode": mode, "n_events": len(events),
                "first_nonzero_index": first_nonzero, "inert_events": inert,
                "elapsed_s": round(time.monotonic() - t0, 3), **r,
            })
    return {"controller": controller, "trace": rel_path, "facts": reference_facts(events, controller), "rows": rows}


# --------------------------------------------------------------------------
# Controls and analysis
# --------------------------------------------------------------------------

LEDGER = {  # docs/CURRENT_STATE.md section 14
    "reno": {"events": 112051, "field_comparisons": 224120},
    "covegas": {"events": 190277, "field_comparisons": 4982990},
}
ORACLE_PREFIXES = ("post_", "priv_post_", "result")


def controls(results):
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    for controller in TRACES:
        rows = [r for t in results if t["controller"] == controller for r in t["rows"]]
        base_a = [r for r in rows if r["mask"] == "BASELINE" and r["mode"] == "A"]
        base_b = [r for r in rows if r["mask"] == "BASELINE" and r["mode"] == "B"]
        ev = sum(r["n_events"] for r in base_a)
        fc = sum(r["field_comparisons"] for r in base_a)
        mm = sum(r["mismatch_events"] for r in base_a)
        check(f"{controller} baseline Mode A reproduces ledger (events, field comparisons, 0 mismatches)",
              (ev, fc, mm) == (LEDGER[controller]["events"], LEDGER[controller]["field_comparisons"], 0),
              {"events": ev, "field_comparisons": fc, "mismatches": mm, "ledger": LEDGER[controller]})
        check(f"{controller} baseline Mode B: first divergence NONE on every trace",
              all(r["first_failure"] is None for r in base_b), [r["first_failure"] for r in base_b])
        ident = [r for r in rows if r["mask"] == "IDENTITY"]
        check(f"{controller} identity mask indistinguishable from baseline",
              all(r["mismatch_events"] == 0 and r["first_failure"] is None for r in ident), len(ident))
        masked = {f for _, _, fs in masks_for(controller) for f in (fs or [])}
        check(f"{controller} no masked field is an oracle field",
              not any(f.startswith(ORACLE_PREFIXES) for f in masked), sorted(masked))
    return checks


def analyze(results):
    a = {"controls": controls(results), "load_bearing": {}, "checks": {}, "facts": {}}
    for t in results:
        a["facts"][t["trace"]] = t["facts"]
    for controller in TRACES:
        rows = [r for t in results if t["controller"] == controller for r in t["rows"]]
        table = {}
        for r in rows:
            if r["kind"] == "control":
                continue
            d = table.setdefault(r["mask"], {"kind": r["kind"], "fields": r["fields"], "per_trace": {}})
            pt = d["per_trace"].setdefault(r["trace"], {})
            ff = r["first_failure"]
            pt[r["mode"]] = {"mismatch_events": r["mismatch_events"],
                             "first_index": ff["index"] if ff else None,
                             "first_seq": ff["seq"] if ff else None,
                             "first_callback": ff["callback"] if ff else None,
                             "first_nonzero_index": r["first_nonzero_index"],
                             "inert_fraction": round(r["inert_events"] / r["n_events"], 6)}
        for mask, d in table.items():
            d["load_bearing"] = any(v["A"]["mismatch_events"] > 0 for v in d["per_trace"].values())
        a["load_bearing"][controller] = table

        # U1: first Mode-A failure never before the first non-zero masked event.
        u1 = [(m, tr) for m, d in table.items() for tr, v in d["per_trace"].items()
              if v["A"]["first_index"] is not None and
              (v["A"]["first_nonzero_index"] is None or v["A"]["first_index"] < v["A"]["first_nonzero_index"])]
        # U2: shared-input masks, Mode B first divergence == Mode A first failure.
        shared = [m for m, d in table.items() if not any(f.startswith("priv_pre_") for f in d["fields"])]
        u2 = [(m, tr, v["A"]["first_index"], v["B"]["first_index"]) for m in shared
              for tr, v in table[m]["per_trace"].items() if v["A"]["first_index"] != v["B"]["first_index"]]
        # U3: private masks never affect Mode B.
        priv = [m for m in table if m not in shared]
        u3 = [(m, tr) for m in priv for tr, v in table[m]["per_trace"].items() if v["B"]["first_index"] is not None]
        a["checks"][controller] = {"U1_violations": u1, "U2_violations": u2, "U3_violations": u3}
    return a


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay ABI ablation")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.analyze_only:
        manifest = {"command": "python user/replay_ablation.py " + " ".join(sys.argv[1:]),
                    "git_commit": _git("rev-parse", "HEAD"), "dirty": _git("status", "--porcelain"),
                    "host": {"platform": platform.platform(), "python": platform.python_version(),
                             "cpu_count": os.cpu_count()},
                    "workers": args.workers, "started": _now()}
        tasks = [(c, p) for c, ps in TRACES.items() for p in ps]
        with mp.get_context("spawn").Pool(args.workers) as pool:
            results = []
            for res in pool.imap_unordered(run_trace, tasks):
                results.append(res)
                print(f"done {res['controller']} {res['trace']} ({len(res['rows'])} runs)", flush=True)
        results.sort(key=lambda t: (t["controller"], t["trace"]))
        (OUT_DIR / "results.json").write_text(json.dumps(results, indent=1, default=str) + "\n")
        manifest["finished"] = _now()
        (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    results = json.loads((OUT_DIR / "results.json").read_text())
    a = analyze(results)
    (OUT_DIR / "analysis.json").write_text(json.dumps(a, indent=1, default=str) + "\n")
    for c in a["controls"]:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['name']}")
    for controller, d in a["load_bearing"].items():
        print(controller, "classes:", {m: v["load_bearing"] for m, v in d.items() if v["kind"] == "class"})
        print(controller, "non-load-bearing fields:", [m for m, v in d.items() if v["kind"] == "field" and not v["load_bearing"]])
    print({c: {k: len(v) for k, v in d.items()} for c, d in a["checks"].items()})
    return 0 if all(c["ok"] for c in a["controls"]) else 2


if __name__ == "__main__":
    sys.exit(main())
