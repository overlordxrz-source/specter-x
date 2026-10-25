#!/usr/bin/env python3
"""Generate the compact SPECTER-X context brief.

The brief is a derived index over canonical repository sources. It is not a
source of evidence and must not be hand-edited. Run:

    python tools/context_brief.py --write
    python tools/context_brief.py --print
    python tools/context_brief.py --update-protected

`python tools/check_context.py` verifies the generated brief, source hashes,
ADR IDs, protected-document hashes and local links.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "docs" / "context"
BRIEF = CONTEXT / "CONTEXT_BRIEF.md"
SOURCES = CONTEXT / "sources.json"
STATE = CONTEXT / "CONTEXT_STATE.json"
TRUTHS = CONTEXT / "CONTEXT_TRUTHS.md"
DECISIONS = ROOT / "docs" / "handbook" / "decisions.md"
PROTECTED = CONTEXT / "protected-docs.json"

PROTECTED_PATHS = (
    "AGENTS.md",
    "docs/handbook/north-star.md",
    "docs/handbook/architecture.md",
    "docs/handbook/decisions.md",
    "docs/handbook/research-ideas.md",
    "docs/handbook/experiment-ledger.md",
    "docs/handbook/hardware-inventory.md",
    "docs/handbook/roadmap.md",
    "docs/handbook/agent-handoff.md",
    "docs/architecture/ENGINEERING_CONTRACT.md",
    "docs/context/CONTEXT_TRUTHS.md",
    "docs/context/README.md",
    "docs/context/CONTEXT_RECEIPT.md",
    "docs/context/DECISION_CHANGE.md",
    "docs/context/BRANCH_HANDOFF_TEMPLATE.md",
    "docs/context/AUTOMATION_LIMITS.md",
    "docs/context/CHATGPT_RECOVERY.md",
    "docs/procurement/HARK_CONTEXT.md",
)

ADR_HEADING = re.compile(r"^## (ADR-(\d{3}))\s+—\s+(.+)$", re.MULTILINE)
ADR_ANY = re.compile(r"^#{1,6}\s+ADR(?:\b|[- ]).*$", re.MULTILINE)
ADR_STATUS = re.compile(r"\*\*Status:\*\*\s*([^\n]+)")
VALID_STATUS = ("accepted", "proposed", "superseded")
STATUS_ALIASES = {"accepted research policy": "accepted"}  # historical ADR-004


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


def load_sources() -> list[dict]:
    data = read_json(SOURCES)
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources.json must contain a non-empty sources list")
    return sources


def parse_adrs(text: str) -> list[dict]:
    for line in ADR_ANY.finditer(text):
        if not ADR_HEADING.match(line.group(0)):
            raise ValueError(f"malformed ADR heading: {line.group(0).strip()!r}")
    matches = list(ADR_HEADING.finditer(text))
    adrs = []
    for index, match in enumerate(matches):
        section = text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        status_match = ADR_STATUS.search(section)
        if not status_match:
            raise ValueError(f"{match.group(1)}: missing **Status:** line")
        raw_status = status_match.group(1).strip()
        status = raw_status.split("·", 1)[0].strip().lower()
        status = STATUS_ALIASES.get(status, status)
        if status not in VALID_STATUS:
            raise ValueError(f"{match.group(1)}: invalid status {raw_status!r}")
        adrs.append(
            dict(
                id=match.group(1),
                number=int(match.group(2)),
                title=match.group(3).strip(),
                status=status,
                raw_status=raw_status,
            )
        )
    if not adrs:
        raise ValueError("no ADR headings found")
    expected = list(range(1, len(adrs) + 1))
    actual = [adr["number"] for adr in adrs]
    if actual != expected:
        raise ValueError(f"ADR numbering must be sequential 1..{len(adrs)}; got {actual}")
    return adrs


def active_decisions(adrs: list[dict]) -> list[dict]:
    return [adr for adr in adrs if adr["status"] == "accepted"]


def state() -> dict:
    data = read_json(STATE)
    milestone = data.get("milestone")
    if not isinstance(milestone, dict) or not milestone.get("id") or not milestone.get("name"):
        raise ValueError("CONTEXT_STATE.json requires milestone.id and milestone.name")
    unresolved = data.get("unresolved_questions")
    if not isinstance(unresolved, list):
        raise ValueError("CONTEXT_STATE.json requires unresolved_questions list")
    ids = [item.get("id") for item in unresolved if isinstance(item, dict)]
    if len(ids) != len(unresolved) or len(set(ids)) != len(ids):
        raise ValueError("unresolved question IDs must be unique strings")
    return data


def _truths_body() -> str:
    text = TRUTHS.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def build_brief(commit: str | None = None) -> str:
    sources = load_sources()
    adrs = parse_adrs(DECISIONS.read_text(encoding="utf-8"))
    state_data = state()
    source_lines = []
    for source in sources:
        path = ROOT / source["path"]
        if not path.is_file():
            raise ValueError(f"source missing: {source['path']}")
        source_lines.append(
            f"| `{source['id']}` | `{source['path']}` | `{sha256_file(path)}` | {source['role']} |"
        )
    accepted = active_decisions(adrs)
    decision_lines = "\n".join(
        f"- **{adr['id']}** — {adr['title']} (`{adr['raw_status']}`)" for adr in accepted
    )
    unresolved = "\n".join(
        f"- **{item['id']}** — {item.get('question', '')} "
        f"(`{item.get('status', 'open')}`; owner: {item.get('owner', 'unknown')})"
        for item in state_data["unresolved_questions"]
    )
    milestone = state_data["milestone"]
    commit_value = commit or git_commit()
    return f"""# SPECTER-X Context Brief

<!-- generated by tools/context_brief.py; do not edit by hand -->

Protocol version: **{state_data.get('protocol_version', 'UNKNOWN')}**
Source commit at generation: `{commit_value}`

This is a compact recovery index over canonical repository sources. It is
**not** evidence, a capability promotion, an owner authorization or a substitute
for the linked documents. If this Brief disagrees with a canonical source, stop
and produce a Context Receipt.

## Accepted context truths

{_truths_body()}

## Active accepted decisions

{decision_lines}

## Current milestone

- **{milestone.get('id')} — {milestone.get('name')}**: {milestone.get('status', 'UNKNOWN')}
- {milestone.get('summary', 'No summary recorded.')}
- Next action: {milestone.get('next_action', 'Not recorded.')}

## Unresolved questions

{unresolved}

## Authoritative source revisions

| ID | Path | SHA-256 | Role |
|---|---|---|---|
{chr(10).join(source_lines)}

## Required recovery receipt

Before materially changing direction, fill in `docs/context/CONTEXT_RECEIPT.md`
with this commit, these source hashes, the active ADRs applied, contradictions,
unknowns and authorization. If a proposal contradicts an accepted ADR, use
`docs/context/DECISION_CHANGE.md`; owner approval is required before adoption.
A brief read is not a permission grant.
"""


def write_brief() -> Path:
    BRIEF.write_text(build_brief(), encoding="utf-8")
    return BRIEF


def update_protected() -> Path:
    files = {}
    for relative in PROTECTED_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"protected document missing: {relative}")
        files[relative] = sha256_file(path)
    PROTECTED.write_text(
        json.dumps(
            {"schema": "specter.context.protected/1.0.0", "files": files},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return PROTECTED


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the brief")
    group.add_argument("--print", action="store_true", dest="print_brief", help="print the brief")
    group.add_argument("--update-protected", action="store_true", help="update protected-document hashes")
    args = parser.parse_args(argv)
    if args.write:
        print(write_brief())
    elif args.print_brief:
        print(build_brief())
    elif args.update_protected:
        print(update_protected())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
