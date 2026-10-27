"""C6 mutant generator (SPEC.md section 3).

Parses a reference model's source with `ast`, applies ONE operator at ONE
site per mutant, and unparses the result. Mutants are built in memory only
(same compile+exec-into-a-fresh-module approach as
ccreplay.controllers.clone_base); no file under user/ is ever written.

Every site is enumerated (nothing is sampled), in a fixed traversal order,
so two runs produce byte-identical output (SPEC.md section 5, control 3).

Usage:
    python results/c6_mutation_campaign/mutate.py            # writes mutants.jsonl
    python results/c6_mutation_campaign/mutate.py --check    # regenerate, compare bytes
"""
import argparse
import ast
import copy
import difflib
import hashlib
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
MUTANTS_PATH = ROOT / "runtime/experiments/c6_complete/mutants.jsonl"

MODEL_SOURCES = {
    "reno": ROOT / "user" / "reno_model.py",
    "cubic": ROOT / "user" / "cubic_model.py",
}

# SPEC.md section 3.2: the oracle and the harness, not the controller.
EXCLUDED_FUNCS = {
    "transition", "pre_from_event", "private_pre_from_event",
    "comparison_fields",
    "u32", "s32", "u64", "fls64",
}
EXCLUDED_MODULE_NAMES = {
    "COMPARISON_FIELDS", "CALLBACK_NAMES", "PRIVATE_FIELDS", "_ALL_PRIV_POST", "_COMMON_POST",
    "NONE_PRIVATE_STATE", "INITIAL_PRIVATE_STATE", "MASK32", "_CBRT_TABLE",
}
EXCLUDED_MODULE_PREFIXES = ("CCR_CB_",)

AOR = {
    ast.Add: ast.Sub, ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
    ast.LShift: ast.RShift, ast.RShift: ast.LShift,
    ast.BitAnd: ast.BitOr, ast.BitOr: ast.BitAnd,
}
ROR = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}
OP_SYMBOL = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.FloorDiv: "//", ast.LShift: "<<",
    ast.RShift: ">>", ast.BitAnd: "&", ast.BitOr: "|", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=", ast.And: "and", ast.Or: "or",
}
MASK_FUNCS = ("u32", "s32", "u64")


def _is_excluded_module_assign(stmt):
    if not isinstance(stmt, ast.Assign):
        return True  # module docstring, imports, etc.: nothing to mutate
    names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
    return not names or any(
        n in EXCLUDED_MODULE_NAMES or n.startswith(EXCLUDED_MODULE_PREFIXES) for n in names)


def _scopes(tree):
    """Yield (function_name, top-level statement) for every mutable scope,
    in source order. function_name is "<module>" for module-level assigns."""
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef):
            if stmt.name not in EXCLUDED_FUNCS:
                yield stmt.name, stmt
        elif not _is_excluded_module_assign(stmt):
            yield "<module>", stmt


def _walk(node):
    """Deterministic pre-order walk yielding (node, parent, field, index)."""
    stack = [(node, None, None, None)]
    while stack:
        cur, parent, field, idx = stack.pop()
        yield cur, parent, field, idx
        children = []
        for fname, value in ast.iter_fields(cur):
            if isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, ast.AST):
                        children.append((item, cur, fname, i))
            elif isinstance(value, ast.AST):
                children.append((value, cur, fname, None))
        stack.extend(reversed(children))


def _is_docstring(node, parent, field, idx):
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str) and field == "body" and idx == 0)


def _sites(scope_name, scope_node):
    """Yield (site_index, operator, variant, description, node) for one scope.
    site_index is the node's position in _walk order within the scope; it is
    how the same node is found again in a deep copy of the tree."""
    for site_index, (node, parent, field, idx) in enumerate(_walk(scope_node)):
        if node is scope_node and isinstance(node, ast.FunctionDef):
            continue
        if _is_docstring(node, parent, field, idx):
            continue
        if isinstance(node, (ast.BinOp, ast.AugAssign)) and type(node.op) in AOR:
            new = AOR[type(node.op)]
            yield site_index, "AOR", 0, f"{OP_SYMBOL[type(node.op)]} -> {OP_SYMBOL[new]}", node
        if isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                if type(op) in ROR:
                    new = ROR[type(op)]
                    yield site_index, "ROR", k, f"{OP_SYMBOL[type(op)]} -> {OP_SYMBOL[new]}", node
        if (isinstance(node, ast.Constant) and type(node.value) is int):
            yield site_index, "CRP", 0, f"{node.value} -> {node.value + 1}", node
            yield site_index, "CRP", 1, f"{node.value} -> {node.value - 1}", node
        if isinstance(node, ast.BoolOp):
            new = ast.Or if isinstance(node.op, ast.And) else ast.And
            yield site_index, "LCR", 0, f"{OP_SYMBOL[type(node.op)]} -> {OP_SYMBOL[new]}", node
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            yield site_index, "NOT", 0, "remove not", node
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("min", "max"):
                new = "max" if node.func.id == "min" else "min"
                yield site_index, "MMS", 0, f"{node.func.id} -> {new}", node
            if node.func.id in MASK_FUNCS and len(node.args) == 1 and not node.keywords:
                yield site_index, "MASK", 0, f"remove {node.func.id}()", node
        if (scope_name != "<module>" and isinstance(node, (ast.Assign, ast.AugAssign))
                and field is not None and idx is not None):
            yield site_index, "SDL", 0, "statement -> pass", node


def _apply(node, parent, field, idx, operator, variant):
    """Mutate `node` (inside a deep-copied tree) in place."""
    if operator == "AOR":
        node.op = AOR[type(node.op)]()
    elif operator == "ROR":
        node.ops[variant] = ROR[type(node.ops[variant])]()
    elif operator == "CRP":
        node.value = node.value + (1 if variant == 0 else -1)
    elif operator == "LCR":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif operator == "NOT":
        _replace(parent, field, idx, node.operand)
    elif operator == "MMS":
        node.func.id = "max" if node.func.id == "min" else "min"
    elif operator == "MASK":
        _replace(parent, field, idx, node.args[0])
    elif operator == "SDL":
        _replace(parent, field, idx, ast.Pass())
    else:
        raise ValueError(operator)


def _replace(parent, field, idx, new):
    if idx is None:
        setattr(parent, field, new)
    else:
        getattr(parent, field)[idx] = new


def _scope_index(tree, scope_node):
    return tree.body.index(scope_node)


def reference_source(controller):
    """The unparsed reference: the baseline every mutant diff is taken
    against, and the identity control's source (SPEC.md section 5)."""
    return ast.unparse(ast.parse(MODEL_SOURCES[controller].read_text()))


def _sha(src):
    return hashlib.sha256(src.encode()).hexdigest()


def generate(controller):
    """Return the full, ordered list of mutant records for one controller,
    including stillborn and duplicate rows (so counts are reproducible).
    Each record carries its mutant source under "source" (not written to
    mutants.jsonl -- regenerable, verified by sha256)."""
    path = MODEL_SOURCES[controller]
    original = ast.parse(path.read_text())
    ref_src = ast.unparse(original)
    ref_lines = ref_src.splitlines(keepends=True)
    seen = {_sha(ref_src): "reference"}
    out = []
    for scope_name, scope_node in _scopes(original):
        body_index = _scope_index(original, scope_node)
        for site_index, operator, variant, desc, node in _sites(scope_name, scope_node):
            fn_slug = "module" if scope_name == "<module>" else scope_name
            # S<site_index> is needed: nested expressions such as `(a + b) >> c`
            # start at the same line and column, so L/C alone are not unique.
            mid = (f"{controller}-{operator}-{fn_slug}-L{node.lineno}-C{node.col_offset}"
                   f"-S{site_index}-{variant}")
            tree = copy.deepcopy(original)
            target = list(_walk(tree.body[body_index]))[site_index]
            _apply(*target, operator, variant)
            ast.fix_missing_locations(tree)
            rec = {
                "id": mid, "controller": controller, "operator": operator,
                "function": scope_name, "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "col": node.col_offset, "variant": variant, "description": desc,
            }
            try:
                src = ast.unparse(tree)
                compile(src, mid, "exec")
            except Exception as exc:  # noqa: BLE001 -- any failure is "stillborn"
                rec.update(status="stillborn", reason=f"{type(exc).__name__}: {exc}")
                out.append(rec)
                continue
            sha = _sha(src)
            if sha in seen:
                rec.update(status="duplicate", duplicate_of=seen[sha], sha256=sha)
                out.append(rec)
                continue
            seen[sha] = mid
            diff = "".join(difflib.unified_diff(
                ref_lines, src.splitlines(keepends=True), "reference", mid, n=1))
            rec.update(status="live", sha256=sha, diff=diff, source=src)
            out.append(rec)
    return out


def build_module(name, source, controller):
    """In-memory module from source, same approach as
    ccreplay.controllers.clone_base. Raises if module-level code fails."""
    m = types.ModuleType(name)
    m.__file__ = str(MODEL_SOURCES[controller])
    exec(compile(source, f"<{name}>", "exec"), m.__dict__)
    return m


def jsonl_bytes(controllers=("reno", "cubic")):
    lines = []
    for c in controllers:
        for rec in generate(c):
            row = {k: v for k, v in rec.items() if k != "source"}
            lines.append(json.dumps(row, sort_keys=True))
    return ("\n".join(lines) + "\n").encode()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="regenerate and compare byte-for-byte against mutants.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=MUTANTS_PATH)
    args = ap.parse_args(argv)
    destination = args.out
    data = jsonl_bytes()
    if args.check:
        same = destination.exists() and destination.read_bytes() == data
        print("deterministic: identical" if same else "MISMATCH vs mutants.jsonl")
        return 0 if same else 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    rows = [json.loads(x) for x in data.decode().splitlines()]
    for c in MODEL_SOURCES:
        rs = [r for r in rows if r["controller"] == c]
        by = {}
        for r in rs:
            by[r["status"]] = by.get(r["status"], 0) + 1
        print(f"{c}: {len(rs)} generated, {by}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
