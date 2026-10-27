import json
from pathlib import Path
import subprocess
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from ccreplay.lab_metrics import socket_samples,select_data_flow,queue_sample,receiver_summary
from ccreplay.lab_protocol import Message,Scenario
from ccreplay.lab_runner import Run


def test_protocol_has_no_shell_or_executable_path():
    with pytest.raises(ValidationError):Message(operation='shell',command='echo unsafe')
    with pytest.raises(ValidationError):Message(operation='status',run_id='../owner-data')
    with pytest.raises(ValidationError):Scenario(duration_s=0)
    with pytest.raises(ValidationError):Scenario(output_path='/tmp/other')


def test_data_socket_does_not_use_small_iperf_control_connection():
    output='''ESTAB 0 0 10.77.1.1:41000 10.77.2.2:5201
\t cubic rtt:39.2/1.2 cwnd:10 bytes_acked:128
ESTAB 0 0 10.77.1.1:41002 10.77.2.2:5201
\t reno rtt:42.5/1.3 cwnd:26 bytes_acked:45000 bytes_retrans:1448
'''
    flows=socket_samples(output)
    chosen=select_data_flow(flows)
    assert chosen['srtt_ms']==42.5 and chosen['cwnd_segments']==26
    assert chosen['controller']=='reno'
    assert select_data_flow(flows,flows[0]['flow_id'])['bytes_acked']==128
    assert queue_sample([{'kind':'htb','drops':99},{'kind':'bfifo','backlog':500,'drops':2}])=={'queue_backlog_bytes':500,'qdisc_drops':2}
    assert receiver_summary({'error':'interrupted'})['receiver_throughput_bps'] is None


def test_failed_setup_cleans_only_successfully_created_namespaces(tmp_path,monkeypatch):
    monkeypatch.setattr('ccreplay.lab_runner.os.chown', lambda *args: None)
    run=Run(tmp_path,65534,65534,Scenario().model_dump(),{'kind':'iperf3','id':'continuous'})
    executed=[]
    def command(argv,**kwargs):
        executed.append(argv)
        if argv[:3]==['ip','netns','add'] and argv[-1].endswith('r'):
            raise RuntimeError('Injected second namespace creation failure')
        return subprocess.CompletedProcess(argv,0,'','')
    monkeypatch.setattr(run,'command',command)
    run.execute()
    deleted=[argv[-1] for argv in executed if argv[:3]==['ip','netns','delete']]
    assert deleted==['cc'+run.id[:7]+'s']
    assert run.meta['status']=='failed' and run.meta['cleanup']['completed']
    assert not any('ns_h1' in argv for argv in executed)


def test_cancel_before_setup_keeps_failure_evidence_and_no_resources(tmp_path, monkeypatch):
    monkeypatch.setattr('ccreplay.lab_runner.os.chown', lambda *args: None)
    run=Run(tmp_path,65534,65534,Scenario().model_dump(),{'kind':'iperf3','id':'continuous'})
    run.cancel_event.set();run.execute()
    assert run.meta['status']=='cancelled'
    assert run.meta['cleanup']['owned_namespaces']==[]
    assert (run.path/'manifest.json').exists()


def test_recovery_unregisters_only_exact_owned_bpf_identity(monkeypatch):
    from ccreplay import lab_runner
    calls=[]
    expected={'id':201,'name':'ccr_reno','btf_id':177}
    def command(argv,**kwargs):
        calls.append(argv)
        if 'show' in argv:return subprocess.CompletedProcess(argv,0,json.dumps({'type':'struct_ops',**expected}),'')
        if 'dump' in argv:return subprocess.CompletedProcess(argv,0,'BPF_STRUCT_OPS_STATE_INUSE','')
        return subprocess.CompletedProcess(argv,0,'','')
    monkeypatch.setattr(lab_runner.subprocess,'run',command)
    assert lab_runner.cleanup_struct_ops([expected])==[]
    assert calls[-1]==['bpftool','struct_ops','unregister','id','201']
    calls.clear()
    assert lab_runner.cleanup_struct_ops([{**expected,'btf_id':999}])
    assert not any('unregister' in cmd for cmd in calls)
