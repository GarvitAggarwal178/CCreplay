import json
from pathlib import Path
import pytest
from ccreplay import recordings
from ccreplay.storage import digest

def test_corrupt_upload_is_atomic_and_missing_sidecar_unknown(tmp_path,monkeypatch):
    monkeypatch.setattr(recordings,'ROOT',tmp_path)
    monkeypatch.setattr(recordings,'RUNTIME',tmp_path/'runtime')
    monkeypatch.setattr(recordings,'REGISTRY',tmp_path/'registry.json')
    data=Path('raw/r0/rep1.ccr').read_bytes()
    with pytest.raises(Exception):recordings.import_bytes(data,b'{invalid')
    assert not (tmp_path/'uploads').exists()
    with pytest.raises(Exception):recordings.import_bytes(data[:-1])
    assert not (tmp_path/'uploads').exists()
    first=recordings.import_bytes(data,name='same.ccr');second=recordings.import_bytes(data,name='same.ccr')
    assert first['id']!=second['id']
    assert first['integrity']=='unknown'
    assert first['sha256']==second['sha256']
    assert len(recordings.entries())==2


def test_wrong_sidecar_does_not_publish(tmp_path,monkeypatch):
    monkeypatch.setattr(recordings,'ROOT',tmp_path);monkeypatch.setattr(recordings,'REGISTRY',tmp_path/'registry.json')
    data=Path('raw/r0/rep1.ccr').read_bytes();meta=json.loads(Path('raw/r0/rep1.meta.json').read_text());meta['emitted']+=1
    with pytest.raises(ValueError):recordings.import_bytes(data,json.dumps(meta).encode())
    assert not (tmp_path/'uploads').exists()
