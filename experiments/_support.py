"""Storage and required-dataset checks for preserved research CLIs."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def output_directory(campaign, *, existing=False):
    parser = argparse.ArgumentParser(description=f'Preserved {campaign} experiment')
    parser.add_argument('--out', type=Path, required=existing,
                        help='Output directory under runtime/experiments (unique per new run)')
    args = parser.parse_args()
    out = args.out or ROOT / 'runtime/experiments' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + campaign)
    out = out.resolve()
    if not out.is_relative_to((ROOT / 'runtime/experiments').resolve()):
        parser.error('--out must be under runtime/experiments; historical evidence is read-only')
    if existing:
        if not out.is_dir():
            parser.error('--out must name an existing generated run directory')
    else:
        out.mkdir(parents=True, exist_ok=False)
    return out


def require_recordings(paths):
    """Explicit complete campaign inputs, independent of the UI catalog."""
    missing = [str(p) for path in paths for p in
               (ROOT / path, (ROOT / path).with_suffix('.meta.json')) if not p.is_file()]
    if missing:
        raise SystemExit('Required campaign inputs are missing: ' + ', '.join(missing) +
                         '. Restore these exact members from the verified source snapshot; '
                         'see docs/PROVENANCE.md and docs/EVIDENCE_INDEX.json. '
                         'A partial repetition set is not the full campaign.')
    return [path.replace('/', '__').removesuffix('.ccr') for path in paths]
