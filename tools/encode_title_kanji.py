#!/usr/bin/env python3
"""Encode an EN kanji PNG (same 110x134 dims as the dump) back into the title's
OBJ sprite tiles, using the EXISTING OAM layout (same sprite positions/tile
numbers as the original 修羅). Validates the sprite-replacement approach before
any OAM/sizing change.

Inverse of tools/dump_title_kanji.py: that composited sprites -> image (cropped
to bbox); this maps the edited image back to each sprite's tile. The EN PNG must
align to the same bbox crop (edited from the original dump).

OBJ base = VRAM word $0000 (byte $0000). Palette 4 = CGRAM 192-207 (idx1=white).
Output: assets/title_kanji.bin (8 KiB OBJ char). Self-validates -> _kanji_validate.png

Usage: python -m tools.encode_title_kanji [export/title_kanji_en.png]
"""
import sys
from pathlib import Path
from PIL import Image

SPLIT = "/home/daniel/.config/Mesen2/SplitTrace/rbshura_en_20260529_233332"


def load_oam_pal():
    oam = Path(SPLIT, "ram_005_oam.bin").read_bytes()
    cg = Path("assets/title_cgram.bin").read_bytes()
    pal = []
    for i in range(16):
        lo, hi = cg[(192+i)*2], cg[(192+i)*2+1]
        w = lo | (hi << 8)
        r = (w & 0x1F) << 3; g = ((w >> 5) & 0x1F) << 3; b = ((w >> 10) & 0x1F) << 3
        pal.append((r | r >> 5, g | g >> 5, b | b >> 5))
    spr = []
    for i in range(128):
        x = oam[i*4]; y = oam[i*4+1]; tile = oam[i*4+2]; attr = oam[i*4+3]
        hb = oam[512+i//4]; bits = (hb >> ((i % 4)*2)) & 0x3
        xhi = bits & 1; size = (bits >> 1) & 1
        X = x | (0x100 if xhi else 0)
        if y < 0xE0:
            spr.append((X, y, tile, attr, size))
    return spr, pal


def orig_bbox(spr):
    """Reproduce the crop bbox the dump used (composite originals, getbbox)."""
    vram = Path(SPLIT, "ram_005_vram.bin").read_bytes()
    canvas = Image.new("RGBA", (320, 256), (0, 0, 0, 0)); px = canvas.load()
    def tile_px(t, x, y):
        base = t*32
        for yy in range(8):
            b0 = vram[base+yy*2]; b1 = vram[base+yy*2+1]; b2 = vram[base+16+yy*2]; b3 = vram[base+16+yy*2+1]
            for xx in range(8):
                bit = 7-xx
                v = ((b0>>bit)&1) | (((b1>>bit)&1)<<1) | (((b2>>bit)&1)<<2) | (((b3>>bit)&1)<<3)
                if v and 0 <= x+xx < 320 and 0 <= y+yy < 256:
                    px[x+xx, y+yy] = (255, 255, 255, 255)
    for X, y, tile, attr, size in spr:
        if size == 0:
            tile_px(tile, X, y)
        else:
            for dy in range(2):
                for dx in range(2):
                    tile_px((tile+dx+dy*16) & 0xFF, X+dx*8, y+dy*8)
    return canvas.getbbox()


def quant(p, pal):
    if p[3] == 0:
        return 0
    best = 0; bd = 1 << 30
    for i in range(1, 16):
        d = sum((a-b)**2 for a, b in zip(p[:3], pal[i]))
        if d < bd:
            bd = d; best = i
    return best


def main():
    png = sys.argv[1] if len(sys.argv) > 1 else "export/title_kanji_en.png"
    spr, pal = load_oam_pal()
    bb = orig_bbox(spr); ox, oy = bb[0], bb[1]
    im = Image.open(png).convert("RGBA"); px = im.load()
    char = bytearray(8192)  # 256 tiles * 32

    def write_tile(t, sx, sy):
        # sprite tile covers screen (sx,sy)..(sx+7,sy+7) -> image (sx-ox, sy-oy)
        idx = [[0]*8 for _ in range(8)]
        for yy in range(8):
            for xx in range(8):
                ix, iy = sx+xx-ox, sy+yy-oy
                if 0 <= ix < im.width and 0 <= iy < im.height:
                    idx[yy][xx] = quant(px[ix, iy], pal)
        base = t*32
        for yy in range(8):
            b0 = b1 = b2 = b3 = 0
            for xx in range(8):
                v = idx[yy][xx]; bit = 7-xx
                b0 |= ((v >> 0) & 1) << bit; b1 |= ((v >> 1) & 1) << bit
                b2 |= ((v >> 2) & 1) << bit; b3 |= ((v >> 3) & 1) << bit
            char[base+yy*2] = b0; char[base+yy*2+1] = b1
            char[base+16+yy*2] = b2; char[base+16+yy*2+1] = b3

    for X, y, tile, attr, size in spr:
        if size == 0:
            write_tile(tile, X, y)
        else:
            for dy in range(2):
                for dx in range(2):
                    write_tile((tile+dx+dy*16) & 0xFF, X+dx*8, y+dy*8)

    Path("assets/title_kanji.bin").write_bytes(char)
    print(f"wrote assets/title_kanji.bin (8 KiB) from {png}  (bbox origin {ox},{oy})")

    # validate: re-composite new char with OAM
    out = Image.new("RGB", (im.width, im.height), (30, 15, 15)); op = out.load()
    def blit(t, sx, sy):
        base = t*32
        for yy in range(8):
            b0 = char[base+yy*2]; b1 = char[base+yy*2+1]; b2 = char[base+16+yy*2]; b3 = char[base+16+yy*2+1]
            for xx in range(8):
                bit = 7-xx
                v = ((b0>>bit)&1) | (((b1>>bit)&1)<<1) | (((b2>>bit)&1)<<2) | (((b3>>bit)&1)<<3)
                if v:
                    ix, iy = sx+xx-ox, sy+yy-oy
                    if 0 <= ix < im.width and 0 <= iy < im.height:
                        op[ix, iy] = pal[v]
    for X, y, tile, attr, size in spr:
        if size == 0: blit(tile, X, y)
        else:
            for dy in range(2):
                for dx in range(2):
                    blit((tile+dx+dy*16) & 0xFF, X+dx*8, y+dy*8)
    out.save("export/_kanji_validate.png")
    print("wrote export/_kanji_validate.png")


if __name__ == "__main__":
    main()
