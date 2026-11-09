"""Build and verify a shareable release with datasets, source and executed evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path.home()/'Docuements/alok-complete.zip');args=p.parse_args()
excluded={'.venv','.git','.pytest_cache','__pycache__','node_modules','.ruff_cache','.mypy_cache'}
evidence={'tests.xml','http-smoke.json','browser-smoke.json','navigation-smoke.json','ui-mutation-smoke.json','full-import.json','reproducibility.json','reproducibility-run-b-checksums.json','overview-desktop.png','overview-mobile.png','cart-desktop.png','design-detection.json','release-verification.json'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

for name in ('http-smoke','browser-smoke','navigation-smoke','ui-mutation-smoke','full-import','reproducibility'):
    report=json.loads((ROOT/'artifacts'/f'{name}.json').read_text())
    if not report.get('passed'):raise SystemExit(f'Cannot package without passing {name} evidence')
for profile in ('starter','full'):
    folder=ROOT/'data'/profile
    for name,expected in json.loads((folder/'metadata/checksums.json').read_text()).items():
        if digest(folder/name)!=expected:raise SystemExit(f'Dataset checksum mismatch: {profile}/{name}')
files=[]
for path in sorted(ROOT.rglob('*')):
    rel=path.relative_to(ROOT)
    if path.is_symlink() or not path.is_file() or any(part in excluded for part in rel.parts):continue
    if path.name=='.env' or (path.name.startswith('.env.') and path.name!='.env.example'):continue
    if path.name in {'.plan-url','.plan-state.json'} or path.name.startswith('.plan-local-') or path.suffix in {'.pyc','.pyo','.zip'}:continue
    if rel.parts[0]=='data' and (len(rel.parts)<2 or rel.parts[1] not in ('starter','full')):continue
    if rel.parts[0]=='artifacts' and (len(rel.parts)!=2 or path.name not in evidence):continue
    if rel.parts[0]=='.impeccable' and rel.as_posix()!='.impeccable/design.json':continue
    files.append((path,'alok/'+rel.as_posix()))
manifest={name:digest(path) for path,name in files}
args.out.parent.mkdir(parents=True,exist_ok=True)
temporary=args.out.with_suffix('.zip.tmp')
with ZipFile(temporary,'w',compression=ZIP_DEFLATED,compresslevel=9) as archive:
    for path,name in files:archive.write(path,name)
    archive.writestr('alok/RELEASE-MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
with ZipFile(temporary) as archive:
    if archive.testzip() is not None:raise SystemExit('ZIP integrity failure')
    for name,expected in manifest.items():
        h=hashlib.sha256()
        with archive.open(name) as source:
            for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
        if h.hexdigest()!=expected:raise SystemExit('Archive checksum mismatch: '+name)
temporary.replace(args.out)
checksum=digest(args.out);args.out.with_suffix('.zip.sha256').write_text(checksum+'  '+args.out.name+'\n')
print(json.dumps({'archive':str(args.out),'files':len(files)+1,'bytes':args.out.stat().st_size,'sha256':checksum,'integrity':'verified'},indent=2))
