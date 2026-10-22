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
   fragments (``build.py --check``);
8. case-insensitive path collisions (paths differing only in case clobber each
   other on Windows/macOS checkouts — found once in the 2026-10-22 audit);
9. U+FFFD replacement characters in first-party tracked ``.md``/``.py`` files;
10. twin/viz FLORIS 3D payloads stay equal (``twin/src/data/floris3dData.mjs``
    vs ``viz/site/assets/data_3d_real.js``, modulo header comment and the
    ``export default`` / ``window.WIND_3D_REAL`` wrappers);
11. every tracked ``.py`` compiles and every tracked ``.json`` parses
    (tsconfig files are JSONC and excluded by name).
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

# ADR-2026-003（2026-10-22 生效）：>50 MiB 的二进制不进 git，走 Release 资产。
# 「存量不动」——这两个文件在 ADR 生效前已入库，登记为基线，不再重复告警；
# 新增的大文件不在基线内，必须同时满足「有 SHA256SUMS 条目」才不告警。
LARGE_ASSET_BASELINE = {
    "materials/孙承泽/PS科研制图/Figure1_Wake_Steering_Mechanism.psd",
    "materials/洪祖名/20261007_optimization_handoff/archives/task_bundle.zip.001",
}

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
        elif size > MAX_WARN_BYTES and relative not in LARGE_ASSET_BASELINE:
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


def check_large_assets(files: list[Path], errors: list[str], warnings: list[str]) -> int:
    """ADR-2026-003：新增的 >50 MiB 文件要么有清单留证，要么就不该进 git。

    判据只有一条：**能不能在某个 SHA256SUMS.txt 里找到它**。找不到就告警并给出
    正确做法（传到带 tag 的 Release，仓库留清单 + 下载命令），而不是静默放行。
    存量文件见 LARGE_ASSET_BASELINE，不在此重复告警。
    """
    covered: set[Path] = set()
    for manifest in (path for path in files if path.name == CHECKSUM_FILENAME and path.is_file()):
        for line in manifest.read_text(encoding="utf-8").splitlines():
            match = CHECKSUM_LINE_RE.match(line.strip())
            if match:
                covered.add((manifest.parent / match.group("name")).resolve())
    large = 0
    for path in files:
        if not path.is_file() or path.stat().st_size <= MAX_WARN_BYTES:
            continue
        relative = rel(path)
        if relative in LARGE_ASSET_BASELINE:
            continue
        large += 1
        if path.resolve() not in covered:
            warnings.append(
                f"大文件无清单留证（ADR-2026-003：>50 MiB 应作 Release 资产并在 SHA256SUMS.txt 登记）: {relative}"
            )
    return large


def check_whitepaper_build(errors: list[str]) -> None:
    build = ROOT / WHITEPAPER_BUILD
    if not build.exists():
        return
    result = subprocess.run([sys.executable, str(build), "--check"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        errors.append(f"whitepaper fragments and assembled file differ: {WHITEPAPER_BUILD} --check -> {detail[-1] if detail else result.returncode}")


def check_case_collisions(files: list[Path], errors: list[str]) -> None:
    seen: dict[str, str] = {}
    for path in files:
        name = rel(path)
        key = name.lower()
        if key in seen and seen[key] != name:
            errors.append(
                f"case-insensitive path collision: {seen[key]} vs {name} "
                "(Windows/macOS checkouts would clobber one of them)"
            )
        seen.setdefault(key, name)


def check_text_hygiene(files: list[Path], warnings: list[str]) -> None:
    for path in files:
        if path.suffix.lower() not in {".md", ".py"}:
            continue
        if path.name in {"markitdown_sync.py", "repo_quality.py"}:
            continue  # these two legitimately contain the U+FFFD literal/escape
        if rel(path).startswith("skills/") or is_mirror(path):
            continue  # third-party packs and generated mirrors: extraction artefacts, not authoring damage
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "�" in text:
            warnings.append(f"{rel(path)}: contains U+FFFD replacement character(s)")


def check_floris3d_sync(errors: list[str]) -> None:
    twin = ROOT / "twin" / "src" / "data" / "floris3dData.mjs"
    site = ROOT / "viz" / "site" / "assets" / "data_3d_real.js"
    if not twin.exists() or not site.exists():
        errors.append("floris3d sync: twin/src/data/floris3dData.mjs or viz/site/assets/data_3d_real.js missing")
        return
    import ast
    import json

    twin_body = twin.read_text(encoding="utf-8").split("export default", 1)[1].strip().rstrip(";").strip()
    site_text = site.read_text(encoding="utf-8")
    site_body = site_text.split("window.WIND_3D_REAL =", 1)[1].strip()
    site_body = site_body[: site_body.rfind(";")].strip() if ";" in site_body else site_body
    try:
        twin_data = json.loads(twin_body)
        try:
            site_data = json.loads(site_body)
        except json.JSONDecodeError:
            site_data = ast.literal_eval(
                site_body.replace("null", "None").replace("true", "True").replace("false", "False")
            )
    except Exception as exc:  # parse failure is itself the signal
        errors.append(f"floris3d sync: cannot parse payloads for comparison ({exc.__class__.__name__})")
        return
    if twin_data != site_data:
        errors.append(
            "floris3d sync: twin/src/data/floris3dData.mjs and viz/site/assets/data_3d_real.js payloads differ; "
            "regenerate both from the same FLORIS run (see docs/audits/2026-10-22_全仓完整审计_问题清单.md AUD-22)"
        )


def check_parseable(files: list[Path], errors: list[str]) -> None:
    import json

    for path in files:
        suffix = path.suffix.lower()
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        if suffix == ".py":
            try:
                compile(text, str(path), "exec")
            except SyntaxError as exc:
                errors.append(f"{rel(path)}: python syntax error ({exc.msg} line {exc.lineno})")
        elif suffix == ".json" and "tsconfig" not in path.name:
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"{rel(path)}: invalid JSON ({exc.msg} line {exc.lineno})")


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
    check_large_assets(files, errors, warnings)
    check_whitepaper_build(errors)
    check_case_collisions(files, errors)
    check_text_hygiene(files, warnings)
    check_floris3d_sync(errors)
    check_parseable(files, errors)

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
