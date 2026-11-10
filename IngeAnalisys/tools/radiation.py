# SPDX-License-Identifier: GPL-3.0-or-later
"""Incident solar radiation on the model surfaces.

BioSim (and Ecotect / Ladybug) method, for each sample point of a surface,
accumulated over the chosen period (kWh/m²):

    I = I_dir + I_dif + I_ref
    I_dir = DNI · cos θ · sunny       (θ: sun ↔ normal; sunny 0/1 by
                                        ray tracing against ALL visible
                                        geometry, context included)
    I_dif = DHI · F_sky               (isotropic sky; F_sky measured with
                                        Tregenza's 145 patches, so an
                                        enclosed courtyard sees less sky)
    I_ref = GHI · ρ · (1 − cos β) / 2 (reflected by the ground, albedo ρ)

with DNI/DHI from the EPW (EPW hour h = interval h−1…h, sun at mid-hour),
or, without an EPW, a theoretical clear sky (Meinel), flagged as such.

Efficiency: the period's hours are grouped by sun position (1° for one
day, 2° for long periods): one year becomes ~1000 directions, not 4400
hours. Each direction is tested at once for all points with a 2D grid in
the plane perpendicular to the sun (numpy, no per-point loop).

Surfaces are subdivided into triangles of side ≤ ``grid`` m: each is one
sample point (the analysis mesh) or, in "per face" mode, area-averaged
into its face.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from core.sun import solar_position

from . import solar
from .data import ext_data
from .i18n import tr

YEAR = solar.YEAR
_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


# ---- Palettes ---------------------------------------------------------------

# Palette id → (English name, ((stop, rgb), …)). Names translated on
# display via :func:`palette_name`.
PALETTES = {
    # Ecotect "Incident Solar Radiation": blue → violet → red → yellow.
    "ecotect": ("Ecotect (blue → yellow; in shadows, yellow = lit)",
                ((0.0, (0, 0, 255)), (0.15, (64, 0, 200)), (0.3, (110, 0, 150)),
                 (0.45, (150, 0, 110)), (0.6, (210, 0, 50)), (0.72, (255, 30, 0)),
                 (0.85, (255, 140, 0)), (1.0, (255, 255, 0)))),
    # BioSim "Total radiation": blue → cyan → green → yellow → red.
    "grises": ("Grays (white = sun, black = shadow)",
               ((0.0, (255, 255, 255)), (1.0, (20, 20, 20)))),
    # Ecotect "Shading time [h]": one class per hour, from yellow (sun)
    # to navy (shadow). Painted by classes, not as a gradient.
    "ecotect_horas": ("Ecotect by hours (yellow = sun → blue = shadow)",
                      tuple((i / 10.0, c) for i, c in enumerate((
                          (255, 255, 51), (255, 178, 0), (255, 122, 0),
                          (255, 26, 26), (240, 20, 110), (225, 25, 175),
                          (20, 178, 178), (26, 138, 204), (26, 80, 180),
                          (42, 26, 153), (13, 13, 102))))),
    "termica": ("Thermal (black → white; in shadows, black = shadow)",
                ((0.0, (0, 0, 0)), (0.35, (120, 20, 20)), (0.65, (240, 120, 0)),
                 (0.85, (255, 220, 60)), (1.0, (255, 255, 255)))),
}


def palette_name(pal: str) -> str:
    return tr(PALETTES.get(pal, PALETTES["ecotect"])[0])


#: Palettes painted by classes (bands), like Ecotect.
STEPPED = {"ecotect_horas"}

#: Palettes whose high end is light (yellow, white): in shade maps they
#: read reversed — most lit is light, most shaded is dark (blue, black).
#: In radiation maps they are used as-is.
LIGHT_HIGH = {"ecotect", "termica"}


def color_at(t: float, palette: str = "ecotect") -> tuple[int, int, int]:
    stops = PALETTES.get(palette, PALETTES["ecotect"])[1]
    t = max(0.0, min(1.0, float(t)))
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(int(round(a + (b - a) * f)) for a, b in zip(c0, c1))
    return stops[-1][1]


def colors_for(values, vmin: float, vmax: float, palette: str) -> np.ndarray:
    """Colors 0–1 (n, 3) — a 256-shade lookup table, no per-value loop."""
    lut = np.asarray([color_at(i / 255.0, palette) for i in range(256)],
                     float) / 255.0
    v = np.asarray(values, float)
    span = max(vmax - vmin, 1e-9)
    idx = np.clip(np.round((v - vmin) / span * 255), 0, 255).astype(int)
    return lut[idx]


# ---- Period and climate -----------------------------------------------------

def period_hours(kind: str, doy: int = 172, month: int = 6,
                 period: dict | None = None) -> list[int]:
    """Year hour indices (0…8759) for the period."""
    def day_range(d0, d1):
        return [h for d in range(d0, d1 + 1) for h in range((d - 1) * 24, d * 24)]
    if kind == "day":
        return day_range(doy, doy)
    if kind == "month":
        d0 = sum(_DAYS[:month - 1]) + 1
        return day_range(d0, d0 + _DAYS[month - 1] - 1)
    if kind == "period" and period:
        from .climate import in_period
        out = []
        for i in range(8760):
            d = date(YEAR, 1, 1) + timedelta(days=i // 24)
            if in_period(d.month, i % 24, period):
                out.append(i)
        return out
    return list(range(8760))


def _clear_sky(alt: float) -> tuple[float, float]:
    """Clear-sky DNI, DHI (W/m²): Meinel with Kasten–Young air mass;
    diffuse ≈ 10 % of direct normal (ASHRAE order)."""
    if alt <= 0:
        return 0.0, 0.0
    z = math.radians(90.0 - alt)
    am = 1.0 / (math.cos(z) + 0.50572 * (96.07995 - math.degrees(z)) ** -1.6364)
    dni = 1353.0 * 0.7 ** (am ** 0.678)
    return dni, 0.1 * dni


def sun_bins(site: dict, hours, epw=None, step_deg: float | None = None):
    """Group hours by sun position. Returns ``(dirs (k,3) in the model,
    W_dir (k,) Wh/m² of DNI, DHI_total, GHI_total, source)``."""
    lat, lon, tz = site["lat"], site["lon"], site["tz"]
    hours = list(hours)
    step = step_deg or (1.0 if len(hours) <= 48 else
                        2.0 if len(hours) <= 31 * 24 else 3.0)
    fr = solar.Frame((0, 0, 0), 1.0, site.get("north", 0.0))
    bins: dict = {}
    dhi_t = ghi_t = 0.0
    tzinfo = timezone(timedelta(hours=tz))
    for i in hours:
        d = date(YEAR, 1, 1) + timedelta(days=i // 24)
        when = datetime(d.year, d.month, d.day, i % 24, 30, tzinfo=tzinfo)
        alt, az = solar_position(lat, lon, when.astimezone(timezone.utc))
        if epw is not None:
            dni, dhi = float(epw["dni"][i]), float(epw["dhr"][i])
        else:
            dni, dhi = _clear_sky(alt)
        if alt <= 0.5:
            continue
        if dni + dhi < 1:
            continue
        ghi = dni * math.sin(math.radians(alt)) + dhi
        dhi_t += dhi
        ghi_t += ghi
        if dni <= 0:
            continue
        key = (round(alt / step) * step, round(az / step) * step % 360)
        bins[key] = bins.get(key, 0.0) + dni
    dirs = np.asarray([fr.direction(a, z) for a, z in bins], float).reshape(-1, 3)
    w = np.asarray(list(bins.values()), float)
    return dirs, w, dhi_t, ghi_t, (tr("EPW") if epw is not None else
                                  tr("theoretical clear sky"))


def tregenza(north: float = 0.0):
    """Tregenza's 145 directions and their solid angles."""
    bands = ((6, 30), (18, 30), (30, 24), (42, 24), (54, 18), (66, 12), (78, 6))
    fr = solar.Frame((0, 0, 0), 1.0, north)
    dirs, omega = [], []
    for alt, n in bands:
        lo, hi = math.radians(alt - 6), math.radians(alt + 6)
        om = 2 * math.pi * (math.sin(hi) - math.sin(lo)) / n
        for k in range(n):
            dirs.append(fr.direction(alt, k * 360.0 / n))
            omega.append(om)
    dirs.append((0.0, 0.0, 1.0))
    omega.append(2 * math.pi * (1 - math.sin(math.radians(84))))
    return np.asarray(dirs), np.asarray(omega)


# ---- Geometry ---------------------------------------------------------------

def _mat(m):
    if m is None:
        return None
    return np.asarray(m.data(), float).reshape(4, 4).T      # column → row


def _xf(pts: np.ndarray, M) -> np.ndarray:
    if M is None:
        return pts
    return pts @ M[:3, :3].T + M[:3, 3]


def face_tris(face, M) -> np.ndarray:
    """Triangles of the face in world coordinates: (t, 3, 3)."""
    tris = face.triangulate()
    if not tris:
        return np.zeros((0, 3, 3))
    a = np.asarray([[(p.x(), p.y(), p.z()) for p in t] for t in tris], float)
    return _xf(a.reshape(-1, 3), M).reshape(-1, 3, 3)


def subdivide(tris: np.ndarray, grid: float) -> np.ndarray:
    """Each triangle into k² similar ones with side ≤ ``grid``."""
    out = []
    for t in tris:
        e = max(np.linalg.norm(t[1] - t[0]), np.linalg.norm(t[2] - t[1]),
                np.linalg.norm(t[0] - t[2]))
        k = max(1, min(64, int(math.ceil(e / max(grid, 1e-3)))))
        if k == 1:
            out.append(t[None])
            continue
        a, b, c = t
        u, v = (b - a) / k, (c - a) / k
        sub = []
        for i in range(k):
            for j in range(k - i):
                p = a + u * i + v * j
                sub.append((p, p + u, p + v))
                if i + j < k - 1:
                    sub.append((p + u, p + u + v, p + v))
        out.append(np.asarray(sub))
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


class Targets:
    """The analyzed surfaces: cells (triangles), their source face, normal
    and area."""

    def __init__(self) -> None:
        self.cells = []          # (n,3,3) per face
        self.normals = []        # (3,) per face
        self.polys = []          # (outer, holes) in world, per face
        self.ground = []         # True for the generated ground
        self.n_faces = 0

    def add_face(self, face, M, grid: float) -> None:
        tris = face_tris(face, M)
        if not len(tris):
            return
        n = face.normal()
        nv = np.array([n.x(), n.y(), n.z()], float)
        if M is not None:
            nv = M[:3, :3] @ nv
        ln = np.linalg.norm(nv)
        if ln < 1e-9:
            return
        nv /= ln
        self.cells.append(subdivide(tris, grid))
        self.normals.append(nv)
        outer = _xf(np.asarray([(p.x(), p.y(), p.z()) for p in face.vertices]), M)
        holes = [_xf(np.asarray([(p.x(), p.y(), p.z()) for p in h]), M)
                 for h in face.holes]
        self.polys.append((outer, holes))
        self.ground.append(False)
        self.n_faces += 1

    def add_plane(self, x0, y0, x1, y1, z, grid: float, cover=None) -> None:
        """A horizontal rectangle (the ground) in square cells, without the
        cells below ``cover`` (faces flush with the ground)."""
        nx = max(1, int(math.ceil((x1 - x0) / grid)))
        ny = max(1, int(math.ceil((y1 - y0) / grid)))
        xs = np.linspace(x0, x1, nx + 1)
        ys = np.linspace(y0, y1, ny + 1)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        a = np.stack([X[:-1, :-1], Y[:-1, :-1]], -1).reshape(-1, 2)
        b = np.stack([X[1:, :-1], Y[1:, :-1]], -1).reshape(-1, 2)
        c = np.stack([X[1:, 1:], Y[1:, 1:]], -1).reshape(-1, 2)
        d = np.stack([X[:-1, 1:], Y[:-1, 1:]], -1).reshape(-1, 2)

        def z3(p):
            return np.column_stack([p, np.full(len(p), z)])
        t1 = np.stack([z3(a), z3(b), z3(c)], 1)
        t2 = np.stack([z3(a), z3(c), z3(d)], 1)
        cells = np.concatenate([t1, t2])
        if cover is not None and len(cells):
            probe = cells.mean(axis=1) - np.array([0.0, 0.0, 0.5])
            free = cover.lit(probe, np.array([0.0, 0.0, 1.0]))
            cells = cells[free]
        if not len(cells):
            return
        self.cells.append(cells)
        self.normals.append(np.array([0.0, 0.0, 1.0]))
        outer = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]])
        self.polys.append((outer, []))
        self.ground.append(True)
        self.n_faces += 1

    def arrays(self):
        if not self.cells:
            z = np.zeros((0, 3))
            return z, z, np.zeros(0), np.zeros(0, int)
        tris = np.concatenate(self.cells)
        owner = np.concatenate([np.full(len(c), i) for i, c in enumerate(self.cells)])
        normals = np.asarray(self.normals)[owner]
        cent = tris.mean(axis=1)
        area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0],
                                             tris[:, 2] - tris[:, 0]), axis=1)
        return cent, normals, area, owner


# ---- Ray tracing ------------------------------------------------------------

def _basis(d):
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    return u, np.cross(d, u)


class Occluders:
    """All triangles that cast shadows, ready to test directions."""

    def __init__(self, tris: np.ndarray) -> None:
        self.tris = np.asarray(tris, float).reshape(-1, 3, 3)

    def lit(self, pts: np.ndarray, d: np.ndarray) -> np.ndarray:
        """Which points see the direction ``d`` (toward the sun / sky)?"""
        n = len(pts)
        lit = np.ones(n, bool)
        if not len(self.tris) or not n:
            return lit
        u, v = _basis(d)
        T = self.tris
        tu, tv, td = T @ u, T @ v, T @ d                     # (t,3)
        pu, pv, pd = pts @ u, pts @ v, pts @ d
        # Only triangles with some vertex "in front of" (toward the sun)
        # the farthest point: the rest cannot occlude anything.
        keep = td.max(axis=1) > pd.min() + 1e-6
        tu, tv, td = tu[keep], tv[keep], td[keep]
        if not len(tu):
            return lit
        lo_u, hi_u = min(tu.min(), pu.min()), max(tu.max(), pu.max())
        lo_v, hi_v = min(tv.min(), pv.min()), max(tv.max(), pv.max())
        span = max(hi_u - lo_u, hi_v - lo_v, 1e-6)
        g = int(min(256, max(8, math.sqrt(len(tu)) * 1.5)))
        cs = span / g
        ci0 = np.clip(((tu.min(1) - lo_u) / cs).astype(int), 0, g - 1)
        ci1 = np.clip(((tu.max(1) - lo_u) / cs).astype(int), 0, g - 1)
        cj0 = np.clip(((tv.min(1) - lo_v) / cs).astype(int), 0, g - 1)
        cj1 = np.clip(((tv.max(1) - lo_v) / cs).astype(int), 0, g - 1)
        nu, nv = ci1 - ci0 + 1, cj1 - cj0 + 1
        cnt = nu * nv
        big = cnt > 4096                                    # huge floors
        tri_ids, cells = [], []
        small = np.nonzero(~big)[0]
        if len(small):
            reps = cnt[small]
            tid = np.repeat(small, reps)
            off = np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)
            nvr = np.repeat(nv[small], reps)
            ii = np.repeat(ci0[small], reps) + off // nvr
            jj = np.repeat(cj0[small], reps) + off % nvr
            tri_ids.append(tid)
            cells.append(ii * g + jj)
        pi = np.clip(((pu - lo_u) / cs).astype(int), 0, g - 1)
        pj = np.clip(((pv - lo_v) / cs).astype(int), 0, g - 1)
        pcell = pi * g + pj
        pairs_p, pairs_t = [], []
        if tri_ids:
            tid = np.concatenate(tri_ids)
            cel = np.concatenate(cells)
            order = np.argsort(cel, kind="stable")
            tid, cel = tid[order], cel[order]
            start = np.searchsorted(cel, pcell, "left")
            stop = np.searchsorted(cel, pcell, "right")
            cnt_p = stop - start
            if cnt_p.sum():
                pp = np.repeat(np.arange(n), cnt_p)
                off = np.arange(cnt_p.sum()) - np.repeat(np.cumsum(cnt_p) - cnt_p,
                                                          cnt_p)
                pairs_p.append(pp)
                pairs_t.append(tid[np.repeat(start, cnt_p) + off])
        bigs = np.nonzero(big)[0]
        if len(bigs):
            pairs_p.append(np.repeat(np.arange(n), len(bigs)))
            pairs_t.append(np.tile(bigs, n))
        if not pairs_p:
            return lit
        P = np.concatenate(pairs_p)
        Tt = np.concatenate(pairs_t)
        # Exact test: point inside the projected triangle and the triangle,
        # at that place, closer to the sun than the point.
        for a in range(0, len(P), 2_000_000):
            p, t = P[a:a + 2_000_000], Tt[a:a + 2_000_000]
            x, y = pu[p], pv[p]
            x0, y0 = tu[t, 0], tv[t, 0]
            x1, y1 = tu[t, 1], tv[t, 1]
            x2, y2 = tu[t, 2], tv[t, 2]
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            ok = np.abs(den) > 1e-12
            den = np.where(ok, den, 1.0)
            w0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / den
            w1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / den
            w2 = 1.0 - w0 - w1
            inside = ok & (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
            depth = w0 * td[t, 0] + w1 * td[t, 1] + w2 * td[t, 2]
            hit = inside & (depth > pd[p] + 1e-4)
            lit[p[hit]] = False
        return lit


def occluders_from_scene(scene, skip=()) -> Occluders:
    """Triangles of everything visible (model, masses, context…), minus the
    groups in ``skip`` (the radiation maps themselves)."""
    skip_faces = set()
    for g in skip:
        if g is not None:
            skip_faces.update(g.mesh.faces)
    chunks = []
    for f, m in scene.iter_world_faces():
        if f in skip_faces or f.attrs.get("hidden"):
            continue
        t = face_tris(f, _mat(m))
        if len(t):
            chunks.append(t)
    return Occluders(np.concatenate(chunks) if chunks else np.zeros((0, 3, 3)))


# ---- Computation ------------------------------------------------------------

def compute(targets: Targets, occ: Occluders, site: dict, hours, epw=None,
            albedo: float = 0.2, progress=None) -> dict:
    """Radiation per cell (kWh/m² in the period) and per face."""
    cent, normals, area, owner = targets.arrays()
    n = len(cent)
    pts = cent + normals * 0.02                     # just off its own face
    dirs, w, dhi_t, ghi_t, source = sun_bins(site, hours, epw)
    sky_d, sky_om = tregenza(site.get("north", 0.0))
    steps = len(dirs) + len(sky_d)
    direct = np.zeros(n)
    done = 0
    for k in range(len(dirs)):
        cos = normals @ dirs[k]
        front = cos > 1e-6
        if front.any():
            idx = np.nonzero(front)[0]
            lit = occ.lit(pts[idx], dirs[k])
            direct[idx[lit]] += w[k] * cos[idx[lit]]
        done += 1
        if progress and done % 10 == 0 and progress(done / steps):
            return {}
    fsky = np.zeros(n)
    for k in range(len(sky_d)):
        cos = normals @ sky_d[k]
        front = cos > 1e-6
        if front.any():
            idx = np.nonzero(front)[0]
            lit = occ.lit(pts[idx], sky_d[k])
            fsky[idx[lit]] += cos[idx[lit]] * sky_om[k] / math.pi
        done += 1
        if progress and done % 10 == 0 and progress(done / steps):
            return {}
    # Normalize to the exact open-sky view (discretization gives ~1 on a
    # roof, not 1.000): a clear horizontal plane sees 1.
    open_h = float(np.sum(sky_d[:, 2].clip(0) * sky_om) / math.pi)
    fsky = np.clip(fsky / max(open_h, 1e-9), 0.0, 1.0)
    cosb = normals[:, 2]
    floor = cosb < -0.98                             # faces looking down
    gnd = np.where(floor, 0.0, (1 - cosb) / 2)
    diffuse = dhi_t * fsky
    refl = ghi_t * albedo * gnd
    total = (direct + diffuse + refl) / 1000.0       # Wh → kWh
    nf = targets.n_faces
    face_val = np.zeros(nf)
    face_area = np.zeros(nf)
    np.add.at(face_val, owner, total * area)
    np.add.at(face_area, owner, area)
    face_val = face_val / np.maximum(face_area, 1e-12)
    return {"cell": total, "cell_dir": direct / 1000.0,
            "cell_dif": diffuse / 1000.0, "cell_ref": refl / 1000.0,
            "face": face_val, "face_area": face_area, "owner": owner,
            "area": area, "source": source, "n_sun": len(dirs),
            "svf": fsky}


# ---- Shade hours (shadow study) ---------------------------------------------

def compute_shadow_hours(targets: Targets, occ: Occluders, site: dict, doy: int,
                         h0: float, h1: float, step_min: int,
                         progress=None) -> dict:
    """Shade hours per cell between ``h0`` and ``h1`` (local time) of
    ``doy``, sampling the sun every ``step_min`` minutes. A face facing
    away from the sun is in shade (self-shade); each step with the sun above
    the horizon counts Δt."""
    cent, normals, area, owner = targets.arrays()
    pts = cent + normals * 0.02
    fr = solar.Frame((0, 0, 0), 1.0, site.get("north", 0.0))
    dt = step_min / 60.0
    times = []
    t = float(h0)
    while t <= h1 + 1e-6:
        times.append(round(t, 4))
        t += dt
    shade = np.zeros(len(cent))
    n_sun = 0
    for i, t in enumerate(times):
        if progress and progress(i / max(1, len(times))):
            return {}
        alt, az = solar.sun_at(site["lat"], site["lon"], site["tz"], doy, t)
        if alt <= 0.5:
            continue
        n_sun += 1
        d = np.asarray(fr.direction(alt, az))
        cos = normals @ d
        lit = np.zeros(len(cent), bool)
        idx = np.nonzero(cos > 1e-6)[0]
        if len(idx):
            lit[idx] = occ.lit(pts[idx], d)
        shade[~lit] += dt
    nf = targets.n_faces
    face_val = np.zeros(nf)
    face_area = np.zeros(nf)
    np.add.at(face_val, owner, shade * area)
    np.add.at(face_area, owner, area)
    return {"cell": shade, "face": face_val / np.maximum(face_area, 1e-12),
            "area": area, "steps": n_sun, "hours": n_sun * dt, "times": times}


# ---- The maps in the model --------------------------------------------------

#: The two map classes: group title and layer.
KINDS = {"radiation": "Solar Radiation", "shadows": "Shadow Study"}
LAYER = "Solar Radiation"
OFFSET = 0.08            # m above the surface: no z-fighting at distance


def kind_title(kind: str) -> str:
    return tr(KINDS.get(kind, KINDS["radiation"]))


def find_group(scene, key: str, kind: str = "radiation"):
    for g in scene.groups:
        data = ext_data(g, key)
        if data is not None and data.get("kind") == kind:
            return g
    return None


def map_groups(scene, key: str) -> list:
    return [g for g in (find_group(scene, key, k) for k in KINDS) if g is not None]


def visible_map(scene, key: str):
    """The visible map (only one at a time)."""
    for g in map_groups(scene, key):
        if not g.hidden and scene.entity_visible(g):
            return g
    return None


def build_group(key: str, targets: Targets, res: dict, mode: str,
                meta: dict, kind: str = "radiation"):
    """The map group: one face per cell (``mode`` "cells") or per surface
    ("faces"), offset from the original and colored."""
    from core.group import Group
    from core.mesh import Mesh
    pos, sizes, counts, values = [], [], [], []
    lift = np.asarray([OFFSET * (0.5 if g else 1.0) for g in targets.ground])
    if mode == "faces":
        for i, (outer, holes) in enumerate(targets.polys):
            nv = targets.normals[i] * lift[i]
            rings = [outer + nv] + [h + nv for h in holes]
            for r in rings:
                pos.extend(r.tolist())
                sizes.append(len(r))
            counts.append(len(rings))
            values.append(float(res["face"][i]))
    else:
        cent, normals, _a, owner = targets.arrays()
        tris = np.concatenate(targets.cells)
        tris = tris + (normals * lift[owner][:, None])[:, None, :]
        pos = tris.reshape(-1, 3).tolist()
        sizes = [3] * len(tris)
        counts = [1] * len(tris)
        values = [float(v) for v in res["cell"]]
    mesh = Mesh()
    faces = mesh.add_faces_bulk(np.asarray(pos, float),
                                np.asarray(sizes, np.int64),
                                np.asarray(counts, np.int64))
    if mode != "faces":
        for e in mesh.edges:                 # no triangle wireframe
            if len(e.faces) > 1:
                e.hidden = True
    g = Group(mesh, name=kind_title(kind))
    g.component = False
    g.ext = {key: dict(meta, kind=kind, mode=mode,
                       values=[round(v, 3) for v in values[:len(faces)]])}
    paint(g, key)
    return g


def value_range(g, key: str) -> tuple[float, float]:
    vals = (ext_data(g, key) or {}).get("values") or [0.0]
    return float(min(vals)), float(max(vals))


def scale(data: dict) -> dict:
    """The scale of a map, the same for painting and for its legend.

    - ``lo``/``hi``: values shown (for shade maps, shade hours, or, with
      ``show`` = "sun", sun hours = total − shade);
    - ``stepped``: by classes (one per hour in shade, 10 in radiation);
    - ``invert``: in sun hours the palette is inverted so the sun color
      stays the same (yellow / white = sunny)."""
    vals = data.get("values") or [0.0]
    shadows = data.get("kind") == "shadows"
    sun = shadows and data.get("show") == "sun"
    total = float(data.get("hours", max(vals)))
    if shadows:
        lo, hi = 0.0, total
    else:
        lo, hi = float(min(vals)), float(max(vals))
        if not data.get("auto", True):
            lo, hi = float(data.get("vmin", lo)), float(data.get("vmax", hi))
    pal = data.get("palette", "grises" if shadows else "ecotect")
    if pal not in PALETTES:                      # e.g. "BioSim", removed
        pal = "grises" if shadows else "ecotect"
    stepped = pal in STEPPED
    n = 10
    if stepped and shadows:
        n = max(1, int(math.ceil(total - 1e-6)))
    return {"lo": lo, "hi": hi, "palette": pal, "stepped": stepped, "n": n,
            "invert": sun, "sun": sun, "total": total, "shadows": shadows}


def scale_t(sc: dict, disp) -> np.ndarray:
    """Shown value → position 0–1 in the palette."""
    v = np.asarray(disp, float)
    span = max(sc["hi"] - sc["lo"], 1e-9)
    if sc["stepped"]:
        if sc["shadows"]:
            # Classes always count shade hours: in "sun hours" each point
            # keeps its color and only the labels change.
            shade = sc["total"] - v if sc["sun"] else v
            cls = np.floor(shade + 1e-6)
            return np.clip(cls, 0, sc["n"]) / sc["n"]
        else:
            cls = np.floor((v - sc["lo"]) / span * sc["n"] + 1e-9)
        t = np.clip(cls, 0, sc["n"]) / sc["n"]
    else:
        t = np.clip((v - sc["lo"]) / span, 0.0, 1.0)
    t = 1.0 - t if sc["invert"] else t           # now: shade fraction
    if sc["shadows"] and sc["palette"] in LIGHT_HIGH:
        t = 1.0 - t                              # light = lit, dark = shade
    return t


def shown_values(data: dict) -> np.ndarray:
    vals = np.asarray(data.get("values") or [], float)
    if data.get("kind") == "shadows" and data.get("show") == "sun":
        return float(data.get("hours", 0.0)) - vals
    return vals


def paint(g, key: str) -> bool:
    """Color the map faces with the stored palette and scale."""
    data = ext_data(g, key) or {}
    vals = data.get("values") or []
    faces = list(g.mesh.faces)
    if len(vals) != len(faces):
        return False
    sc = scale(data)
    data["lo"], data["hi"] = sc["lo"], sc["hi"]
    t = scale_t(sc, shown_values(data))
    if sc["stepped"]:
        # Classes: exact color per class (few, no table).
        uniq, inv = np.unique(np.round(t, 9), return_inverse=True)
        table = np.asarray([color_at(u, sc["palette"]) for u in uniq],
                           float) / 255.0
        cols = table[inv]
    else:
        lut = np.asarray([color_at(i / 255.0, sc["palette"])
                          for i in range(256)], float) / 255.0
        cols = lut[np.clip(np.round(t * 255), 0, 255).astype(int)]
    for f, c in zip(faces, cols):
        f.attrs["color"] = (float(c[0]), float(c[1]), float(c[2]))
    mesh = g.mesh
    mesh._chunk_dirty = True
    if hasattr(mesh, "_mut_serial"):
        mesh._mut_serial += 1
    return True


# ---- End to end -------------------------------------------------------------

MAX_CELLS = 60000


def collect_targets(sitio, mode: str, grid: float, ground: bool = False,
                    ground_r: float = 0.0) -> Targets:
    """Surfaces to analyze: the selection, masses and lots, or the whole
    visible model (without the OSM context or the maps), and optionally a
    ground around it (where shadows fall even without geometry)."""
    from core.group import iter_placements
    from core.mesh import Face

    from . import actions as act
    scene = sitio.scene
    key = sitio.store.key
    maps = map_groups(scene, key)
    ctx_g = act.context_group(sitio)
    T = Targets()

    def add_group(g0):
        for g, m in iter_placements(g0):
            M = _mat(m)
            for f in g.mesh.faces:
                if not f.attrs.get("hidden"):
                    T.add_face(f, M, grid)

    if mode == "sel":
        for e in list(scene.selection):
            if isinstance(e, Face):
                T.add_face(e, None, grid)
            elif hasattr(e, "mesh") and e not in maps:
                add_group(e)
    elif mode == "masses":
        for g in act.masses(sitio):
            if scene.entity_visible(g):
                add_group(g)
    elif mode == "all":
        skip = set()
        for g in maps + [ctx_g]:
            if g is not None:
                skip.update(g.mesh.faces)
        for f, m in scene.iter_world_faces():
            if f not in skip and not f.attrs.get("hidden"):
                T.add_face(f, _mat(m), grid)
    if ground:
        add_ground(T, sitio, grid, ground_r, maps + [ctx_g])
    return T


def add_ground(T: Targets, sitio, grid: float, radius: float, skip) -> None:
    """A square ground under the model: around the chosen surfaces (or the
    whole model), with margin for long shadows."""
    if T.cells:
        pts = np.concatenate(T.cells).reshape(-1, 3)
    else:
        chunks = []
        skip_f = set()
        for g in skip:
            if g is not None:
                skip_f.update(g.mesh.faces)
        for f, m in sitio.scene.iter_world_faces():
            if f not in skip_f:
                chunks.append(face_tris(f, _mat(m)).reshape(-1, 3))
        pts = np.concatenate(chunks) if chunks else np.zeros((1, 3))
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    height = max(hi[2] - lo[2], 3.0)
    margin = float(radius) if radius > 0 else min(max(2.5 * height, 15.0), 150.0)
    x0, y0 = lo[0] - margin, lo[1] - margin
    x1, y1 = hi[0] + margin, hi[1] + margin
    g = max(grid, max(x1 - x0, y1 - y0) / 160.0)    # ≤ ~50 000 cells
    z0 = float(lo[2])
    # Ground excludes what already covers it: building bases (OSM
    # included) and lots. There the ground does not count and its map
    # would flicker against those faces.
    flat = []
    skip_f = set()
    for gg in skip:
        if gg is not None and gg is not _ctx_of(skip):
            skip_f.update(gg.mesh.faces)
    for f, m in sitio.scene.iter_world_faces():
        if f in skip_f:
            continue
        t = face_tris(f, _mat(m))
        if len(t):
            zz = t[:, :, 2]
            keep = (np.abs(zz - z0) < 0.3).all(axis=1)
            if keep.any():
                flat.append(t[keep])
    T.add_plane(x0, y0, x1, y1, z0, g,
                cover=Occluders(np.concatenate(flat)) if flat else None)


def _ctx_of(skip):
    """In ``skip`` go the maps and, at the end, the context group: the
    context DOES count for trimming the ground below its buildings."""
    return skip[-1] if skip else None


def n_cells(T: Targets) -> int:
    return int(sum(len(c) for c in T.cells))


def _occ(sitio):
    return occluders_from_scene(sitio.scene,
                                skip=map_groups(sitio.scene, sitio.store.key))


def _targets(sitio, settings):
    from .actions import SiteError
    grid = float(settings.get("grid", 1.0))
    target = settings.get("target", "all")
    ground = bool(settings.get("ground", False))
    gr = float(settings.get("ground_r", 0.0))
    T = collect_targets(sitio, target, grid, ground, gr)
    if not T.n_faces or not n_cells(T):
        raise SiteError({
            "sel": tr("Select the faces or groups to analyze."),
            "masses": tr("There are no visible masses or lots."),
        }.get(target, tr("There are no visible surfaces to analyze.")))
    while n_cells(T) > MAX_CELLS and grid < 20:
        grid *= 1.6
        T = collect_targets(sitio, target, grid, ground, gr)
    return T, grid


def _place(sitio, kind: str, new, message: str) -> None:
    """Place the new map (replacing the one of its class and hiding the
    other)."""
    from .data import run_step
    from .geometry import ensure_layer
    key = sitio.store.key
    old = find_group(sitio.scene, key, kind)
    others = [g for g in map_groups(sitio.scene, key) if g is not old]

    def mutate(sc):
        if old is not None and old in sc.groups:
            sc.groups.remove(old)
            sc.selection.discard(old)
        for o in others:
            o.hidden = True
        new.layer = ensure_layer(sc, LAYER)
        new.locked = True
        sc.groups.append(new)

    run_step(sitio.app.viewport, mutate, message=message)


def analyse(sitio, settings: dict, progress=None) -> dict | None:
    """Incident radiation: compute and leave the map in the model (one
    undo step). Returns the summary, or None if cancelled."""
    import time
    t0 = time.monotonic()
    T, grid = _targets(sitio, settings)
    doy, _h = sitio.when()
    view = sitio.store.view()
    hours = period_hours(settings.get("period", "day"), doy,
                         int(settings.get("month", 6)), view.get("period"))
    res = compute(T, _occ(sitio), sitio.site(), hours, sitio.epw(),
                  float(settings.get("albedo", 0.2)), progress)
    if not res:
        return None
    key = sitio.store.key
    per = settings.get("period", "day")
    m, d = solar.month_day(doy)
    from .climate import month_long, month_short
    if per == "day":
        label = tr("{d} {month}", d=d, month=month_long(m - 1))
    elif per == "month":
        label = month_long(int(settings.get('month', 6)) - 1).capitalize()
    elif per == "period":
        label = tr("Analysis period ({m0}–{m1}, {h0}–{h1} h)",
                   m0=month_short(view['period']['m0'] - 1),
                   m1=month_short(view['period']['m1'] - 1),
                   h0=view['period']['h0'], h1=view['period']['h1'])
    elif per == "year":
        label = tr("Full year")
    else:
        label = per
    meta = {"period": label, "source": res["source"], "grid": round(grid, 2),
            "palette": settings.get("palette", "ecotect"),
            "auto": bool(settings.get("auto", True)),
            "vmin": float(settings.get("vmin", 0.0)),
            "vmax": float(settings.get("vmax", 1000.0))}
    new = build_group(key, T, res, settings.get("mode", "cells"), meta)
    _place(sitio, "radiation", new, tr("Radiation map ready."))
    a, tot = res["area"], res["cell"]
    summary = {
        "faces": T.n_faces, "cells": len(tot), "area": float(a.sum()),
        "min": float(tot.min()), "max": float(tot.max()),
        "mean": float((tot * a).sum() / max(a.sum(), 1e-9)),
        "energy": float((tot * a).sum()), "source": res["source"],
        "n_sun": res["n_sun"], "grid": grid, "period": label,
        "seconds": time.monotonic() - t0}
    new.ext[key]["summary"] = summary
    sitio.changed.emit()
    return summary


def shadow_study(sitio, settings: dict, progress=None) -> dict | None:
    """Shadow study of the day in section 4, over the model and the ground,
    in the main view: shade hours per point."""
    import time

    from .actions import SiteError
    from .climate import month_short
    t0 = time.monotonic()
    h0, h1 = float(settings.get("h0", 7)), float(settings.get("h1", 18))
    step = int(settings.get("step", 30))
    if h1 <= h0:
        raise SiteError(tr("The end hour must be greater than the start hour."))
    T, grid = _targets(sitio, settings)
    doy, _h = sitio.when()
    res = compute_shadow_hours(T, _occ(sitio), sitio.site(), doy, h0, h1, step,
                               progress)
    if not res:
        return None
    if not res["steps"]:
        raise SiteError(tr("The sun is not above the horizon in that interval."))
    key = sitio.store.key
    m, d = solar.month_day(doy)
    caption = (tr("{month} {d} · {h0}→{h1} · Δt {step} min · {n} steps",
                  month=month_short(m - 1), d=d,
                  h0=solar.fmt_hour(h0), h1=solar.fmt_hour(h1),
                  step=step, n=res['steps']))
    meta = {"period": caption, "source": tr("{h:.1f} h of sun in the interval",
                                            h=res['hours']),
            "grid": round(grid, 2), "palette": settings.get("palette", "grises"),
            "show": settings.get("show", "shade"),
            "auto": False, "vmin": 0.0, "vmax": float(res["hours"]),
            "steps": res["steps"], "hours": res["hours"]}
    new = build_group(key, T, res, settings.get("mode", "cells"), meta,
                      kind="shadows")
    _place(sitio, "shadows", new, tr("Shadow study ready."))
    a, sh = res["area"], res["cell"]
    summary = {"faces": T.n_faces, "cells": len(sh), "area": float(a.sum()),
               "steps": res["steps"], "hours": res["hours"], "grid": grid,
               "caption": caption,
               "full_sun": float(a[sh < 1e-9].sum()),
               "full_shade": float(a[sh >= res["hours"] - 1e-9].sum()),
               "mean": float((sh * a).sum() / max(a.sum(), 1e-9)),
               "seconds": time.monotonic() - t0}
    new.ext[key]["summary"] = summary
    sitio.changed.emit()
    return summary


def recolor(sitio, kind: str = "radiation", **changes) -> bool:
    g = find_group(sitio.scene, sitio.store.key, kind)
    if g is None:
        return False
    data = ext_data(g, sitio.store.key)
    if data is None:                     # cannot happen: find_group found it
        return False
    data.update(changes)
    ok = paint(g, sitio.store.key)
    sitio.scene.version += 1
    notify = getattr(sitio.app.viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    sitio.app.viewport.update()
    return ok


def show_map(sitio, kind: str | None) -> None:
    """Show one map (and hide the other), or none with ``None``."""
    for k in KINDS:
        g = find_group(sitio.scene, sitio.store.key, k)
        if g is not None:
            g.hidden = (k != kind)
    sitio.store.touch()
    notify = getattr(sitio.app.viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()