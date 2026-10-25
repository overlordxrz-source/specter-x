"""Offline adversarial context checks in disposable clones; never changes source checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results = []
    with tempfile.TemporaryDirectory(prefix='context-probes-') as folder:
        root = Path(folder) / 'repo'
        subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(ROOT), str(root)], check=True)
        def run(*command):
            return subprocess.run(command, cwd=root, capture_output=True, text=True,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        def require(*command):
            result = run(*command)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result
        require('git', 'checkout', '--quiet', '--detach', args.ref)
        require('git', 'config', 'user.name', 'Disposable Context Probe')
        require('git', 'config', 'user.email', 'probe@invalid.local')
        def append(path, text):
            p = root / path
            p.write_text(p.read_text() + text)
        cases = ['baseline', 'missing_source', 'tampered_hash', 'stale_state',
                 'invalid_adr_reference', 'protected_unrefreshed',
                 'governance_refreshed_without_brief', 'unauthorized_all_refreshed',
                 'invalid_status_prefix']
        for case in cases:
            require('git', 'reset', '--hard', args.ref)
            generation = None
            if case == 'missing_source':
                (root / 'docs/handbook/north-star.md').unlink()
            elif case == 'tampered_hash':
                p = root / 'docs/context/CONTEXT_BRIEF.md'
                import re
                p.write_text(re.sub(r'(\| `AGENTS.md` \| `)[0-9a-f]{64}', r'\g<1>' + '0'*64, p.read_text()))
            elif case == 'stale_state':
                p = root / 'docs/context/CONTEXT_STATE.json'
                data = json.loads(p.read_text())
                data['milestone']['name'] += ' MUTATION'
                p.write_text(json.dumps(data))
            elif case == 'invalid_adr_reference':
                append('docs/context/CONTEXT_RECEIPT.md', '\nProbe ADR-999\n')
            elif case in ('protected_unrefreshed', 'unauthorized_all_refreshed'):
                append('docs/handbook/north-star.md', '\nDisposable probe: no owner approval was obtained.\n')
            elif case == 'governance_refreshed_without_brief':
                append('docs/context/DECISION_CHANGE.md', '\nDisposable process revision.\n')
            elif case == 'invalid_status_prefix':
                p = root / 'docs/handbook/decisions.md'
                text = p.read_text()
                prefix, section = text.split('## ADR-007', 1)
                p.write_text(prefix + '## ADR-007' + section.replace('**Status:** accepted ·', '**Status:** accepted_pending_owner_approval ·', 1))
            if case in ('governance_refreshed_without_brief', 'unauthorized_all_refreshed', 'invalid_status_prefix'):
                require(sys.executable, 'tools/context_brief.py', '--update-protected')
                require('git', 'add', '-A')
                require('git', 'commit', '--quiet', '-m', 'Disposable synthetic context mutation')
                if case != 'governance_refreshed_without_brief':
                    generation = run(sys.executable, 'tools/context_brief.py', '--write')
            checked = run(sys.executable, 'tools/check_context.py')
            (args.out / (case + '.log')).write_text(checked.stdout + checked.stderr)
            results.append(dict(case=case, exit_code=checked.returncode,
                checker_output=checked.stdout, generation_exit=None if generation is None else generation.returncode,
                generation_error=None if generation is None else generation.stderr))
        (args.out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps([{k:v for k,v in r.items() if k in ('case','exit_code','generation_exit')} for r in results], indent=2))


if __name__ == '__main__':
    main()
