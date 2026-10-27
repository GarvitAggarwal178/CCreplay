"""Normal-user API for the owner-started Unix-socket lab agent."""
import base64
import json
from pathlib import Path
import tempfile
import threading
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import JSONResponse,FileResponse
from pydantic import BaseModel,Field
from ccreplay import lab_client,workloads,recordings
from ccreplay.lab_protocol import Scenario
from ccreplay.lab_runner import preflight,TERMINAL
from ccreplay.storage import RUNTIME,atomic_json,safe_id

router=APIRouter(prefix='/api')
RUNS=RUNTIME/'lab_runs'
_registration_lock=threading.Lock()


def local_path(rid):return RUNS/safe_id(rid)


def bridge(operation,**kwargs):
    try:return lab_client.call(operation,**kwargs)
    except ConnectionError as exc:raise HTTPException(503,str(exc))
    except (ValueError,KeyError) as exc:raise HTTPException(400,str(exc))


def persist(meta):
    path=local_path(meta['id'])/'manifest.json'
    old=json.loads(path.read_text()) if path.exists() else {}
    if old.get('recording_id'):meta['recording_id']=old['recording_id']
    atomic_json(path,meta);return meta


def download(rid,artifact,dest):
    offset=0
    with Path(dest).open('wb') as f:
        while True:
            chunk=bridge('artifact',run_id=rid,artifact=artifact,offset=offset)
            data=base64.b64decode(chunk['data']);f.write(data);offset+=len(data)
            if offset>=chunk['total_bytes']:break
            if not data:raise ValueError('Agent artifact stream ended early')


def capture_ready(meta):
    rid=meta['id']
    if meta.get('recording',{}):
        if meta['status']=='completed' and meta['recording'].get('replayable') and not meta.get('recording_id'):
            with _registration_lock:
                cached=local_path(rid)/'manifest.json'
                if cached.exists():
                    previous=json.loads(cached.read_text())
                    if previous.get('recording_id'):
                        meta['recording_id']=previous['recording_id'];return meta
                with tempfile.TemporaryDirectory() as tmp:
                    trace=Path(tmp)/'trace.ccr';sidecar=Path(tmp)/'trace.meta.json'
                    download(rid,'trace.ccr',trace);download(rid,'trace.meta.json',sidecar)
                    entry=recordings.register(trace,sidecar,origin='lab',run_id=rid,name=f"{meta['config']['controller']} · network run {rid[:8]}")
                meta['recording_id']=entry['id']
                persist(meta)
    return meta


@router.get('/lab/capabilities')
def capabilities():
    info=preflight()
    try:
        result=lab_client.call('capabilities');result['api_uid']=__import__('os').getuid();return result
    except Exception as exc:
        info.update(agent_connected=False,can_run_lab=False,reason=str(exc),api_uid=__import__('os').getuid(),result_files=[])
        return info


@router.post('/lab/runs')
def start(config:Scenario):
    try:workload=workloads.get(config.workload_revision)
    except (FileNotFoundError,ValueError):raise HTTPException(400,'Unknown workload revision')
    return persist(bridge('start',config=config,workload=workload))


@router.get('/lab/runs')
def list_runs():
    values={}
    for p in RUNS.glob('*/manifest.json'):
        try:value=json.loads(p.read_text());values[value['id']]=value
        except (ValueError,OSError):continue
    try:
        for meta in lab_client.call('list'):
            values[meta['id']]=persist(meta)
    except Exception:pass
    return sorted(values.values(),key=lambda v:v['created_at'],reverse=True)[:100]


@router.get('/lab/runs/{rid}')
def get_run(rid:str):
    try:
        meta=persist(bridge('status',run_id=rid))
        meta=capture_ready(meta)
        marker=local_path(rid)/'streams_complete'
        if meta['status'] in TERMINAL and meta.get('cleanup') and not marker.exists():
            complete=True
            for kind in ('samples','log'):
                cursor=0
                while True:
                    result=cursor_data(rid,kind,cursor,500)
                    if result.get('agent_unavailable'):
                        complete=False;break
                    if not result['items']:break
                    cursor=result['cursor']
            if complete:marker.touch()
        return meta
    except HTTPException as exc:
        path=local_path(rid)/'manifest.json'
        if not path.exists():raise exc
        meta=json.loads(path.read_text())
        if meta['status'] not in TERMINAL:
            meta.update(status='interrupted',error='Agent unavailable; cannot confirm cleanup until it reconnects',agent_unavailable=True)
        return meta


def cursor_data(rid,kind,after,limit):
    path=local_path(rid)/(kind+'.jsonl')
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        result=lab_client.call(kind,run_id=rid,after=after,limit=limit)
        if result['items']:
            # Merge by real cursor; repeated polling never fabricates or duplicates samples.
            cached={}
            if path.exists():
                for line in path.read_text().splitlines():
                    try:v=json.loads(line);cached[v['cursor']]=v
                    except ValueError:pass
            cached.update({v['cursor']:v for v in result['items']})
            path.write_text(''.join(json.dumps(cached[k])+'\n' for k in sorted(cached)))
        return result
    except Exception:
        values=[]
        if path.exists():
            values=[json.loads(line) for line in path.read_text().splitlines() if line]
        selected=[v for v in values if v['cursor']>after][:limit]
        return {'items':selected,'cursor':selected[-1]['cursor'] if selected else after,'agent_unavailable':True}


@router.get('/lab/runs/{rid}/samples')
def samples(rid:str,after:int=Query(0,ge=0),limit:int=Query(500,ge=1,le=500)):
    return cursor_data(rid,'samples',after,limit)


@router.get('/lab/runs/{rid}/log')
def log(rid:str,after:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=500)):
    return cursor_data(rid,'log',after,limit)


@router.post('/lab/runs/{rid}/stop')
def stop(rid:str):return persist(bridge('stop',run_id=rid))


@router.post('/lab/runs/{rid}/cancel')
def cancel(rid:str):return persist(bridge('cancel',run_id=rid))


@router.get('/lab/compare')
def compare(left:str,right:str):
    a,b=get_run(left),get_run(right)
    if left==right or any(v['status']!='completed' or v['config'].get('capture') for v in (a,b)):
        raise HTTPException(400,'Choose two distinct completed native runs with capture disabled')
    if any(v['instrumentation']!='native-uninstrumented' for v in (a,b)):
        raise HTTPException(400,'Native comparisons require two separately executed uninstrumented runs')
    differences={k:{'left':a['config'].get(k),'right':b['config'].get(k)} for k in a['config'] if a['config'].get(k)!=b['config'].get(k)}
    return {'left':a,'right':b,'configuration_differences':differences,
            'left_samples':cursor_data(left,'samples',0,500)['items'],'right_samples':cursor_data(right,'samples',0,500)['items'],
            'scope':'Descriptive measurements from these executions; no universal winner or significance claim'}


@router.get('/lab/runs/{rid}/export')
def export(rid:str):
    meta=get_run(rid)
    return JSONResponse(meta,headers={'Content-Disposition':f'attachment; filename="network-{rid}.json"'})


@router.get('/lab/runs/{rid}/artifact/{name}')
def artifact(rid:str,name:str):
    if name not in ('trace.ccr','trace.meta.json','receiver.json','manifest.json','workload.py'):
        raise HTTPException(404,'Unknown artifact')
    if name=='manifest.json':return JSONResponse(get_run(rid))
    target=local_path(rid)/name
    if not target.exists():download(rid,name,target)
    return FileResponse(target,filename=name)


class WorkloadRequest(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    source:str=Field(min_length=1,max_length=131072)


@router.get('/workloads')
def list_workloads():return workloads.list_workloads()


@router.post('/workloads')
def save_workload(req:WorkloadRequest):
    try:return workloads.save(req.name,req.source)
    except (ValueError,SyntaxError) as exc:raise HTTPException(400,str(exc))


@router.get('/workloads/{revision}')
def get_workload(revision:str):
    try:return workloads.get(revision)
    except (FileNotFoundError,ValueError):raise HTTPException(404,'Unknown workload revision')
