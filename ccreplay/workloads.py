"""Immutable trusted-local traffic source revisions."""
import hashlib
import json
import uuid
from ccreplay.storage import ROOT,RUNTIME,atomic_json,safe_id,utc

DIRECTORY=RUNTIME/'workloads'


def get(revision):
    if revision=='continuous':
        return {'id':'continuous','name':'Continuous TCP transfer','kind':'iperf3','source':None,'sha256':None}
    if revision=='bursty_template':
        source=(ROOT/'examples/workloads/bursty_sender.py').read_text()
        return {'id':'bursty_template','name':'Bursty TCP template','kind':'script','source':source,
                'sha256':hashlib.sha256(source.encode()).hexdigest()}
    return json.loads((DIRECTORY/(safe_id(revision)+'.json')).read_text())


def save(name,source):
    if not name.strip() or len(name)>100:raise ValueError('Workload name must contain 1–100 characters')
    if not source.strip() or len(source.encode())>131072:raise ValueError('Workload source must contain 1–131072 bytes')
    compile(source,'workload-draft','exec')
    rid=uuid.uuid4().hex
    value={'id':rid,'name':name,'kind':'script','source':source,'sha256':hashlib.sha256(source.encode()).hexdigest(),'created_at':utc()}
    atomic_json(DIRECTORY/(rid+'.json'),value);return value


def list_workloads():
    return [get('continuous'),get('bursty_template')]+[json.loads(p.read_text()) for p in sorted(DIRECTORY.glob('*.json'))]
