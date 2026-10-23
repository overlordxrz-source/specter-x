"""Hash and syntax-check the complete source/config surface without executing it.

Usage: python tools/audit_inventory.py --root . --out /private/audit.json
Not a semantic proof, coverage measurement or firmware build.
"""

from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

EXTENSIONS = {
    ".py",
    ".js",
    ".cjs",
    ".c",
    ".h",
    ".sh",
    ".command",
    ".toml",
    ".yml",
    ".yaml",
    ".css",
    ".html",
    ".json",
}


def inventory(root):
    paths = []
    for directory in ("specter", "firmware", "tools", "tests", ".github"):
        base = root / directory
        if base.exists():
            paths.extend(
                p
                for p in base.rglob("*")
                if p.is_file()
                and not any(
                    part in {"__pycache__", "build", "node_modules"} for part in p.parts
                )
            )
    paths.extend(p for p in root.iterdir() if p.is_file())
    result = []
    for p in sorted(set(paths)):
        if p.suffix not in EXTENSIONS and not p.name.startswith("requirements"):
            continue
        raw = p.read_bytes()
        row = {
            "path": str(p.relative_to(root)),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "lines": len(raw.splitlines()),
            "syntax": "NOT_CHECKED",
            "semantic_review": "NOT_CERTIFIED_LINE_BY_LINE",
        }
        try:
            if p.suffix == ".py":
                ast.parse(raw, filename=str(p))
                row["syntax"] = "PASS_PYTHON_AST"
            elif p.suffix in {".js", ".cjs"}:
                check = subprocess.run(
                    ["node", "--check", str(p)], capture_output=True, text=True
                )
                row["syntax"] = "PASS_NODE_CHECK" if check.returncode == 0 else "FAIL"
                if check.returncode:
                    row["error"] = check.stderr[:2048]
            elif p.suffix == ".json":
                json.loads(raw)
                row["syntax"] = "PASS_JSON"
        except (ValueError, SyntaxError) as exc:
            row.update(syntax="FAIL", error=str(exc))
        result.append(row)
    return {
        "root": str(root),
        "files": len(result),
        "lines": sum(r["lines"] for r in result),
        "failures": sum(r["syntax"] == "FAIL" for r in result),
        "scope": "All source/config/test files under listed code roots; excludes build/cache, raw runs and prose. Static syntax is not semantic review.",
        "entries": result,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    data = inventory(args.root.resolve())
    args.out.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({k: v for k, v in data.items() if k != "entries"}, indent=2))
    return bool(data["failures"])


if __name__ == "__main__":
    raise SystemExit(main())
