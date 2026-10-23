# CI workflows

## Automatic — `pytest.yml`

Runs on:

- pushes to `main`;
- pull requests (including draft PRs);
- manual `workflow_dispatch`.

It installs `requirements-ci.txt` and runs:

```text
python -m pytest -q -m "not hardware"
```

The job is deterministic and offline. It uses OpenCV headless and includes
`pyserial` because the ESP32 integration tests import `serial` while faking
the port. `pip check` catches an inconsistent dependency set before tests.

Feature-branch pushes without a PR do **not** run this workflow. A PR gets one
run per update; the concurrency group cancels superseded runs.

## Manual — `hardware-tests.yml`

Runs only by `workflow_dispatch` on a self-hosted runner labelled `hardware`.
It runs:

```text
python -m pytest -q -m hardware
```

Tests carrying `@pytest.mark.hardware` require an attached instrument or board.
They are excluded from automatic CI. If no hardware runner is registered, the
manual job queues rather than running on a hosted machine.

## Local reproduction

```bash
python3.11 -m venv .venv-ci
.venv-ci/bin/pip install -r requirements-ci.txt
.venv-ci/bin/python -m pytest -q -m "not hardware"
```

For a machine with hardware attached, run the marked suite explicitly:

```bash
.venv-ci/bin/python -m pytest -q -m hardware
```

Do not weaken or delete a test to make CI green. If a test needs hardware,
mark it and put it in the manual workflow; if a dependency is required, add it
to the dependency set and reproduce in a clean environment.
