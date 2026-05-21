#!/usr/bin/env python3
"""Dump the FE-escape kanji font ($104000) as a labeled 16-cell-wide grid.

Each cell shows a 16x16 (4-tile) glyph with its byte index above it, so a
human can fill in the byte→kanji mapping table that the intro and scen
14/15 renderers expect.

Glyph layout in ROM (verified 2026-05-19 by sweeping $1F0000 / $100000 /
$104000 with `tools/dump_font_tiles.py`):
    base = $104000
    each glyph = 64 bytes = 4×16B 2bpp tiles in (TL, TR, BL, BR) order
    glyph N → bytes [N*64 .. N*64+63]

Output: export/font_tiles/kanji_grid.png — 16 glyphs per row, ~16 rows
visible at a time. Re-run after editing CHARS_PER_PAGE / PAGE to scroll.

Usage:
    python tools/dump_kanji_grid.py                # all 256 entries
    python tools/dump_kanji_grid.py --start 0x40 --count 64
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
ROM = ROOT / "rbshura.sfc"
OUT = ROOT / "export" / "font_tiles" / "kanji_grid.png"

KANJI_BASE = 0x104000      # font region for FE-escape glyphs (intro renderer)
GLYPH_BYTES = 64           # 4 tiles × 16 B (2bpp 8x8)
GLYPH_W = GLYPH_H = 16     # pixels per glyph

PALETTE = [
    (0, 0, 0, 255),
    (96, 96, 144, 255),
    (192, 192, 224, 255),
    (255, 255, 255, 255),
]


def _decode_tile_2bpp(buf: bytes, off: int) -> list[int]:
    out = [0] * 64
    for r in range(8):
        b0 = buf[off + r * 2]
        b1 = buf[off + r * 2 + 1]
        for c in range(8):
            bit = 7 - c
            out[r * 8 + c] = ((b0 >> bit) & 1) | (((b1 >> bit) & 1) << 1)
    return out


def render_glyph(buf: bytes, glyph_off: int) -> Image.Image:
    """Render one 16x16 glyph from 4 tiles in TL/TR/BL/BR order."""
    img = Image.new("RGBA", (GLYPH_W, GLYPH_H), (0, 0, 0, 0))
    for ti, (gx, gy) in enumerate([(0, 0), (8, 0), (0, 8), (8, 8)]):
        pix = _decode_tile_2bpp(buf, glyph_off + ti * 16)
        for py in range(8):
            for px in range(8):
                v = pix[py * 8 + px]
                img.putpixel((gx + px, gy + py), PALETTE[v])
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="0",
                    help="First glyph index (hex or dec). Default 0.")
    ap.add_argument("--count", type=int, default=256,
                    help="Number of glyphs to render. Default 256.")
    ap.add_argument("--cols", type=int, default=16,
                    help="Glyphs per row. Default 16.")
    ap.add_argument("--scale", type=int, default=3,
                    help="Per-pixel scale for legibility. Default 3.")
    ap.add_argument("--rom", type=Path, default=ROM)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--base", default=hex(KANJI_BASE),
                    help=f"Font base offset in ROM (default {KANJI_BASE:#x}).")
    args = ap.parse_args()

    start = int(args.start, 16) if args.start.lower().startswith("0x") else int(args.start)
    base = int(args.base, 16) if args.base.lower().startswith("0x") else int(args.base)

    if not args.rom.exists():
        sys.exit(f"ROM not found: {args.rom}")
    rom = args.rom.read_bytes()

    cell_w = GLYPH_W * args.scale + 4         # 4 px padding for label gutter
    cell_h = GLYPH_H * args.scale + 12        # 12 px label band on top
    rows = (args.count + args.cols - 1) // args.cols
    canvas = Image.new("RGBA",
                       (cell_w * args.cols, cell_h * rows),
                       (24, 24, 32, 255))

    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 10)
    except OSError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(canvas)

    for i in range(args.count):
        idx = start + i
        if idx > 0xFF:
            break
        off = base + idx * GLYPH_BYTES
        if off + GLYPH_BYTES > len(rom):
            break
        glyph = render_glyph(rom, off)
        if args.scale != 1:
            glyph = glyph.resize(
                (GLYPH_W * args.scale, GLYPH_H * args.scale),
                Image.NEAREST,
            )
        gx = (i % args.cols) * cell_w
        gy = (i // args.cols) * cell_h
        # Label band: byte index as hex
        draw.text((gx + 2, gy + 1), f"{idx:02X}",
                  fill=(200, 200, 220, 255), font=font)
        canvas.paste(glyph, (gx + 2, gy + 11))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out)
    print(f"wrote {args.out.relative_to(ROOT)} — "
          f"{args.count} glyphs from {base:#08x} starting at index {start:#04x}")


if __name__ == "__main__":
    main()
