"""Tile a directory of images into one sheet, so a person can look at them.

    uv run python -m scripts.contact_sheet --source ../data/_sources/building \
        --out ../data/.cache/sheets/building.jpg

A category name is not a description of its contents. The first batch of
`phone_screen` images pulled from a Commons category called "Broken telephone
screens" included a photograph of a Kraków market square, and nothing in the
metadata said so -- the licence was clean, the resolution was fine, the title was
in Polish. It was only visible by looking.

An evaluation set nobody has looked at measures whatever happens to be in it,
and reports the result as though it measured what the label claims.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=8)
    parser.add_argument("--cell", type=int, default=200)
    parser.add_argument("--limit", type=int, default=64)
    arguments = parser.parse_args()

    images = sorted(p for p in arguments.source.rglob("*") if p.suffix.lower() in SUFFIXES)
    if not images:
        print(f"no images under {arguments.source}")
        return 1
    images = images[: arguments.limit]

    columns = arguments.columns
    rows = (len(images) + columns - 1) // columns
    cell = arguments.cell
    label = 14

    sheet = Image.new("RGB", (columns * cell, rows * (cell + label)), "white")
    draw = ImageDraw.Draw(sheet)

    for index, path in enumerate(images):
        try:
            tile = Image.open(path).convert("RGB")
        except Exception as error:  # a corrupt file is itself worth seeing
            print(f"  unreadable: {path.name}: {error}")
            continue
        tile.thumbnail((cell, cell))

        column, row = index % columns, index // columns
        x = column * cell + (cell - tile.width) // 2
        y = row * (cell + label)
        sheet.paste(tile, (x, y))
        draw.text((column * cell + 2, y + cell + 1), f"{index}", fill="black")

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(arguments.out, quality=88)
    print(f"{len(images)} images -> {arguments.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
