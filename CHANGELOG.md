# Changelog — Site Analysis (IngeTrazo extension)

The version is `__version__` in `IngeAnalisys/__init__.py`, the `version`
of the catalog entry (`catalog/ingeanalisys.toml`) and the tag
(`v1.9.0`): the three must match, and `scripts/check_plugin.py` says so
when they do not.

## Credits

The extension `analisis_sitio` — its idea, its method and its first
implementation — is the work of **jufegofoto-cell**
(<https://github.com/jufegofoto-cell/IngeAnalisys>), who brought the
*Análisis de Sitio 3D* web app into IngeTrazo. Everything below in this file
is a modification made in a fork, and it is credited as such in `CREDITS.md`,
in the docstring of `IngeAnalisys/__init__.py`, in the header of every module
of the package and in the catalog entry (`author = "jufegofoto-cell"`). The
original author was informed of these changes before publication:
<https://github.com/jufegofoto-cell/IngeAnalisys/issues/2>.

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

## 1.9.1 — the modules of the build that runs, again

The previous release had rewritten five modules — `tools/data.py`,
`tools/drawing.py`, `tools/geometry.py`, `tools/panel.py` and
`tools/radiation.py` — with three changes that stopped the extension from
working:

- `Store.view()` returned a **copy** of the view instead of the dict kept in
  `plugin_data`, so the panel changed the colours, radii and checkboxes of a
  copy and every change was lost on the next repaint;
- a `data.ext_data()` fallback read the parameters of a group under several
  names;
- the information and the colour-scale boxes became draggable
  `FloatingBox` widgets.

All five are back to the modules of the build that runs — byte for byte, plus
the credit line every file carries — so there is no `ext_data()`, no
`FloatingBox`, and `Store.view()` returns the stored dict again.
`scripts/check_plugin.py` now checks the names the values used to have
(`.vista` / `.clima` / `.contexto`) instead of `ext_data()`. The ZIP was
rebuilt (the catalogue's `sha256` follows it).

What a project saved through the *other* installation route does lose: values
are written and read under the name of the folder the extension is installed
in, so a document saved while the folder was called `IngeAnalisys` is not
read by an installation called `ingeanalisys`.

## 1.8.x and earlier

Feature work before the catalog: 3D solar diagram, real shadows, EPW
weather and charts, radiation and shade-hour maps, OpenStreetMap context,
masses and lots with areas and ratios, annotations, notes, unified toolbar,
nine language catalogs and PNG export. See the README of each language.
