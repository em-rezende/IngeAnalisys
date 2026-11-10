# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""What the site analysis stores IN THE DOCUMENT (.igz).

Four values in ``scene.plugin_data``, each with its own pace:

- ``<key>`` (``app.document_data``): the content — pins and winds. Every
  change is one undo step (``app.set_document_data``).
- ``<key>.vista`` → ``<key>.view``: how it looks — colors, radii, checkboxes.
  Written directly and marks the document as modified, without filling the
  history (like IngeTrazo's Shadows panel while dragging the hour).
- ``<key>.clima`` → ``<key>.climate``: the compact EPW (≈ 400 kB). Separated
  so undoing a pin does not copy a whole year of hourly data.
- ``<key>.contexto`` → ``<key>.context``: the OpenStreetMap buildings and
  the group that draws them; changes together with that group in a single
  step (:class:`Step`).

The study's hour and date are NOT here: they belong to ``scene.shadows``
(a single truth with IngeTrazo's shadows). The location is
``scene.georef``.
"""
from __future__ import annotations

import copy
import json

from core.history import Command

from .i18n import tr

PALETTE = ("#e5e7eb", "#f4c27a", "#9ec5fe", "#b9e3a5", "#f3a6a6", "#d5b8f5",
           "#a7e3df")
WIND_COLORS = ("#b5d16b", "#d79bd4", "#e8c95a", "#7dd3fc", "#fca5a5")


def default_view() -> dict:
    return {
        "on": False,
        "site_name": "",
        "radius": 100.0,
        "center": [0.0, 0.0, 0.0],
        "sun": {"months": [6, 3, 12], "band": True, "analemma": True,
                "day": True, "labels": True, "ray": True,
                "color": "#b09c45", "ball": "#ff3b30", "diagram": True},
        "wind": {"show": False, "anim": False, "rose": True, "hourly": False,
                 "height": 8.0, "width": 1.0, "pal": "blue",
                 "c0": "#bfdbfe", "c1": "#1e3a8a", "opa": 0.8, "scale": 0.62},
        "rings": {"n": 4, "step": 25.0, "color": "#5ec8ff"},
        "view": {"compass": True, "notes": False,
                 "notes_title": "SITE ANALYSIS", "label_scale": 1.0,
                 "notes_corner": "tr"},
        "period": {"m0": 1, "m1": 12, "h0": 0, "h1": 24},
        "ctx": {"color": "#9aa4b8", "opacity": 0.6, "hscale": 1.0,
                "radius": 300.0, "def_h": 9.0, "terrain": True},
        "model": {"floor_h": 3.2, "def_h": 12.0},
        "annot": {"color": "#facc15", "text": "#ffffff", "line": "#facc15",
                  "bg": True, "bg_color": "#0e1626", "size": 6.0, "h": 6.0,
                  "line_on": True, "label_on": True},
        "map": {"provider": "esri_imagery", "custom": "", "extent": 700.0,
                "zoom": 0},
        "rad": {"period": "day", "month": 6, "target": "all", "grid": 1.0,
                "ground": True, "ground_r": 0.0,
                "mode": "cells", "albedo": 0.2, "palette": "ecotect",
                "auto": True, "vmin": 0.0, "vmax": 1000.0, "legend": True},
        "sd": {"h0": 7, "h1": 18, "step": 30, "palette": "grises",
               "show": "shade"},
    }


def default_content() -> dict:
    # Stored in English; displayed through :func:`pin_label_text` /
    # :func:`wind_label_text` so old documents ("Viento-Sur", "Punto 1")
    # keep working.
    return {"pins": [], "winds": [
        {"on": True, "label": "Wind-South", "dir": 180.0, "speed": 2.5,
         "color": "#b5d16b"},
        {"on": True, "label": "Wind-West", "dir": 270.0, "speed": 2.0,
         "color": "#d79bd4"},
        {"on": True, "label": "Wind-Northwest", "dir": 315.0, "speed": 1.6,
         "color": "#e8c95a"},
    ]}


#: Folder names this extension has answered to. IngeTrazo keys an
#: extension's data by the name of its folder — the ``key`` of
#: ``ExtensionApp`` and the stem in ``ingetrazo_plugin_<stem>`` — and the
#: extension manager installs a package from the catalog as ``<id>``
#: (``ingeanalisys``). A document made while the folder was called
#: ``IngeAnalisys`` (copied by hand, as the README said) must keep opening
#: after that, so the older names are READ as well; new values are always
#: written under the current one.
LEGACY_KEYS = ("IngeAnalisys", "analisis_sitio")

#: ``<key><suffix>`` values that changed name along the way.
_LEGACY_SUFFIXES = {".view": (".vista",), ".climate": (".clima",),
                    ".context": (".contexto",)}


def keys(key: str) -> tuple[str, ...]:
    """The plugin's current key first, then the names it used to have."""
    return (str(key), *[k for k in LEGACY_KEYS if k != key])


def ext_data(group, key: str):
    """``group.ext[key]`` — this extension's parameters for ``group``, also
    when they were stored under an older name — or ``None`` when the group
    is not ours. The dict is the one in ``group.ext`` (change it in place)."""
    ext = getattr(group, "ext", None) or {}
    for k in keys(key):
        data = ext.get(k)
        if isinstance(data, dict):
            return data
    return None


def _suffix_keys(key: str, suffix: str) -> tuple[str, ...]:
    names = []
    for base in keys(key):
        for s in (suffix, *_LEGACY_SUFFIXES.get(suffix, ())):
            names.append(base + s)
    return tuple(names)


#: Legacy Spanish/Pt labels still seen in old .igz files.
_LEGACY_WIND = {
    "Viento-Sur": "Wind-South",
    "Viento-Oeste": "Wind-West",
    "Viento-Noroeste": "Wind-Northwest",
    "Viento-Norte": "Wind-North",
    "Viento-Este": "Wind-East",
}
_LEGACY_PIN = {"Punto": "Point"}


def wind_label_text(label: str) -> str:
    """Translate a stored wind label for display. Only known legacy names
    and the ``Wind-<sector>`` pattern are translated; anything else passes
    through unchanged (user-typed labels)."""
    label = _LEGACY_WIND.get(label, label)
    if label.startswith("Wind-"):
        return tr("Wind-{sector}", sector=tr(label[5:]))
    return label


def pin_label_text(label: str) -> str:
    """Translate a stored pin label for display (``Point N`` pattern)."""
    for legacy, en in _LEGACY_PIN.items():
        if label.startswith(legacy + " "):
            label = en + label[len(legacy):]
            break
    if label.startswith("Point "):
        return tr("Point {n}", n=label[6:])
    return label


def _merge(base: dict, raw) -> dict:
    """``raw`` over the defaults, one level of nesting."""
    out = copy.deepcopy(base)
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if k not in out:
            continue
        if isinstance(out[k], dict) and isinstance(v, dict):
            for kk, vv in v.items():
                if kk in out[k]:
                    out[k][kk] = vv
        else:
            out[k] = v
    return out


class Store:
    """Access to the four document values for one extension."""

    def __init__(self, app) -> None:
        self.app = app
        self.key = app.key

    @property
    def scene(self):
        return self.app.scene

    def _pd(self) -> dict:
        pd = getattr(self.scene, "plugin_data", None)
        if pd is None:
            self.scene.plugin_data = pd = {}
        return pd

    def _get(self, suffix: str, default=None):
        pd = self._pd()
        for k in _suffix_keys(self.key, suffix):
            if k in pd:
                return pd[k]
        return default

    def _set(self, suffix: str, value) -> None:
        self._pd()[self.key + suffix] = value

    # ---- View (direct, no undo) ---------------------------------------------
    def view(self) -> dict:
        pd = self._pd()
        key = self.key + ".view"
        merged = _merge(default_view(), self._get(".view"))
        if pd.get(key) != merged:
            pd[key] = merged
        return merged

    def touch(self) -> None:
        """The view changed: mark the document modified and repaint."""
        self.scene.version += 1
        vp = self.app.viewport
        vp.update()

    # ---- Content (undo) -----------------------------------------------------
    def content(self) -> dict:
        raw = self.app.document_data(None)
        if raw is None:                  # written while under an older name
            pd = self._pd()
            for k in keys(self.key):
                if k in pd:
                    raw = pd[k]
                    break
        if not isinstance(raw, dict):
            return default_content()
        out = default_content()
        if isinstance(raw.get("pins"), list):
            out["pins"] = [p for p in raw["pins"] if isinstance(p, dict)]
        if isinstance(raw.get("winds"), list):
            out["winds"] = [w for w in raw["winds"] if isinstance(w, dict)]
        return out

    def set_content(self, value: dict) -> None:
        self.app.set_document_data(value)

    # ---- Climate ------------------------------------------------------------
    def climate(self):
        return self._get(".climate")

    def set_climate(self, value) -> None:
        from core.history import SetPluginDataCommand
        vp = self.app.viewport
        vp.history.execute(SetPluginDataCommand(self.key + ".climate", value))
        notify = getattr(vp, "notify_scene_changed", None)
        if callable(notify):
            notify()
        vp.update()

    # ---- Context ------------------------------------------------------------
    def context(self) -> dict:
        raw = self._get(".context")
        return raw if isinstance(raw, dict) else {"buildings": [], "group": None}

    def context_key(self) -> str:
        return self.key + ".context"


class Step(Command):
    """ONE undo step for everything that touches groups, layers and
    extension data at once (creating or rebuilding masses, OSM context).

    Rebuilds replace the whole ``Group`` object, so remembering the lists
    is enough: the old objects stay intact."""

    def __init__(self, mutate, keys=()) -> None:
        self.mutate = mutate
        self.keys = tuple(keys)
        self.before = self.after = None

    def _capture(self, scene) -> dict:
        pd = scene.plugin_data
        return {
            "mesh": scene.mesh.capture_state(),
            "groups": list(scene.groups),
            "layers": list(scene.layers),
            "hidden": [(g, g.hidden) for g in scene.groups],
            "data": {k: (json.loads(json.dumps(pd[k])) if k in pd else None)
                     for k in self.keys},
        }

    def _restore(self, scene, s) -> None:
        scene.mesh.restore_state(s["mesh"])
        scene.groups[:] = s["groups"]
        scene.layers[:] = s["layers"]
        for g, h in s["hidden"]:
            g.hidden = h
        for k, v in s["data"].items():
            if v is None:
                scene.plugin_data.pop(k, None)
            else:
                scene.plugin_data[k] = json.loads(json.dumps(v))
        live = set(scene.mesh.faces) | set(scene.mesh.edges) | set(scene.groups)
        scene.selection.intersection_update(live)

    def do(self, scene) -> None:
        if self.after is None:
            self.before = self._capture(scene)
            try:
                self.mutate(scene)
            except BaseException:
                self._restore(scene, self.before)
                raise
            self.after = self._capture(scene)
        else:
            self._restore(scene, self.after)
        scene.version += 1

    def undo(self, scene) -> None:
        self._restore(scene, self.before)
        scene.version += 1


def run_step(viewport, mutate, keys=(), message: str | None = None) -> bool:
    """Run ``mutate(scene)`` as one step; False (and a flash) on failure."""
    hist = viewport.history
    hist.execute(Step(mutate, keys))
    err = getattr(hist, "last_error", None)
    if err:
        viewport.flash_status(str(err).split(": ", 1)[-1], 5000)
        return False
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    viewport.update()
    if message:
        viewport.flash_status(message, 3500)
    return True