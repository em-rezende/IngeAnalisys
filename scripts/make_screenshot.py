# SPDX-License-Identifier: GPL-3.0-or-later
"""Make the picture the extension catalog shows (under 600 KB, ~1200×750).

The catalog in ``ingetrazo-extensions`` refuses a screenshot larger than
600 KB and wants a plain lowercase file name; this turns the wide screenshot
of the README (``screenshots/IngeAnalisys.png``) into that file, with Qt
(already a dependency of IngeTrazo, so nothing extra to install).

    python scripts/make_screenshot.py

Writes ``screenshots/ingeanalisys.jpg`` — the file to upload to the catalog
repository — and never touches the source: on Windows ``IngeAnalisys.png``
and ``ingeanalisys.png`` are the *same* file, so writing a PNG there would
overwrite the original (it did, once; the copy installed in
``%APPDATA%\\ingetrazo\\plugins`` brought it back).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "screenshots" / "IngeAnalisys.png"
TARGET = ROOT / "screenshots" / "ingeanalisys.jpg"
MAX_BYTES = 600 * 1024          # the catalog's limit
WIDTH = 1200                    # the catalog's suggestion (~1200×750)


def _same_file(a: Path, b: Path) -> bool:
    """True when ``a`` and ``b`` are one file — case and all (Windows)."""
    try:
        return a.exists() and b.exists() and a.samefile(b)
    except OSError:
        return False


def shrink(image: QImage, width: int) -> QImage:
    if image.width() <= width:
        return image
    return image.scaledToWidth(width, Qt.SmoothTransformation)


def build(source: Path = SOURCE, target: Path = TARGET,
          width: int = WIDTH, quality: int = 88) -> Path:
    image = QImage(str(source))
    if image.isNull():
        raise SystemExit(f"cannot read {source}")
    if _same_file(source, target):
        raise SystemExit(f"{target} IS {source} on this filesystem "
                         "(names differing only in case): choose another "
                         "name with --target")
    image = shrink(image, width)
    target.parent.mkdir(parents=True, exist_ok=True)
    jpeg = target.suffix.lower() in (".jpg", ".jpeg")
    staged = target.with_name(target.name + ".part")
    for step_quality in (quality, max(60, quality - 12), max(50, quality - 24)):
        if not image.save(str(staged), "JPEG" if jpeg else "PNG",
                          step_quality):
            raise SystemExit(f"Qt cannot write {staged.name}")
        if staged.stat().st_size <= MAX_BYTES:
            staged.replace(target)
            return target
    staged.unlink(missing_ok=True)
    raise SystemExit(f"still larger than {MAX_BYTES // 1024} KB: use "
                     "--width 1000 or --target screenshots/ingeanalisys.jpg")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--quality", type=int, default=88)
    args = parser.parse_args(argv)
    out = build(args.source, args.target, args.width, args.quality)
    image = QImage(str(out))
    print(f"{out.relative_to(ROOT)}  {image.width()}×{image.height()}  "
          f"{out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
