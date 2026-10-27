"""Replay session routes; opening a run never launches computation."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import JSONResponse, PlainTextResponse
from backend import jobs
from ccreplay import replay_session as sessions, traces
from ccreplay.storage import json_safe

router = APIRouter(prefix='/api')

class Request(BaseModel):
    trace_id: str
    reference_revision: str
    candidate_revision: str
    mode: str = 'B'

class Checkpoint(BaseModel):
    interval: int = 500


def get(sid):
    try:
        meta = sessions.read(sid)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, 'Unknown replay session')
    job = jobs.get_experiment(meta.get('job_id',''))
    if job and job['status'] in ('error','cancelled','interrupted'):
        meta.update(status=job['status'], error=job.get('error'))
    return meta


def queue(sid):
    jid = jobs.create_experiment('replay', {'session_id':sid})
    sessions.update(sid, job_id=jid)
    return {'id':sid,'status':'queued'}


@router.post('/replay/sessions')
def create(req: Request):
    try:
        return queue(sessions.create(req.trace_id,req.reference_revision,req.candidate_revision,req.mode))
    except (ValueError,KeyError,FileNotFoundError) as exc:
        raise HTTPException(400,str(exc))


@router.get('/replay/sessions')
def list_sessions():
    return [get(p.parent.name) for p in sorted(sessions.SESSIONS.glob('*/session.json'),key=lambda p:p.stat().st_mtime,reverse=True)][:100]


@router.get('/replay/sessions/{sid}')
def detail(sid: str):
    return json_safe(get(sid))


def ready(sid):
    meta = get(sid)
    if meta['status'] != 'done':
        raise HTTPException(409, 'Computed events are available after session completion')
    return meta


@router.get('/replay/sessions/{sid}/events')
def events(sid: str, offset: int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),callback:str|None=None,differences_only:bool=False, direction:str='after',anchor:int|None=None):
    ready(sid)
    return sessions.event_rows(sid,offset,limit,callback,differences_only,direction,anchor)


@router.get('/replay/sessions/{sid}/event/{index}')
def event(sid: str,index:int):
    ready(sid)
    try:
        return sessions.detail(sid,index)
    except KeyError:
        raise HTTPException(404,'Event index out of range')


@router.get('/replay/sessions/{sid}/timeline')
def timeline(sid:str,start:int=Query(0,ge=0),end:int|None=None,max_points:int=Query(1000,ge=2,le=4000),selected:int|None=None):
    ready(sid)
    try:
        return sessions.timeline(sid,start,end,max_points,selected)
    except ValueError as exc:
        raise HTTPException(400,str(exc))


@router.post('/replay/sessions/{sid}/rerun')
def rerun(sid:str):
    meta=get(sid)
    try:
        return queue(sessions.create('', '', '', original=meta,parent_run_id=sid))
    except (ValueError,FileNotFoundError) as exc:
        raise HTTPException(400,str(exc))


@router.post('/replay/sessions/{sid}/cancel')
def cancel(sid:str):
    meta=get(sid)
    (sessions.folder(sid)/'cancel').touch()
    jobs.cancel(meta['job_id'])
    return get(sid)


@router.post('/replay/sessions/{sid}/checkpoint')
def checkpoint(sid:str,req:Checkpoint):
    ready(sid)
    if not 1 <= req.interval <= 10000:
        raise HTTPException(400,'interval must be 1–10000')
    return {'id':jobs.create_experiment('session_checkpoint',{'session_id':sid,'interval':req.interval}),'status':'queued'}


@router.get('/replay/sessions/{sid}/export')
def export(sid:str,format:str='json'):
    meta=get(sid)
    if format=='md':
        return PlainTextResponse('# CCReplay investigation\n\n```json\n'+__import__('json').dumps(meta,indent=2)+'\n```',media_type='text/markdown')
    return JSONResponse(json_safe(meta),headers={'Content-Disposition':f'attachment; filename="replay-{sid}.json"'})


@router.get('/traces/{tid}/event')
def recorded_event(tid:str,seq:str):
    try:
        _,_,events,_,_=traces._full_cached(traces.resolve_id(tid))
        for index,event in enumerate(events):
            if str(event['seq'])==seq:
                return {'index':index,'event':json_safe(event)}
    except KeyError:
        pass
    raise HTTPException(404,'Recorded sequence not found')
