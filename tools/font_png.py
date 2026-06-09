#!/usr/bin/env python3
"""Round-trip the relocated EN+PT font between its .bin and an editable PNG.

The build loads fonts/rbshura_font_ext.bin at $E2:0000 — 89 slots x 64 B (each
slot = an 8x16 2bpp glyph in the first 32 B + 32 B zero pad). This tool exports
those glyphs to a PNG you can paint in any pixel editor, and re-imports an edited
PNG back to the .bin, so the Portuguese accents (slots 0x4C..0x58) — or any
glyph — can be tweaked by hand without touching the Python.

  # export the font to an editable PNG (8x-scaled grid, 16 glyphs per row)
  python tools/font_png.py export
  python tools/font_png.py export --scale 12 --png fonts/rbshura_font_ext.png

  # after editing the PNG, write the glyphs back into the .bin
  python tools/font_png.py import

The PNG is a 4-colour grid (value 0=black .. 3=white) laid out 16 glyphs per row;
slot index = row*16 + col. The Portuguese accents are slots 0x4C..0x58
(row 4 col 12 .. row 5 col 8). Re-import preserves the 64 B slot stride
(32 B glyph + 32 B zero pad) and is lossless for unedited cells.

NOTE: editing a *Latin* slot (0x00..0x4B) here changes only this $E2 font, not
the $100000 safety-net copy (fonts/rbshura_en.bin). For Latin changes, prefer
editing the font source (tools/apply_pk_font.py) so both stay in sync. The
accents (0x4C..0x58) live only in this font, so editing them here is safe.

Requires Pillow (in the project venv): run with ./.venv/bin/python.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_BIN = ROOT / "fonts" / "rbshura_font_ext.bin"
FONT_PNG = ROOT / "fonts" / "rbshura_font_ext.png"

SLOT_STRIDE = 64        # 32 B glyph + 32 B pad
GLYPH_BYTES = 32        # top tile (16 B) + bottom tile (16 B)
GW, GH = 8, 16          # glyph pixel dimensions
COLS = 16               # glyphs per PNG row
# value -> grey level (0=bg .. 3=stroke highlight)
PALETTE = [(0, 0, 0), (90, 90, 90), (170, 170, 170), (255, 255, 255)]


def decode_glyph(b: bytes) -> list[list[int]]:
    """32 B glyph -> 16 rows x 8 cols of 2bpp values."""
    grid = []
    for tile in (b[0:16], b[16:32]):
        for r in range(8):
            bp0, bp1 = tile[2 * r], tile[2 * r + 1]
            grid.append([((bp0 >> (7 - x)) & 1) | (((bp1 >> (7 - x)) & 1) << 1)
                         for x in range(8)])
    return grid


def encode_glyph(grid: list[list[int]]) -> bytes:
    out = bytearray()
    for rows in (grid[0:8], grid[8:16]):
        for row in rows:
            bp0 = bp1 = 0
            for x, v in enumerate(row):
                if v & 1:
                    bp0 |= 0x80 >> x
                if v & 2:
                    bp1 |= 0x80 >> x
            out += bytes((bp0, bp1))
    return bytes(out)


def nearest(rgb) -> int:
    r, g, b = rgb[:3]
    return min(range(4), key=lambda i: (r - PALETTE[i][0]) ** 2
              + (g - PALETTE[i][1]) ** 2 + (b - PALETTE[i][2]) ** 2)


def cmd_export(args) -> None:
    from PIL import Image
    data = FONT_BIN.read_bytes()
    n_slots = len(data) // SLOT_STRIDE
    rows = (n_slots + COLS - 1) // COLS
    scale = args.scale
    img = Image.new("RGB", (COLS * GW * scale, rows * GH * scale), PALETTE[0])
    px = img.load()
    for slot in range(n_slots):
        gx, gy = (slot % COLS) * GW, (slot // COLS) * GH
        glyph = decode_glyph(data[slot * SLOT_STRIDE:slot * SLOT_STRIDE + GLYPH_BYTES])
        for y in range(GH):
            for x in range(GW):
                col = PALETTE[glyph[y][x]]
                for dy in range(scale):
                    for dx in range(scale):
                        px[(gx + x) * scale + dx, (gy + y) * scale + dy] = col
    out = Path(args.png)
    img.save(out)
    print(f"Wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} "
          f"({img.width}x{img.height}, {n_slots} slots @ {scale}x). "
          f"PT accents are slots 0x4C..0x58.")


def cmd_import(args) -> None:
    from PIL import Image
    base = bytearray(FONT_BIN.read_bytes())
    n_slots = len(base) // SLOT_STRIDE
    img = Image.open(args.png).convert("RGB")
    px = img.load()
    # Derive scale from the image size; require an exact multiple.
    sx, sy = img.width / (COLS * GW), img.height / ((n_slots + COLS - 1) // COLS * GH)
    if sx != sy or sx != int(sx) or sx < 1:
        sys.exit(f"PNG size {img.width}x{img.height} is not an integer multiple "
                 f"of the {COLS*GW}x{(n_slots+COLS-1)//COLS*GH} glyph grid.")
    scale = int(sx)
    for slot in range(n_slots):
        gx, gy = (slot % COLS) * GW, (slot // COLS) * GH
        grid = [[0] * GW for _ in range(GH)]
        for y in range(GH):
            for x in range(GW):
                # sample the centre of each logical pixel block
                px_x = (gx + x) * scale + scale // 2
                px_y = (gy + y) * scale + scale // 2
                grid[y][x] = nearest(px[px_x, px_y])
        g32 = encode_glyph(grid)
        base[slot * SLOT_STRIDE:slot * SLOT_STRIDE + GLYPH_BYTES] = g32
        # leave the 32 B pad as-is (zero)
    FONT_BIN.write_bytes(base)
    print(f"Wrote {FONT_BIN.relative_to(ROOT)} ({len(base)} bytes, {n_slots} slots) "
          f"from {Path(args.png).name} @ {scale}x. Rebuild to apply.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="font .bin -> editable .png")
    e.add_argument("--png", default=str(FONT_PNG))
    e.add_argument("--scale", type=int, default=8, help="pixel scale (default 8)")
    e.set_defaults(func=cmd_export)
    i = sub.add_parser("import", help="edited .png -> font .bin")
    i.add_argument("--png", default=str(FONT_PNG))
    i.set_defaults(func=cmd_import)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
