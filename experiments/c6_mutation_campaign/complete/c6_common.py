"""Shared C6 configuration: trace sets, the R3B exact prefixes, and the
event loading used by the coverage and out-of-schema passes.

Event loading reuses the engine's own helpers (user.ccreplay_diff), exactly
as ccreplay.diff.all_decisions_core does: parse, select the dominant
connection, sort by seq.
"""
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
import os
HERE = pathlib.Path(os.environ.get("CCREPLAY_C6_OUTPUT", str(ROOT / "runtime/experiments/c6_complete")))
for _p in (str(ROOT), str(pathlib.Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ccreplay  # noqa: E402,F401  (adds user/ to sys.path)
from ccreplay import controllers as controllers_mod  # noqa: E402
from user.ccreplay_diff import _detect_version_and_parse  # noqa: E402

# SPEC.md section 2.
PRIMARY = {
    "reno": ["raw/r0/rep1.ccr", "raw/r0/rep2.ccr", "raw/r0/rep3.ccr"],
    "cubic": ["raw/cubic_replay/primary/rep1.ccr", "raw/cubic_replay/primary/rep2.ccr",
              "raw/cubic_replay/primary/rep3.ccr"],
}
AUXILIARY = {
    "reno": [],
    "cubic": ["raw/cubic_replay/auxiliary/undo_cwnd/aux1.ccr"],
}
ABI = {"reno": 0, "cubic": 1}

# PREDICTIONS.md S2: number of leading events R3B replays exactly
# (CURRENT_STATE.md section 5). The auxiliary trace's R3B first divergence is
# NONE, and Reno R2 is exact on all r0 traces, so their prefix is the whole trace.
R3B_EXACT_PREFIX = {
    "raw/cubic_replay/primary/rep1.ccr": 51323,
    "raw/cubic_replay/primary/rep2.ccr": 75603,
    "raw/cubic_replay/primary/rep3.ccr": 61729,
}

MODES = ("A", "B")


def traces_for(controller):
    return [(p, "primary") for p in PRIMARY[controller]] + \
           [(p, "auxiliary") for p in AUXILIARY[controller]]


def load_events(rel_path):
    """(dominant_events sorted by seq, CALLBACK_NAMES) -- same steps as
    all_decisions_core."""
    _, events, select_dominant_connection, callback_names = \
        _detect_version_and_parse(str(ROOT / rel_path))
    _, dominant, _ = select_dominant_connection(events)
    dominant.sort(key=lambda e: e["seq"])
    return dominant, callback_names


def base_pre_fn(controller):
    """The recorded-private-PRE extractor Mode A uses (None for Reno)."""
    base = importlib.import_module(controllers_mod.BUILTINS[controller]["module"])
    return getattr(base, "private_pre_from_event", None)
