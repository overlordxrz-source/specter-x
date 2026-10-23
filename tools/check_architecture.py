"""Static offline-WORLD dependency gate; never imports inspected application code.

This is a review aid, not a Python sandbox. Run from any directory.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "AGENTS.md",
    "docs/handbook/north-star.md",
    "docs/architecture/ENGINEERING_CONTRACT.md",
    "docs/architecture/WORK_ORDER.md",
)
PURE_SENSOR = {
    "specter.sensors",
    "specter.sensors.esp32",
    "specter.sensors.esp32.dispatcher",
    "specter.sensors.esp32.protocol",
}
BLOCKED_EXTERNAL = {
    "serial",
    "picamera2",
    "ultralytics",
    "spidev",
    "smbus",
    "smbus2",
    "subprocess",
}
BLOCKED_INTERNAL = (
    "specter.net",
    "specter.localization",
    "specter.fusion.team",
    "specter.app",
    "specter.ml",
    "specter.hw",
)


def check_boundary(root: Path) -> dict:
    modules = {}
    for p in (root / "specter").rglob("*.py"):
        parts = list(p.relative_to(root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = p
    queue = [
        m for m in modules if m == "specter.world" or m.startswith("specter.world.")
    ]
    seen, errors = set(), []
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        p = modules[module]
        tree = ast.parse(p.read_text(), filename=str(p))
        package = module if p.name == "__init__.py" else module.rpartition(".")[0]
        dependencies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.extend((a.name, node.lineno) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parents = package.split(".")
                    base = ".".join(
                        parents[: len(parents) - node.level + 1]
                        + ([base] if base else [])
                    )
                dependencies.append((base, node.lineno))
                dependencies.extend(
                    (base + "." + a.name, node.lineno)
                    for a in node.names
                    if base + "." + a.name in modules
                )
            elif isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name in {
                    "__import__",
                    "eval",
                    "exec",
                    "importlib.import_module",
                    "import_module",
                }:
                    errors.append(
                        f"{p.relative_to(root)}:{node.lineno}: dynamic execution/import {name}"
                    )
        for dep, line in dependencies:
            blocked = (
                dep.split(".")[0] in BLOCKED_EXTERNAL
                or any(dep == b or dep.startswith(b + ".") for b in BLOCKED_INTERNAL)
                or (dep.startswith("specter.sensors.") and dep not in PURE_SENSOR)
            )
            if blocked:
                errors.append(
                    f"{p.relative_to(root)}:{line}: offline WORLD cannot import {dep}"
                )
                continue
            # Importing a submodule also executes each package initializer.
            for i in range(1, len(dep.split(".")) + 1):
                prefix = ".".join(dep.split(".")[:i])
                if prefix in modules and prefix not in seen:
                    queue.append(prefix)
    return {"modules": sorted(seen), "errors": sorted(set(errors))}


def main() -> int:
    result = check_boundary(ROOT)
    result["errors"].extend(
        f"missing required document: {p}" for p in REQUIRED if not (ROOT / p).is_file()
    )
    result["status"] = "FAIL" if result["errors"] else "PASS"
    print(json.dumps(result, indent=2))
    return bool(result["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
