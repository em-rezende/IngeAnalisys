# SPDX-License-Identifier: GPL-3.0-or-later
"""Weather from an EPW (EnergyPlus Weather) file.

EPW reading, statistics for the analysis period, wind rose (16 sectors × 5
speed ranges) and monthly climate. Pure Python: no Qt, so it can be tested
without a window.

Same rules as the web app «Análisis de Sitio 3D»:

- February 29 is dropped; an EPW must give ≥ 8000 hourly records;
- calm = wind < 0.5 m/s; ranges 0.5–2, 2–4, 4–6, 6–8, > 8 m/s;
- EPW hour 1 is 00:00–01:00 (use ``hour - 1``);
- the dominant winds are the three most frequent non-adjacent sectors.

The document stores a compact, rounded version (lists of numbers), not the
file text: it fits in the .igz and reopens without the original EPW.
"""
from __future__ import annotations

import math

from .i18n import tr

# Speed range edges (m/s) and their labels. Labels are numeric — not
# translated; only the "calm" caption is.
SPEED_EDGES = (0.5, 2.0, 4.0, 6.0, 8.0, math.inf)
SPEED_LABELS = ("0.5–2", "2–4", "4–6", "6–8", ">8")
CALM = 0.5

# 16-point compass — short codes are universal, long names are translated
# at display time via :func:`dir16_long_name`.
DIR16 = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
         "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
DIR16_LONG_EN = ("North", "North-northeast", "Northeast", "East-northeast",
                 "East", "East-southeast", "Southeast", "South-southeast",
                 "South", "South-southwest", "Southwest", "West-southwest",
                 "West", "West-northwest", "Northwest", "North-northwest")
#: Legacy Spanish array, kept so old documents still resolve.
DIR16_LONG = ("Norte", "Nor-noreste", "Noreste", "Este-noreste", "Este",
              "Este-sureste", "Sureste", "Sur-sureste", "Sur", "Sur-suroeste",
              "Suroeste", "Oeste-suroeste", "Oeste", "Oeste-noroeste",
              "Noroeste", "Nor-noroeste")

MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_LONG_EN = ("January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November",
                  "December")
#: Legacy Spanish arrays (used only for reading old call sites).
MONTHS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep",
          "Oct", "Nov", "Dic")
MONTHS_LONG = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
               "julio", "agosto", "septiembre", "octubre", "noviembre",
               "diciembre")

# Hourly fields kept (name → EPW column).
FIELDS = {"t": 6, "rh": 8, "ghr": 13, "dni": 14, "dhr": 15, "wd": 20, "ws": 21}


def dir16_long_name(i: int) -> str:
    return tr(DIR16_LONG_EN[i % 16])


def month_short(i: int) -> str:
    return tr(MONTHS_EN[i])


def month_long(i: int) -> str:
    return tr(MONTHS_LONG_EN[i])


class EpwError(ValueError):
    """The file is not a usable EPW."""


def parse_epw(text: str) -> dict:
    """EPW text → ``{"info": {...}, "month": [...], "day": [...],
    "hour": [...], "t": [...], ...}`` with 8760 hourly records."""
    lines = text.splitlines()
    head = (lines[0] if lines else "").split(",")
    if not head or not head[0].strip().upper().startswith("LOCATION"):
        raise EpwError(tr("This does not look like an EPW file "
                          "(missing LOCATION line)."))

    def num(i):
        try:
            return float(head[i])
        except (IndexError, ValueError):
            return math.nan

    info = {
        "city": head[1].strip() if len(head) > 1 else "",
        "state": head[2].strip() if len(head) > 2 else "",
        "country": head[3].strip() if len(head) > 3 else "",
        "source": head[4].strip() if len(head) > 4 else "",
        "wmo": head[5].strip() if len(head) > 5 else "",
        "lat": num(6), "lon": num(7), "tz": num(8), "elev": num(9),
    }
    if math.isnan(info["lat"]) or math.isnan(info["lon"]):
        raise EpwError(tr("Invalid coordinates in the EPW header."))
    start = 0
    for i, ln in enumerate(lines[:20]):
        if ln.upper().startswith("DATA PERIODS"):
            start = i + 1
            break
    start = start or 8
    out = {"info": info, "month": [], "day": [], "hour": []}
    for k in FIELDS:
        out[k] = []
    for ln in lines[start:]:
        if len(out["month"]) >= 8760:
            break
        c = ln.split(",")
        if len(c) < 22:
            continue
        try:
            m, d, h = int(float(c[1])), int(float(c[2])), int(float(c[3]))
            vals = {k: float(c[i]) for k, i in FIELDS.items()}
        except ValueError:
            continue
        if m == 2 and d == 29:
            continue
        out["month"].append(m)
        out["day"].append(d)
        out["hour"].append(h)
        for k, v in vals.items():
            out[k].append(v)
    n = len(out["month"])
    if n < 8000:
        raise EpwError(tr("The EPW has {n} hourly records; 8760 were expected.",
                          n=n))
    return out


def compact(epw: dict) -> dict:
    """What the document stores: rounded numbers, JSON friendly."""
    out = {"info": dict(epw["info"]), "month": list(epw["month"]),
           "day": list(epw["day"]), "hour": list(epw["hour"])}
    for k in FIELDS:
        dec = 0 if k in ("ghr", "dni", "dhr", "wd", "rh") else 1
        out[k] = [round(v, dec) if dec else int(round(v)) for v in epw[k]]
    return out


def valid(epw) -> bool:
    try:
        return (isinstance(epw, dict) and isinstance(epw.get("info"), dict)
                and len(epw["month"]) >= 8000
                and all(len(epw[k]) == len(epw["month"]) for k in FIELDS))
    except (KeyError, TypeError):
        return False


def in_period(month: int, hour0: int, period: dict) -> bool:
    """Does the record (month 1–12, hour 0–23) fall inside ``period``?
    Periods can wrap the year (Nov→Feb) or the night (20→6)."""
    m0, m1 = period.get("m0", 1), period.get("m1", 12)
    h0, h1 = period.get("h0", 0), period.get("h1", 24)
    ok_m = (m0 <= month <= m1) if m0 <= m1 else (month >= m0 or month <= m1)
    ok_h = (h0 <= hour0 < h1) if h0 <= h1 else (hour0 >= h0 or hour0 < h1)
    return ok_m and ok_h


def direction_index(deg: float) -> int:
    return int(round(((deg % 360.0) + 360.0) % 360.0 / 22.5)) % 16


def speed_bin(ws: float) -> int:
    k = 0
    while ws >= SPEED_EDGES[k + 1]:
        k += 1
    return k


def stats(epw: dict, period: dict | None = None) -> dict:
    """Period statistics: rose, frequencies, mean speeds per sector,
    dominants, means, and the monthly climate (always whole year)."""
    period = period or {}
    rose = [[0] * len(SPEED_LABELS) for _ in range(16)]
    sp_sum = [0.0] * 16
    cnt = [0] * 16
    total = calm = 0
    s_t = s_rh = s_ws = 0.0
    t_min, t_max = math.inf, -math.inf
    monthly = [{"t": 0.0, "tmin": math.inf, "tmax": -math.inf, "rh": 0.0,
                "ghr": 0.0, "ws": 0.0, "n": 0} for _ in range(12)]
    M, H = epw["month"], epw["hour"]
    T, RH, WD, WS, GHR = epw["t"], epw["rh"], epw["wd"], epw["ws"], epw["ghr"]
    for i in range(len(M)):
        m, t = M[i], T[i]
        mo = monthly[m - 1]
        mo["t"] += t
        mo["rh"] += RH[i]
        mo["ghr"] += GHR[i]
        mo["ws"] += WS[i]
        mo["n"] += 1
        mo["tmin"] = min(mo["tmin"], t)
        mo["tmax"] = max(mo["tmax"], t)
        if not in_period(m, H[i] - 1, period):
            continue
        total += 1
        s_t += t
        s_rh += RH[i]
        s_ws += WS[i]
        t_min, t_max = min(t_min, t), max(t_max, t)
        ws = WS[i]
        if ws < CALM:
            calm += 1
            continue
        d = direction_index(WD[i])
        rose[d][speed_bin(ws)] += 1
        sp_sum[d] += ws
        cnt[d] += 1
    for mo in monthly:
        n = mo["n"]
        if n:
            mo["t"] /= n
            mo["rh"] /= n
            mo["ws"] /= n
            mo["ghr"] /= 1000.0           # kWh/m² in the month
        else:
            mo["tmin"] = mo["tmax"] = mo["t"]
    freq = [c / total if total else 0.0 for c in cnt]
    avg_sp = [sp_sum[d] / cnt[d] if cnt[d] else 0.0 for d in range(16)]
    order = sorted(range(16), key=lambda d: -freq[d])
    top: list[int] = []
    for d in order:
        if freq[d] <= 0:
            break
        if not any(min(abs(d - o), 16 - abs(d - o)) <= 1 for o in top):
            top.append(d)
            if len(top) >= 3:
                break
    nan = math.nan
    return {
        "total": total, "calm": calm / total if total else 0.0,
        "rose": rose, "freq": freq, "avg_sp": avg_sp, "top": top,
        "monthly": monthly,
        "avg_t": s_t / total if total else nan,
        "avg_rh": s_rh / total if total else nan,
        "avg_ws": s_ws / total if total else nan,
        "t_min": t_min if total else nan, "t_max": t_max if total else nan,
    }


def hourly(epw: dict | None, doy: int, hour: float) -> dict | None:
    """The record for day of year (1–365) and local hour (0–24)."""
    if not epw:
        return None
    n = len(epw["month"])
    i = max(0, min(n - 1, (int(doy) - 1) * 24 + min(23, int(math.floor(hour)))))
    return {k: epw[k][i] for k in ("t", "rh", "wd", "ws", "ghr")}


# ---- Rose palettes (OKLab interpolation, as in the web app) ----

# Palette id → (English name, (start, end) hex stops). Names are
# translated at display time via :func:`palette_name`.
PALETTES = {
    "amber": ("Amber", ("#fde68a", "#9a3f06")),
    "blue": ("Blue", ("#bfdbfe", "#1e3a8a")),
    "teal": ("Teal", ("#99f6e4", "#115e59")),
    "green": ("Green", ("#d9f99d", "#3f6212")),
    "purple": ("Purple", ("#e9d5ff", "#581c87")),
    "red": ("Red", ("#fecaca", "#991b1b")),
    "gray": ("Gray", ("#e5e7eb", "#374151")),
    "custom": ("Custom (2 colors)", None),
}


def palette_name(pal: str) -> str:
    return tr(PALETTES.get(pal, PALETTES["amber"])[0])


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c: float) -> int:
    v = c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return int(round(max(0.0, min(1.0, v)) * 255))


def _to_oklab(hexc: str):
    v = int(hexc.lstrip("#")[:6], 16)
    r, g, b = _lin((v >> 16) & 255), _lin((v >> 8) & 255), _lin(v & 255)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def _from_oklab(lab) -> str:
    L, a, b = lab
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = _gam(4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_)
    g = _gam(-1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_)
    bb = _gam(-0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    return f"#{r:02x}{g:02x}{bb:02x}"


def rose_colors(pal: str, c0: str = "#bfdbfe", c1: str = "#1e3a8a") -> list[str]:
    """One color per speed range, from calm to strong."""
    ends = PALETTES.get(pal, PALETTES["amber"])[1] or (c0, c1)
    a, b = _to_oklab(ends[0]), _to_oklab(ends[1])
    n = len(SPEED_LABELS)
    return [_from_oklab(tuple(a[k] + (b[k] - a[k]) * i / (n - 1)
                              for k in range(3))) for i in range(n)]