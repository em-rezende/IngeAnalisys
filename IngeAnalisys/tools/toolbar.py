# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""Unified toolbar (19 buttons, organized by panel section)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QSizePolicy, QToolBar, QWidget

from . import actions as act
from .i18n import tr
from .icons import icon as svg_icon

TOOLBAR_NAME = "analisis_sitio_toolbar"
ICON_PX = 22


def _add(tb, glyph, svg_name, tooltip, slot, *, shortcut=None,
         checkable=False, checked=False):
    ic = svg_icon(svg_name, tb.window())
    if not ic.isNull():
        a = QAction(ic, "", tb)
    else:
        a = QAction(glyph, tb)
    tip = tr(tooltip)
    a.setToolTip(f"{tip}  ({shortcut})" if shortcut else tip)
    a.setStatusTip(tip)
    if shortcut:
        a.setShortcut(QKeySequence(shortcut))
        a.setShortcutContext(Qt.WindowShortcut)
    a.setCheckable(bool(checkable))
    if checkable:
        a.setChecked(bool(checked))
    if slot is not None:
        a.triggered.connect(slot)
    tb.addAction(a)
    return a

def build(app, sitio, panel, dock):
    tb = QToolBar(tr("Site Analysis"), app.window)
    tb.setObjectName(TOOLBAR_NAME)
    tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
    tb.setIconSize(QSize(ICON_PX, ICON_PX))
    tb.setMovable(True)
    tb.setFloatable(True)
    tb.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    # Section 1 · EPW
    _add(tb, "☁", "epw", "Open EPW…",
         panel._on_open_epw, shortcut="Shift+Y")

    # Section 2 · Location
    _add(tb, "⌖", "pin", "Pick location on the map…",
         panel._on_pick_map, shortcut="Shift+K")

    # Section 3 · North
    _add(tb, "➤", "north", "Set north from selected edge",
         panel._on_pick_north_edge, shortcut="Shift+C")

    # Section 4 · Time
    eye = _add(tb, "👁", "eye", "Show / hide analysis",
               lambda checked: (act.toggle_analysis(sitio), panel.refresh()),
               shortcut="Shift+H", checkable=True,
               checked=bool(sitio.store.view().get("on", True)))
    tb._eye_action = eye

    play = _add(tb, "▶", "play", "Animate the sun path",
                panel._on_anim, shortcut="Shift+Space", checkable=True)
    tb._play_action = play

    # Section 5 · Winds
    _add(tb, "◑", "wind", "Apply dominant winds (EPW)",
         panel._on_dominant, shortcut="Shift+W")

    # Section 6 · Charts
    _add(tb, "📊", "chart", "Save climate charts (PNG)…",
         panel._on_save_charts, shortcut="Shift+G")

    # Section 7 · Map and Context
    _add(tb, "🌐", "basemap", "Download basemap",
         panel._on_basemap, shortcut="Shift+B")
    _add(tb, "🏙", "osm", "Load OSM buildings",
         panel._on_osm, shortcut="Shift+O")
    _add(tb, "🧹", "osm_off", "Remove OSM context",
         lambda: act.set_context(sitio, None, tr("Context removed.")),
         shortcut="Shift+Delete")

    # Section 8 · Masses
    _add(tb, "⬛", "mass", "Mass from selected faces",
         lambda: panel._make_masses("mass"), shortcut="Shift+M")
    _add(tb, "▬", "lot", "Lot from selected faces",
         lambda: panel._make_masses("lot"), shortcut="Shift+L")

    # Section 9 · Annotations
    _add(tb, "★", "star", "Annotate with the selected icon",
         lambda: panel._place_pin(True), shortcut="Shift+A")

    # Section 10 · Views
    _add(tb, "⊞", "view_top", "Top view",
         lambda: panel.set_view("top"), shortcut="Shift+5")
    _add(tb, "⌂", "fit", "Fit to site",
         lambda: panel.set_view("fit"), shortcut="Shift+0")

    # Section 11 · Solar analysis
    _add(tb, "☀", "sun", "Compute radiation",
         panel._on_rad, shortcut="Shift+R")

    # Section 12 · Export and Info panel
    _add(tb, "⇩", "export", "Export PNG…",
         panel._on_png, shortcut="Shift+E")
         
    notes = _add(tb, "🎛", "info", "Show / hide the info and conventions panel",
                 None, shortcut="Shift+I", checkable=True,
                 checked=bool(getattr(sitio, "show_notes", False)))

    def _on_notes_toggled(checked):
        if bool(getattr(sitio, "show_notes", False)) != bool(checked):
            panel._on_notes(checked)

    notes.toggled.connect(_on_notes_toggled)
    tb._notes_action = notes
    
    tb.addSeparator()

    # Panel on/off (End of bar)
    panel_toggle = _add(tb, "⚙", "panel", "Show / hide the analysis panel",
                        None, shortcut="Shift+P", checkable=True,
                        checked=bool(dock.isVisible()) if dock else True)

    def _on_panel_toggled(checked):
        if dock:
            if checked:
                app.show_panel(dock)
            else:
                dock.hide()

    panel_toggle.toggled.connect(_on_panel_toggled)
    tb._panel_action = panel_toggle
    tb._dock = dock

    return tb


def register(app, sitio, panel, dock=None):
    # Remove a barra antiga se ela existir (para evitar duplicação)
    existing = app.window.findChild(QToolBar, TOOLBAR_NAME)
    if existing is not None:
        app.window.removeToolBar(existing)
        existing.deleteLater()
        
    # Cria uma nova barra do zero
    tb = build(app, sitio, panel, dock)
    
    # Adiciona à janela
    add = getattr(app, "add_toolbar", None)
    if callable(add):
        add(tb)
    else:
        app.window.addToolBar(tb)
        
    # FORÇA a barra a ser visível
    tb.show()
    
    return tb


def refresh(tb, sitio, dock=None):
    if tb is None:
        return
    eye = getattr(tb, "_eye_action", None)
    if eye is not None:
        on = bool(sitio.store.view().get("on", True))
        if eye.isChecked() != on:
            eye.blockSignals(True)
            eye.setChecked(on)
            eye.blockSignals(False)
            
    play = getattr(tb, "_play_action", None)
    if play is not None:
        on = bool(sitio.animating_sun)
        if play.isChecked() != on:
            play.blockSignals(True)
            play.setChecked(on)
            play.blockSignals(False)

    notes = getattr(tb, "_notes_action", None)
    if notes is not None:
        on = bool(getattr(sitio, "show_notes", False))
        if notes.isChecked() != on:
            notes.blockSignals(True)
            notes.setChecked(on)
            notes.blockSignals(False)
            
    panel_toggle = getattr(tb, "_panel_action", None)
    if panel_toggle is not None and dock is not None:
        on = bool(dock.isVisible())
        if panel_toggle.isChecked() != on:
            panel_toggle.blockSignals(True)
            panel_toggle.setChecked(on)
            panel_toggle.blockSignals(False)