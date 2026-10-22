"""Create NEW task bundle, ZIP, chunks and integrity manifests; never push or delete."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CHUNK = 80 * 1024**2


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(4 << 20), b''):
            h.update(data)
    return h.hexdigest()


def regular(directory):
    return [p for p in directory.rglob('*') if p.is_file() and not any(x in ('__pycache__','.git','.venv') for x in p.parts)
            and p.suffix not in ('.pyc','.pyo') and not p.name.startswith('~$')]


def main():
    bundle = OUT / 'bundle'
    bundle.mkdir(exist_ok=True)
    tracked = subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','ls-files','-z'],cwd=ROOT).decode().split('\0')
    files = {ROOT / n for n in tracked if n and ((n.startswith('optimization_control/') and '/experiments/' not in n)
            or (n.startswith('tools/') and Path(n).suffix in ('.py','.md','.ps1')) or ('/' not in n and Path(n).suffix=='.md'))}
    files.add(ROOT / 'optimization_control/maddpg_wind_farm/portable_random_replay.py')
    for directory in (ROOT / 'optimization_control/experiments').glob('20261022*'):
        files.update(regular(directory))
    # Frozen source records are copied verbatim, with their teammate ownership explicit.
    source_manifest = ROOT / 'optimization_control/experiments/20261022_wind_pinn_integration/data/source_manifest.json'
    dependencies = json.loads(source_manifest.read_text(encoding='utf-8'))['source_hashes']
    for value, expected in dependencies.items():
        path = Path(value)
        if sha(path) != expected:
            raise ValueError('Source dependency changed')
        files.add(path)
    records=[]
    for path in sorted(files):
        rel=path.relative_to(ROOT)
        target_rel=Path('project_context/README.md') if rel.as_posix()=='README.md' else rel
        target=bundle / target_rel
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if sha(target) != sha(path):
                raise ValueError('Existing bundle member differs: ' + str(target_rel))
        else:
            shutil.copy2(path,target)
        records.append(dict(path=target_rel.as_posix(),source_path=rel.as_posix(),bytes=path.stat().st_size,sha256=sha(path),
            location='task_zip',ownership='teammate_runtime_dependency' if str(path) in dependencies else 'optimization_work_or_context'))
    for name in ('任务说明.docx','readme.md','environment_versions.txt'):
        if (bundle/name).exists():
            if sha(OUT/name) != sha(bundle/name):
                raise ValueError('Existing handoff document differs: ' + name)
        else:
            shutil.copy2(OUT/name,bundle/name)
        records.append(dict(path=name,bytes=(OUT/name).stat().st_size,sha256=sha(OUT/name),location='task_zip',ownership='handoff_document'))
    manifest=dict(schema_version=1,seed=42,date='2026-10-22',source_commit=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        files=records,history_reference=dict(directory='materials/洪祖名/20261007_optimization_handoff',
        final_commit='782368a31e412ff318595d7166a7e8eae30104fe',included_in_main=True),
        exclusions=['virtual environments','credentials','teammate raw datasets and full delivery','unrelated files'])
    (bundle/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    archive=OUT/'三机优化控制与中期答辩交付_20261022.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(regular(bundle)):
            z.write(p,p.relative_to(bundle).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for record in records:
            assert hashlib.sha256(z.read(record['path'])).hexdigest()==record['sha256']
    archives=OUT/'archives'; archives.mkdir(exist_ok=False)
    chunks=[]
    with archive.open('rb') as f:
        while data:=f.read(CHUNK):
            name=f'task_bundle.zip.{len(chunks)+1:03d}'
            target=archives/name;target.write_bytes(data)
            chunks.append(dict(path='archives/'+name,kind='task_zip_chunk',bytes=len(data),sha256=sha(target)))
    manifest.update(task_zip=dict(name=archive.name,bytes=archive.stat().st_size,sha256=sha(archive)),archives=chunks,
                    task_chunk_order=[c['path'] for c in chunks])
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(f"{c['sha256']}  {c['path']}" for c in chunks)+f"\n{sha(archive)}  {archive.name}\n",encoding='utf-8',newline='\n')
    assert all(sha(ROOT/r['source_path'])==r['sha256'] for r in records if 'source_path' in r)
    print(json.dumps(dict(files=len(records),task_zip_mib=archive.stat().st_size/1024**2,chunks=len(chunks)),ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
