#!/usr/bin/env python3
"""Dump a ROM region as a tile grid PNG.

Usage:
    python tools/dump_font_tiles.py <offset> [<count>] [--bpp 2|4] [--cols N]
                                    [--rom rbshura.sfc] [--out out.png]
                                    [--label LABEL]

Examples — exploring for the intro kanji font:

    # 2bpp tiles starting at file $100000 (dialog font region), 200 tiles
    python tools/dump_font_tiles.py 0x100000 200

    # 4bpp, 256 tiles, 32 wide for easier scanning
    python tools/dump_font_tiles.py 0x1F0000 256 --bpp 4 --cols 32

    # Sweep candidate banks: pass --sweep to render every 0x4000 chunk
    python tools/dump_font_tiles.py --sweep 0x000000 0x400000 --bpp 2

The script defaults to `rbshura.sfc` as the ROM source so the output is
deterministic across runs even after rebuilding the EN ROM. Output PNGs
land in `export/font_tiles/` so iteration doesn't clutter the project root.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent.parent
DEFAULT_ROM = ROOT / "rbshura.sfc"
DEFAULT_OUT = ROOT / "export" / "font_tiles"

PALETTE_2BPP = [
    (0, 0, 0, 255),
    (96, 96, 144, 255),
    (192, 192, 224, 255),
    (255, 255, 255, 255),
]
PALETTE_4BPP = [
    (i * 17, i * 17, i * 17, 255) for i in range(16)
]
# Shade index 0 a tiny bit so blank tiles still have a faint outline.
PALETTE_4BPP[0] = (16, 16, 32, 255)


def decode_tile_2bpp(buf: bytes, off: int) -> list[int]:
    """One 8x8 2bpp tile → 64 palette indices (0..3). 16 B/tile."""
    out = [0] * 64
    for r in range(8):
        b0 = buf[off + r * 2]
        b1 = buf[off + r * 2 + 1]
        for c in range(8):
            bit = 7 - c
            out[r * 8 + c] = ((b0 >> bit) & 1) | (((b1 >> bit) & 1) << 1)
    return out


def decode_tile_4bpp(buf: bytes, off: int) -> list[int]:
    """One 8x8 4bpp tile → 64 palette indices (0..15). 32 B/tile.
    SNES 4bpp = 2 interleaved 2bpp planes (planes 0/1 first 16B, 2/3 next 16B)."""
    out = [0] * 64
    for r in range(8):
        b0 = buf[off + r * 2]
        b1 = buf[off + r * 2 + 1]
        b2 = buf[off + 16 + r * 2]
        b3 = buf[off + 16 + r * 2 + 1]
        for c in range(8):
            bit = 7 - c
            v = ((b0 >> bit) & 1) | (((b1 >> bit) & 1) << 1) \
                | (((b2 >> bit) & 1) << 2) | (((b3 >> bit) & 1) << 3)
            out[r * 8 + c] = v
    return out


def render_region(
    rom: bytes,
    offset: int,
    count: int,
    *,
    bpp: int = 2,
    cols: int = 16,
    scale: int = 2,
) -> Image.Image:
    """Render `count` tiles starting at file `offset` into a grid image."""
    decode = decode_tile_2bpp if bpp == 2 else decode_tile_4bpp
    palette = PALETTE_2BPP if bpp == 2 else PALETTE_4BPP
    tile_bytes = 16 if bpp == 2 else 32
    rows = (count + cols - 1) // cols
    img = Image.new("RGBA", (cols * 8, rows * 8), (0, 0, 0, 255))
    for ti in range(count):
        off = offset + ti * tile_bytes
        if off + tile_bytes > len(rom):
            break
        pix = decode(rom, off)
        gx = (ti % cols) * 8
        gy = (ti // cols) * 8
        for py in range(8):
            for px in range(8):
                img.putpixel((gx + px, gy + py), palette[pix[py * 8 + px]])
    if scale != 1:
        img = img.resize((img.size[0] * scale, img.size[1] * scale), Image.NEAREST)
    return img


def parse_int(s: str) -> int:
    return int(s, 16) if s.lower().startswith("0x") else int(s)


def main() -> None:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("offset", nargs="?", help="ROM file offset (hex or decimal)")
    ap.add_argument("count", nargs="?", default="256",
                    help="Number of tiles to render (default 256)")
    ap.add_argument("--bpp", type=int, choices=(2, 4), default=2,
                    help="Bit depth (2 or 4)")
    ap.add_argument("--cols", type=int, default=16,
                    help="Tiles per row in the output image")
    ap.add_argument("--scale", type=int, default=2,
                    help="Pixel-doubling factor for legibility")
    ap.add_argument("--rom", type=Path, default=DEFAULT_ROM,
                    help=f"ROM file (default {DEFAULT_ROM.name})")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output PNG path. Defaults to "
                         "export/font_tiles/tiles_{offset:06x}_{bpp}bpp.png")
    ap.add_argument("--label", default="",
                    help="Tag appended to default output filename")
    ap.add_argument("--sweep", nargs=2, metavar=("START", "END"),
                    help="Sweep mode: render every 0x4000-byte chunk in "
                         "[START, END), one PNG per chunk")
    args = ap.parse_args()

    if not args.rom.exists():
        sys.exit(f"ROM not found: {args.rom}")
    rom = args.rom.read_bytes()
    out_dir = DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    def render_one(offset: int, count: int) -> Path:
        img = render_region(rom, offset, count,
                            bpp=args.bpp, cols=args.cols, scale=args.scale)
        if args.out:
            path = args.out
        else:
            tag = f"_{args.label}" if args.label else ""
            path = out_dir / f"tiles_{offset:06x}_{args.bpp}bpp{tag}.png"
        img.save(path)
        return path

    if args.sweep:
        start, end = parse_int(args.sweep[0]), parse_int(args.sweep[1])
        chunk = 0x4000
        tiles_per_chunk = chunk // (16 if args.bpp == 2 else 32)
        for off in range(start, end, chunk):
            path = render_one(off, tiles_per_chunk)
            print(f"  {path.relative_to(ROOT)}  ({off:#08x})")
        return

    if args.offset is None:
        ap.error("offset is required (or use --sweep)")
    offset = parse_int(args.offset)
    count = parse_int(args.count)
    path = render_one(offset, count)
    print(f"wrote {path.relative_to(ROOT)} — "
          f"{count} {args.bpp}bpp tiles starting at file ${offset:06X}")


if __name__ == "__main__":
    main()
