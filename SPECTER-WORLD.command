#!/bin/zsh
# Offline research desktop. No serial/camera acquisition.
set -eu
specter_dir=${0:A:h}
cd "$specter_dir"
specter_python="${SPECTER_X_PYTHON:-$specter_dir/.venv/bin/python}"
if [[ ! -x "$specter_python" ]]; then
  specter_python="$specter_dir/../specter-x/.venv/bin/python"
fi
if [[ ! -x "$specter_python" ]]; then
  print 'Create the project Python environment first; see docs/world/README.md.'
  exit 1
fi
specter_capture="${SPECTER_WORLD_CAPTURE:-$specter_dir/../specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi}"
export PYTHONDONTWRITEBYTECODE=1
if [[ -f "$specter_capture" ]]; then
  exec "$specter_python" -m specter.world --replay "$specter_capture" --root "$specter_dir/docs/checkpoints" --root "$specter_dir/docs/handbook"
else
  exec "$specter_python" -m specter.world --root "$specter_dir/docs/checkpoints" --root "$specter_dir/docs/handbook"
fi
