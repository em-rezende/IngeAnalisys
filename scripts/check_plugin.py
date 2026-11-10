# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the extension against the rules IngeTrazo and its catalog apply.

Three things are checked, and IngeTrazo itself is not needed: the host
modules are stubbed.

1. **The plugin loads the way IngeTrazo loads it.** ``core/extensions.py``
   imports a package by file path under ``ingetrazo_plugin_<folder>`` with
   the folder as its search location; that is reproduced here, and every
   module of the package is imported, so a typo, a syntax error or a
   missing import fails here instead of silently in the application.
2. **The catalog entry** (``catalog/ingeanalisys.toml``) follows the rules
   of ``ingetrazo-extensions`` (its ``tools/catalog.py``).
3. **The package ZIP** (``dist/IngeAnalisys.zip``) holds exactly one folder
   with an ``__init__.py``, and its SHA-256 is the one in the entry.

    python scripts/check_plugin.py               # everything
    python scripts/check_plugin.py --no-import    # skip 1 (no Qt or numpy)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import re
import sys
import tomllib
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "IngeAnalisys"
CATALOG = ROOT / "catalog" / "ingeanalisys.toml"
ARCHIVE = ROOT / "dist" / "IngeAnalisys.zip"
SHOTS = ROOT / "screenshots"

#: Copied from ``ingetrazo-extensions/tools/catalog.py`` (keep in sync).
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}([.-]?[a-z0-9]+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
LICENCES = {
    "GPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0-or-later",
    "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later",
    "MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "MPL-2.0",
    "ISC", "Zlib", "0BSD", "Unlicense", "CC0-1.0",
}
TAGS = {
    "architecture", "bim", "structures", "terrain", "drawing", "analysis",
    "import-export", "rendering", "fabrication", "productivity",
    "education", "other",
}
REQUIRED = ("id", "name", "summary", "author", "license", "repository",
            "version", "download", "sha256", "ingetrazo", "tags")
OPTIONAL = ("author_url", "screenshot", "description")
MAX_ARCHIVE = 5 * 1024 * 1024       # the catalog refuses bigger packages
MAX_SHOT = 600 * 1024               # … and bigger screenshots

problems: list[str] = []
notes: list[str] = []


def problem(text: str) -> None:
    problems.append(text)


def report() -> int:
    for line in notes:
        print(f"  {line}")
    if problems:
        print()
        for line in problems:
            print(f"FAIL  {line}")
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("\nAll checks passed.")
    return 0


# ---- 1. The plugin, loaded as IngeTrazo loads it -------------------------

def _stub(name: str) -> types.ModuleType:
    """A host module: any attribute asked for becomes a dummy class, so
    ``from core.mesh import Face`` works without IngeTrazo installed."""
    mod = types.ModuleType(name)

    def __getattr__(attr: str) -> type:
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        cls = type(attr, (object,), {"__module__": name})
        setattr(mod, attr, cls)
        return cls

    mod.__getattr__ = __getattr__          # PEP 562, module level
    return mod


#: Host packages and modules the extension touches while importing.
HOST_PACKAGES = ("core", "georef", "views", "tools", "extensions")
HOST_MODULES = ("core.group", "core.history", "core.i18n", "core.layers",
                "core.mesh", "core.paths", "core.snap", "core.sun",
                "core.tls", "core.version", "georef.datum", "georef.geocode",
                "georef.tiles", "views.fold_section", "views.location_dialog",
                "tools.base")


def install_stubs() -> list[str]:
    """Put the fake host in ``sys.modules``. Returns what had to be faked."""
    faked = []
    for name in HOST_PACKAGES + HOST_MODULES:
        if name not in sys.modules:
            sys.modules[name] = _stub(name)
            faked.append(name)
    try:
        import numpy                                         # noqa: F401
    except ImportError:
        sys.modules["numpy"] = _stub("numpy")
        faked.append("numpy")
    return faked


def load_package():
    """Import the package by path, as ``core/extensions.py`` does."""
    init = PACKAGE / "__init__.py"
    mod_name = f"ingetrazo_plugin_{PACKAGE.name}"
    spec = importlib.util.spec_from_file_location(
        mod_name, init, submodule_search_locations=[str(PACKAGE)])
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot build an import spec for {init}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def check_entry_point() -> None:
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    setups = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "setup"]
    if not setups:
        problem("IngeAnalisys/__init__.py has no top-level setup(app): the "
                "catalog's check would find no entry point")
    elif len(setups[0].args.args) != 1:
        problem("setup() must take exactly one argument (the ExtensionApp)")


def check_import():
    faked = install_stubs()
    if faked:
        notes.append(f"stubbed host modules: {len(faked)}")
    try:
        mod = load_package()
    except Exception as exc:                                 # noqa: BLE001
        problem(f"the package does not import by path: "
                f"{type(exc).__name__}: {exc}")
        return None
    if not callable(getattr(mod, "setup", None)):
        problem("the imported module has no callable setup(app)")
    notes.append(f"imported {mod.__name__} {getattr(mod, '__version__', '?')}")
    stems = sorted(p.stem for p in (PACKAGE / "tools").glob("*.py")
                   if p.stem != "__init__")
    for stem in stems:
        try:
            importlib.import_module(f"{mod.__name__}.tools.{stem}")
        except Exception as exc:                             # noqa: BLE001
            problem(f"tools/{stem}.py does not import: "
                    f"{type(exc).__name__}: {exc}")
    notes.append(f"{len(stems)} modules under tools/ imported")
    return mod


class _Scene:
    """The two attributes the store touches, and nothing else."""

    def __init__(self, plugin_data: dict) -> None:
        self.plugin_data = plugin_data
        self.version = 0


class _App:
    """A host whose data was written under the OLD folder name."""

    key = "ingeanalisys"

    def __init__(self, scene) -> None:
        self.scene = scene
        self.viewport = None

    def document_data(self, default=None):
        return self.scene.plugin_data.get(self.key, default)


def check_data_keys(mod) -> None:
    """A project saved while the folder was called ``IngeAnalisys`` must
    keep opening once the manager installs the package as ``ingeanalisys``
    (the catalog id): the store and the group parameters read both."""
    data = importlib.import_module(f"{mod.__name__}.tools.data")
    scene = _Scene({
        "IngeAnalisys": {"pins": [{"id": "p1"}], "winds": []},
        "IngeAnalisys.view": {"on": True, "radius": 55.0},
        "IngeAnalisys.climate": {"header": "legacy"},
        "IngeAnalisys.context": {"buildings": [{"id": 7}], "group": None},
    })
    store = data.Store(_App(scene))
    if store.content()["pins"] != [{"id": "p1"}]:
        problem("content written under an older plugin name is not read")
    view = store.view()
    if view.get("radius") != 55.0 or not view.get("on"):
        problem("view written under an older plugin name is not read")
    if store.climate() != {"header": "legacy"}:
        problem("climate written under an older plugin name is not read")
    if store.context()["buildings"] != [{"id": 7}]:
        problem("context written under an older plugin name is not read")

    class _Group:
        ext = {"IngeAnalisys": {"pts": [(0, 0), (1, 0), (1, 1)], "h": 6.0}}

    group = _Group()
    if data.ext_data(group, "ingeanalisys") is not group.ext["IngeAnalisys"]:
        problem("ext_data() does not fall back to an older plugin name")
    geometry = importlib.import_module(f"{mod.__name__}.tools.geometry")
    if geometry.mass_params(group, "ingeanalisys") is None:
        problem("a mass of an older document is not recognised")
    notes.append("data written under the old folder name is read")



def check_package_tree() -> None:
    for rel in ("__init__.py", "tools/__init__.py", "i18n", "icons"):
        if not (PACKAGE / rel).exists():
            problem(f"IngeAnalisys/{rel} is missing")
    if not (PACKAGE / "i18n" / "pt-BR.json").is_file():
        problem("i18n/pt-BR.json is missing")
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            compile(text, rel, "exec")
        except SyntaxError as exc:
            problem(f"{rel} does not compile: {exc}")
        for needle in ("sys.path.insert", "sys.path.append"):
            if needle in text:
                problem(f"{rel} touches sys.path ({needle}): docs/plugins.md "
                        "forbids relying on it")


# ---- 2. The catalog entry ------------------------------------------------

def load_catalog() -> dict:
    if not CATALOG.is_file():
        problem(f"{CATALOG.relative_to(ROOT)} is missing")
        return {}
    try:
        return tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        problem(f"{CATALOG.name} is not valid TOML: {exc}")
        return {}


def check_catalog(entry: dict) -> None:
    if not entry:
        return
    for field in REQUIRED:
        if field not in entry:
            problem(f"catalog entry: '{field}' is required")
    for field in entry:
        if field not in REQUIRED + OPTIONAL:
            problem(f"catalog entry: unknown field '{field}'")
    ident = str(entry.get("id", ""))
    if not ID_RE.match(ident):
        problem(f"catalog entry: id {ident!r} must be lowercase letters, "
                "digits and _ (2 to 48 characters)")
    if ident != CATALOG.stem:
        problem(f"catalog entry: id {ident!r} must match the file name "
                f"{CATALOG.stem!r}")
    if not VERSION_RE.match(str(entry.get("version", ""))):
        problem('catalog entry: version must look like "1.9.0"')
    if entry.get("license") not in LICENCES:
        problem(f"catalog entry: {entry.get('license')!r} is not a free "
                "licence the catalog accepts")
    for field, limit in (("name", 60), ("summary", 240),
                         ("description", 2000)):
        if field not in entry:
            if field == "description":      # optional
                continue
            problem(f"catalog entry: [{field}] must have es and/or en")
            continue
        table = entry.get(field)
        if not isinstance(table, dict) or not table:
            problem(f"catalog entry: [{field}] must have es and/or en")
            continue
        for lang, value in table.items():
            if lang not in ("es", "en", "pt"):
                problem(f"catalog entry: [{field}.{lang}] is not a language "
                        "the page shows (es, en, pt)")
            elif not str(value).strip():
                problem(f"catalog entry: [{field}.{lang}] is empty")
            elif len(str(value)) > limit:
                problem(f"catalog entry: [{field}.{lang}] is longer than "
                        f"{limit} characters")
        if not any(lang in table for lang in ("es", "en")):
            problem(f"catalog entry: [{field}] needs Spanish or English")
    tags = entry.get("tags")
    if not isinstance(tags, list) or not tags:
        problem("catalog entry: 'tags' needs at least one tag")
    else:
        unknown = [t for t in tags if t not in TAGS]
        if unknown:
            problem(f"catalog entry: unknown tags {unknown}")
        if len(tags) > 4:
            problem("catalog entry: at most 4 tags")
    url = str(entry.get("download", ""))
    if not url.startswith("https://"):
        problem("catalog entry: 'download' must be an https:// address")
    if not (url.endswith(".py") or url.endswith(".zip")):
        problem("catalog entry: 'download' must point at a .py or a .zip")
    if re.search(r"raw\.githubusercontent\.com/[^/]+/[^/]+/"
                 r"(main|master|develop|dev)/", url):
        problem("catalog entry: 'download' points at a branch, which "
                "changes; use a tag or a commit in the address")
    if not str(entry.get("repository", "")).startswith("https://"):
        problem("catalog entry: 'repository' must be an https:// address")
    if not SHA_RE.match(str(entry.get("sha256", ""))):
        problem("catalog entry: 'sha256' must be 64 lowercase hex characters")
    shot = entry.get("screenshot")
    if shot is not None:
        path = SHOTS / str(shot)
        if not re.match(r"^[a-z0-9_.-]+\.(png|jpg|jpeg|webp)$", str(shot)):
            problem("catalog entry: 'screenshot' must be a plain file name "
                    "(.png, .jpg or .webp, lowercase)")
        elif not path.is_file():
            problem(f"catalog entry: screenshot {shot} is not in screenshots/")
        elif path.stat().st_size > MAX_SHOT:
            problem(f"catalog entry: screenshot {shot} is larger than "
                    f"{MAX_SHOT // 1024} KB ({path.stat().st_size // 1024} KB)"
                    ": python scripts/make_screenshot.py")
    version = str(entry.get("version", ""))
    module_version = _module_version()
    if version and module_version and version != module_version:
        problem(f"catalog version {version} != __version__ "
                f"{module_version} in IngeAnalisys/__init__.py")


def _module_version() -> str | None:
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value,
                                                       ast.Constant):
            if any(isinstance(t, ast.Name) and t.id == "__version__"
                   for t in node.targets):
                return str(node.value.value)
    return None



# ---- 3. The package ZIP --------------------------------------------------

def check_archive(entry: dict) -> None:
    if not ARCHIVE.is_file():
        problem(f"{ARCHIVE.relative_to(ROOT)} is missing: "
                "python scripts/build_zip.py")
        return
    with zipfile.ZipFile(ARCHIVE) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        tops = {n.split("/")[0] for n in names}
        if len(tops) != 1:
            problem(f"the ZIP must hold exactly one folder, not {sorted(tops)}")
        elif f"{next(iter(tops))}/__init__.py" not in names:
            problem("the ZIP's folder has no __init__.py inside")
        if any("__pycache__" in n.split("/") for n in names):
            problem("the ZIP carries __pycache__")
        for name in names:
            if name.startswith(("/", "\\")) or ".." in Path(name).parts \
                    or ":" in name or "\\" in name:
                problem(f"the ZIP has an unsafe member {name!r}")
        unpacked = sum(i.file_size for i in zf.infolist())
    size = ARCHIVE.stat().st_size
    if size > MAX_ARCHIVE:
        problem(f"the ZIP is larger than the 5 MB the catalog accepts "
                f"({size // 1024} KB)")
    if unpacked > 8 * MAX_ARCHIVE:
        problem("the ZIP unpacks to too much data")
    sha = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    notes.append(f"{ARCHIVE.relative_to(ROOT)}: {len(names)} files, "
                 f"{size / 1024:.1f} KB, sha256 {sha}")
    if entry and entry.get("sha256") and entry["sha256"] != sha:
        problem("the SHA-256 in the catalog entry is not the ZIP's "
                f"({sha}): python scripts/build_zip.py --update-catalog")
    download = str(entry.get("download", ""))
    tag = str(entry.get("version", ""))
    if download and tag and not any(f"/{t}/" in download
                                    for t in (tag, f"v{tag}")):
        problem("the 'download' address does not carry the version "
                f"{tag!r} as its tag (…/v{tag}/…)")


# ---- 4. Repository files -------------------------------------------------

def check_repo_files() -> None:
    for rel in ("LICENSE", "README.md"):
        if not (ROOT / rel).is_file():
            problem(f"{rel} is missing at the repository root")
            return
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8", errors="replace")
    if "GNU GENERAL PUBLIC LICENSE" not in licence:
        problem("LICENSE does not look like the GNU GPL text the catalog "
                "entry declares")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-import", action="store_true",
                        help="skip importing the package (no Qt or numpy)")
    args = parser.parse_args(argv)

    print(f"checking {PACKAGE.name} at {ROOT}")
    check_repo_files()
    check_package_tree()
    check_entry_point()
    if not args.no_import:
        mod = check_import()
        if mod is not None:
            check_data_keys(mod)
    entry = load_catalog()
    check_catalog(entry)
    check_archive(entry)
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
