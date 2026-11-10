# SPDX-License-Identifier: GPL-3.0-or-later
"""Build ``dist/IngeAnalisys.zip`` — the file the extension catalog installs.

IngeTrazo's manager (``core/extension_manager.py``) and the catalog's check
(``tools/catalog.py`` in ``ingetrazo-extensions``) both want the same thing:
**one** top-level folder holding an ``__init__.py``. This script packs the
``IngeAnalisys`` package that way, excluding caches, and prints the SHA-256
that goes into the catalog entry.

    python scripts/build_zip.py                 # build and report
    python scripts/build_zip.py --update-catalog # also patch catalog/*.toml

The archive is byte-for-byte reproducible (sorted entries, fixed timestamp,
fixed permissions), so rebuilding the same sources gives the same hash and a
tag can always be verified against the catalog.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "IngeAnalisys"
OUTPUT = ROOT / "dist" / "IngeAnalisys.zip"
CATALOG = ROOT / "catalog" / "ingeanalisys.toml"

#: Never inside the archive: caches, editor droppings, source assets.
SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode", ".pytest_cache"}
SKIP_FILES = {"Thumbs.db", "desktop.ini", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".cdr", ".epw", ".bak", ".orig"}

#: Fixed timestamp/attributes: same sources → same bytes → same SHA-256.
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def version_of(package: Path) -> str:
    """``__version__`` read from the source, without importing it (no Qt)."""
    tree = ast.parse((package / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Name) and target.id == "__version__"
                        and isinstance(node.value, ast.Constant)):
                    return str(node.value.value)
    raise SystemExit("no __version__ in IngeAnalisys/__init__.py")


def members(package: Path) -> list[Path]:
    files = []
    for path in sorted(package.rglob("*")):
        rel = path.relative_to(package)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_dir() or path.name in SKIP_FILES:
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def build(package: Path = PACKAGE, output: Path = OUTPUT) -> Path:
    files = members(package)
    if not (package / "__init__.py").is_file():
        raise SystemExit(f"{package} has no __init__.py: not a plugin package")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            rel = path.relative_to(package).as_posix()
            info = zipfile.ZipInfo(f"{package.name}/{rel}", _FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16     # plain file, rw-r--r--
            zf.writestr(info, path.read_bytes())
    return output


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(output: Path) -> list[str]:
    """The two rules a host applies to a package ZIP (manager + catalog)."""
    problems = []
    with zipfile.ZipFile(output) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        tops = {n.split("/")[0] for n in names}
        if len(tops) != 1:
            problems.append(f"the ZIP must hold exactly one folder, not {tops}")
        elif f"{next(iter(tops))}/__init__.py" not in names:
            problems.append("the ZIP's folder has no __init__.py inside")
        for name in names:
            if name.startswith(("/", "\\")) or ".." in Path(name).parts \
                    or ":" in name or "\\" in name:
                problems.append(f"unsafe member {name!r}")
        if any("__pycache__" in n.split("/") for n in names):
            problems.append("__pycache__ inside the ZIP")
        unpacked = sum(i.file_size for i in zf.infolist())
    if output.stat().st_size > 5 * 1024 * 1024:
        problems.append("the ZIP is larger than the 5 MB the catalog accepts")
    if unpacked > 8 * 5 * 1024 * 1024:
        problems.append("the ZIP unpacks to too much data")
    return problems


def update_catalog(catalog: Path, version: str, sha: str) -> bool:
    if not catalog.is_file():
        return False
    text = catalog.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version = "[^"]*"', f'version = "{version}"', text)
    text = re.sub(r'(?m)^sha256 = "[^"]*"', f'sha256 = "{sha}"', text)
    catalog.write_text(text, encoding="utf-8")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-catalog", action="store_true",
                        help=f"write version and sha256 into {CATALOG}")
    args = parser.parse_args(argv)

    version = version_of(PACKAGE)
    output = build()
    problems = verify(output)
    sha = digest(output)
    size = output.stat().st_size / 1024

    print(f"package   {PACKAGE.name} {version}")
    print(f"archive   {output.relative_to(ROOT)}  ({size:.1f} KB)")
    print(f"sha256    {sha}")
    if args.update_catalog and update_catalog(CATALOG, version, sha):
        print(f"updated   {CATALOG.relative_to(ROOT)}")
    for problem in problems:
        print(f"PROBLEM   {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
