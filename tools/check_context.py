#!/usr/bin/env python3
"""Read-only integrity checks for the Persistent Context Protocol.

Checks:
- declared source files exist and the generated brief is current;
- ADR IDs are unique/sequential and statuses are valid;
- protected architectural documents match their reviewed hash manifest;
- required context artifacts exist;
- local Markdown links in the context/procurement documents resolve;
- AGENTS.md contains the context-preflight obligations.

It cannot detect semantic contradictions, owner intent, false provenance or a
maliciously edited checker. See docs/context/AUTOMATION_LIMITS.md.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import context_brief as cb

LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
COMMIT_LINE = re.compile(r"^Source commit at generation:.*$", re.MULTILINE)
BRIEF_COMMIT = re.compile(r"^Source commit at generation: `([0-9a-f]{40})`$", re.MULTILINE)
BRIEF_SOURCE_ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \|", re.MULTILINE)

REQUIRED = (
    "docs/context/README.md",
    "docs/context/CONTEXT_BRIEF.md",
    "docs/context/RECOVERY_TEST.md",
    "docs/context/CONTEXT_RECEIPT.md",
    "docs/context/DECISION_CHANGE.md",
    "docs/context/BRANCH_HANDOFF_TEMPLATE.md",
    "docs/context/AUTOMATION_LIMITS.md",
    "docs/context/CHATGPT_RECOVERY.md",
    "docs/context/CONTEXT_TRUTHS.md",
    "docs/context/CONTEXT_STATE.json",
    "docs/context/sources.json",
    "docs/context/protected-docs.json",
    "docs/procurement/HARK_CONTEXT.md",
)

AGENT_TOKENS = (
    "Context Brief",
    "Context Receipt",
    "DECISION_CHANGE.md",
    "BRANCH_HANDOFF_TEMPLATE.md",
    "check_context.py",
    "HARK_CONTEXT.md",
)


def normalize_commit(text: str) -> str:
    return COMMIT_LINE.sub("Source commit at generation: `<checked>`", text)


def check_sources(root: Path = cb.ROOT) -> list[str]:
    errors = []
    try:
        sources = cb.load_sources()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"sources.json: {exc}"]
    ids, paths = set(), set()
    for source in sources:
        source_id = source.get("id")
        relative = source.get("path")
        if not source_id or not isinstance(source_id, str):
            errors.append("source missing string id")
            continue
        if source_id in ids:
            errors.append(f"duplicate source id: {source_id}")
        ids.add(source_id)
        if not relative or not isinstance(relative, str):
            errors.append(f"{source_id}: missing path")
            continue
        if relative in paths:
            errors.append(f"duplicate source path: {relative}")
        paths.add(relative)
        if not (root / relative).is_file():
            errors.append(f"{source_id}: missing source file {relative}")
    return errors


def check_adrs() -> list[str]:
    try:
        adrs = cb.parse_adrs(cb.DECISIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"decisions: {exc}"]
    errors = []
    if not cb.active_decisions(adrs):
        errors.append("decisions: no accepted ADR")
    return errors


def check_adr_references() -> list[str]:
    try:
        adrs = cb.parse_adrs(cb.DECISIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"decisions: {exc}"]
    ids = {adr["id"] for adr in adrs}
    paths = [
        cb.ROOT / "AGENTS.md",
        cb.ROOT / "README.md",
        cb.ROOT / "docs/README.md",
        cb.ROOT / "docs/procurement/HARK_CONTEXT.md",
    ]
    paths.extend(sorted(cb.CONTEXT.rglob("*.md")))
    paths.extend(sorted(cb.CONTEXT.glob("*.json")))
    paths.extend(cb.ROOT / relative for relative in cb.PROTECTED_PATHS)
    try:
        paths.extend(cb.ROOT / source["path"] for source in cb.load_sources())
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    errors = []
    seen = set()
    for path in paths:
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        for token in sorted(set(re.findall(r"ADR-\d{3}", path.read_text(encoding="utf-8")))):
            if token not in ids:
                errors.append(f"{path.relative_to(cb.ROOT)}: missing decision ID {token}")
    return errors


def check_protected() -> list[str]:
    errors = []
    try:
        data = cb.read_json(cb.PROTECTED)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"protected-docs.json: {exc}"]
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        return ["protected-docs.json: files map missing"]
    for relative in cb.PROTECTED_PATHS:
        path = cb.ROOT / relative
        expected = files.get(relative)
        if not path.is_file():
            errors.append(f"protected document missing: {relative}")
            continue
        if not expected:
            errors.append(f"protected document not in manifest: {relative}")
        elif cb.sha256_file(path) != expected:
            errors.append(
                f"protected document changed without reviewed manifest update: {relative}"
            )
    for relative in sorted(set(files) - set(cb.PROTECTED_PATHS)):
        errors.append(f"manifest contains unknown protected path: {relative}")
    return errors


def check_brief_provenance() -> list[str]:
    if not cb.BRIEF.is_file():
        return ["generated brief missing"]
    text = cb.BRIEF.read_text(encoding="utf-8")
    commit_match = BRIEF_COMMIT.search(text)
    if not commit_match:
        return ["generated brief lacks a 40-hex source commit"]
    commit = commit_match.group(1)
    try:
        subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
            cwd=cb.ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return [
            f"recorded source commit is not available locally: {commit}; "
            "fetch full history (CI uses fetch-depth: 0)"
        ]
    rows = {path: expected for _, path, expected in BRIEF_SOURCE_ROW.findall(text)}
    try:
        sources = cb.load_sources()
        expected_paths = {source["path"] for source in sources}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot verify brief provenance: {exc}"]
    errors = []
    if set(rows) != expected_paths:
        errors.append(
            "generated brief source table does not match sources.json paths: "
            f"missing={sorted(expected_paths - set(rows))}, extra={sorted(set(rows) - expected_paths)}"
        )
    for path, expected in sorted(rows.items()):
        try:
            data = subprocess.check_output(
                ["git", "show", f"{commit}:{path}"],
                cwd=cb.ROOT,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            errors.append(f"source {path} is absent at recorded commit {commit}")
            continue
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            errors.append(f"source hash mismatch at recorded commit {commit}: {path}")
    return errors


def check_brief() -> list[str]:
    if not cb.BRIEF.is_file():
        return ["generated brief missing"]
    try:
        expected = normalize_commit(cb.build_brief(commit="<checked>"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"brief generation failed: {exc}"]
    actual = normalize_commit(cb.BRIEF.read_text(encoding="utf-8"))
    if actual != expected:
        return [
            "generated context brief is stale or hand-edited; "
            "run python tools/context_brief.py --write"
        ]
    return []


def check_required() -> list[str]:
    errors = [f"required context artifact missing: {relative}" for relative in REQUIRED if not (cb.ROOT / relative).is_file()]
    agents = cb.ROOT / "AGENTS.md"
    if not agents.is_file():
        errors.append("AGENTS.md missing")
    else:
        text = agents.read_text(encoding="utf-8")
        for token in AGENT_TOKENS:
            if token not in text:
                errors.append(f"AGENTS.md missing context token: {token}")
    return errors


def markdown_anchors(path: Path) -> set[str]:
    anchors, seen = set(), {}
    for match in HEADING.finditer(path.read_text(encoding="utf-8")):
        raw = re.sub(r"[`*_]", "", match.group(2)).strip().lower()
        slug = re.sub(r"[^\w\s-]", "", raw)
        slug = re.sub(r"\s+", "-", slug).strip("-")
        if not slug:
            continue
        count = seen.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return anchors


def local_link_errors(root: Path, paths: list[Path]) -> list[str]:
    errors = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            raw = match.group(1).strip()
            if raw.startswith("<") and raw.endswith(">"):
                raw = raw[1:-1].strip()
            if not raw or raw.startswith(("http://", "https://", "mailto:")):
                continue
            target, _, anchor = raw.partition("#")
            target = unquote(target.strip())
            if not target:
                resolved = path.resolve()
            else:
                resolved = (path.parent / target).resolve()
                try:
                    resolved.relative_to(root.resolve())
                except ValueError:
                    errors.append(f"{path.relative_to(root)}: link escapes repository: {raw}")
                    continue
                if not resolved.exists():
                    errors.append(f"{path.relative_to(root)}: missing link target: {raw}")
                    continue
            if anchor and resolved.suffix.lower() == ".md":
                if anchor not in markdown_anchors(resolved):
                    errors.append(f"{path.relative_to(root)}: missing anchor: {raw}")
    return errors


def check_links() -> list[str]:
    paths = sorted(cb.CONTEXT.rglob("*.md"))
    paths.extend([cb.ROOT / "docs/procurement/HARK_CONTEXT.md", cb.ROOT / "AGENTS.md"])
    paths.extend(cb.ROOT / relative for relative in cb.PROTECTED_PATHS)
    paths.append(cb.ROOT / "README.md")
    try:
        paths.extend(cb.ROOT / source["path"] for source in cb.load_sources())
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    deduped = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return local_link_errors(cb.ROOT, deduped)


def check_state() -> list[str]:
    try:
        state = cb.state()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"CONTEXT_STATE.json: {exc}"]
    errors = []
    if not state.get("protocol_version"):
        errors.append("CONTEXT_STATE.json: missing protocol_version")
    if not state["milestone"].get("status"):
        errors.append("CONTEXT_STATE.json: missing milestone.status")
    if not state.get("unresolved_questions"):
        errors.append("CONTEXT_STATE.json: unresolved_questions is empty")
    return errors


def check() -> dict:
    errors = []
    for func in (check_sources, check_adrs, check_adr_references, check_protected, check_brief_provenance, check_brief, check_required, check_links, check_state):
        try:
            errors.extend(func())
        except Exception as exc:  # keep the checker itself fail-closed
            errors.append(f"{func.__name__} crashed: {type(exc).__name__}: {exc}")
    try:
        adrs = cb.parse_adrs(cb.DECISIONS.read_text(encoding="utf-8"))
        accepted = len(cb.active_decisions(adrs))
    except Exception:
        accepted = 0
    try:
        source_count = len(cb.load_sources()) if cb.SOURCES.is_file() else 0
    except (OSError, ValueError, json.JSONDecodeError):
        source_count = 0
    return dict(
        status="FAIL" if errors else "PASS",
        errors=sorted(set(errors)),
        source_commit=cb.git_commit(),
        source_count=source_count,
        accepted_decisions=accepted,
        protected_documents=len(cb.PROTECTED_PATHS),
    )


def main() -> int:
    result = check()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
