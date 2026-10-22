"""Writes a NEW handoff bundle and archives. Does not delete, overwrite, or push."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

LATEST = ("20261007_fixed_pinn_curriculum", "20261007_fixed_pinn_pitch_speed_probe", "20261007_fixed_pinn_all_probe")
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".ps1"}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def regular_files(directory):
    return [p for p in directory.rglob("*") if p.is_file() and not any(
        part in ("__pycache__", ".pytest_cache", ".git", ".venv") for part in p.parts)
        and p.suffix not in (".pyc", ".pyo") and not p.name.startswith("~$")]


def write_zip(path, files, root):
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for p in sorted(files):
            z.write(p, p.relative_to(root).as_posix())
    with zipfile.ZipFile(path) as z:
        failure = z.testzip()
        if failure:
            raise ValueError(f"corrupt zip member: {failure}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    root, out = Path(a.root).resolve(), Path(a.output).resolve()
    if not out.is_relative_to(root / "deliverables"):
        raise ValueError("output must stay in project deliverables")
    bundle = out / "bundle"
    bundle.mkdir(parents=True, exist_ok=False)
    tracked = subprocess.check_output(["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-z"], cwd=root).decode().split("\0")
    source = {root / p for p in tracked if p.startswith("optimization_control/") and "/experiments/" not in p}
    source.update(root / p for p in ["optimization_control/WORK_INDEX.md", "optimization_control/maddpg_wind_farm/handoff_replay.py",
        "tools/unpack_optimization.py", "tools/package_optimization.py", "tools/project_git_status.ps1", "tools/README.md"])
    source.update(root / p for p in tracked if p and "/" not in p and Path(p).suffix in (".md", ""))
    latest = set(source)
    for name in LATEST:
        experiment = root / "optimization_control/experiments" / name
        selection = json.loads((experiment / "selection.json").read_text(encoding="utf-8-sig"))
        chosen = set()
        for r in selection["results"]:
            chosen.update([Path(r["initial"]), Path(r["final"]), Path(r["best"]["checkpoint"])])
        latest.update(p for p in regular_files(experiment) if p.suffix != ".pth" or p in chosen)
    latest.update(regular_files(root / "optimization_control/experiments/20261007_fixed_pinn_demo_checked"))
    metadata = json.loads((root / "optimization_control/experiments/20261007_fixed_pinn_demo_checked/data/metadata.json").read_text(encoding="utf-8-sig"))
    dependencies = {Path(p) for p in metadata["source_hashes"]}
    for p in dependencies:
        if sha(p) != metadata["source_hashes"][str(p)]:
            raise ValueError("team provenance changed")
    latest.update(dependencies)
    records = []
    for p in sorted(latest):
        source_rel = p.relative_to(root)
        rel = Path("project_context/README.md") if source_rel.as_posix() == "README.md" else source_rel
        target = bundle / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        records.append(dict(path=rel.as_posix(), source_path=source_rel.as_posix(), bytes=p.stat().st_size, sha256=sha(p),
            ownership="teammate_runtime_dependency" if p in dependencies else "optimization_work_or_context",
            location="task_zip"))
    for name in ("任务说明.docx", "任务说明.md", "readme.md"):
        shutil.copy2(out / name, bundle / name)
        records.append(dict(path=name, bytes=(bundle / name).stat().st_size, sha256=sha(bundle / name),
            ownership="handoff_document", location="task_zip"))
    (bundle / "pinn/README.md").write_text("# 必要 PINN 依赖\n\n此处仅复制队友原交付的加载脚本与联调所需冻结模型和配置，保持原字节与来源 SHA256。不是优化侧独立训练的 PINN 成果，不包含队友整个交付。实际联调模型为 optimization_control/experiments/20261007_fixed_pinn_demo_checked/model/trained.keras，标签为合成 Mock，未做物理精度验证。\n", encoding="utf-8")
    (bundle / "manifest.json").write_text(json.dumps(dict(seed=42, original_commit="042c634", files=records), ensure_ascii=False, indent=2), encoding="utf-8")
    task = out / "三机MADDPG逐级控制验证_20261007.zip"
    write_zip(task, regular_files(bundle), bundle)
    archive_dir = out / "archives"
    archive_dir.mkdir(exist_ok=False)
    archives = []
    chunk_limit = 80 * 1024**2
    all_artifacts = []
    for d in sorted((root / "optimization_control/experiments").iterdir()):
        if d.is_dir():
            all_artifacts.extend(regular_files(d))
    for d in (root / "models/ppo", root / "runs"):
        if d.exists():
            all_artifacts.extend(regular_files(d))
    all_artifacts.extend(root.glob("工作记录_优化控制模块_*.html"))
    all_artifacts.extend(root.glob("项目结构全景梳理_*.html"))
    all_artifacts = sorted(set(all_artifacts) - latest)
    groups = {}
    for p in all_artifacts:
        rel = p.relative_to(root)
        key = rel.parts[2] if rel.parts[:2] == ("optimization_control", "experiments") else "legacy_ppo_models_runs"
        groups.setdefault(key, []).append(p)
    for group, files in groups.items():
        part, size, partitions = [], 0, []
        for p in files:
            if p.stat().st_size >= chunk_limit:
                raise ValueError("unexpected individual artifact larger than archive limit")
            if size + p.stat().st_size > chunk_limit and part:
                partitions.append(part); part, size = [], 0
            part.append(p); size += p.stat().st_size
        if part:
            partitions.append(part)
        for i, files in enumerate(partitions, 1):
            archive = archive_dir / f"{group}_part{i:02d}.zip"
            write_zip(archive, files, root)
            archives.append(dict(path=f"archives/{archive.name}", kind="independent_zip", bytes=archive.stat().st_size,
                sha256=sha(archive), files=[p.relative_to(root).as_posix() for p in files]))
            for p in files:
                records.append(dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha(p),
                    ownership="optimization_historical_artifact", location=f"archives/{archive.name}"))
            print(f"archived {archive.name} {archive.stat().st_size / 1024**2:.1f} MiB", flush=True)
    # The local task is one ZIP. GitHub gets byte chunks below its single-file limit.
    with task.open("rb") as src:
        i = 0
        while True:
            data = src.read(chunk_limit)
            if not data:
                break
            i += 1
            path = archive_dir / f"task_bundle.zip.{i:03d}"
            with path.open("xb") as f:
                f.write(data)
            archives.append(dict(path=f"archives/{path.name}", kind="task_zip_chunk", bytes=len(data), sha256=sha(path)))
    manifest = dict(schema_version=1, seed=42, original_commit="042c634", date="2026-10-07",
        task_zip=dict(name=task.name, bytes=task.stat().st_size, sha256=sha(task)),
        task_chunk_order=[x["path"] for x in archives if x["kind"] == "task_zip_chunk"], archives=archives, files=records,
        exclusions=["local virtual environments and caches", "teammate raw datasets and full PINN delivery", "unrelated personal tools and temporary folders"],
        provenance="Original bytes preserved in archives; historical absolute paths are records. Replay launcher relocates paths in memory.")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    sums = [f"{x['sha256']}  {x['path']}" for x in archives]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps(dict(files=len(records), archives=len(archives), task_zip_mib=task.stat().st_size / 1024**2,
        archive_mib=sum(x["bytes"] for x in archives) / 1024**2)), flush=True)


if __name__ == "__main__":
    main()
