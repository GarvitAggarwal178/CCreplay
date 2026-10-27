"""CLI dataset-scope reporting; no replay or comparison logic."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def validation_scope(arguments, family):
    missing_inputs = [path for path in arguments if not Path(path).is_file()]
    if missing_inputs:
        raise SystemExit('Missing requested input(s): ' + ', '.join(missing_inputs) +
                         '. Restore exact archived members; see docs/PROVENANCE.md '
                         'and docs/EVIDENCE_INDEX.json.')
    expected = [ROOT / 'raw' / family / f'rep{i}.ccr' for i in (1, 2, 3)]
    missing = [str(path.relative_to(ROOT)) for path in expected
               if not path.is_file() or not path.with_suffix('.meta.json').is_file()]
    selected = {Path(path).resolve() for path in arguments[::2]}
    complete = set(expected).issubset(selected) and not missing
    if not complete:
        print('Selected-recording validation only; this is not the complete '
              'three-repetition historical primary gate. Restore missing inputs '
              'per docs/PROVENANCE.md to reproduce that gate.', file=sys.stderr)
    return {'kind': 'selected_recordings', 'historical_primary_complete': complete,
            'missing_primary_recordings': missing, 'selected_trace_count': len(selected)}
