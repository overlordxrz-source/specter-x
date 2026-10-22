"""The SPECTER-X visual theme.

One source of truth for the palette and the type scale, so the HUD reads as
a single instrument rather than a collection of panels that happen to sit on
the same screen.

The palette is a **deep burgundy / charcoal** ground with **muted crimson and
rose** accents. It is deliberately desaturated: on a 7" panel in a dim room
the screen is the only light source, and saturated primaries buzz.

Two rules the palette has to keep:

* **Health stays legible.** The OK / DEGRADED / FAULT colours are muted, not
  the same as the accents, so a state can never be mistaken for decoration.
* **Nothing is drawn that the sensor did not say.** A colour is a claim. If
  the value behind it is unknown, the value is drawn as unknown.

Colours are OpenCV **BGR** triples.
"""
from __future__ import annotations

from typing import Sequence, Tuple

import cv2
import numpy as np

# --- ground -----------------------------------------------------------------
BG = (16, 12, 16)              # the page
BG_DEEP = (11, 8, 12)          # recessed wells (waterfall, trace)
PANEL = (24, 18, 22)           # a card
PANEL_HI = (31, 23, 28)        # a card that is live / selected
RULE = (56, 47, 55)            # a hard separator
RULE_SOFT = (37, 31, 37)       # a soft separator

# --- accents ----------------------------------------------------------------
BURGUNDY = (44, 21, 56)        # the brand ground
BURGUNDY_DEEP = (30, 15, 39)
CRIMSON = (80, 46, 160)        # the primary accent
ROSE = (122, 98, 184)          # the secondary accent
ROSE_DIM = (95, 76, 138)
ROSE_PALE = (168, 150, 205)

# --- type -------------------------------------------------------------------
TEXT = (226, 218, 218)
TEXT_DIM = (136, 126, 130)
TEXT_FAINT = (94, 86, 90)

# --- health (never the same as an accent) -----------------------------------
OK = (126, 176, 130)           # muted sage
WARN = (70, 156, 212)          # muted amber
FAULT = (86, 58, 202)          # crimson
SIM = (150, 122, 192)          # rose, for a simulated source

FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_MONO = cv2.FONT_HERSHEY_PLAIN

#: The type scale. Four sizes, no more - the restraint is the point.
T_MICRO = 0.36
T_SMALL = 0.44
T_LABEL = 0.52
T_VALUE = 0.66
T_TITLE = 0.86
T_HERO = 1.05


def health_color(value) -> Tuple[int, int, int]:
    """Map a health word to its colour. Unknown words are never green."""
    word = getattr(value, "value", value)
    word = str(word or "").upper()
    if word in ("OK", "CONNECTED", "HEALTHY", "AVAILABLE"):
        return OK
    if word in ("DEGRADED", "STALLED", "CONNECTING", "SIMULATED", "NOT_INSTALLED"):
        return WARN if word != "SIMULATED" else SIM
    if word in ("OFFLINE", "ERROR", "FAULT", "DISCONNECTED"):
        return FAULT
    return TEXT_DIM


def text(img, s: str, org, scale: float = T_SMALL, color=TEXT, thick: int = 1,
         shadow: bool = True):
    """Draw text with a soft shadow, so it stays readable over any ground."""
    x, y = int(org[0]), int(org[1])
    if shadow:
        cv2.putText(img, s, (x, y + 1), FONT, scale, (0, 0, 0), thick, cv2.LINE_AA)
    cv2.putText(img, s, (x, y), FONT, scale, color, thick, cv2.LINE_AA)


def label(img, s: str, org, color=TEXT_DIM, scale: float = T_LABEL):
    """A small uppercase field label."""
    text(img, str(s).upper(), org, scale, color, 1)


def value(img, s: str, org, color=TEXT, scale: float = T_VALUE):
    """A value."""
    text(img, str(s), org, scale, color, 1)


def rule(img, x0: int, y0: int, x1: int, y1: int, color=RULE, thick: int = 1):
    cv2.line(img, (int(x0), int(y0)), (int(x1), int(y1)), color, thick, cv2.LINE_AA)


def card(img, x0: int, y0: int, x1: int, y1: int, fill=PANEL, border=RULE,
         border_thick: int = 1):
    """A card: a filled panel with a one-pixel border."""
    cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), fill, -1)
    if border is not None:
        cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), border,
                      border_thick, cv2.LINE_AA)


def well(img, x0: int, y0: int, x1: int, y1: int, fill=BG_DEEP, border=RULE_SOFT):
    """A recessed well - for data surfaces that sit *inside* a card."""
    cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), fill, -1)
    if border is not None:
        cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), border, 1,
                      cv2.LINE_AA)


def accent_bar(img, x0: int, y0: int, x1: int, y1: int, color=CRIMSON,
               thickness: int = 2):
    """The short accent bar that marks a section without shouting."""
    cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y0 + thickness)), color, -1)


def _lerp(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def waterfall_lut(size: int = 256) -> np.ndarray:
    """The colour ramp for the subcarrier waterfall.

    Deep burgundy in the troughs, crimson in the body, rose towards the top
    and a pale warm highlight at the extreme. It is monotonic in lightness so
    that the picture can be read even by someone who cannot separate the
    hues.
    """
    stops = [
        (0.00, (10, 6, 14)),      # near black
        (0.18, (34, 16, 40)),     # deep burgundy
        (0.45, (70, 34, 84)),     # burgundy
        (0.68, (104, 60, 132)),   # crimson-rose
        (0.86, (150, 116, 186)),  # rose
        (1.00, (222, 200, 236)),  # pale highlight
    ]
    lut = np.zeros((size, 3), np.uint8)
    for i in range(size):
        t = i / (size - 1)
        for j in range(len(stops) - 1):
            t0, c0 = stops[j]
            t1, c1 = stops[j + 1]
            if t0 <= t <= t1:
                k = (t - t0) / max(t1 - t0, 1e-9)
                lut[i] = _lerp(c0, c1, k)
                break
        else:
            lut[i] = stops[-1][1]
    return lut


def trace_lut(size: int = 256) -> np.ndarray:
    """The colour ramp for the signal-change trace."""
    stops = [
        (0.00, (18, 14, 20)),
        (0.35, (52, 32, 62)),
        (0.70, (112, 66, 142)),
        (1.00, (188, 140, 214)),
    ]
    lut = np.zeros((size, 3), np.uint8)
    for i in range(size):
        t = i / (size - 1)
        for j in range(len(stops) - 1):
            t0, c0 = stops[j]
            t1, c1 = stops[j + 1]
            if t0 <= t <= t1:
                k = (t - t0) / max(t1 - t0, 1e-9)
                lut[i] = _lerp(c0, c1, k)
                break
        else:
            lut[i] = stops[-1][1]
    return lut
