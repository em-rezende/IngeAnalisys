# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""Minimal i18n for Site Analysis.

Keys are US-English strings. ``tr(key, **kw)`` looks the key up in
``i18n/<lang>.json`` (UTF-8, flat dict) and applies ``str.format(**kw)``.
Without a catalog (or with ``en``), the key itself is returned, so the
code always works — catalogs are optional.

Language resolution (first match wins):

1. ``analisis_sitio.i18n.set_language(<explicit>)`` — highest priority.
2. IngeTrazo's own core: ``core.i18n.current_language()`` (or
   ``app.settings.get("language")`` when available).
3. OS locale via ``QLocale.system()`` (pt* → pt-BR, es* → es, en).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QLocale

log = logging.getLogger("ingetrazo.plugins.analisis_sitio.i18n")

_LANG = "en"
_TABLE: dict[str, str] = {}
_MISSING: set[str] = set()
_SOURCE = "default"                       # where _LANG came from
_EXPLICIT: str | None = None              # set via set_language(<code>)

#: ``i18n.py`` lives inside ``tools/``; the catalogs live in
#: ``<package>/i18n/`` (one level up).
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_I18N_DIR = _ROOT / "i18n"

#: Known catalogs (also used to trim/normalize incoming codes).
_KNOWN = {"en", "pt-BR", "es", "de", "it", "fr", "zh-CN", "ru", "ja"}

#: Aliases: language tags seen in the wild → canonical code.
_ALIASES = {
    "pt": "pt-BR", "pt-br": "pt-BR", "pt_br": "pt-BR",
    "pt-pt": "pt-BR", "pt_pt": "pt-BR",
    "es": "es", "es-es": "es", "es_es": "es",
    "es-mx": "es", "es-ar": "es", "es-co": "es", "es-cl": "es",
    "en": "en", "en-us": "en", "en_us": "en", "en-gb": "en", "en_gb": "en",
    "de": "de", "de-de": "de", "de_de": "de", "de-at": "de", "de-ch": "de",
    "it": "it", "it-it": "it", "it_it": "it",
    "fr": "fr", "fr-fr": "fr", "fr_fr": "fr", "fr-ca": "fr", "fr_ca": "fr",
    "zh": "zh-CN", "zh-cn": "zh-CN", "zh_cn": "zh-CN",
    "zh-hans": "zh-CN", "zh-hans-cn": "zh-CN",
    "zh-sg": "zh-CN", "zh-tw": "zh-CN", "zh-hk": "zh-CN",
    "ru": "ru", "ru-ru": "ru", "ru_ru": "ru",
    "ja": "ja", "ja-jp": "ja", "ja_jp": "ja",
}


def _normalize(code: str | None) -> str:
    if not code:
        return "en"
    raw = str(code).strip()
    if not raw:
        return "en"
    key = raw.replace("_", "-").lower()
    if key in _ALIASES:
        return _ALIASES[key]
    base = key.split("-")[0]
    if base in ("pt", "es", "en", "de", "it", "fr", "zh", "ru", "ja"):
        return {"pt": "pt-BR", "es": "es", "en": "en",
                "de": "de", "it": "it", "fr": "fr",
                "zh": "zh-CN", "ru": "ru", "ja": "ja"}[base]
    return "en"


def _from_host() -> tuple[str | None, str]:
    """Ask IngeTrazo for its active language (best effort)."""
    try:
        from core.i18n import current_language        # type: ignore
        code = current_language()
        if code:
            return str(code), "core.i18n.current_language()"
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        settings = getattr(app, "settings", None)
        if settings is not None and hasattr(settings, "get"):
            code = settings.get("language")
            if code:
                return str(code), "app.settings['language']"
    except Exception:
        pass
    return None, ""


def _from_locale() -> tuple[str, str]:
    try:
        name = QLocale.system().name().replace("_", "-")
        if name:
            return name, "QLocale.system()"
    except Exception:
        pass
    return "en", "default"


def _catalog_path(code: str) -> Path:
    return _I18N_DIR / f"{code}.json"


def _load_catalog(code: str) -> dict[str, str]:
    if code == "en":
        return {}
    p = _catalog_path(code)
    if not p.is_file():
        log.info("i18n: no catalog for %r (%s); using English keys",
                 code, p)
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))   # BOM-safe
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        log.warning("i18n: %s is not a JSON object", p)
    except Exception as exc:                                  # noqa: BLE001
        log.warning("i18n: could not load %s: %s", p, exc)
    return {}


def _apply(code: str, source: str) -> str:
    global _LANG, _TABLE, _MISSING, _SOURCE
    _LANG = code
    _SOURCE = source
    _MISSING = set()
    _TABLE = _load_catalog(code)
    return code


def set_language(code: str | None = None) -> str:
    """Set the language.

    - ``set_language("pt-BR")`` / ``"es"`` / ``"en"`` → force that language.
    - ``set_language(None)`` → re-resolve from IngeTrazo / OS locale.
      If neither has a hint, ``en`` is used.
    """
    global _EXPLICIT
    if code is not None and str(code).strip():
        _EXPLICIT = _normalize(code)
        return _apply(_EXPLICIT, "explicit")
    _EXPLICIT = None
    # Resolve from the host, then from the OS locale.
    hint, source = _from_host()
    if hint:
        return _apply(_normalize(hint), source)
    loc, loc_source = _from_locale()
    return _apply(_normalize(loc), loc_source)


def language() -> str:
    return _LANG


def source() -> str:
    """Human-readable description of where the current language came from."""
    return _SOURCE


def debug_info() -> dict:
    """Diagnostic snapshot for the IngeTrazo console."""
    try:
        host_hint, host_src = _from_host()
    except Exception:
        host_hint, host_src = None, ""
    try:
        loc_hint, loc_src = _from_locale()
    except Exception:
        loc_hint, loc_src = "en", "default"
    return {
        "current_language": _LANG,
        "current_source": _SOURCE,
        "explicit_override": _EXPLICIT,
        "host_hint": (host_hint, host_src),
        "locale_hint": (loc_hint, loc_src),
        "catalog_path": str(_catalog_path(_LANG)),
        "catalog_exists": _catalog_path(_LANG).is_file(),
        "catalog_size": len(_TABLE),
        "missing_count": len(_MISSING),
        "missing_sample": sorted(_MISSING)[:10],
    }


def tr(key: str, **kw) -> str:
    """Translate ``key`` (a US-English string) into the current language.

    Missing catalogs fall back to ``key``. Unknown placeholders are kept
    as-is so a bad catalog never breaks the UI.
    """
    if _LANG != "en":
        s = _TABLE.get(key)
        if s is None:
            if key not in _MISSING:
                _MISSING.add(key)
                log.debug("i18n[%s]: missing key %r", _LANG, key)
            s = key
    else:
        s = key
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError, ValueError):
            return s
    return s


def translate_layer(canonical: str) -> str:
    return tr(canonical)


def migrate_layers(scene) -> None:
    """Rename legacy PT/ES layer names to their English canonical form."""
    legacy = {
        "Masas": "Masses",
        "Lotes": "Lots",
        "Contexto OSM": "OSM Context",
        "Radiación solar": "Solar Radiation",
        "Radiacion solar": "Solar Radiation",
    }
    for ly in getattr(scene, "layers", []) or []:
        new = legacy.get(getattr(ly, "name", ""))
        if new:
            ly.name = new