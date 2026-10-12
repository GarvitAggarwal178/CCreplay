"""CCReplay Studio engine wrappers around the existing `user/*.py` replay engine.

Does not modify bpf/, user/*.py, tests/, raw/, or any verdict text (see
STUDIO_AUTORUN.md Never-do list). This package only wraps and exposes the
existing engine for the web app.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "user")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
