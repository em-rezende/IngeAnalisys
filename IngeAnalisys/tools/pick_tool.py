# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""One-click tools (with inferences): place an annotation, the solar
diagram center… They are created when requested, never at module level:
a ``Tool`` class in the module would get its own entry in the Extensions
menu (core/extensions.py), and the entry is the panel.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QVector3D

from .i18n import tr


def make_pick_tool(prompt: str, done, cancelled, repeat: bool = False):
    """``done(point, ctx)`` with the INFERRED point (endpoint, face, axis…);
    ``cancelled()`` with Esc. With ``repeat`` it stays active after each
    click (several annotations in a row) until Esc."""
    from tools.base import Tool

    class _PickPoint(Tool):
        name = prompt
        shortcut = None
        uses_snap = True

        def __init__(self) -> None:
            self.hover_point = None

        def on_activate(self, viewport) -> None:
            self.hover_point = None

        def on_deactivate(self, viewport) -> None:
            self.hover_point = None

        def on_hover(self, ctx) -> None:
            self.hover_point = ctx.world
            ctx.viewport.update()

        def on_click(self, ctx) -> None:
            # Pega a entidade clicada no contexto do IngeTrazo
            target = getattr(ctx, "entity", None)
            
            # Passa o ponto, o contexto e o alvo para a função 'done'
            done(QVector3D(ctx.world), ctx, target)
            if not repeat:
                cancelled()

        def on_key(self, viewport, key, modifiers) -> bool:
            if key == Qt.Key_Escape:
                cancelled()
                return True
            return False

        def rubber_band_lines(self):
            return []

    return _PickPoint()


def begin(app, tool, prompt: str) -> None:
    vp = app.viewport
    vp.set_active_tool(tool)
    try:
        app.window.statusBar().showMessage(tr("{prompt} — Esc cancels",
                                              prompt=prompt))
    except Exception:                               # noqa: BLE001
        pass
    vp.setFocus()


def end(app) -> None:
    win = app.window
    try:
        win.statusBar().clearMessage()
    except Exception:                               # noqa: BLE001
        pass
    activate = getattr(win, "_activate_tool", None)
    if callable(activate):
        activate("select")