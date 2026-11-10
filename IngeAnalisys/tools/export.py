# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""Outputs: view image with the analysis and climate charts.

OBJ, SKP, DXF and IFC of the masses come from IngeTrazo (File ▸ Export):
the masses are ordinary model geometry.
"""
from __future__ import annotations

from PySide6.QtGui import QPainter

from . import climate
from .actions import SiteError
from .i18n import tr


def render_png(sitio, overlay, width: int):
    """The current view at ``width`` px wide, with the analysis on top
    (and the info panel if it is visible)."""
    vp = sitio.app.viewport
    img = vp.render_image(int(width), sharp_shadows=True)
    if img is None:
        raise SiteError(tr("The view is not ready to be exported."))
    p = QPainter(img)
    p.scale(img.width() / max(1, vp.width()),
            img.height() / max(1, vp.height()))
    overlay.draw(vp, p, export=True)
    p.end()
    return img


def export_png(sitio, overlay, path: str, width: int = 1920) -> str:
    img = render_png(sitio, overlay, width)
    if not img.save(path):
        raise SiteError(tr("Could not save {path}.", path=path))
    return path


def export_charts(sitio, base_path: str) -> list[str]:
    from .charts import chart_image
    stats = sitio.stats()
    if not stats:
        raise SiteError(tr("Load an EPW file first."))
    w = sitio.store.view()["wind"]
    cols = climate.rose_colors(w.get("pal", "amber"), w.get("c0"), w.get("c1"))
    stem = base_path[:-4] if base_path.lower().endswith(".png") else base_path
    out = []
    for kind, suffix in (("rose", "_rose.png"), ("months", "_months.png")):
        path = stem + suffix
        if not chart_image(kind, stats, cols).save(path):
            raise SiteError(tr("Could not save {path}.", path=path))
        out.append(path)
    return out