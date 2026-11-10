# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""Site Analysis — an IngeTrazo EXTENSION.

Sun · Wind · Weather · Context · Masses, over the model itself: the 3D
solar diagram of the site (paths for the 21st of each month, yearly band,
analemmas, hours), the current sun moving IngeTrazo's real shadows, the
weather from an EPW file (wind rose, monthly temperature and humidity),
animated wind arrows and 3D ground wind rose, OpenStreetMap context
buildings, masses and lots with their areas and ratios, icon annotations,
on-screen notes and export (image).

It is the «Análisis de Sitio 3D» web app brought into IngeTrazo the way a
SketchUp extension is made: it does not touch the core, everything enters
through ``setup(app)`` (views/extension_api.py, API 2):

- a tab in the side shelf (``add_panel``) and its own submenu under
  Extensions (``add_menu``), plus right-click entries;
- the drawing over the view (``add_overlay``), with annotations and
  buildings picked with Select and removed with Del (``add_pickable``);
- one unified toolbar (19 buttons) with all actions grouped by panel section;
- data in the document (.igz), with undo;
- location, sun time, basemap and terrain are IngeTrazo's — a single
  truth, not a copy.

CREDIT — this is not the work of whoever maintains this copy. The extension
``analisis_sitio``, its design and every method in it (EPW climate, solar
diagram, shadows, winds, OSM context, masses and lots, radiation and shade
maps, annotations, export) are the work of **jufegofoto-cell**, who brought
the web app into IngeTrazo: https://github.com/jufegofoto-cell/IngeAnalisys.
This copy is a fork that adds the nine language catalogs, the layout in
``tools/``/``i18n/``/``icons/``, the unified toolbar, the floating panels and
fixes to shortcuts and dialogs; each file says so above. What changed, and
under which licence (GPL-3.0-or-later, as the original), is written in
CREDITS.md at the root of the repository.

Installation (docs/plugins.md — a package folder with ``__init__.py``):

- from the catalog: **Extensions ▸ Manage extensions…**, find «Site
  Analysis», install, restart;
- by hand: unzip ``IngeAnalisys.zip`` inside the plugins folder
  (**Extensions ▸ Open plugins folder**, ``%APPDATA%\\ingetrazo\\plugins\\``
  on Windows) and restart. The extension is then in
  ``plugins/IngeAnalisys/__init__.py``.

The manager installs a catalog package under the catalog id
(``ingeanalisys``), so ``app.key`` — the name the document keeps its data
under — differs between the two routes: ``tools/data.py`` reads the values
of both, so a project made with either keeps opening.
"""
from __future__ import annotations

import logging

from .tools import i18n

__version__ = "1.9.0"
log = logging.getLogger("ingetrazo.plugins.analisis_sitio")


def setup(app) -> None:
    if getattr(app, "api_version", 1) not in (1, 2):
        log.warning("Site Analysis expects extensions API 2")
        return
    from PySide6.QtCore import QTimer

    # ---- Language --------------------------------------------------------
    # Load the catalog for this session: from ``app.settings["language"]``
    # when available, else from the OS locale (pt* → pt-BR, es* → es).
    lang = None
    
    settings = getattr(app, "settings", None)
    if settings is not None and hasattr(settings, "get"):
        try:
            lang = settings.get("language")
        except Exception:                             # noqa: BLE001
            lang = None
    i18n.set_language(lang)
    i18n.migrate_layers(app.scene)

    # ---- Imports (after i18n so tr() is available) ----------------------
    from .tools import actions as act
    from .tools.i18n import tr
    from .tools.core import Site
    from .tools.drawing import Overlay, Projector
    from .tools.panel import SitePanel
    from .tools.toolbar import register as register_toolbar, refresh as refresh_toolbar

    # ---- Core objects ---------------------------------------------------
    sitio = Site(app)
    overlay = Overlay(sitio)
    panel = SitePanel(sitio, overlay)
    dock = app.add_panel(tr("Site Analysis"), panel)

    app.add_overlay(lambda vp, painter: overlay.draw(vp, painter))

    # ---- Toolbar (Unified) ----------------------------------------------
    toolbar = register_toolbar(app, sitio, panel, dock)

    _orig_refresh = panel.refresh

    def _panel_refresh():
        _orig_refresh()
        refresh_toolbar(toolbar, sitio, dock)

    panel.refresh = _panel_refresh                    # noqa: SLF001 — intentional

    # ---- Pick with Select, delete with Del ------------------------------
    def pick(viewport, px, py):
        P = Projector(viewport)
        pid = act.pick_pin(sitio, P, px, py)
        if pid is not None:
            return ("pin", pid)
        if sitio.edit_context:
            bid = act.pick_building(sitio, P, px, py)
            if bid is not None:
                return ("bld", bid)
        return None

    def on_select(item):
        if item is None:
            sitio.selected_pin = None
            panel.schedule_refresh()
        elif item[0] == "pin":
            panel.pin_selected(item[1])
        else:
            panel.building_selected(item[1])
        app.viewport.update()

    def delete(item):
        if item[0] == "pin":
            act.delete_pin(sitio, item[1])
        else:
            act.update_building(sitio, item[1], hidden=True)
            sitio.selected_building = None

    app.add_pickable(pick, on_select=on_select, delete=delete)

    # ---- Document changed (edit, undo, open, other tab) -----------------
    def changed():
        sitio.update_animation()
        panel.schedule_refresh()

    app.on_document_changed(changed)
    if hasattr(app, "on_document_closed"):
        app.on_document_closed(lambda _scene: None)

    # ---- Extensions ▸ Site Analysis -------------------------------------
    def show():
        app.show_panel(dock)

    def later(fn):
        return lambda: QTimer.singleShot(0, fn)

    sub = app.add_menu(tr("Site Analysis"))
    if sub is not None:
        entries = (
            (tr("Show panel"), show),
            (None, None),
            (tr("Open weather (EPW)…"),
             lambda: (show(), panel._on_open_epw())),
            (tr("Pick location on the map…"),
             lambda: (show(), panel._on_pick_map())),
            (tr("Download basemap"), panel._on_basemap),
            (tr("Load OpenStreetMap buildings"), panel._on_osm),
            (None, None),
            (tr("Mass from selected faces"),
             lambda: panel._make_masses("mass")),
            (tr("Lot from selected faces"),
             lambda: panel._make_masses("lot")),
            (tr("New annotation (click in the view)"),
             lambda: panel._place_pin(False)),
            (None, None),
            (tr("View from the sun"), lambda: panel.set_view("sun")),
            (tr("Animate sun path"), panel._on_anim),
            (tr("Show / hide analysis"),
             lambda: (act.toggle_analysis(sitio), panel.refresh())),
            (None, None),
            (tr("Export image (PNG)…"), panel._on_png),
        )
        for text, fn in entries:
            if text is None:
                sub.addSeparator()
            else:
                a = sub.addAction(text)
                a.triggered.connect(lambda _c=False, f=fn: f())
    else:                                            # window without that menu
        app.add_menu_action(tr("Site Analysis…"), show)

    # ---- Right-click ----------------------------------------------------
    def context_menu(menu, selection):
        from core.mesh import Face
        scene = app.scene
        groups = [g for g in selection if g in act.masses(sitio)]
        faces = [e for e in selection if isinstance(e, Face)
                 and e in scene.mesh.faces]
        if groups:
            g = groups[0]
            menu.addAction(tr("Edit mass in Site Analysis")).triggered.connect(
                lambda: QTimer.singleShot(0, lambda: (show(), panel.refresh(),
                                                      panel.select_mass(g))))
        if faces:
            menu.addAction(tr("Convert to mass")).triggered.connect(
                later(lambda: panel._make_masses("mass")))
            menu.addAction(tr("Convert to lot")).triggered.connect(
                later(lambda: panel._make_masses("lot")))

    app.add_context_menu(context_menu)

    # ---- Outliner: what these groups are --------------------------------
    key = app.key

    def outliner_kind(group):
        from .tools import geometry as geo
        p = geo.mass_params(group, key)
        if p is None:
            return None
        p = geo.normalize_mass(p)
        st = geo.mass_stats(p)
        if p["kind"] == "lot":
            return {"type": tr("Lot"),
                    "props": [(tr("Area"), f"{st['area']:,.1f} m²")]}
        return {"type": tr("Mass"), "props": [
            (tr("Height"), f"{p['h']:.2f} m"),
            (tr("Floors"), str(st["floors"])),
            (tr("Area"), f"{st['area']:,.1f} m²"),
            (tr("Gross floor area"), f"{st['gfa']:,.0f} m²")]}

    app.add_outliner_kind(outliner_kind)

    sitio.update_animation()

    # ---- Expose for tests and the Python console -----------------------
    app.window.__dict__.setdefault("_ext_instances", {})[key] = {
        "sitio": sitio, "panel": panel, "overlay": overlay,
        "dock": dock, "toolbar": toolbar}