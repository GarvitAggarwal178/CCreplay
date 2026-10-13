"""Controller registry: built-ins, parameter variants, user-written code.

Does not modify any file under user/. Parameter variants and user controllers
are built by executing a fresh copy of an existing module's source into a new
module object (STUDIO_CONTEXT.md §9) -- "import + monkeypatch another module"
does not work here because transition() calls sibling functions through the
module's own namespace, not through imported references.
"""
import importlib
import json
import pathlib
import re
import types

import ccreplay  # noqa: F401

ROOT = ccreplay.ROOT
USER_DIR = ROOT / "controllers" / "user"
USER_DIR.mkdir(parents=True, exist_ok=True)
PARAM_STORE = ROOT / "studio_data" / "param_variants.json"
PARAM_STORE.parent.mkdir(exist_ok=True)

ABI_BY_NAME = {"reno": 0, "cubic": 1, "covegas": 2}

_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,80}$")


def _require_safe_name(name: str):
    """Names become filenames (controllers/user/<id>.py, studio_data param
    keys) -- reject anything that isn't a plain identifier so a crafted name
    like `../../etc/passwd` or `foo/bar` can't escape the intended directory."""
    if not _NAME_RE.match(name):
        raise ValueError(
            f"invalid name {name!r}: must match {_NAME_RE.pattern} (letters, digits, underscore only)")

DEFAULT_TRACE_FOR_ABI = {
    0: "raw/r0/rep1.ccr",
    1: "raw/cubic_replay/primary/rep1.ccr",
    2: "raw/covegas_replay/primary/rep1.ccr",
}

BUILTIN_SOURCE_PATH = {
    "reno": ROOT / "user" / "reno_model.py",
    "cubic": ROOT / "user" / "cubic_model.py",
    "covegas": ROOT / "user" / "covegas_model.py",
}

# {id: {module_path, abi, kind, description, base}}
BUILTINS = {
    "reno": {"module": "user.reno_model", "abi": 0, "kind": "reference",
              "description": "Reference Reno model (real kernel tcp_reno_* parity, R0-R2 PASS)."},
    "cubic": {"module": "user.cubic_model", "abi": 1, "kind": "reference",
               "description": "Reference CUBIC model ported from real kernel source (R3 PARTIAL -- see validation table)."},
    "covegas": {"module": "user.covegas_model", "abi": 2, "kind": "reference",
                 "description": "Reference CoVegas model (E1-E3 PASS, no independent kernel reference)."},
    "cubic_bug_ssthresh": {"module": "user.cubic_model_bug_ssthresh", "abi": 1, "kind": "seeded-bug",
                             "description": "Seeded bug: ssthresh off-by-one (N5 positive control)."},
    "cubic_bug_epoch_reset": {"module": "user.cubic_model_bug_epoch_reset", "abi": 1, "kind": "seeded-bug",
                                "description": "Seeded bug: epoch_start reset condition altered."},
    "cubic_bug_ack_accounting": {"module": "user.cubic_model_bug_ack_accounting", "abi": 1, "kind": "seeded-bug",
                                   "description": "Seeded bug: ack_cnt accounting altered."},
    "cubic_bug_dormant_undo": {"module": "user.cubic_model_bug_dormant_undo", "abi": 1, "kind": "seeded-bug",
                                 "description": "Seeded bug: dormant undo_cwnd defect (negative control -- does not fire on primary traces)."},
    "covegas_v3_latch": {"module": "user.covegas_model_v3_latch", "abi": 2, "kind": "historical",
                           "description": "Reconstructed v3: A3 settle-latch guard reverted to unconditional latch."},
}

CUBIC_TUNABLES = {
    "BETA": {"default": 717, "min": 1, "max": 1023, "note": "beta (shown as BETA/1024); derives BETA_SCALE/CUBE_RTT_SCALE/CUBE_FACTOR"},
    "BIC_SCALE": {"default": 41, "min": 1, "max": 400, "note": "derives CUBE_RTT_SCALE/CUBE_FACTOR"},
    "FAST_CONVERGENCE": {"default": 1, "min": 0, "max": 1, "note": "on/off"},
    "TCP_FRIENDLINESS": {"default": 1, "min": 0, "max": 1, "note": "on/off"},
    "HYSTART": {"default": 1, "min": 0, "max": 1, "note": "on/off"},
}

RENO_TUNABLES = {
    "num": {"default": 1, "min": 1, "max": 99, "note": "fraction of cwnd retained on loss = num/den"},
    "den": {"default": 2, "min": 1, "max": 100, "note": "fraction of cwnd retained on loss = num/den"},
}


def clone_base(base: str, name: str) -> types.ModuleType:
    """Fresh, independent copy of a built-in model module's source, as its
    own module object with its own globals. See module docstring."""
    path = BUILTIN_SOURCE_PATH[base]
    m = types.ModuleType(name)
    m.__file__ = str(path)
    code = compile(path.read_text(), str(path), "exec")
    exec(code, m.__dict__)
    return m


def _recompute_cubic_derived(m: types.ModuleType):
    m.BETA_SCALE = (8 * (m.BICTCP_BETA_SCALE + m.BETA) // 3) // (m.BICTCP_BETA_SCALE - m.BETA)
    m.CUBE_RTT_SCALE = m.BIC_SCALE * 10
    m.CUBE_FACTOR = (1 << (10 + 3 * m.BICTCP_HZ)) // (m.BIC_SCALE * 10)


def _check_range(tunables: dict, key: str, value: int):
    spec = tunables.get(key)
    if spec is None:
        return
    if not (spec["min"] <= value <= spec["max"]):
        raise ValueError(f"{key}={value} out of range [{spec['min']}, {spec['max']}]")


def make_param(base: str, name: str, params: dict) -> types.ModuleType:
    if base == "reno":
        num = int(params.get("num", 1))
        den = int(params.get("den", 2))
        min_ssthresh = int(params.get("min_ssthresh", 2))
        _check_range(RENO_TUNABLES, "num", num)
        _check_range(RENO_TUNABLES, "den", den)
        if den == 0:
            raise ValueError("den must not be 0")
        m = clone_base("reno", name)

        # Real signature (user/reno_model.py): model_ssthresh(pre, private_state)
        # -> (result, next_private_state) -- NOT a plain int-returning function
        # of cwnd alone. `num/den` is the fraction of cwnd retained on loss.
        def model_ssthresh(pre, private_state):
            return max((pre["snd_cwnd"] * num) // den, min_ssthresh), private_state

        m.model_ssthresh = model_ssthresh
        return m
    if base == "cubic":
        m = clone_base("cubic", name)
        for k in ("BETA", "BIC_SCALE", "FAST_CONVERGENCE", "TCP_FRIENDLINESS", "HYSTART"):
            if k in params:
                if not hasattr(m, k):
                    raise KeyError(k)
                v = int(params[k])
                _check_range(CUBIC_TUNABLES, k, v)
                setattr(m, k, v)
        _recompute_cubic_derived(m)
        return m
    raise ValueError(f"no parameter variants defined for base {base!r}")


def _param_store_load() -> dict:
    if PARAM_STORE.exists():
        return json.loads(PARAM_STORE.read_text())
    return {}


def _param_store_save(store: dict):
    PARAM_STORE.write_text(json.dumps(store, indent=2, sort_keys=True))


def save_param_variant(base: str, name: str, params: dict) -> str:
    _require_safe_name(name)
    cid = f"param_{name}"
    store = _param_store_load()
    store[cid] = {"base": base, "name": name, "params": params}
    _param_store_save(store)
    return cid


def list_param_variants() -> dict:
    return _param_store_load()


def save_user_controller(name: str, abi_base: str, code: str) -> str:
    _require_safe_name(name)
    if abi_base not in ABI_BY_NAME:
        raise ValueError(f"unknown abi_base: {abi_base!r} (must be one of {sorted(ABI_BY_NAME)})")
    cid = f"user_{name}"
    path = USER_DIR / f"{cid}.py"
    path.write_text(code)
    # Sidecar so the API process can answer "what ABI is this" (list_controllers,
    # ABI-compatibility checks) WITHOUT exec'ing user-submitted code in-process --
    # only the timed child-process worker (ccreplay.worker) ever executes it.
    (USER_DIR / f"{cid}.meta.json").write_text(json.dumps({"abi_base": abi_base}))
    return cid


def list_user_controllers() -> dict:
    out = {}
    for p in sorted(USER_DIR.glob("*.py")):
        cid = p.stem
        out[cid] = {"path": str(p)}
    return out


def _user_controller_abi_base(cid: str) -> str | None:
    meta_path = USER_DIR / f"{cid}.meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text()).get("abi_base")
        except Exception:
            return None
    return None


def load_controller(controller_id: str) -> types.ModuleType:
    if controller_id in BUILTINS:
        return importlib.import_module(BUILTINS[controller_id]["module"])
    params = _param_store_load()
    if controller_id in params:
        entry = params[controller_id]
        return make_param(entry["base"], entry["name"], entry["params"])
    user_path = USER_DIR / f"{controller_id}.py"
    if user_path.exists():
        m = types.ModuleType(controller_id)
        m.__file__ = str(user_path)
        code = compile(user_path.read_text(), str(user_path), "exec")
        exec(code, m.__dict__)
        if not hasattr(m, "CONTROLLER"):
            raise AttributeError(f"{controller_id}: module does not define CONTROLLER")
        return m.CONTROLLER
    raise KeyError(f"unknown controller id: {controller_id}")


def abi_of(controller_id: str) -> int:
    """Must never exec user-submitted code -- this is called from the API
    process (list_controllers, pre-experiment ABI-compatibility checks), not
    from inside the timed child-process worker. User controllers declare
    their ABI via the sidecar written by save_user_controller; a controller
    with no sidecar (e.g. hand-placed file, pre-ADR-025 upload) has unknown
    ABI until it is validated, which DOES run in the worker."""
    if controller_id in BUILTINS:
        return BUILTINS[controller_id]["abi"]
    params = _param_store_load()
    if controller_id in params:
        return ABI_BY_NAME[params[controller_id]["base"]]
    base = _user_controller_abi_base(controller_id)
    if base in ABI_BY_NAME:
        return ABI_BY_NAME[base]
    raise KeyError(f"no declared ABI for controller {controller_id!r} (missing/invalid sidecar)")


def list_controllers():
    out = []
    for cid, meta in BUILTINS.items():
        out.append({"id": cid, "abi": meta["abi"], "kind": meta["kind"],
                    "description": meta["description"], "name": cid, "source_editable": False})
    for cid, entry in list_param_variants().items():
        out.append({"id": cid, "abi": ABI_BY_NAME[entry["base"]], "kind": "param",
                    "description": f"Parameter variant of {entry['base']}: {entry['params']}",
                    "name": entry["name"], "source_editable": False, "base": entry["base"], "params": entry["params"]})
    for cid in list_user_controllers():
        try:
            abi = abi_of(cid)
        except Exception:
            abi = None
        out.append({"id": cid, "abi": abi, "kind": "user",
                    "description": "User-written controller", "name": cid, "source_editable": True})
    return out


def get_source(controller_id: str) -> str:
    if controller_id in BUILTINS:
        path = ROOT / (BUILTINS[controller_id]["module"].replace(".", "/") + ".py")
        return path.read_text()
    params = _param_store_load()
    if controller_id in params:
        return json.dumps(params[controller_id], indent=2)
    user_path = USER_DIR / f"{controller_id}.py"
    if user_path.exists():
        return user_path.read_text()
    raise KeyError(controller_id)


TEMPLATES = {
    # OFFSET=0 is a deliberate no-op default: saving the template UNCHANGED
    # must self-replay as NO DIVERGENCE against the reference (it's the same
    # computation), so "did my edit actually do anything" has a clean
    # baseline. Setting OFFSET=1 reproduces STUDIO_CONTEXT.md SS8's verified
    # "User override" row: cubic rep1, seq 1,705, ssthresh, 145 vs 144.
    "cubic": '''"""Example user controller: subtract OFFSET from the ssthresh result once
cwnd >= 100. OFFSET=0 (the default) is a no-op -- saving this file unchanged
diffs as NO DIVERGENCE against the reference. Set OFFSET=1 and re-validate to
see a real divergence. CONTROLLER must be a module-like object exposing
transition(event, private_state), INITIAL_PRIVATE_STATE, COMPARISON_FIELDS."""
from ccreplay.controllers import clone_base

OFFSET = 0

base = clone_base("cubic", name="my_cubic")
_orig_transition = base.transition

def my_transition(event, ca):
    computed, next_ca = _orig_transition(event, ca)
    if event["callback_id"] == 1 and event.get("pre_snd_cwnd", 0) >= 100:  # ssthresh
        computed = dict(computed)
        computed["result"] = computed["result"] - OFFSET
    return computed, next_ca

base.transition = my_transition
CONTROLLER = base
''',
    "reno": '''"""Example user controller: Reno retaining NUM/DEN of cwnd on loss instead of
the standard 1/2. NUM=1, DEN=2 (the default) is a no-op -- saving this file
unchanged diffs as NO DIVERGENCE against the reference. Edit, Save, Validate."""
from ccreplay.controllers import clone_base

NUM = 1
DEN = 2

base = clone_base("reno", name="my_reno")

# Real signature (user/reno_model.py): model_ssthresh(pre, private_state)
# -> (result, next_private_state).
def model_ssthresh(pre, private_state):
    return max((pre["snd_cwnd"] * NUM) // DEN, 2), private_state

base.model_ssthresh = model_ssthresh
CONTROLLER = base
''',
}


def get_template(base: str) -> str:
    if base not in TEMPLATES:
        raise KeyError(base)
    return TEMPLATES[base]


def validate_controller(controller_id: str) -> dict:
    """Runs entirely in-process here; the API layer invokes this inside a
    timed child process (backend/worker). Checks: loads; has transition;
    has a seed; has a comparison schema; runs Mode B against its OWN base
    reference on the first 2000 events of the default trace for its ABI
    without exceptions; output contains every declared comparison field;
    two runs are identical (determinism)."""
    from user.ccreplay_diff import _detect_version_and_parse, _initial_state

    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    try:
        mod = load_controller(controller_id)
    except Exception as exc:
        return {"ok": False, "checks": [{"name": "loads", "ok": False, "detail": str(exc)}]}
    check("loads", True)

    has_transition = check("has_transition", hasattr(mod, "transition"))
    has_seed = check("has_seed", hasattr(mod, "INITIAL_PRIVATE_STATE") or hasattr(mod, "NONE_PRIVATE_STATE"))
    has_schema = check("has_comparison_schema", hasattr(mod, "COMPARISON_FIELDS") or hasattr(mod, "comparison_fields"))
    if not (has_transition and has_seed and has_schema):
        return {"ok": False, "checks": checks}

    try:
        abi = abi_of(controller_id)
    except Exception as exc:
        check("abi_detected", False, str(exc))
        return {"ok": False, "checks": checks}
    check("abi_detected", True, f"abi={abi}")

    base_id = {0: "reno", 1: "cubic", 2: "covegas"}[abi]
    trace_path = str(ROOT / DEFAULT_TRACE_FOR_ABI[abi])

    def run_first_n(n):
        hdr, events, select_dominant_connection, CALLBACK_NAMES = _detect_version_and_parse(trace_path)
        _, dominant_events, _ = select_dominant_connection(events)
        dominant_events.sort(key=lambda e: e["seq"])
        dominant_events = dominant_events[:n]
        base_mod = importlib.import_module(BUILTINS[base_id]["module"])
        cand_state = _initial_state(mod)
        base_state = _initial_state(base_mod)
        v2 = not hasattr(mod, "COMPARISON_FIELDS") and hasattr(mod, "comparison_fields")
        first_divergence = None
        n_run = 0
        seen_fields = set()
        for idx, e in enumerate(dominant_events):
            cb = e["callback_id"]
            cand_computed, cand_state = mod.transition(e, cand_state)
            base_computed, base_state = base_mod.transition(e, base_state)
            seen_fields.update(cand_computed.keys())
            if v2:
                fields = mod.comparison_fields(cb, e.get("priv_pre_mode"), cand_computed.get("priv_post_mode"))
            else:
                fields = mod.COMPARISON_FIELDS[cb]
            diffs = [f for f in fields if cand_computed.get(f) != base_computed.get(f)]
            n_run += 1
            if diffs and first_divergence is None:
                first_divergence = {"event_index": idx, "seq": e["seq"], "fields": diffs}
        return n_run, first_divergence, seen_fields, dominant_events, base_mod

    try:
        n_run, first_divergence, seen_fields, dominant_events, base_mod = run_first_n(2000)
        check("runs_without_exception", True, f"{n_run} events replayed against its base reference ({base_id})")
    except Exception as exc:
        check("runs_without_exception", False, f"{type(exc).__name__}: {exc}")
        return {"ok": False, "checks": checks}

    v2 = not hasattr(mod, "COMPARISON_FIELDS") and hasattr(mod, "comparison_fields")
    if v2:
        declared = set()
        for cb in range(1, 8):
            for pm in (0, 1):
                for om in (0, 1):
                    try:
                        declared.update(mod.comparison_fields(cb, pm, om))
                    except Exception:
                        pass
    else:
        declared = set()
        for fields in mod.COMPARISON_FIELDS.values():
            declared.update(fields)
    missing = declared - seen_fields
    check("output_contains_declared_fields", len(missing) == 0, f"missing={sorted(missing)}" if missing else "all present")

    try:
        n_run2, first_divergence2, _, _, _ = run_first_n(2000)
        deterministic = (first_divergence == first_divergence2)
        check("deterministic_rerun", deterministic,
              "two runs identical" if deterministic else f"{first_divergence} != {first_divergence2}")
    except Exception as exc:
        check("deterministic_rerun", False, str(exc))

    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "checks": checks,
        "first_2000_divergence": first_divergence,
        "base_reference": base_id,
        "abi": abi,
    }
