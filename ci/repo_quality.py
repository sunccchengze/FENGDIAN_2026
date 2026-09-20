#!/usr/bin/env python3
"""Small, dependency-free repository hygiene checks.

This is intentionally conservative: it checks repository contracts and provenance
hygiene, not scientific correctness. Domain reviewers remain responsible for the
validity of physical, data, and algorithmic conclusions.
"""

from __future__ import annotations

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
    "docs/research/README.md",
    "docs/templates/README.md",
    "materials/README.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/config.yml",
]

GOVERNED_MARKDOWN = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/14_协作治理与可复现研究工作台方案.md",
    "docs/README.md",
    "docs/evidence/README.md",
    "docs/evidence/EVID-2026-001_twin-verify-2026-09-20.md",
    "docs/decisions/README.md",
    "docs/meetings/README.md",
    "docs/project/README.md",
    "docs/research/README.md",
    "docs/templates/README.md",
    "materials/README.md",
    "twin/README.md",
    "viz/README.md",
]

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
TEMP_NAME_RE = re.compile(r"(?:final[_-]?v\d+|really[_-]?final|latest[_-]?new)", re.I)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


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


def check_local_links(errors: list[str], warnings: list[str]) -> None:
    for relative in GOVERNED_MARKDOWN:
        path = ROOT / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
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


def check_files(files: list[Path], errors: list[str], warnings: list[str]) -> None:
    for path in files:
        if not path.exists() or not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        size = path.stat().st_size
        if path.suffix.lower() in IMAGE_SUFFIXES and size == 0:
            errors.append(f"zero-byte image: {relative}")
        if size > MAX_ERROR_BYTES:
            errors.append(f"file exceeds 95 MiB: {relative} ({size} bytes)")
        elif size > MAX_WARN_BYTES:
            warnings.append(f"large tracked file (>50 MiB): {relative} ({size} bytes)")
        if TEMP_NAME_RE.search(path.name):
            warnings.append(f"version-like filename needs human review: {relative}")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    files = tracked_files()

    check_required(errors)
    check_forms(errors)
    check_local_links(errors, warnings)
    check_files(files, errors, warnings)

    for warning in sorted(set(warnings)):
        print(f"WARN: {warning}")
    for error in sorted(set(errors)):
        print(f"ERROR: {error}", file=sys.stderr)

    print(
        f"repo-quality: {len(errors)} error(s), {len(set(warnings))} warning(s), "
        f"{len(files)} tracked file(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
