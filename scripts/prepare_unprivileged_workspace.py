#!/usr/bin/env python3
"""Prepare an accessible, non-root-owned runnable copy for root-only WSL sessions.

Copies known application source/dependencies; never copies secrets, Git metadata,
owner controllers, uploads, saved runs or environments other than the specified
existing Python environment. Existing destination owner data is preserved.
"""
import argparse
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--uid',type=int,required=True);p.add_argument('--gid',type=int,required=True)
p.add_argument('--dest',type=Path,required=True);args=p.parse_args()
if os.geteuid()!=0:raise SystemExit('Run this copy helper as root, then launch Studio under the selected normal uid')
if args.uid<=0 or args.gid<=0:raise SystemExit('Select non-root uid/gid')
dest=args.dest.absolute()
if dest.is_symlink() or dest==ROOT or ROOT in dest.parents:raise SystemExit('Choose an accessible directory outside the root-owned checkout')
marker=dest/'.ccreplay-prepared.json'
if dest.exists():
    if not marker.exists():raise SystemExit('Destination exists without this helper’s marker; refusing to overwrite unknown files')
    old=json.loads(marker.read_text())
    if old!={'source':str(ROOT),'uid':args.uid,'gid':args.gid}:raise SystemExit('Destination belongs to a different source or owner')
else:dest.mkdir(parents=True,mode=0o755)
for name in ['backend','ccreplay','user','bpf','tests','scripts','experiments','examples','raw','data/kernel_source_ref']:
    source=ROOT/name
    if source.exists():
        shutil.copytree(source,dest/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        for path in [dest/name,*(dest/name).rglob('*')]:
            if not path.is_symlink():os.chown(path,args.uid,args.gid)
# Preserve the installed runtime environment on refresh. Recopying an active
# interpreter can fail with ETXTBSY and is unnecessary when dependencies match.
if not (dest/'.venv').exists():
    shutil.copytree(ROOT/'.venv',dest/'.venv',symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
    for path in [dest/'.venv',*(dest/'.venv').rglob('*')]:
        if not path.is_symlink():os.chown(path,args.uid,args.gid)
for name in ['src','public','dist']:
    shutil.copytree(ROOT/'frontend'/name,dest/'frontend'/name,dirs_exist_ok=True)
for source in (ROOT/'frontend').iterdir():
    if source.is_file() and not source.name.startswith('.env'):shutil.copy2(source,dest/'frontend'/source.name)
for name in ['README.md','requirements-studio.txt','run_studio.sh','.gitignore','.gitattributes']:
    if (ROOT/name).exists():shutil.copy2(ROOT/name,dest/name);os.chown(dest/name,args.uid,args.gid)
shutil.copytree(ROOT/'docs',dest/'docs',dirs_exist_ok=True,ignore=shutil.ignore_patterns('session'))
for name in ['frontend','docs']:
    for path in [dest/name,*(dest/name).rglob('*')]:
        if not path.is_symlink():os.chown(path,args.uid,args.gid)
marker.write_text(json.dumps({'source':str(ROOT),'uid':args.uid,'gid':args.gid}))
os.chown(dest,args.uid,args.gid);os.chown(marker,args.uid,args.gid)
print('Prepared',dest)
print(f'cd {dest}')
print(f'setpriv --reuid={args.uid} --regid={args.gid} --clear-groups .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000')
print('Agent, from the original checkout in a separate root terminal:')
print(f'CCREPLAY_OWNER_UID={args.uid} CCREPLAY_OWNER_GID={args.gid} bash scripts/start_lab_agent.sh')
