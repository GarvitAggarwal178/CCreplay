"""Atomic local artifacts; owner data is never overwritten implicitly."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('CCREPLAY_RUNTIME', ROOT / 'runtime'))


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def safe_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value):
        raise ValueError('Invalid artifact ID')
    return value


def json_safe(value):
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, int) and abs(value) > 9007199254740991:
        return str(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value
