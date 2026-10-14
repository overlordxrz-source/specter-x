"""Team simulator package: multi-unit virtual walk for CI."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # lazy: `python -m specter.sim.team` must not pre-import the module
    from .team import VirtualUnit, run_team

__all__ = ["VirtualUnit", "run_team"]


def __getattr__(name: str):
    if name in __all__:
        from . import team as _team

        return getattr(_team, name)
    raise AttributeError(f"specter.sim has no {name!r}")
