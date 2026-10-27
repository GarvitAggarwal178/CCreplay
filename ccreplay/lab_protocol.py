"""Versioned, bounded protocol shared by normal-user API and privileged agent."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

VERSION = 1
MAX_MESSAGE = 1024 * 1024

class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    controller: Literal['reno','cubic','covegas'] = 'reno'
    capture: bool = False
    duration_s: int = Field(30,ge=2,le=180)
    rate_mbit: int = Field(10,ge=1,le=1000)
    delay_ms: int = Field(20,ge=0,le=500)
    queue_bytes: int = Field(50000,ge=1500,le=10000000)
    loss_percent: float = Field(0.0,ge=0,le=10)
    workload_revision: str = Field('continuous',max_length=160,pattern=r'^[A-Za-z0-9_-]+$')

class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = VERSION
    operation: Literal['capabilities','start','status','list','samples','log','stop','cancel','artifact']
    run_id: str | None = Field(None,max_length=64,pattern=r'^[a-f0-9]+$')
    config: Scenario | None = None
    workload: dict | None = None
    after: int = Field(0,ge=0)
    limit: int = Field(100,ge=1,le=500)
    artifact: Literal['trace.ccr','trace.meta.json','manifest.json','receiver.json','workload.py'] | None = None
    offset: int = Field(0,ge=0)
