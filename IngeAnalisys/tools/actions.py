# SPDX-License-Identifier: GPL-3.0-or-later
"""The site-analysis operations, without widgets.

Every operation that changes the model is ONE undo step. The panel, the
menus and the context menu call here; the tests too.
"""
from __future__ import annotations

import copy
import math
import uuid

from . import climate, geometry as geo
from .data import PALETTE, WIND_COLORS, run_step
from .i18n import tr


class SiteError(Exception):
    """Something the user must know (shown as-is)."""


def _new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:8]


def at_top_level(scene) -> bool:
    return getattr(scene, "edit_group", None) is None


# ---- Masses and lots --------------------------------------------------------

def masses(sitio) -> list:
    """Top-level groups that are masses or lots of this extension."""
    key = sitio.store.key
    return [g for g in sitio.scene.groups if geo.mass_params(g, key) is not None]


def _next_name(scene, kind: str) -> str:
    base = tr("Lot") if kind == "lot" else tr("Mass")
    used = {g.name for g in scene.groups}
    i = 1
    while f"{base} {i}" in used:
        i += 1
    return f"{base} {i}"


def sync_from_mesh(sitio, group) -> dict | None:
    """Mass parameters read from the current geometry: if the user moved,
    rotated or pushed it with IngeTrazo tools, the panel shows (and
    rebuilds from) what is there, not what used to be."""
    key = sitio.store.key
    p = geo.mass_params(group, key)
    if p is None:
        return None
    p = geo.normalize_mass(p)
    if group.xform is not None:
        return p
    mesh = group.mesh
    if not mesh.faces:
        return p
    zs = [v.position.z() for v in mesh.vertices]
    if not zs:
        return p
    zmin, zmax = min(zs), max(zs)
    want = -1.0 if p["kind"] == "mass" and zmax - zmin > 1e-4 else None
    best, best_a = None, 0.0
    for f in mesh.faces:
        n = f.normal()
        if abs(n.z()) < 0.98:
            continue
        if want is not None and n.z() > 0:
            continue
        fz = sum(v.position.z() for v in f.loop) / len(f.loop)
        if abs(fz - zmin) > 1e-3:
            continue
        pts = [(v.position.x(), v.position.y()) for v in f.loop]
        a = geo.area(pts)
        if a > best_a:
            best, best_a = pts, a
    if best is None:
        return p
    p["pts"] = geo.ccw(geo.clean(best))
    p["base"] = zmin
    if p["kind"] == "mass":
        p["h"] = zmax - zmin
    return p


def create_masses_from_faces(sitio, kind: str = "mass",
                             height: float | None = None,
                             consume: bool = True) -> list:
    """One mass (or lot) per horizontal face selected in the model. The
    face becomes the mass base (removed from the loose model)."""
    scene = sitio.scene
    if not at_top_level(scene):
        raise SiteError(tr("Close the group you are editing and try again."))
    from core.mesh import Face
    faces = [e for e in scene.selection
             if isinstance(e, Face) and e in scene.mesh.faces]
    plans = []
    for f in faces:
        fp = geo.footprint_of_face(f)
        if fp is not None and len(fp[0]) >= 3:
            plans.append((f, fp))
    if not plans:
        raise SiteError(tr("Select one or more horizontal faces (draw them "
                           "with Rectangle or Line) and try again."))
    view = sitio.store.view()
    h = float(view["model"]["def_h"] if height is None else height)
    key = sitio.store.key
    made = []

    def mutate(sc):
        layer = geo.ensure_layer(sc, geo.LOT_LAYER if kind == "lot"
                                 else geo.MASS_LAYER)
        n0 = len(masses(sitio))
        for i, (face, (pts, z)) in enumerate(plans):
            color = "#ef4444" if kind == "lot" else PALETTE[(n0 + i) % len(PALETTE)]
            params = {"kind": kind, "pts": pts, "h": 0.0 if kind == "lot" else h,
                      "base": z + (0.02 if kind == "lot" else 0.0),
                      "color": color, "opacity": 0.9 if kind == "lot" else 0.95,
                      "floor_h": view["model"]["floor_h"]}
            g = geo.build_mass(key, params, _next_name(sc, kind))
            g.layer = layer
            sc.groups.append(g)
            made.append(g)
        if consume:
            geo.remove_faces_with_edges(sc.mesh, [f for f, _fp in plans])
        sc.selection.clear()
        sc.selection.update(made)

    label = tr("lot(s)") if kind == "lot" else tr("mass(es)")
    if not run_step(sitio.app.viewport, mutate,
                    message=tr("{n} {label} created.", n=len(plans), label=label)):
        return []
    sitio.changed.emit()
    return made


def create_mass(sitio, pts, kind="mass", h=None, base=0.0, name=None,
                color=None, opacity=None):
    """A mass from a given footprint (import, tests, scripts)."""
    view = sitio.store.view()
    key = sitio.store.key
    out = []

    def mutate(sc):
        layer = geo.ensure_layer(sc, geo.LOT_LAYER if kind == "lot"
                                 else geo.MASS_LAYER)
        n0 = len(masses(sitio))
        params = {"kind": kind, "pts": pts,
                  "h": 0.0 if kind == "lot" else float(
                      view["model"]["def_h"] if h is None else h),
                  "base": float(base),
                  "color": color or ("#ef4444" if kind == "lot"
                                     else PALETTE[n0 % len(PALETTE)]),
                  "opacity": opacity if opacity is not None else (
                      0.9 if kind == "lot" else 0.95),
                  "floor_h": view["model"]["floor_h"]}
        g = geo.build_mass(key, params, name or _next_name(sc, kind))
        g.layer = layer
        sc.groups.append(g)
        out.append(g)

    run_step(sitio.app.viewport, mutate)
    sitio.changed.emit()
    return out[0] if out else None


def update_mass(sitio, group, changes: dict, name: str | None = None):
    """Rebuild the mass with ``changes`` (footprint, height, base, color…)
    in place, as ONE step. Returns the new group."""
    key = sitio.store.key
    p = sync_from_mesh(sitio, group)
    if p is None:
        return None
    p.update(changes)
    if p.get("kind") == "lot":
        p["h"] = 0.0
    out = []

    def mutate(sc):
        new = geo.build_mass(key, p, name or group.name)
        new.layer = group.layer if p["kind"] == group_kind(sitio, group) else (
            geo.ensure_layer(sc, geo.LOT_LAYER if p["kind"] == "lot"
                             else geo.MASS_LAYER))
        new.hidden = group.hidden
        new.ifc = copy.deepcopy(group.ifc)
        idx = sc.groups.index(group)
        sc.groups[idx] = new
        was = group in sc.selection
        sc.selection.discard(group)
        if was:
            sc.selection.add(new)
        out.append(new)

    run_step(sitio.app.viewport, mutate)
    sitio.changed.emit()
    return out[0] if out else None


def group_kind(sitio, group) -> str:
    p = geo.mass_params(group, sitio.store.key) or {}
    return "lot" if p.get("kind") == "lot" else "mass"


def rotate_mass(sitio, group, deg: float):
    p = sync_from_mesh(sitio, group)
    if p is None:
        return None
    return update_mass(sitio, group, {"pts": geo.rotate_pts(p["pts"], deg)})


def duplicate_mass(sitio, group, dx: float = 5.0, dy: float = -5.0):
    p = sync_from_mesh(sitio, group)
    if p is None:
        return None
    pts = [[x + dx, y + dy] for x, y in p["pts"]]
    return create_mass(sitio, pts, p["kind"], p["h"], p["base"],
                       name=None, color=p["color"], opacity=p["opacity"])


def delete_mass(sitio, group) -> bool:
    def mutate(sc):
        if group in sc.groups:
            sc.groups.remove(group)
        sc.selection.discard(group)

    ok = run_step(sitio.app.viewport, mutate,
                  message=tr("«{name}» deleted.", name=group.name))
    sitio.changed.emit()
    return ok


def summary(sitio) -> dict:
    """Totals: footprint, gross floor area (floors × footprint), volume,
    lots and, when lots exist, the occupancy and building ratios."""
    tot = {"masses": 0, "lots": 0, "footprint": 0.0, "gfa": 0.0,
           "volume": 0.0, "lot_area": 0.0}
    for g in masses(sitio):
        p = sync_from_mesh(sitio, g)
        st = geo.mass_stats(p)
        if p["kind"] == "lot":
            tot["lots"] += 1
            tot["lot_area"] += st["area"]
        else:
            tot["masses"] += 1
            tot["footprint"] += st["area"]
            tot["gfa"] += st["gfa"]
            tot["volume"] += st["volume"]
    if tot["lot_area"] > 0:
        tot["ios"] = tot["footprint"] / tot["lot_area"]
        tot["ica"] = tot["gfa"] / tot["lot_area"]
    return tot


# ---- OSM context ------------------------------------------------------------

def context_group(sitio):
    return geo.find_group(sitio.scene, sitio.store.context().get("group"))


def set_context(sitio, buildings: list | None, message: str | None = None):
    """Write the buildings and (re)build their group — one step. ``None``
    removes everything."""
    st = sitio.store
    view = st.view()
    ck = st.context_key()
    old = context_group(sitio)
    terrain = getattr(sitio.scene, "terrain", None) if view["ctx"].get(
        "terrain", True) else None

    def mutate(sc):
        if old is not None and old in sc.groups:
            sc.groups.remove(old)
            sc.selection.discard(old)
        if not buildings:
            sc.plugin_data.pop(ck, None)
            return
        for b in buildings:
            z = 0.0
            if terrain is not None:
                lows = [terrain.height_at(p[0], p[1]) for p in b["pts"]]
                lows = [v for v in lows if v is not None]
                z = min(lows) if lows else 0.0
            b["z0"] = round(z, 3)
        g = geo.build_context(buildings, float(view["ctx"]["hscale"]),
                              terrain=terrain)
        g.layer = geo.ensure_layer(sc, geo.CONTEXT_LAYER,
                                   color=geo.hex_rgb(view["ctx"]["color"]))
        g.material = {"color": geo.hex_rgb(view["ctx"]["color"]),
                      "opacity": float(view["ctx"]["opacity"])}
        g.locked = True
        if old is not None:
            g.hidden = old.hidden
        sc.groups.append(g)
        sc.plugin_data[ck] = {"buildings": buildings, "group": g.uid}

    run_step(sitio.app.viewport, mutate, keys=(ck,), message=message)
    sitio.changed.emit()


def context_from_osm(sitio, payload: dict) -> int:
    from . import osm
    d = sitio.datum()
    if d is None:
        raise SiteError(tr("Locate the project before loading buildings."))
    view = sitio.store.view()

    def to_local(lat, lon):
        p = d.geodetic_to_local(lat, lon)
        return p.x(), p.y()

    bl = osm.parse(payload, to_local, float(view["ctx"]["def_h"]))
    if not bl:
        raise SiteError(tr("OpenStreetMap has no buildings in that radius."))
    set_context(sitio, bl,
                message=tr("{n} context buildings loaded.", n=len(bl)))
    return len(bl)


def update_building(sitio, bid: str, **changes) -> None:
    ctx = copy.deepcopy(sitio.store.context())
    for b in ctx.get("buildings", []):
        if b.get("id") == bid:
            b.update(changes)
            break
    else:
        return
    set_context(sitio, ctx["buildings"])


def restyle_context(sitio) -> None:
    """Color and opacity of the context: without rebuilding geometry."""
    g = context_group(sitio)
    if g is None:
        return
    v = sitio.store.view()["ctx"]
    g.material = {"color": geo.hex_rgb(v["color"]), "opacity": float(v["opacity"])}
    for ly in sitio.scene.layers:
        if ly.name == geo.CONTEXT_LAYER:
            ly.color = geo.hex_rgb(v["color"])
    sitio.store.touch()


def pick_building(sitio, P, px: float, py: float):
    """The building under the pixel (nearest to the camera)."""
    ctx = sitio.store.context()
    hs = float(sitio.store.view()["ctx"]["hscale"])
    eye = P.eye
    best, best_d = None, math.inf
    for b in ctx.get("buildings", []):
        if b.get("hidden"):
            continue
        z = float(b.get("z0", 0.0)) + float(b.get("h", 9)) * hs
        pts = [(p[0], p[1], z) for p in b["pts"]]
        xy, ok = P(pts)
        if not ok.all():
            continue
        if not geo.point_in_polygon(px, py, xy.tolist()):
            continue
        cx, cy = geo.centroid(b["pts"])
        d = math.dist((eye.x(), eye.y(), eye.z()), (cx, cy, z))
        if d < best_d:
            best, best_d = b["id"], d
    return best


# ---- Annotations ------------------------------------------------------------

def add_pin(sitio, point, label: str | None = None, icon: str | None = None):
    st = sitio.store
    c = st.content()
    n = len(c["pins"]) + 1
    pin = {"id": _new_id("p"), "pos": [point.x(), point.y(), point.z()],
           "label": label if label is not None else f"Point {n}",
           "icon": icon or None}
    c["pins"].append(pin)
    st.set_content(c)
    sitio.selected_pin = pin["id"]
    sitio.changed.emit()
    return pin["id"]


def update_pin(sitio, pid: str, **changes) -> None:
    st = sitio.store
    c = st.content()
    for p in c["pins"]:
        if p.get("id") == pid:
            p.update(changes)
            break
    else:
        return
    st.set_content(c)
    sitio.changed.emit()


def delete_pin(sitio, pid: str) -> None:
    st = sitio.store
    c = st.content()
    c["pins"] = [p for p in c["pins"] if p.get("id") != pid]
    st.set_content(c)
    if sitio.selected_pin == pid:
        sitio.selected_pin = None
    sitio.changed.emit()


def style_all_pins(sitio) -> None:
    """Remove each annotation's own style: all take the current one."""
    st = sitio.store
    c = st.content()
    keys = set(st.view()["annot"])
    for p in c["pins"]:
        for k in keys:
            p.pop(k, None)
    st.set_content(c)
    sitio.changed.emit()


def pick_pin(sitio, P, px, py):
    view = sitio.store.view()
    from .drawing import pin_style
    best, best_d = None, math.inf
    for p in sitio.store.content()["pins"]:
        try:
            x, y, z = (float(v) for v in p["pos"])
        except (KeyError, TypeError, ValueError):
            continue
        s = pin_style(p, view["annot"])
        top = (x, y, z + s["h"])
        q = P.one(top)
        if q is None:
            continue
        r = max(7.0, min(26.0, P.pixel_size(top, s["size"] / 2)))
        d = math.hypot(q.x() - px, q.y() - py)
        if d <= r + 4 and d < best_d:
            best, best_d = p["id"], d
    return best


# ---- Wind -------------------------------------------------------------------

def set_winds(sitio, winds: list) -> None:
    st = sitio.store
    c = st.content()
    c["winds"] = winds
    st.set_content(c)
    sitio.update_animation()
    sitio.changed.emit()


def dominant_winds(sitio) -> list:
    s = sitio.stats()
    if not s:
        raise SiteError(tr("Load an EPW file first."))
    out = []
    for i, d in enumerate(s["top"]):
        out.append({"on": True,
                    "label": "Wind-" + climate.DIR16_LONG_EN[d].split("-")[0],
                    "dir": d * 22.5, "speed": round(s["avg_sp"][d], 1),
                    "color": WIND_COLORS[i % len(WIND_COLORS)],
                    "freq": round(s["freq"][d] * 100, 1)})
    if not out:
        raise SiteError(tr("The chosen period has no windy hours."))
    return out


# ---- Climate ----------------------------------------------------------------

def load_epw_text(sitio, text: str) -> dict:
    epw = climate.parse_epw(text)
    sitio.store.set_climate(climate.compact(epw))
    sitio.changed.emit()
    return epw["info"]


def clear_epw(sitio) -> None:
    sitio.store.set_climate(None)
    sitio.changed.emit()

# ---- Analysis on/off (toolbar + menu) --------------------------------------

def toggle_analysis(sitio) -> bool:
    """Flip ``view["on"]`` (show / hide the analysis in the view).

    Returns the new state. Used by the toolbar and the Extensions menu,
    which used to duplicate this logic. Does not touch the panel —
    callers refresh it themselves if they are the panel."""
    v = sitio.store.view()
    v["on"] = not v.get("on", True)
    sitio.store.touch()
    sitio.update_animation()
    return v["on"]

# ---- Basemap ----------------------------------------------------------------

def auto_zoom(lat: float, extent: float) -> int:
    for z in range(19, 11, -1):
        mpp = 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)
        if 2 * extent / mpp <= 2600:
            return z
    return 12


def load_basemap(sitio, provider: str, extent: float, zoom: int = 0,
                 custom: str = "") -> int:
    from georef.tiles import PRESETS, TileLayer, custom_source
    d = sitio.datum()
    if d is None:
        raise SiteError(tr("Locate the project before downloading the basemap."))
    if provider == "custom":
        if "{z}" not in custom or "{x}" not in custom or "{y}" not in custom:
            raise SiteError(tr("The tile URL must contain {z}, {x} and {y}."))
        src = custom_source(custom, name=tr("Custom"))
    else:
        src = PRESETS.get(provider) or next(iter(PRESETS.values()))
    z = int(zoom) if zoom else auto_zoom(d.lat, extent)
    z = min(z, getattr(src, "max_zoom", 19))
    layer = TileLayer(src, zoom=z)
    layer.set_rectangle(float(extent), float(extent))
    layer.cap_detail(d, max_tiles=500)
    layer.visible = True
    sitio.scene.tile_layer = layer
    vp = sitio.app.viewport
    reset = getattr(vp, "reset_tiles", None)
    if callable(reset):
        reset()
    sitio.scene.version += 1
    vp.update()
    return layer.zoom