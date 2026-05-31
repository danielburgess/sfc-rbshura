#!/usr/bin/env python3
"""Dump the main title's 修羅 kanji, which is rendered as OBJ sprites (not BG).

From the title state (ram_005): 61 visible sprites, OBSEL=$00 -> OBJ tile base =
VRAM word $0000 (byte $0000), sizes 8x8/16x16, palette 4 (CGRAM 192-207).
We composite the visible sprites (their tiles + positions) into one image — the
kanji as it appears on screen (minus the BG2 flame color-math overlay).

Usage:
  python tools/dump_title_kanji.py SPLITTRACE_DIR OUT.png
"""
import sys
from pathlib import Path
from PIL import Image

from tools.dump_title import cgram_to_palette, decode_tile  # reuse helpers


def main():
    tdir = Path(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else "export/title_kanji.png"
    vram = tdir.joinpath("ram_005_vram.bin").read_bytes()
    oam = tdir.joinpath("ram_005_oam.bin").read_bytes()
    pal = cgram_to_palette(tdir.joinpath("ram_005_cgram.bin").read_bytes())

    OBJ_BASE = 0x0000  # byte (OBSEL=$00 -> word $0000)
    canvas = Image.new("RGBA", (256, 240), (0, 0, 0, 0))
    px = canvas.load()
    used_tiles = set()

    def blit_tile(tile_idx, palgroup, ox, oy, xflip, yflip):
        t = decode_tile(vram, OBJ_BASE, tile_idx, 4)
        pbase = 128 + palgroup * 16  # OBJ palettes are CGRAM 128..255
        for y in range(8):
            sy = 7 - y if yflip else y
            for x in range(8):
                sx = 7 - x if xflip else x
                v = t[sy][sx]
                if v == 0:
                    continue
                X, Y = ox + x, oy + y
                if 0 <= X < 256 and 0 <= Y < 240:
                    r, g, b = pal[pbase + v]
                    px[X, Y] = (r, g, b, 255)

    for i in range(128):
        x = oam[i * 4]; y = oam[i * 4 + 1]; tile = oam[i * 4 + 2]; attr = oam[i * 4 + 3]
        hb = oam[512 + i // 4]; bits = (hb >> ((i % 4) * 2)) & 0x3
        xhi = bits & 1; size = (bits >> 1) & 1
        X = x | (0x100 if xhi else 0)
        if y >= 0xE0:
            continue
        palg = (attr >> 1) & 7
        xflip = (attr >> 6) & 1; yflip = (attr >> 7) & 1
        if size == 0:  # 8x8
            used_tiles.add(tile)
            blit_tile(tile, palg, X, y, xflip, yflip)
        else:  # 16x16 = 4 tiles (T, T+1, T+16, T+17), 16x16 wrap on tile row
            for dy in range(2):
                for dx in range(2):
                    t = (tile + dx + dy * 16) & 0xFF
                    used_tiles.add(t)
                    sxo = (1 - dx) * 8 if xflip else dx * 8
                    syo = (1 - dy) * 8 if yflip else dy * 8
                    blit_tile(t, palg, X + sxo, y + syo, xflip, yflip)

    # crop to content
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"wrote {out}  ({canvas.width}x{canvas.height})")
    if used_tiles:
        print(f"OBJ tiles used: {min(used_tiles):#04x}..{max(used_tiles):#04x} "
              f"({len(used_tiles)} tiles) -> VRAM byte "
              f"${OBJ_BASE + min(used_tiles)*32:04X}..${OBJ_BASE + max(used_tiles)*32+32:04X}")


if __name__ == "__main__":
    main()
