"""Routes for a local, executable comparison workbench."""
from typing import Literal
import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from backend import jobs
from ccreplay.teaching_workbench import validate_scenario, capture_window, MAX_SOURCE

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples' / 'algorithm_workbench'
router = APIRouter(prefix='/api/algorithm-workbench')

class CompareRequest(BaseModel):
    source_a: str = Field(min_length=1, max_length=MAX_SOURCE)
    source_b: str = Field(min_length=1, max_length=MAX_SOURCE)
    input_kind: Literal['scenario','recording'] = 'scenario'
    execution_mode: Literal['event_local','stateful'] = 'event_local'
    name_a: str = Field(default='Algorithm A', max_length=160)
    name_b: str = Field(default='Algorithm B', max_length=160)
    scenario: dict | None = None
    trace_id: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)

@router.get('/presets')
def presets():
    return {'source_a': (EXAMPLES / 'step_growth.py').read_text(),
            'source_b': (EXAMPLES / 'batch_growth.py').read_text(),
            'scenario': json.loads((EXAMPLES / 'scenario.json').read_text())}

@router.post('/compare')
def compare(request: CompareRequest):
    if os.environ.get('CCREPLAY_DEMO_MODE') == '1':
        raise HTTPException(403, 'Custom algorithm execution requires the local application')
    config = request.model_dump()
    try:
        if any(len(s.encode()) > MAX_SOURCE for s in (request.source_a, request.source_b)):
            raise ValueError('Algorithm source exceeds 100000 bytes')
        if request.input_kind == 'scenario':
            validate_scenario(request.scenario or {})
        elif request.input_kind == 'recording':
            from ccreplay import traces
            if not request.trace_id or traces.get_abi(request.trace_id) != 0:
                raise ValueError('Select an ABI-v0 recording')
            config['recording_snapshot'] = capture_window(config)
        else:
            raise ValueError('Unknown input kind')
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    # Sources and synthetic inputs are captured in the job config. No source is
    # compiled/imported in this API process. The existing worker owns execution.
    return {'id': jobs.create_experiment('algorithm_workbench', config)}


@router.post('/{exp_id}/cancel')
def cancel(exp_id: str):
    saved=jobs.get_experiment(exp_id)
    if not saved or saved['type']!='algorithm_workbench':
        raise HTTPException(404,'Unknown algorithm run')
    jobs.cancel(exp_id)
    return {'id':exp_id,'status':'cancelled'}


@router.get('/template.py')
def template():
    return FileResponse(EXAMPLES/'blank_controller.py', media_type='text/x-python', filename='controller_template.py')
