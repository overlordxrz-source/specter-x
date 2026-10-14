"""EXPERIMENTAL modules: stub drivers + simulators, real drivers later.

Everything here is marked EXPERIMENTAL and UNVERIFIED. Each module ships a
stub driver (hardware path opens lazily, never at import) and a Synthetic*
source so CI exercises the Measurement path. Nothing experimental claims
certainty: confidences are capped and notes say so.
"""
from .acoustic import SyntheticAcousticArray
from .event_camera import SyntheticEventCamera
from .gas import SyntheticGas
from .lora import LoRaFallback
from .vitals import SyntheticVitals
from .vlm import summarize_tracks

EXPERIMENTAL = True

__all__ = [
    "EXPERIMENTAL",
    "LoRaFallback",
    "SyntheticAcousticArray",
    "SyntheticEventCamera",
    "SyntheticGas",
    "SyntheticVitals",
    "summarize_tracks",
]
