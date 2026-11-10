# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""Solar diagram geometry — paths, analemmas, yearly band.

The sun position comes from IngeTrazo itself (``core.sun``, NOAA
equations): the same one that casts the real shadows, so the diagram and
the shadow never disagree. Here we only map (altitude, azimuth) to model
points: X east, Y north, Z up, rotated by the datum north angle
(``SceneDatum.north``) when the model does not look north.

Everything returns lists of tuples (x, y, z) in meters; the drawer
projects them in one batch with ``ExtensionApp.world_to_pixels``.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

from core.sun import solar_position

from .i18n import tr

YEAR = 2026                       # ShadowSettings year (not a leap year)
OBLIQUITY = 23.44
EMPTY_TIME = "—"                  # em dash, not translated


def doy_of(month: int, day: int) -> int:
    try:
        return date(YEAR, month, day).timetuple().tm_yday
    except ValueError:
        return 80


def month_day(doy: int) -> tuple[int, int]:
    d = date(YEAR, 1, 1) + timedelta(days=max(1, min(365, int(doy))) - 1)
    return d.month, d.day


def sun_at(lat: float, lon: float, tz: float, doy: int,
           hour: float) -> tuple[float, float]:
    """``(altitude, azimuth)`` in degrees for the local hour of ``doy``."""
    m, d = month_day(doy)
    base = datetime(YEAR, m, d, tzinfo=timezone(timedelta(hours=tz)))
    when = (base + timedelta(hours=hour)).astimezone(timezone.utc)
    return solar_position(lat, lon, when)


def sun_times(lat: float, lon: float, tz: float, doy: int,
              horizon: float = -0.833) -> tuple[float | None, float | None]:
    """Local sunrise and sunset (standard refraction), or None."""
    rise = sset = None
    prev = sun_at(lat, lon, tz, doy, 0.0)[0]
    step = 5.0 / 60.0
    h = step
    while h <= 24.0 + 1e-9:
        cur = sun_at(lat, lon, tz, doy, h)[0]
        if prev < horizon <= cur and rise is None:
            rise = _refine(lat, lon, tz, doy, h - step, h, horizon)
        if prev >= horizon > cur:
            sset = _refine(lat, lon, tz, doy, h - step, h, horizon)
        prev = cur
        h += step
    return rise, sset


def _refine(lat, lon, tz, doy, a, b, horizon) -> float:
    fa = sun_at(lat, lon, tz, doy, a)[0] - horizon
    for _ in range(18):
        m = 0.5 * (a + b)
        fm = sun_at(lat, lon, tz, doy, m)[0] - horizon
        if (fa < 0) == (fm < 0):
            a, fa = m, fm
        else:
            b = m
    return 0.5 * (a + b)


def fmt_hour(h: float | None) -> str:
    if h is None or (isinstance(h, float) and math.isnan(h)):
        return EMPTY_TIME
    hh = int(math.floor(h))
    mm = int(round((h - hh) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    return f"{hh:02d}:{mm:02d}"


class Frame:
    """Diagram center and orientation: (alt, az) → model points."""

    def __init__(self, center=(0.0, 0.0, 0.0), radius: float = 100.0,
                 north_deg: float = 0.0) -> None:
        self.cx, self.cy, self.cz = (float(c) for c in center)
        self.r = float(radius)
        b = math.radians(north_deg)
        self._c, self._s = math.cos(b), math.sin(b)

    def grid_to_local(self, e: float, n: float) -> tuple[float, float]:
        """Geographic east/north → model axes (like SceneDatum)."""
        return e * self._c + n * self._s, n * self._c - e * self._s

    def direction(self, alt: float, az: float) -> tuple[float, float, float]:
        er, ar = math.radians(alt), math.radians(az)
        x, y = self.grid_to_local(math.cos(er) * math.sin(ar),
                                  math.cos(er) * math.cos(ar))
        return x, y, math.sin(er)

    def sky(self, alt: float, az: float, scale: float = 1.0,
            lift: float = 0.0) -> tuple[float, float, float]:
        """Point on the sky dome of radius ``r·scale`` (altitude ≥ 0)."""
        dx, dy, dz = self.direction(max(alt, 0.0), az)
        r = self.r * scale
        return (self.cx + dx * r, self.cy + dy * r, self.cz + dz * r + lift)

    def ground(self, az: float, radius: float,
               lift: float = 0.0) -> tuple[float, float, float]:
        """Ground-plane point at ``radius`` in the ``az`` bearing."""
        x, y = self.grid_to_local(math.sin(math.radians(az)) * radius,
                                  math.cos(math.radians(az)) * radius)
        return (self.cx + x, self.cy + y, self.cz + lift)


def _split_day(samples):
    """[(alt, az, …)] → runs of consecutive above-horizon samples."""
    runs, cur = [], []
    for s in samples:
        if s[0] > 0:
            cur.append(s)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def day_path(lat, lon, tz, doy, frame: Frame, steps_per_hour: int = 12):
    """Runs (lists of points) of the day's path."""
    samples = [sun_at(lat, lon, tz, doy, i / steps_per_hour)
               for i in range(24 * steps_per_hour + 1)]
    return [[frame.sky(a, z) for a, z in run] for run in _split_day(samples)]


def hour_marks(lat, lon, tz, doy, frame: Frame, min_alt: float = 0.5):
    """[(hour, point, alt)] for whole hours with the sun up."""
    out = []
    for h in range(24):
        a, z = sun_at(lat, lon, tz, doy, float(h))
        if a > min_alt:
            out.append((h, frame.sky(a, z), a))
    return out


def analemmas(lat, lon, tz, frame: Frame):
    """For each hour, the runs of its analemma (day 1 → 365, step 3)."""
    out = []
    for h in range(24):
        samples = [sun_at(lat, lon, tz, min(d, 365), float(h))
                   for d in range(1, 367, 3)]
        if not any(a > 0 for a, _ in samples):
            continue
        samples.append(samples[0])
        out.extend([frame.sky(a, z) for a, z in run]
                   for run in _split_day(samples) if len(run) > 1)
    return out


def _alt_az(lat: float, decl: float, ha: float) -> tuple[float, float]:
    """Altitude/azimuth from declination and hour angle (radians)."""
    phi = math.radians(lat)
    s = (math.sin(phi) * math.sin(decl)
         + math.cos(phi) * math.cos(decl) * math.cos(ha))
    alt = math.asin(max(-1.0, min(1.0, s)))
    az = math.degrees(math.atan2(
        math.sin(ha), math.cos(ha) * math.sin(phi)
        - math.tan(decl) * math.cos(phi))) + 180.0
    return math.degrees(alt), az % 360.0


def band_quads(lat: float, frame: Frame, rows: int = 16, cols: int = 96):
    """Quads of the yearly solar band (solstices to solstices): the sky
    strip the sun crosses across the year."""
    e = math.radians(OBLIQUITY)
    grid = []
    for i in range(rows + 1):
        decl = -e + 2 * e * i / rows
        row = []
        for j in range(cols + 1):
            ha = math.radians(-180.0 + 360.0 * j / cols)
            row.append(_alt_az(lat, decl, ha))
        grid.append(row)
    quads = []
    for i in range(rows):
        for j in range(cols):
            c = (grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j])
            if any(a > 0 for a, _ in c):
                quads.append([frame.sky(a, z) for a, z in c])
    return quads