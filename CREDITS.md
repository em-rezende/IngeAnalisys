# Credits — Site Analysis for IngeTrazo

This extension is **not** the original work of the maintainer of this fork.
It is a derivative work and the credit belongs to the people below. Nothing
here is claimed as work from scratch.

| Layer | Author |
|---|---|
| The web app *Análisis de Sitio 3D* the extension comes from (method, panels, calculations, texts) | its own authors |
| The IngeTrazo extension `analisis_sitio` — design and first implementation of everything: EPW climate, 3D solar diagram and real shadows, winds, OSM context, masses and lots with areas and ratios, radiation and shade-hour maps, annotations, PNG export | **jufegofoto-cell** — <https://github.com/jufegofoto-cell/IngeAnalisys> |
| This fork, 1.9.0 — nine language catalogs, layout in `tools/` + `i18n/` + `icons/`, one 19-button toolbar with SVG icons, draggable floating panels, fixes to shortcuts and dialog loading, packaging for the extension catalog | Ezequiel M. Rezende — <https://github.com/em-rezende> |

The original author was informed of these changes before anything was
published: <!-- issue link -->

## Licence

GPL-3.0-or-later, as IngeTrazo and as the original extension; the full text is
in [`LICENSE`](LICENSE). Every file of `IngeAnalisys/` keeps its licence
notice and carries one line saying it was modified in 2026-11, as GPL-3.0
§5a asks. The extension keeps the name and the behaviour of the original: a
map of the site on the model itself, without touching IngeTrazo's core.

## What this fork changed (1.9.0)

1. **Complete internationalisation** — `pt-BR`, `es`, `en`, `de`, `it`, `fr`,
   `zh-CN`, `ru` and `ja` in `IngeAnalisys/i18n/*.json`: US-English keys,
   `tr()`, the language taken from IngeTrazo or from the system locale, and a
   fallback to English when a key is missing. The original was Spanish only.
2. **Code organised in folders** — `tools/` (14 modules), `i18n/`, `icons/`,
   with `__init__.py` and `setup(app)`, which is the layout
   [`docs/plugins.md`](https://github.com/ingelibre/ingetrazo/blob/main/docs/plugins.md)
   asks for. The flat `nucleo.py`, `datos.py`, `dibujo.py`, `panel.py`… of the
   original became `tools/core.py`, `tools/data.py`, `tools/drawing.py`,
   `tools/panel.py`…
3. **One unified toolbar with 19 buttons**, grouped by panel section, with
   theme-aware SVG icons (dark/light) and a single `refresh()`.
4. **Draggable floating panels** — information and conventions, and the colour
   scale of the radiation and shade maps.
5. **Fixes** — keyboard shortcuts that did not fire (or fired twice) and
   dialogs that failed to load. The code has been run and works: the package
   loads, the tab, the toolbar and the menus appear, and the document keeps its
   data.

## Compatibility with documents of the original

The document keys of the original are still **read**, so a project saved with
`analisis_sitio` opens here with its masses, radiation maps, pins, winds, EPW
and view settings:

- `plugin_data["analisis_sitio"]` (and `analisis_sitio.vista`, `.clima`,
  `.contexto`);
- `group.ext["analisis_sitio"]`.

See `IngeAnalisys/tools/data.py` (`LEGACY_KEYS`, `ext_data()`). New data is
written under the name of the folder the extension is installed in, because
that is how IngeTrazo keys an extension's data.

## Contact

- Bugs of **this fork**: <https://github.com/em-rezende/IngeAnalisys/issues>
- The original extension: <https://github.com/jufegofoto-cell/IngeAnalisys>

---

## Español (resumen)

Esta extensión es obra de **jufegofoto-cell**
(<https://github.com/jufegofoto-cell/IngeAnalisys>), que convirtió la app web
*Análisis de Sitio 3D* en extensión de IngeTrazo. Este fork (1.9.0) añade
internacionalización a nueve idiomas, el código en carpetas (`tools/`,
`i18n/`, `icons/`), una barra unificada de 19 botones, paneles flotantes
arrastrables y correcciones de atajos y de carga de diálogos; está probado y
funciona. Licencia GPL-3.0-or-later. Los `.igz` hechos con la versión original
se abren igual, porque se siguen leyendo sus claves
(`analisis_sitio`, `group.ext["analisis_sitio"]`). Crédito de la idea y del
método: el autor original; este fork solo mantiene las modificaciones.

## Português (resumo)

Esta extensão é obra de **jufegofoto-cell**
(<https://github.com/jufegofoto-cell/IngeAnalisys>), que transformou o app web
*Análisis de Sitio 3D* em extensão do IngeTrazo. Este fork (1.9.0) acrescenta
internacionalização para nove idiomas, o código em pastas (`tools/`, `i18n/`,
`icons/`), uma barra unificada de 19 botões, painéis flutuantes arrastáveis e
correções de atalhos e de carregamento de diálogos; está testado e funciona.
Licença GPL-3.0-or-later. Projetos `.igz` feitos na versão original continuam
abrindo, porque as chaves dela são lidas (`analisis_sitio`,
`group.ext["analisis_sitio"]`). O crédito da ideia e do método é do autor
original; este fork mantém apenas as modificações.
