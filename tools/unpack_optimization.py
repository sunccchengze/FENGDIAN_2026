"""Validate handoff chunks and extract into a NEW directory; never overwrite existing files."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import tarfile


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_safe(path, output):
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            target = (output / info.filename).resolve()
            if not target.is_relative_to(output):
                raise ValueError("archive traversal rejected")
            if target.exists():
                raise FileExistsError(target)
        z.extractall(output)


def extract_solid(path, output):
    with zipfile.ZipFile(path) as wrapper:
        with wrapper.open("payload.tar.xz") as compressed:
            with tarfile.open(fileobj=compressed, mode="r|xz") as tar:
                for member in tar:
                    target = (output / member.name).resolve()
                    if not target.is_relative_to(output) or not member.isfile():
                        raise ValueError("non-file or unsafe solid-archive member")
                    if target.exists():
                        raise FileExistsError(target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as source, target.open("xb") as dest:
                        while chunk := source.read(4 << 20):
                            dest.write(chunk)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--all-history", action="store_true")
    a = ap.parse_args()
    source, output = Path(a.handoff).resolve(), Path(a.output).resolve()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    needed = [r for r in manifest["archives"] if a.all_history or r["kind"] == "task_zip_chunk"]
    for r in needed:
        p = (source / r["path"]).resolve()
        if not p.is_relative_to(source) or digest(p) != r["sha256"]:
            raise ValueError("archive hash mismatch")
    output.mkdir(parents=True, exist_ok=False)
    reconstructed = output / "task_bundle.zip"
    with reconstructed.open("xb") as f:
        for name in manifest["task_chunk_order"]:
            with (source / name).open("rb") as chunk:
                while data := chunk.read(4 << 20):
                    f.write(data)
    if digest(reconstructed) != manifest["task_zip"]["sha256"]:
        raise ValueError("reconstructed task ZIP differs")
    extract_safe(reconstructed, output)
    if a.all_history:
        for r in manifest["archives"]:
            if r["kind"] == "independent_zip":
                extract_safe(source / r["path"], output)
            elif r["kind"] == "solid_tar_xz_zip":
                extract_solid(source / r["path"], output)
    expected = [r for r in manifest["files"] if a.all_history or r["location"] == "task_zip"]
    for r in expected:
        if digest(output / r["path"]) != r["sha256"]:
            raise ValueError("extracted file hash mismatch")
    print(json.dumps(dict(verified_files=len(expected), output=str(output)), ensure_ascii=False))


if __name__ == "__main__":
    main()
