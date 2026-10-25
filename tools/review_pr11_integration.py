"""Temporary-tree PR11/approved PR10 integration rehearsal; no branch merges.

Local Git objects/history must contain the reviewed heads. All reconciliation,
manifest refreshes, synthetic commits and tests occur inside a temporary clone.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PR11 = "b58c96ef998e68e841b12d9ad671325053c009e4"
PR10 = "8a84369941c74d5f884c9ec6cc33d10395223597"
BASE = "f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corrections-ref", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)
    virtual = subprocess.run(["git", "merge-tree", "--write-tree", PR11, PR10],
        cwd=ROOT, text=True, capture_output=True)
    (args.out / "merge-tree.txt").write_text(virtual.stdout + virtual.stderr)
    if virtual.returncode != 1 or "CONFLICT (content): Merge conflict in docs/handbook/agent-handoff.md" not in virtual.stdout:
        raise RuntimeError("integration conflict surface changed; inspect before reconciliation")
    tree = virtual.stdout.splitlines()[0]
    with tempfile.TemporaryDirectory(prefix="pr11-integration-") as folder:
        root = Path(folder) / "repo"
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(root)], check=True)
        def run(command, check=True):
            return subprocess.run(command, cwd=root, text=True, capture_output=True,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), check=check)
        run(["git", "checkout", "--quiet", "--detach", PR11])
        run(["git", "read-tree", tree]); run(["git", "checkout-index", "-a", "-f"])
        canonical = git("show", PR11 + ":docs/handbook/agent-handoff.md").decode()
        previous = git("show", PR10 + ":docs/handbook/agent-handoff.md").decode()
        addition = previous.partition("**Open independent-review packet:")[0].split("\n", 1)[1]
        # Relocation changes relative link depth; original content/SHAs remain.
        addition = addition.replace("](../", "](../../")
        (root / "docs/context/handoffs/approved-pr10-bench-evidence.md").write_text(
            "# Synthetic integration evidence — PR10\n\nSimulation only; neither PR is merged. Approved PR10's historical handoff additions follow; links adjusted for location.\n" + addition)
        (root / "docs/handbook/agent-handoff.md").write_text(canonical +
            "\n## Virtual integration checkpoint (not main)\n\nApproved PR10 evidence: [branch handoff](../context/handoffs/approved-pr10-bench-evidence.md). No physical test authorization.\n")
        changed = git("diff", "--name-only", BASE + ".." + PR10).decode().splitlines()
        preserved = {f: git("show", PR10 + ":" + f) == (root / f).read_bytes()
            for f in changed if f not in ("docs/README.md", "docs/handbook/agent-handoff.md")}
        if not all(preserved.values()):
            raise RuntimeError("approved PR10 content lost")
        before = run([sys.executable, "tools/check_context.py"], check=False)
        (args.out / "before-refresh.json").write_text(before.stdout)
        patch = git("diff", "--binary", PR11 + ".." + args.corrections_ref)
        subprocess.run(["git", "apply", "--binary"], cwd=root, input=patch, check=True)
        run([sys.executable, "tools/context_brief.py", "--update-protected"])
        run(["git", "config", "user.name", "Virtual Integration Probe"])
        run(["git", "config", "user.email", "probe@invalid.local"])
        run(["git", "add", "-A"])
        run(["git", "commit", "--quiet", "-m", "Synthetic integration only; no branch merged"])
        run([sys.executable, "tools/context_brief.py", "--write"])
        context = run([sys.executable, "tools/check_context.py"], check=False)
        tests = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not hardware"], check=False)
        architecture = run([sys.executable, "tools/check_architecture.py"], check=False)
        for name, result in (("context", context), ("python", tests), ("architecture", architecture)):
            (args.out / (name + ".log")).write_text(result.stdout + result.stderr)
        result = dict(actual_branches_merged=False, original_handoff_conflict=True,
            original_head=PR11, approved_pr10=PR10, corrections=args.corrections_ref,
            preserved_pr10=preserved, context_exit=context.returncode,
            pytest_exit=tests.returncode, architecture_exit=architecture.returncode)
        (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(tests.stdout[-400:]); print(json.dumps(result, indent=2))
        return 0 if context.returncode == tests.returncode == architecture.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
