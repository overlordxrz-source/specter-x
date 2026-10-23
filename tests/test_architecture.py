"""Dependency gate controls: real closure plus deliberate direct/indirect violations."""

from pathlib import Path
import pytest
from tools.check_architecture import check_boundary, ROOT, REQUIRED


def test_offline_world_boundary():
    result = check_boundary(ROOT)
    assert not result["errors"], result["errors"]
    assert "specter.sensors.esp32.dispatcher" in result["modules"]
    assert all((ROOT / p).is_file() for p in REQUIRED)


@pytest.mark.parametrize(
    "bad",
    [
        "import serial",
        "from specter.net import transport",
        '__import__("serial")',
        "import subprocess",
    ],
)
def test_dependency_violation_cannot_hide_behind_wrapper(tmp_path, bad):
    world = tmp_path / "specter/world"
    world.mkdir(parents=True)
    (world / "__init__.py").write_text("from . import helper\n")
    helper = world / "helper.py"
    helper.write_text("import json\n")
    assert not check_boundary(tmp_path)["errors"]
    helper.write_text(bad + "\n")
    assert check_boundary(tmp_path)["errors"]
