#!/usr/bin/env python3
"""Create explicit source and separate owner-data exports; never prune a checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'node_modules','__pycache__','.git','.venv','.autorun','.cache'}

def allowed(path):
    return not any(p in EXCLUDED for p in path.parts) and not any(
        ':' in p or p.startswith('.env') or p.lower() in {'credentials','credentials.json','secrets.json','token.json','.npmrc','.pypirc','.netrc','id_rsa','id_ed25519'}
        or p.lower().endswith(('.pem','.key','.p12','.pfx','.pyc','.pyo')) for p in path.parts)


def external(path):
    path=path.absolute()
    if path.is_relative_to(ROOT):raise SystemExit('Exports must be outside the canonical checkout')
    if path.exists():raise SystemExit('Refusing to overwrite an existing export: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    return path


def build(output, with_dist=False, with_host_build=False):
    paths=set()
    for directory in ['backend','ccreplay','tests','scripts','experiments','examples','user','bpf','frontend/src','frontend/public','data/kernel_source_ref']:
        paths.update(p for p in (ROOT/directory).rglob('*') if p.is_file())
    for name in ['README.md','requirements-studio.txt','run_studio.sh','.gitignore','.gitattributes','Makefile']:
        if (ROOT/name).is_file():paths.add(ROOT/name)
    paths.update(ROOT.glob('LICENSE*'))
    for pattern in ['package*.json','tsconfig*.json','vite.config.*','eslint.config.*','oxlint*.json','index.html']:
        paths.update(p for p in (ROOT/'frontend').glob(pattern) if p.is_file())
    for name in ['ARCHITECTURE.md','REPLAY_CONTRACT.md','VALIDATION.md','DEVELOPMENT.md','DEMO.md','PROVENANCE.md','EVIDENCE_INDEX.json','LIMITATIONS.zip']:
        if (ROOT/'docs'/name).is_file():paths.add(ROOT/'docs'/name)
    evidence=json.loads((ROOT/'docs/EVIDENCE_INDEX.json').read_text())
    paths.update(ROOT/f['target'] for f in evidence['files'] if f['action']=='keep' and f['semantic_category']=='recording' and f['sha256'])
    if with_dist:paths.update(p for p in (ROOT/'frontend/dist').rglob('*') if p.is_file())
    if with_host_build:paths.update(p for p in (ROOT/'build_local').rglob('*') if p.is_file())
    manifest={}
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths):
            rel=p.relative_to(ROOT)
            if not p.is_file() or p.is_symlink() or not allowed(rel) or p.suffix in {'.o','.h'} and (p.name.endswith('.skel.h') or p.name=='vmlinux.h'):continue
            data=p.read_bytes();z.writestr(str(rel),data)
            manifest[str(rel)]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        z.writestr('RELEASE_MANIFEST.json',json.dumps({'files':manifest,'host_build_optional':with_host_build,
                     'owner_data':'Excluded; use the separate owner export. External evidence identities are in docs/EVIDENCE_INDEX.json.'},indent=2))
    with zipfile.ZipFile(output) as z:
        for name,entry in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==entry['sha256']
    return len(manifest)


def export_owner(output, roots, lab_root=None):
    count=0
    with tarfile.open(output,'x:gz') as t:
        for i,root in enumerate(roots):
            for folder in ['runtime','studio_data','controllers/user','uploads']:
                for p in sorted((root/folder).rglob('*')):
                    if p.is_file() and not p.is_symlink() and allowed(p.relative_to(root)):
                        t.add(p,arcname=f'owner-{i}/{p.relative_to(root)}',recursive=False);count+=1
        if lab_root:
            for p in sorted(p for session in lab_root.glob('session-*') for p in session.rglob('*')):
                if p.is_file() and not p.is_symlink() and allowed(p.relative_to(lab_root)):
                    t.add(p,arcname=f'lab/{p.relative_to(lab_root)}',recursive=False);count+=1
        import io
        refs={'lab_root':str(lab_root) if lab_root else None,'owner_roots':[str(p) for p in roots], 'evidence_index':json.loads((ROOT/'docs/EVIDENCE_INDEX.json').read_text())}
        raw=json.dumps(refs,indent=2).encode();info=tarfile.TarInfo('EXPORT_IDENTITIES.json');info.size=len(raw);t.addfile(info,io.BytesIO(raw))
    return count


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--with-dist',action='store_true');p.add_argument('--with-host-build',action='store_true')
    p.add_argument('--owner-export',type=Path);p.add_argument('--owner-root',type=Path,action='append');p.add_argument('--lab-root',type=Path)
    a=p.parse_args()
    print('Release files:',build(external(a.out),a.with_dist,a.with_host_build))
    if a.owner_export:
        print('Owner files:',export_owner(external(a.owner_export),[x.resolve() for x in (a.owner_root or [ROOT])],a.lab_root))
    print('Release SHA-256:',hashlib.sha256(a.out.read_bytes()).hexdigest())

if __name__=='__main__':main()
