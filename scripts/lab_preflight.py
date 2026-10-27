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
if info['uid']==0:info['normal_user_launch']='Root development startup can use CCREPLAY_ALLOW_ROOT=1 bash run_studio.sh. This does not enable lab-agent access: the agent still requires a matching non-root workload owner and API peer.'
print(json.dumps(info,indent=2))
