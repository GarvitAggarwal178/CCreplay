"""Reference-model line coverage per trace (SPEC.md section 4.2, label U).

Replays the UNMUTATED reference model in Mode A (recorded private PRE, the
same inputs the kill measurement uses) over every event of every C6 trace,
and records which source lines of the model file execute during
`transition()` calls. Module-level code is not traced (it runs at import, so
module-level mutants are never labelled U -- see SPEC.md 4.2).

Usage: python results/c6_mutation_campaign/coverage_ref.py   # writes coverage.json
"""
import importlib
import json
import sys
import time

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from experiments.c6_mutation_campaign.complete import c6_common as common
from ccreplay import controllers as controllers_mod

OUT = common.HERE / "coverage.json"


def line_coverage(controller, rel_path):
    mod = importlib.import_module(controllers_mod.BUILTINS[controller]["module"])
    target = mod.__file__
    events, _ = common.load_events(rel_path)
    pre_fn = common.base_pre_fn(controller)
    lines = set()

    def local(frame, event, arg):
        if event == "line":
            lines.add(frame.f_lineno)
        return local

    def glob(frame, event, arg):
        if frame.f_code.co_filename == target:
            return local
        return None

    sys.settrace(glob)
    try:
        for e in events:
            mod.transition(e, pre_fn(e) if pre_fn else None)
    finally:
        sys.settrace(None)
    return sorted(lines), len(events)


def main():
    out = {}
    for controller in ("reno", "cubic"):
        out[controller] = {}
        for rel_path, role in common.traces_for(controller):
            t0 = time.monotonic()
            lines, n = line_coverage(controller, rel_path)
            out[controller][rel_path] = {"role": role, "n_events": n, "lines": lines}
            print(f"{controller} {rel_path}: {len(lines)} lines over {n} events "
                  f"({time.monotonic() - t0:.1f}s)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
