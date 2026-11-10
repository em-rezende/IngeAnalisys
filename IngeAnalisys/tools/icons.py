# SPDX-License-Identifier: GPL-3.0-or-later
"""Theme-aware SVG icon loader for Site Analysis.

Icons live in ``icons/`` next to this file. Naming:

- ``<name>.svg``         dark theme (light strokes, e.g. #ffffff)
- ``<name>_light.svg``   light theme (dark strokes, e.g. #000000)

When a light-theme file is missing, the dark file is used. When neither
exists, the caller gets an *empty* QIcon (``isNull()`` is True) so the
toolbar can fall back to a Unicode glyph.
"""
from __future__ import annotations

import os

from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import QApplication

#: ``icons.py`` lives inside ``tools/``; the SVGs live in
#: ``<package>/icons/`` (one level up).
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_ICONS_DIR = os.path.join(_ROOT, "icons")

#: Cache: (name, dark?) -> QIcon
_CACHE: dict[tuple[str, bool], QIcon] = {}


def is_dark(window=None) -> bool:
    """True when the effective window background is dark."""
    try:
        win = window
        if win is None:
            qapp = QApplication.instance()
            win = qapp.activeWindow() if qapp else None
        if win is not None:
            bg = win.palette().color(QPalette.Window)
            return bg.lightness() < 128
    except Exception:
        pass
    return True


def _file(name: str, light: bool) -> str | None:
    if not _ICONS_DIR or not os.path.isdir(_ICONS_DIR):
        return None
    base = name[:-4] if name.endswith(".svg") else name
    candidates = (
        (os.path.join(_ICONS_DIR, f"{base}_light.svg"),
         os.path.join(_ICONS_DIR, f"{base}.svg"))
        if light else
        (os.path.join(_ICONS_DIR, f"{base}.svg"),)
    )
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def icon(name: str, window=None) -> QIcon:
    """Return the QIcon for ``name`` (SVG, theme-aware).

    Empty QIcon when the SVG cannot be found — the caller should then
    fall back to a Unicode glyph or a standard Qt icon.
    """
    light = not is_dark(window)
    key = (name, light)
    if key in _CACHE:
        return _CACHE[key]
    path = _file(name, light)
    ic = QIcon(path) if path else QIcon()
    _CACHE[key] = ic
    return ic


def glyph(name: str, fallback: str) -> str:
    """Unicode fallback for ``name`` (returned when the SVG is missing)."""
    return fallback