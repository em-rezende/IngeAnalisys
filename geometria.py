# SPDX-License-Identifier: GPL-3.0-or-later
"""Masas, lotes y edificios de contexto como geometría de IngeTrazo.

Una **masa** es un grupo normal del modelo (se mueve, gira, se pinta, se
exporta a OBJ/SKP/IFC como cualquier otro) que recuerda sus parámetros en
``group.ext[<key>]``: planta, altura, cota base, tipo. Editarla desde el
panel la reconstruye en su sitio; empujarla con Empujar/Tirar sigue siendo
posible — es geometría de verdad, como un volumen de SketchUp.

Un **lote** es lo mismo sin altura: una cara plana con su área.

El **contexto** de OpenStreetMap es UN grupo con todas las huellas
extruidas (miles de edificios no deben ser miles de objetos), en su propia
capa, bloqueado para no tocarlo por error.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtGui import QVector3D

CONTEXT_LAYER = "Contexto OSM"
MASS_LAYER = "Masas"
LOT_LAYER = "Lotes"


# ---- Polígonos en planta ----------------------------------------------------

def signed_area(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def area(pts) -> float:
    return abs(signed_area(pts))


def perimeter(pts) -> float:
    n = len(pts)
    return sum(math.hypot(pts[(i + 1) % n][0] - pts[i][0],
                          pts[(i + 1) % n][1] - pts[i][1]) for i in range(n))


def centroid(pts) -> tuple[float, float]:
    a = signed_area(pts)
    if abs(a) < 1e-12:
        n = max(1, len(pts))
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        k = x0 * y1 - x1 * y0
        cx += (x0 + x1) * k
        cy += (y0 + y1) * k
    return cx / (6 * a), cy / (6 * a)


def ccw(pts) -> list[list[float]]:
    """La planta en sentido antihorario visto desde arriba (+Z)."""
    pts = [[float(p[0]), float(p[1])] for p in pts]
    return pts if signed_area(pts) >= 0 else pts[::-1]


def clean(pts, tol: float = 0.01) -> list[list[float]]:
    """Quita vértices repetidos y el cierre duplicado."""
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append([float(p[0]), float(p[1])])
    if len(out) > 2 and math.hypot(out[0][0] - out[-1][0],
                                   out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def point_in_polygon(x: float, y: float, pts) -> bool:
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i][0], pts[i][1]
        xj, yj = pts[j][0], pts[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def rotate_pts(pts, deg: float, about=None) -> list[list[float]]:
    cx, cy = about if about is not None else centroid(pts)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [[cx + (p[0] - cx) * c - (p[1] - cy) * s,
             cy + (p[0] - cx) * s + (p[1] - cy) * c] for p in pts]


# ---- Mallas -----------------------------------------------------------------

def _rings_for_prism(pts, z0: float, z1: float):
    """Anillos (listas de (x,y,z)) de un prisma con normales hacia fuera:
    base hacia abajo, tapa hacia arriba, muros hacia fuera."""
    p = ccw(pts)
    rings = []
    if z1 - z0 < 1e-6:
        rings.append([(x, y, z0) for x, y in p])
        return rings
    rings.append([(x, y, z0) for x, y in reversed(p)])
    rings.append([(x, y, z1) for x, y in p])
    n = len(p)
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        rings.append([(a[0], a[1], z0), (b[0], b[1], z0),
                      (b[0], b[1], z1), (a[0], a[1], z1)])
    return rings


def prisms_mesh(items, mesh=None):
    """``items``: ``[(pts, z0, z1)]`` → una ``Mesh`` (creada de una vez,
    vectorizada: miles de edificios en un instante)."""
    from core.mesh import Mesh
    mesh = mesh if mesh is not None else Mesh()
    pos, sizes = [], []
    for pts, z0, z1 in items:
        pts = clean(pts)
        if len(pts) < 3:
            continue
        for ring in _rings_for_prism(pts, z0, z1):
            pos.extend(ring)
            sizes.append(len(ring))
    if sizes:
        mesh.add_faces_bulk(np.asarray(pos, dtype=np.float64),
                            np.asarray(sizes, dtype=np.int64),
                            np.ones(len(sizes), dtype=np.int64))
    return mesh


def hex_rgb(hexc: str) -> tuple[float, float, float]:
    try:
        v = int(str(hexc).lstrip("#")[:6], 16)
    except ValueError:
        v = 0xCCCCCC
    return ((v >> 16 & 255) / 255.0, (v >> 8 & 255) / 255.0, (v & 255) / 255.0)


def rgb_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def ensure_layer(scene, name: str, color=None) -> str:
    from core.layers import Layer
    if not any(ly.name == name for ly in scene.layers):
        scene.layers.append(Layer(name, color=color))
    return name


# ---- Masas ------------------------------------------------------------------

def mass_params(group, key: str):
    ext = getattr(group, "ext", None) or {}
    data = ext.get(key)
    return data if isinstance(data, dict) and "pts" in data else None


def normalize_mass(p: dict) -> dict:
    kind = "lot" if p.get("kind") == "lot" else "mass"
    h = 0.0 if kind == "lot" else max(0.0, float(p.get("h", 12.0)))
    return {"kind": kind, "pts": ccw(clean(p.get("pts", []))),
            "h": h, "base": float(p.get("base", 0.0)),
            "color": str(p.get("color", "#e5e7eb")),
            "opacity": max(0.1, min(1.0, float(p.get("opacity", 0.95)))),
            "floor_h": max(0.5, float(p.get("floor_h", 3.2)))}


def build_mass(key: str, params: dict, name: str):
    """Un grupo nuevo con la geometría de ``params``."""
    from core.group import Group
    p = normalize_mass(params)
    if len(p["pts"]) < 3:
        raise ValueError("La planta necesita al menos tres vértices.")
    mesh = prisms_mesh([(p["pts"], p["base"], p["base"] + p["h"])])
    g = Group(mesh, name=name)
    g.component = False
    g.material = {"color": hex_rgb(p["color"]), "opacity": p["opacity"]}
    g.ext = {key: p}
    return g


def mass_stats(p: dict) -> dict:
    a = area(p["pts"])
    floors = 0 if p["kind"] == "lot" else int(math.floor(p["h"] / p["floor_h"]
                                                         + 1e-6))
    return {"area": a, "perimeter": perimeter(p["pts"]),
            "volume": a * p["h"], "floors": floors, "gfa": a * floors,
            "top": p["base"] + p["h"]}


def footprint_of_face(face):
    """Planta (x, y) y cota de una cara horizontal, o None si no lo es."""
    n = face.normal() if callable(getattr(face, "normal", None)) else None
    if n is None or abs(n.z()) < 0.98:
        return None
    pts = [(v.position.x(), v.position.y()) for v in face.loop]
    z = sum(v.position.z() for v in face.loop) / len(face.loop)
    return ccw(clean(pts)), z


def remove_faces_with_edges(mesh, faces) -> None:
    """Quita caras y las aristas que queden sueltas (sin otra cara)."""
    edges = set()
    for f in faces:
        for lp in (f.loop, *f.hole_loops):
            n = len(lp)
            for i in range(n):
                e = mesh.find_edge(lp[i], lp[(i + 1) % n])
                if e is not None:
                    edges.add(e)
        mesh.remove_face(f)
    for e in edges:
        if not e.faces:
            mesh.remove_edge(e)
    prune = getattr(mesh, "prune_orphan_vertices", None)
    if callable(prune):
        prune()


# ---- Contexto ---------------------------------------------------------------

def build_context(buildings, hscale: float, terrain=None, name="Contexto OSM"):
    """El grupo del contexto. Con terreno 3D, cada edificio se apoya en la
    cota más baja del terreno bajo su huella (``b["z0"]``)."""
    from core.group import Group
    items = []
    for b in buildings:
        if b.get("hidden"):
            continue
        z = float(b.get("z0", 0.0))
        if "z0" not in b and terrain is not None:
            lows = [terrain.height_at(p[0], p[1]) for p in b["pts"]]
            lows = [v for v in lows if v is not None]
            z = min(lows) if lows else 0.0
        z0 = z + float(b.get("min", 0.0)) * hscale
        z1 = z + float(b.get("h", 9.0)) * hscale
        if z1 - z0 < 0.5:
            z1 = z0 + 0.5
        items.append((b["pts"], z0, z1))
    mesh = prisms_mesh(items)
    g = Group(mesh, name=name)
    g.component = False
    return g


def find_group(scene, uid):
    if not uid:
        return None
    for g in scene.groups:
        if getattr(g, "uid", None) == uid:
            return g
    return None


def vec(x, y, z=0.0) -> QVector3D:
    return QVector3D(float(x), float(y), float(z))
