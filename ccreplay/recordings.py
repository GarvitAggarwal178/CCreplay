"""Atomic unique recording imports and provenance registry."""
import json
from pathlib import Path
import tempfile
import threading
import uuid
from ccreplay.storage import ROOT, RUNTIME, atomic_json, digest, utc
from user.ccreplay_diff import _detect_version_and_parse

REGISTRY = RUNTIME / 'recordings.json'
_lock = threading.Lock()
MAX_UPLOAD = 256 * 1024 * 1024


def entries():
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}


def inspect(path, meta_path=None):
    hdr, events, select, names = _detect_version_and_parse(str(path))
    _, dominant, _ = select(events)
    status = 'unknown'
    validation = None
    if meta_path:
        module = __import__({0:'user.ccr_trace',1:'user.ccr_trace_v1',2:'user.ccr_trace_v2'}[hdr.trace_version],fromlist=['validate_run'])
        validate = getattr(module, 'validate_run', None) or getattr(module, 'validate_run_v1', None) or getattr(module,'validate_run_v2',None)
        validation = validate(str(path),str(meta_path))
        status = 'pass' if validation['pass'] else 'failed'
        if status == 'failed':
            raise ValueError('Recording sidecar/integrity check failed: ' + json.dumps(validation['checks']))
    return {'abi':hdr.trace_version,'n_events':len(dominant),'integrity':status,'replayable':bool(dominant),
            'validation':validation,'sha256':digest(path),'created_at':utc(),
            'callback_counts':{names[k]:sum(e['callback_id']==k for e in dominant) for k in names}}


def register(path, meta_path=None, origin='upload', run_id=None, name=None):
    path=Path(path);meta_path=Path(meta_path) if meta_path else None
    if path.stat().st_size > MAX_UPLOAD:
        raise ValueError('Recording exceeds 256 MiB limit')
    info=inspect(path,meta_path)
    rid='recording_'+uuid.uuid4().hex
    dest=RUNTIME/'lab'/rid if origin=='lab' else ROOT/'uploads'/rid
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent,prefix='.stage-') as stage:
        stage=Path(stage)
        import shutil
        shutil.copyfile(path,stage/'trace.ccr')
        if meta_path:
            shutil.copyfile(meta_path,stage/'trace.meta.json')
        stage.rename(dest)
        # TemporaryDirectory cleanup tolerates the renamed directory.
    relative=str((dest/'trace.ccr').relative_to(ROOT))
    info.update(id=relative.replace('/','__').removesuffix('.ccr'),path=relative,origin=origin,
                run_id=run_id,name=name or path.name)
    with _lock:
        data=entries();data[info['id']]=info;atomic_json(REGISTRY,data)
    return info


def import_bytes(data,metadata=None,name='recording.ccr'):
    if len(data)>MAX_UPLOAD:
        raise ValueError('Recording exceeds 256 MiB limit')
    if metadata is not None:
        parsed=json.loads(metadata)
        if not isinstance(parsed,dict):
            raise ValueError('Metadata must be a JSON object')
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'trace.ccr';path.write_bytes(data)
        mp=Path(tmp)/'trace.meta.json' if metadata is not None else None
        if mp:mp.write_bytes(metadata)
        return register(path,mp,name=name)
