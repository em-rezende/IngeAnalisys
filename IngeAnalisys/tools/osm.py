# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""Context buildings from OpenStreetMap (Overpass API).

Footprints (``building`` and ``building:part``, ways and relations) in a
radius around the site, with height from the tags: ``height`` /
``building:height``; else ``building:levels`` × 3 m (+ ``roof:levels``);
else the default height. Base: ``min_height`` or
``building:min_level`` × 3 m. Same rules as the web app.

The download runs in a thread (``OsmWorker``); the result comes back to the
main thread by signal, the only one that touches the document.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QThread, Signal

from .i18n import tr

ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
LEVEL_H = 3.0
_NUM = re.compile(r"[\d.]+")


def query(lat: float, lon: float, radius: float) -> str:
    r = int(round(radius))
    a = f"(around:{r},{lat:.7f},{lon:.7f})"
    return (f'[out:json][timeout:40];(way["building"]{a};'
            f'way["building:part"]{a};relation["building"]{a};);out geom;')


def _num(v) -> float | None:
    if v is None:
        return None
    m = _NUM.search(str(v).replace(",", "."))
    try:
        return float(m.group(0)) if m else None
    except ValueError:
        return None


def heights(tags: dict, default_h: float) -> dict:
    """``{"h", "min", "src"}`` — ``src`` is "tag" or "def" (guessed)."""
    tags = tags or {}
    h = _num(tags.get("height", tags.get("building:height")))
    if h is None:
        lv = _num(tags.get("building:levels"))
        if lv is not None:
            roof = _num(tags.get("roof:levels")) or 0.0
            h = (lv + roof) * LEVEL_H
    src = "tag"
    if h is None:
        h, src = float(default_h), "def"
    mn = _num(tags.get("min_height"))
    if mn is None:
        ml = _num(tags.get("building:min_level"))
        mn = ml * LEVEL_H if ml is not None else 0.0
    return {"h": max(1.0, h), "min": max(0.0, mn), "src": src}


def parse(payload: dict, to_local, default_h: float) -> list[dict]:
    """Overpass reply → ``[{"id", "pts": [[x, y]…], "h", "min", "src",
    "name", "hidden"}]`` in model-local coordinates."""
    out = []

    def add(geom, tags, ident):
        if not geom or len(geom) < 4:
            return
        pts = []
        for g in geom:
            try:
                x, y = to_local(float(g["lat"]), float(g["lon"]))
            except (KeyError, TypeError, ValueError):
                return
            pts.append([round(x, 3), round(y, 3)])
        if (abs(pts[0][0] - pts[-1][0]) < 0.01
                and abs(pts[0][1] - pts[-1][1]) < 0.01):
            pts.pop()
        if len(pts) < 3 or abs(signed_area(pts)) < 0.5:
            return
        hh = heights(tags, default_h)
        tags = tags or {}
        out.append({"id": ident, "pts": pts, "h": hh["h"], "min": hh["min"],
                    "src": hh["src"],
                    "name": tags.get("name") or tags.get("addr:street") or "",
                    "hidden": False})

    for el in payload.get("elements", []) or []:
        kind = el.get("type")
        if kind == "way":
            add(el.get("geometry"), el.get("tags"), f"w{el.get('id')}")
        elif kind == "relation":
            outers = [m for m in el.get("members", []) or []
                      if m.get("role") == "outer" and m.get("geometry")]
            for k, m in enumerate(outers):
                add(m["geometry"], el.get("tags"), f"r{el.get('id')}_{k}")
    return out


def signed_area(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def fetch(lat: float, lon: float, radius: float, timeout: int = 60) -> dict:
    """Ask the Overpass servers, one after another. Blocking."""
    try:
        from core.version import USER_AGENT
    except ImportError:                                   # pragma: no cover
        USER_AGENT = "IngeTrazo-AnalisisSitio"
    try:
        from core.tls import https_context
        ctx = https_context()
    except Exception:                                     # pragma: no cover
        ctx = None
    body = urllib.parse.urlencode({"data": query(lat, lon, radius)}).encode()
    last = None
    for url in ENDPOINTS:
        req = urllib.request.Request(url, data=body, headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:                          # noqa: BLE001
            last = exc
    raise RuntimeError(tr("Overpass did not respond: {error}", error=last))


class _Job(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, lat, lon, radius) -> None:
        super().__init__()
        self.args = (lat, lon, radius)

    def run(self) -> None:
        try:
            self.done.emit(fetch(*self.args))
        except Exception as exc:                          # noqa: BLE001
            self.failed.emit(str(exc))


class OsmWorker(QObject):
    """Background download. ``finished(payload)`` or ``failed(msg)``
    arrive on the main thread (queued connection to bound methods)."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread = None
        self._job = None

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self, lat, lon, radius) -> bool:
        if self._thread is not None:
            return False
        self._thread = QThread()
        self._job = _Job(lat, lon, radius)
        self._job.moveToThread(self._thread)
        self._thread.started.connect(self._job.run)
        self._job.done.connect(self._on_done)
        self._job.failed.connect(self._on_failed)
        self._thread.start()
        return True

    def _on_done(self, payload) -> None:
        self._stop()
        self.finished.emit(payload)

    def _on_failed(self, msg: str) -> None:
        self._stop()
        self.failed.emit(msg)

    def _stop(self) -> None:
        th = self._thread
        self._thread = None
        if th is not None:
            th.quit()
            th.wait(2000)
        self._job = None