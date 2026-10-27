#!/usr/bin/env python3
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ccreplay.lab_runner import preflight
from ccreplay.lab_client import call
info=preflight()
try:info['agent']=call('capabilities')
except Exception as exc:info['agent']={'connected':False,'reason':str(exc)}
if info['uid']==0:info['normal_user_launch']='Root session detected: configure a normal WSL login user and use a checkout under its home; run Studio without sudo and the agent with sudo.'
print(json.dumps(info,indent=2))
