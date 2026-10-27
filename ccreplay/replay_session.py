"""Persist actual full computed streams for bounded, exact event inspection."""
import ast
from collections import Counter
from copy import deepcopy
import json
import math
import sqlite3
import uuid
import zlib

from ccreplay import controllers, revisions, traces
from ccreplay.storage import RUNTIME, atomic_json, digest, json_safe, safe_id, utc
from ccreplay.transitions import iterate
from user.ccreplay_diff import _detect_version_and_parse

SESSIONS = RUNTIME / 'replay'


def folder(sid):
    return SESSIONS / safe_id(sid)


def read(sid):
    return json.loads((folder(sid) / 'session.json').read_text())


def update(sid, **values):
    meta = read(sid)
    meta.update(values)
    atomic_json(folder(sid) / 'session.json', meta)
    return meta


def create(trace_id, reference, candidate, mode='B', parent_run_id=None, original=None):
    if mode not in ('A', 'B'):
        raise ValueError('Mode must be A or B')
    if original:
        config = deepcopy(original['config'])
        for side in ('reference', 'candidate'):
            revisions.verify(config[side])
    else:
        info = traces.get_trace(trace_id)
        if not info['n_dominant_events']:
            raise ValueError('Empty recordings are not replayable')
        config = {'trace_id': trace_id, 'trace_path': str(traces.resolve_id(trace_id)),
                  'trace_sha256': info['sha256'], 'abi': info['abi'], 'mode': mode,
                  'reference': revisions.snapshot(reference), 'candidate': revisions.snapshot(candidate)}
    if any(config[k]['abi'] != config['abi'] for k in ('reference', 'candidate')):
        raise ValueError('Recording and both controllers must have the same Replay ABI')
    if digest(config['trace_path']) != config['trace_sha256']:
        raise ValueError('Saved recording hash changed; refusing to substitute different bytes')
    sid = uuid.uuid4().hex
    folder(sid).mkdir(parents=True, exist_ok=False)
    atomic_json(folder(sid) / 'session.json', {'id': sid, 'created_at': utc(), 'parent_run_id': parent_run_id,
                'status': 'queued', 'config': config, 'progress': {'processed': 0, 'total': None, 'phase': 'queued'}})
    return sid


def _db(sid):
    con = sqlite3.connect(folder(sid) / 'events.sqlite')
    con.execute('PRAGMA journal_mode=WAL')
    return con


def accumulate_profile(profile, callback, reference, candidate, fields, diffs):
    """Bounded presentation aggregates, using only declared comparable outputs."""
    types = profile.setdefault('types', {'private_only': 0, 'return_value': 0, 'computed_post': 0})
    if diffs:
        if all(f.startswith('priv_') for f in diffs):
            types['private_only'] += 1
        if 'result' in diffs and callback in ('ssthresh', 'undo_cwnd'):
            types['return_value'] += 1
        if any(f.startswith('post_') for f in diffs):
            types['computed_post'] += 1
    metrics = profile.setdefault('metrics', {})
    for field in ('result', 'post_snd_cwnd'):
        if field not in fields or (field == 'result' and callback not in ('ssthresh', 'undo_cwnd')):
            continue
        a, b = reference.get(field), candidate.get(field)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (a, b)):
            continue
        key = callback + '.' + field
        m = metrics.setdefault(key, {'count': 0, 'changed': 0, 'min_delta': None, 'max_delta': None,
                                     'mean_absolute_delta': 0, 'max_absolute_delta': 0, 'unit': 'segments'})
        delta = b - a
        m['count'] += 1
        m['changed'] += int(delta != 0)
        m['min_delta'] = delta if m['min_delta'] is None else min(m['min_delta'], delta)
        m['max_delta'] = delta if m['max_delta'] is None else max(m['max_delta'], delta)
        m['mean_absolute_delta'] += (abs(delta) - m['mean_absolute_delta']) / m['count']
        m['max_absolute_delta'] = max(m['max_absolute_delta'], abs(delta))


def run(sid):
    meta = read(sid)
    cfg = meta['config']
    if digest(cfg['trace_path']) != cfg['trace_sha256']:
        raise ValueError('Recording hash changed since submission')
    ref, cand = revisions.load(cfg['reference']), revisions.load(cfg['candidate'])
    trusted = controllers.load_controller({0: 'reno', 1: 'cubic', 2: 'covegas'}[cfg['abi']])
    _, events, select, names = _detect_version_and_parse(cfg['trace_path'])
    _, events, _ = select(events)
    events.sort(key=lambda e: e['seq'])
    if not events:
        raise ValueError('No dominant events to replay')
    con = _db(sid)
    con.execute('CREATE TABLE events (idx INTEGER PRIMARY KEY, seq TEXT, callback TEXT, t REAL, differs INTEGER, cascaded INTEGER, ref_cwnd INTEGER, cand_cwnd INTEGER, ref_result INTEGER, cand_result INTEGER, detail BLOB)')
    con.execute('CREATE INDEX by_seq ON events(seq)')
    con.execute('CREATE INDEX by_difference ON events(differs,idx)')
    first = None
    counts, differences = Counter(), Counter()
    profile = {}
    update(sid, status='running', started_at=utc())
    try:
        for i, e, rc, cc, rp, cp, rn, cn, fields, diffs, cascade in iterate(events, ref, cand, trusted, cfg['mode']):
            if (folder(sid) / 'cancel').exists():
                raise InterruptedError('Cancelled by owner')
            cb = names.get(e['callback_id'], str(e['callback_id']))
            counts[cb] += 1
            accumulate_profile(profile, cb, rc, cc, fields, diffs)
            if diffs:
                differences[cb] += 1
                if first is None:
                    first = {'event_index': i, 'seq': str(e['seq']), 'callback': cb, 'fields': diffs}
            row = {'index': i, 'seq': str(e['seq']), 'callback': cb, 'fields': fields, 'diff_fields': diffs,
                   'cascaded': cascade, 'reference': {'computed': rc, 'private_pre': rp, 'private_post': rn},
                   'candidate': {'computed': cc, 'private_pre': cp, 'private_post': cn}}
            con.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (i, str(e['seq']), cb, (e['ts_ns'] - events[0]['ts_ns']) / 1e9, bool(diffs), cascade,
                         rc.get('post_snd_cwnd'), cc.get('post_snd_cwnd'),
                         rc.get('result') if cb in ('ssthresh','undo_cwnd') else None,
                         cc.get('result') if cb in ('ssthresh','undo_cwnd') else None,
                         zlib.compress(json.dumps(row, separators=(',', ':')).encode())))
            if i % 1000 == 0:
                con.commit()
                update(sid, progress={'processed': i + 1, 'total': len(events), 'phase': 'computing'})
        con.commit()
    finally:
        con.close()
    summary = {'n_events': len(events), 'processed': len(events), 'n_disagree': sum(differences.values()),
               'first_difference': first, 'matched_prefix': first['event_index'] if first else len(events),
               'callback_counts': dict(counts), 'differences_by_callback': dict(differences),
               'result': 'DIVERGENCE' if first else 'NO DIVERGENCE',
               'comparison_profile_v1': profile}
    # Independent authoritative first-diff cross-check for stateful sessions.
    if cfg['mode'] == 'B':
        from user.ccreplay_diff import diff_trace
        oracle = diff_trace(cfg['trace_path'], None, revisions.load(cfg['reference']), revisions.load(cfg['candidate']))
        actual = oracle['divergence']['first_divergent_event']['event_index'] if oracle['divergence'] else None
        if actual != (first['event_index'] if first else None):
            raise ValueError('Session first difference disagrees with authoritative diff_trace')
        summary['first_diff_cross_check'] = True
    update(sid, status='done', finished_at=utc(), summary=summary,
           progress={'processed': len(events), 'total': len(events), 'phase': 'complete'})
    return summary


def event_rows(sid, offset=0, limit=100, callback=None, differences_only=False, direction='after', anchor=None):
    if offset < 0 or not 1 <= limit <= 500:
        raise ValueError('offset >= 0 and limit between 1 and 500 required')
    where, args = [], []
    if callback:
        where.append('callback=?'); args.append(callback)
    if differences_only:
        where.append('differs=1')
    if anchor is not None:
        where.append('idx' + ('<?' if direction == 'before' else '>?')); args.append(anchor)
    clause = ' WHERE ' + ' AND '.join(where) if where else ''
    with _db(sid) as con:
        total = con.execute('SELECT COUNT(*) FROM events' + clause, args).fetchone()[0]
        rows = con.execute('SELECT idx,seq,callback,t,differs,cascaded FROM events' + clause +
                           (' ORDER BY idx DESC' if direction == 'before' else ' ORDER BY idx') + ' LIMIT ? OFFSET ?', args+[limit, offset]).fetchall()
    return {'total': total, 'events': [dict(zip(['index','seq','callback','t_s','differs','cascaded'], r)) for r in rows]}


def detail(sid, index):
    with _db(sid) as con:
        row = con.execute('SELECT detail FROM events WHERE idx=?', (index,)).fetchone()
    if not row:
        raise KeyError('Event index out of range')
    value = json.loads(zlib.decompress(row[0]))
    cfg = read(sid)['config']
    _, _, events, _, _ = traces._full_cached(__import__('pathlib').Path(cfg['trace_path']))
    value['recorded'] = traces._json_safe_event(events[index])
    value['source'] = {k: source_context(cfg[k], value['callback']) for k in ('reference','candidate')}
    e = events[index]
    value['clock'] = {k: ('stable' if e[k] == e.get(k.replace('_before', '_after')) else 'ambiguous')
                      for k in e if k.startswith('clock_') and k.endswith('_before')}
    return json_safe(value)


def source_context(capsule, callback):
    source = capsule['source']
    if capsule.get('params'):
        base = capsule['params']['base']
        source = capsule["source"]
    try:
        nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        relevant = [n for n in nodes if callback in n.name or n.name == 'transition' or n.name.endswith('_transition')]
        if not relevant:
            return {'source': source, 'function': 'custom module', 'start_line': 1, 'end_line': len(source.splitlines()), 'parameters': capsule.get('params')}
        n = next((n for n in relevant if callback in n.name), relevant[0])
        return {'source': '\n'.join(source.splitlines()[n.lineno-1:n.end_lineno]), 'function': n.name,
                'start_line': n.lineno, 'end_line': n.end_lineno, 'parameters': capsule.get('params')}
    except SyntaxError:
        return {'source': source, 'function': 'source', 'start_line': 1, 'end_line': len(source.splitlines())}


def timeline(sid, start=0, end=None, max_points=1000, selected=None):
    if start < 0 or not 2 <= max_points <= 4000:
        raise ValueError('Invalid timeline bounds')
    meta = read(sid)
    end = end if end is not None else meta.get('progress',{}).get('processed',0)
    if end < start:
        raise ValueError('end must be >= start')
    stride = max(1, (end - start) // max_points)
    with _db(sid) as con:
        # Exact changed points can exceed max_points: never silently discard a difference.
        rows = con.execute('SELECT idx,seq,callback,t,differs,ref_cwnd,cand_cwnd,ref_result,cand_result FROM events WHERE idx>=? AND idx<? AND (idx%?=0 OR differs=1 OR idx=? OR idx=? OR idx=? ) ORDER BY idx',
                           (start,end,stride,selected if selected is not None else -1,start,end-1)).fetchall()
    if len(rows) > max_points * 2:
        # Dense overview is a truthful count by bin; exact selected neighborhood uses events API.
        with _db(sid) as con:
            bins = con.execute('SELECT idx / ?,COUNT(*),SUM(differs) FROM events WHERE idx>=? AND idx<? GROUP BY idx / ?', (stride,start,end,stride)).fetchall()
        return {'kind':'bins','bins':[{'start':b[0]*stride,'count':b[1],'differences':b[2]} for b in bins],
                'selected': event_rows(sid, max(0,(selected or start)-5),11)['events']}
    return {'kind':'points','points':[dict(zip(['index','seq','callback','t_s','differs','reference_cwnd','candidate_cwnd','reference_result','candidate_result'],r)) for r in rows]}


def checkpoint(sid, interval):
    if not 1 <= interval <= 10000:
        raise ValueError('interval must be between 1 and 10000')
    meta = read(sid); cfg = meta['config']
    if cfg['mode'] != 'B':
        raise ValueError('Checkpoint reproduction applies to stateful Mode B')
    first = meta['summary']['first_difference']
    if first is None:
        return {'result':'NO DIVERGENCE','reproduced_same_divergence':None}
    D = first['event_index']; K = (D//interval)*interval
    row = detail(sid,K); expected = detail(sid,D)
    cfg = meta['config']
    if digest(cfg['trace_path']) != cfg['trace_sha256']:
        raise ValueError('Recording hash changed')
    from user.ccreplay_checkpoint import CHECKPOINT_SCHEMA_VERSION, replay_suffix_from_checkpoint, suffix_length
    from user.ccreplay_diff import _detect_version_and_parse
    _,events,select,_ = _detect_version_and_parse(cfg['trace_path']);_,events,_=select(events);events.sort(key=lambda e:e['seq'])
    # Schema 2: private state immediately BEFORE event K; resume executes K..D inclusive.
    ck = {'schema_version':CHECKPOINT_SCHEMA_VERSION,'next_event_index':K,'next_seq':int(row['seq']),
          'ref_state':deepcopy(row['reference']['private_pre']),'cand_state':deepcopy(row['candidate']['private_pre'])}
    ref,cand = revisions.load(cfg['reference']),revisions.load(cfg['candidate'])
    resumed = replay_suffix_from_checkpoint(ck,events,ref,cand,D)
    exact = (resumed is not None and resumed['event_index']==D
             and json_safe(resumed['ref_computed'])==expected['reference']['computed']
             and json_safe(resumed['cand_computed'])==expected['candidate']['computed']
             and json_safe(resumed['ref_post_state'])==expected['reference']['private_post']
             and json_safe(resumed['cand_post_state'])==expected['candidate']['private_post'])
    result = {'result':'DIVERGENCE','nearest_checkpoint':{'next_event_index':K,'next_seq':row['seq']},'suffix_length':suffix_length(ck,D),
              'first_divergence_full_run':first,'reproduced_same_divergence':exact,'values_and_private_state_verified':exact}
    atomic_json(folder(sid)/'checkpoint.json',result)
    return result
