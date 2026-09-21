#!/usr/bin/env python3
"""Small, dependency-free repository hygiene checks.

This is intentionally conservative: it checks repository contracts and provenance
hygiene, not scientific correctness. Domain reviewers remain responsible for the
validity of physical, data, and algorithmic conclusions.

Checks (all stdlib, no network):
1. required governance paths exist;
2. issue forms / PR template keep their required sections;
3. local Markdown links resolve — for every tracked ``*.md`` except third-party
   packs, sealed archives and generated mirrors (see ``LINK_SCOPE_EXCLUDE``);
4. tracked files: zero-byte images, >50/95 MiB, version-like names, ``(``/``)`` in
   ``docs/`` and ``materials/`` paths (parentheses break Markdown link parsing);
5. markitdown mirrors (``materials/README.md`` rule 9): every docx/pptx/xlsx/pdf under
   ``materials/`` has a sibling ``.md`` mirror whose recorded sha256 matches the source,
   and no mirror has lost its source;
6. ``SHA256SUMS.txt`` manifests (ADR-2026-001 "manifest + SHA-256"): every listed file
   exists and hashes as recorded; files in the same tree that are not listed are warned;
7. the self-study whitepaper assembles byte-identically from its ``whitepaper_src/``
   fragments (``build.py --check``).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_ERROR_BYTES = 95 * 1024 * 1024
MAX_WARN_BYTES = 50 * 1024 * 1024

REQUIRED_PATHS = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/14_协作治理与可复现研究工作台方案.md",
    "docs/README.md",
    "docs/evidence/README.md",
    "docs/evidence/EVID-2026-001_twin-verify-2026-09-20.md",
    "docs/decisions/README.md",
    "docs/meetings/README.md",
    "docs/project/README.md",
    "docs/audits/README.md",
    "docs/audits/2026-09-20_治理实现自审.md",
    "docs/research/README.md",
    "docs/templates/README.md",
    "materials/README.md",
    "tools/markitdown_sync.py",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/config.yml",
]

# Markdown files whose links are NOT checked (everything else tracked is).
LINK_SCOPE_EXCLUDE = (
    "skills/",  # third-party skill packs copied whole; cross-pack relative links live upstream
    "viz/_archive/",  # sealed history; only MANIFEST.md (kept below) is a live document
    ".learnings/",  # agent learning logs at any depth (viz/.learnings/ too) are historical, matched by segment below
    # notes excerpted from the -SKILL- repo; their upstream references/ were deliberately not migrated
    "materials/孙承泽/学习计划与Agent准则/skills-notes/",
)
LINK_SCOPE_KEEP = {"viz/_archive/MANIFEST.md"}

MIRROR_ROOT = "materials/"
MIRROR_SOURCE_SUFFIXES = {".docx", ".pptx", ".xlsx", ".pdf"}
MIRROR_SKIP_PREFIXES = ("materials/孙承泽/自学白皮书/pdf/",)  # PDFs rendered from Markdown sources
MIRROR_RE = re.compile(r'^<!-- markitdown-mirror: source="(?P<src>[^"]+)" sha256="(?P<sha>[0-9a-f]{12})"')

WHITEPAPER_BUILD = "materials/孙承泽/自学白皮书/whitepaper_src/build.py"
CHECKSUM_FILENAME = "SHA256SUMS.txt"
CHECKSUM_LINE_RE = re.compile(r"^(?P<sha>[0-9a-f]{64})\s+\*?(?P<name>.+)$")

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
TEMP_NAME_RE = re.compile(r"(?:final[_-]?v\d+|really[_-]?final|latest[_-]?new)", re.I)
PAREN_SCOPE = ("docs/", "materials/")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_head(path: Path, size: int = 400) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(size)
    except OSError:
        return ""


def is_mirror(path: Path) -> bool:
    return path.suffix.lower() == ".md" and MIRROR_RE.match(read_head(path)) is not None


def tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: cannot read tracked files: {exc}", file=sys.stderr)
        return []
    return [ROOT / item for item in result.stdout.decode().split("\0") if item]


def check_required(errors: list[str]) -> None:
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).exists():
            errors.append(f"missing required path: {relative}")


def check_forms(errors: list[str]) -> None:
    forms = sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml"))
    for form in forms:
        if form.name == "config.yml":
            continue
        text = form.read_text(encoding="utf-8")
        for key in ("name:", "description:", "body:"):
            if key not in text:
                errors.append(f"issue form missing {key}: {form.relative_to(ROOT)}")

    pr = ROOT / ".github/PULL_REQUEST_TEMPLATE.md"
    if pr.exists():
        text = pr.read_text(encoding="utf-8")
        for marker in ("关联 Issue", "验证", "合并前清单"):
            if marker not in text:
                errors.append(f"PR template missing section {marker}: {pr.relative_to(ROOT)}")


def link_scope(files: list[Path]) -> list[Path]:
    scoped: list[Path] = []
    for path in files:
        if path.suffix.lower() != ".md" or not path.is_file():
            continue
        relative = rel(path)
        if relative in LINK_SCOPE_KEEP:
            scoped.append(path)
            continue
        if relative.startswith(LINK_SCOPE_EXCLUDE) or "/.learnings/" in f"/{relative}":
            continue
        if is_mirror(path):  # generated; fix the generator, not the mirror
            continue
        scoped.append(path)
    return scoped


def check_local_links(files: list[Path], errors: list[str], warnings: list[str]) -> int:
    scoped = link_scope(files)
    for path in scoped:
        relative = rel(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw_target in LINK_RE.findall(text):
            target = raw_target.strip().split(" ", 1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#"):
                continue
            local = unquote(parsed.path)
            if not local:
                continue
            candidate = (path.parent / local).resolve()
            try:
                candidate.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"link escapes repository: {relative} -> {target}")
                continue
            if not candidate.exists():
                errors.append(f"broken local link: {relative} -> {target}")
    return len(scoped)


def check_files(files: list[Path], errors: list[str], warnings: list[str]) -> None:
    for path in files:
        if not path.exists() or not path.is_file():
            continue
        relative = rel(path)
        size = path.stat().st_size
        if path.suffix.lower() in IMAGE_SUFFIXES and size == 0:
            errors.append(f"zero-byte image: {relative}")
        if size > MAX_ERROR_BYTES:
            errors.append(f"file exceeds 95 MiB: {relative} ({size} bytes)")
        elif size > MAX_WARN_BYTES:
            warnings.append(f"large tracked file (>50 MiB): {relative} ({size} bytes)")
        if TEMP_NAME_RE.search(path.name):
            warnings.append(f"version-like filename needs human review: {relative}")
        if relative.startswith(PAREN_SCOPE) and ("(" in relative or ")" in relative):
            warnings.append(f"path contains parentheses (breaks Markdown links; rename): {relative}")


def check_mirrors(files: list[Path], errors: list[str], warnings: list[str]) -> int:
    """materials/README.md rule 9: Office/PDF files carry an up-to-date markitdown mirror."""
    tracked = {path for path in files}
    mirrors = 0
    for path in files:
        if not path.is_file() or path.suffix.lower() != ".md":
            continue
        match = MIRROR_RE.match(read_head(path))
        if not match:
            continue
        mirrors += 1
        source = path.parent / match.group("src")
        if not source.exists():
            errors.append(f"mirror lost its source ({match.group('src')}): {rel(path)}")
        elif sha256_of(source)[:12] != match.group("sha"):
            errors.append(f"mirror stale, rerun tools/markitdown_sync.py: {rel(path)}")

    for path in files:
        relative = rel(path)
        if not relative.startswith(MIRROR_ROOT) or relative.startswith(MIRROR_SKIP_PREFIXES):
            continue
        if path.suffix.lower() not in MIRROR_SOURCE_SUFFIXES or path.name.startswith("~$") or not path.is_file():
            continue
        mirror = path.with_suffix(".md")
        if mirror not in tracked or not mirror.exists():
            errors.append(f"office/pdf file without markdown mirror, run tools/markitdown_sync.py: {relative}")
        elif not is_mirror(mirror):
            warnings.append(f"same-named markdown is hand-written, source not mirrored: {relative}")
    return mirrors


def check_checksums(files: list[Path], errors: list[str], warnings: list[str]) -> int:
    """SHA256SUMS.txt (sha256sum -c format) next to imported deliverables must still verify."""
    manifests = [path for path in files if path.name == CHECKSUM_FILENAME and path.is_file()]
    for manifest in manifests:
        listed: set[Path] = set()
        for lineno, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = CHECKSUM_LINE_RE.match(line)
            if not match:
                errors.append(f"malformed checksum line {lineno}: {rel(manifest)}")
                continue
            target = manifest.parent / match.group("name")
            listed.add(target.resolve())
            if not target.is_file():
                errors.append(f"checksummed file missing: {rel(manifest)} -> {match.group('name')}")
            elif sha256_of(target) != match.group("sha"):
                errors.append(f"checksum mismatch: {rel(manifest)} -> {match.group('name')}")
        for path in files:
            if path.is_file() and manifest.parent in path.parents and path != manifest:
                if path.resolve() not in listed and not is_mirror(path):
                    warnings.append(f"file not listed in {rel(manifest)}: {rel(path)}")
    return len(manifests)


def check_whitepaper_build(errors: list[str]) -> None:
    build = ROOT / WHITEPAPER_BUILD
    if not build.exists():
        return
    result = subprocess.run([sys.executable, str(build), "--check"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        errors.append(f"whitepaper fragments and assembled file differ: {WHITEPAPER_BUILD} --check -> {detail[-1] if detail else result.returncode}")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    files = tracked_files()

    check_required(errors)
    check_forms(errors)
    linked = check_local_links(files, errors, warnings)
    check_files(files, errors, warnings)
    mirrors = check_mirrors(files, errors, warnings)
    manifests = check_checksums(files, errors, warnings)
    check_whitepaper_build(errors)

    for warning in sorted(set(warnings)):
        print(f"WARN: {warning}")
    for error in sorted(set(errors)):
        print(f"ERROR: {error}", file=sys.stderr)

    print(
        f"repo-quality: {len(errors)} error(s), {len(set(warnings))} warning(s), "
        f"{len(files)} tracked file(s), {linked} markdown link-checked, "
        f"{mirrors} mirror(s) verified, {manifests} checksum manifest(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
