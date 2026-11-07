# SPDX-License-Identifier: GPL-3.0-or-later
"""Análisis de Sitio — una EXTENSIÓN de IngeTrazo.

Sol · Viento · Clima · Contexto · Masas, sobre el propio modelo: el
diagrama solar 3D del sitio (trayectorias del 21 de cada mes, banda anual,
analemas, horas), el sol del momento moviendo las sombras reales de
IngeTrazo, el clima de un archivo EPW (rosa de vientos, temperatura y
humedad mensual), flechas de viento animadas y rosa 3D sobre el
suelo, edificios de contexto de OpenStreetMap, masas y lotes con sus
áreas e índices, anotaciones con iconos, notas en pantalla y exportación
(imagen).

Es el módulo de la app web «Análisis de Sitio 3D» llevado a IngeTrazo como
se hace una extensión de SketchUp: no toca el núcleo, todo pasa por
``setup(app)`` (views/extension_api.py, API 2):

- una pestaña en la bandeja lateral (``add_panel``) y un submenú propio en
  Extensiones (``add_menu``), más entradas en el clic derecho;
- el dibujo sobre la vista (``add_overlay``), con anotaciones y edificios
  que se eligen con Seleccionar y se borran con Supr (``add_pickable``);
- los datos en el documento (.igz), con deshacer;
- la ubicación, la hora del sol, el mapa base y el terreno son los de
  IngeTrazo — una sola verdad, no una copia.

Instalación: copiar la carpeta ``analisis_sitio`` en la carpeta de
extensiones (Extensiones ▸ Abrir carpeta de extensiones) y reiniciar.
"""
from __future__ import annotations

import logging

__version__ = "1.8.0"
log = logging.getLogger("ingetrazo.plugins.analisis_sitio")


def setup(app) -> None:
    if getattr(app, "api_version", 1) not in (1, 2):
        log.warning("Análisis de Sitio espera la API de extensiones 2")
        return
    from PySide6.QtCore import QTimer

    from . import acciones as act
    from .dibujo import Overlay, Projector
    from .nucleo import Sitio
    from .panel import SitePanel

    sitio = Sitio(app)
    overlay = Overlay(sitio)
    panel = SitePanel(sitio, overlay)
    dock = app.add_panel("Análisis de sitio", panel)

    app.add_overlay(lambda vp, painter: overlay.draw(vp, painter))

    # ---- Elegir con Seleccionar, borrar con Supr -------------------------------
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

    # ---- El documento cambió (edición, deshacer, abrir, otra pestaña) ---------
    def changed():
        sitio.update_animation()
        panel.schedule_refresh()

    app.on_document_changed(changed)
    if hasattr(app, "on_document_closed"):
        app.on_document_closed(lambda _scene: None)

    # ---- Menú Extensiones ▸ Análisis de sitio ------------------------------------
    def show():
        app.show_panel(dock)

    def later(fn):
        return lambda: QTimer.singleShot(0, fn)

    sub = app.add_menu("Análisis de sitio")
    if sub is not None:
        entries = (
            ("Mostrar panel", show),
            (None, None),
            ("Abrir clima (EPW)…", lambda: (show(), panel._on_open_epw())),
            ("Elegir ubicación en el mapa…", lambda: (show(), panel._on_pick_map())),
            ("Descargar mapa base", panel._on_basemap),
            ("Cargar edificios de OpenStreetMap", panel._on_osm),
            (None, None),
            ("Masa desde las caras seleccionadas",
             lambda: panel._make_masses("mass")),
            ("Lote desde las caras seleccionadas",
             lambda: panel._make_masses("lot")),
            ("Nueva anotación (clic en la vista)",
             lambda: panel._place_pin(False)),
            (None, None),
            ("Vista desde el sol", lambda: panel.set_view("sun")),
            ("Animar recorrido solar", panel._on_anim),
            ("Mostrar / ocultar el análisis", _toggle(sitio, panel)),
            (None, None),
            ("Exportar imagen (PNG)…", panel._on_png),
        )
        for text, fn in entries:
            if text is None:
                sub.addSeparator()
            else:
                a = sub.addAction(text)
                a.triggered.connect(lambda _c=False, f=fn: f())
    else:                                            # ventana sin ese menú
        app.add_menu_action("Análisis de sitio…", show)

    # ---- Clic derecho ------------------------------------------------------------
    def context_menu(menu, selection):
        from core.mesh import Face
        scene = app.scene
        groups = [g for g in selection if g in act.masses(sitio)]
        faces = [e for e in selection if isinstance(e, Face)
                 and e in scene.mesh.faces]
        if groups:
            g = groups[0]
            menu.addAction("Editar masa en Análisis de sitio").triggered.connect(
                lambda: QTimer.singleShot(0, lambda: (show(), panel.refresh(),
                                                      panel.select_mass(g))))
        if faces:
            menu.addAction("Convertir en masa").triggered.connect(
                later(lambda: panel._make_masses("mass")))
            menu.addAction("Convertir en lote").triggered.connect(
                later(lambda: panel._make_masses("lot")))

    app.add_context_menu(context_menu)

    # ---- Navegador: qué son estos grupos -------------------------------------------
    key = app.key

    def outliner_kind(group):
        from . import geometria as geo
        p = geo.mass_params(group, key)
        if p is None:
            return None
        p = geo.normalize_mass(p)
        st = geo.mass_stats(p)
        if p["kind"] == "lot":
            return {"type": "Lote", "props": [("Área", f"{st['area']:,.1f} m²")]}
        return {"type": "Masa", "props": [
            ("Altura", f"{p['h']:.2f} m"), ("Pisos", str(st["floors"])),
            ("Área", f"{st['area']:,.1f} m²"),
            ("Área construida", f"{st['gfa']:,.0f} m²")]}

    app.add_outliner_kind(outliner_kind)
    sitio.update_animation()
    # Para pruebas y la consola de Python.
    app.window.__dict__.setdefault("_ext_instances", {})[key] = {
        "sitio": sitio, "panel": panel, "overlay": overlay, "dock": dock}


def _toggle(sitio, panel):
    def fn():
        v = sitio.store.view()
        v["on"] = not v.get("on", True)
        sitio.store.touch()
        sitio.update_animation()
        panel.refresh()
    return fn
