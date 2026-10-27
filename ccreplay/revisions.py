"""Immutable source capsules. Changed helper dependencies are rejected on rerun."""
import json
import types
from ccreplay import controllers
from ccreplay.storage import ROOT, digest


def dependencies():
    helpers=['controllers.py','transitions.py','replay_session.py','checkpoint.py','diff.py','revisions.py','storage.py']
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / 'user').glob('*.py'))} | {
        'ccreplay/'+name:digest(ROOT/'ccreplay'/name) for name in helpers}


def snapshot(cid):
    abi = controllers.abi_of(cid)
    params = controllers.list_param_variants().get(cid)
    source = controllers.get_source(params["base"] if params else cid)
    return {'capsule_version':2,'id': cid, 'abi': abi, 'source': source, 'params': params,
            'sha256': __import__('hashlib').sha256(source.encode()).hexdigest(),
            'dependencies': dependencies(), 'builtin': cid in controllers.BUILTINS}


def verify(capsule):
    if capsule.get('capsule_version')!=2:
        raise ValueError('Legacy source capsule lacks complete helper identity; start an explicit new comparison with current sources')
    for relative, expected in capsule['dependencies'].items():
        p = ROOT / relative
        if not p.is_file() or digest(p) != expected:
            raise ValueError(f'Saved source dependency changed or missing: {relative}; restore its revision before rerunning')


def load(capsule):
    verify(capsule)
    if capsule['params']:
        entry = capsule['params']
        return controllers.make_param(entry['base'], entry['name'], entry['params'])
    m = types.ModuleType(capsule['id'])
    m.__file__ = f"saved-revision:{capsule['id']}"
    exec(compile(capsule['source'], m.__file__, 'exec'), m.__dict__)
    return m if capsule['builtin'] else controllers.normalize_identity(m.CONTROLLER, capsule['id'])
