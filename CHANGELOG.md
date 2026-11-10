# Changelog — Site Analysis (IngeTrazo extension)

The version is `__version__` in `IngeAnalisys/__init__.py`, the `version`
of the catalog entry (`catalog/ingeanalisys.toml`) and the tag
(`v1.9.0`): the three must match, and `scripts/check_plugin.py` says so
when they do not.

## 1.9.0 — first release as a catalog extension

Packaging and compatibility, so the extension can be installed by
**Extensions ▸ Manage extensions…** as well as by hand:

- `dist/IngeAnalisys.zip` — the package the catalog installs: one folder
  with `__init__.py`, no caches, reproducible (same sources, same
  SHA-256). Built by `scripts/build_zip.py`.
- `catalog/ingeanalisys.toml` — the entry for
  [ingetrazo-extensions](https://github.com/ingelibre/ingetrazo-extensions):
  id `ingeanalisys`, licence `GPL-3.0-or-later`, name and summary in
  Spanish, English and Portuguese, tags, and the hash of the ZIP above.
- `scripts/check_plugin.py` — imports the package the way
  `core/extensions.py` does (by path, as `ingetrazo_plugin_<folder>`, host
  stubbed) and imports every module of `tools/`; then checks the entry, the
  ZIP and the screenshot against the rules of that repository.
- `scripts/make_screenshot.py` — the catalog's `< 600 KB` screenshot
  (`screenshots/ingeanalisys.jpg`).
- **Projects keep opening.** The manager installs the package as
  `ingeanalisys`, so `app.key` — the name the document keeps this
  extension's data under — differs from a hand-copied `IngeAnalisys`
  folder. `tools/data.py` now reads the values of both (document data,
  `.view`/`.climate`/`.context` and `group.ext`), so masses, radiation
  maps, pins, winds, the EPW and the view survive either install route.
- `tools/geometry.py`, `tools/radiation.py`, `tools/drawing.py` and
  `tools/panel.py` read group parameters through the new
  `data.ext_data()`, so a map or a mass stored under the old name is still
  found, painted and edited.
- Documentation: install through the manager, the publishing steps, the
  `ingetrazo_plugin_<folder>` module name (it is not
  `ingetrazo_plugin_IngeAnalisys` when installed from the catalog) and the
  real requirements (IngeTrazo ≥ 0.6.1, extensions API 2).
- `.gitignore`: `dist/IngeAnalisys.zip` is versioned on purpose (it is what
  the catalog downloads at the tag).

## 1.8.x and earlier

Feature work before the catalog: 3D solar diagram, real shadows, EPW
weather and charts, radiation and shade-hour maps, OpenStreetMap context,
masses and lots with areas and ratios, annotations, notes, unified toolbar,
nine language catalogs and PNG export. See the README of each language.
