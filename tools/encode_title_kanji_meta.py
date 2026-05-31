#!/usr/bin/env python3
"""Build the EN "SHURA" OBJ kanji: 4bpp sprite tiles + a NEW metasprite table,
replacing the original 修羅 (which was a 61-entry metasprite at $DF:EC86).

The original kanji is a metasprite list interpreted by the bank40 engine:
  table entry = [Yoff][Xoff][tile][attr][sizebit]  (signed offsets from base
  $1E04/$1E06 = (176,71); attr=$28 = pal4/pri2; byte4 bit -> 16x16 sprite).
  OBJ tile base = VRAM word $0000.

This tiles title_kanji_en_proposed_size.png (140x72) into a grid of 16x16
sprites. Each 16x16 sprite needs a 2x2 tile block (T, T+1, T+16, T+17) in the
16-wide OBJ tile grid, so we PACK each used cell's 2x2 block into VRAM and point
the metasprite entry at its top-left tile. Fully-transparent cells emit no
sprite (saves OAM + tiles).

Outputs:
  assets/title_kanji.bin       8 KiB OBJ char (packed 2x2 blocks)
  assets/title_kanji_meta.bin  metasprite table (5 B/entry + FFFF terminator)
  export/_kanji_meta_validate.png  re-render (sprites composited)

Placement: centered on the original kanji center (176,79). Tune X0/Y0 to nudge.
"""
import sys
from pathlib import Path
from PIL import Image

BASE_X, BASE_Y = 173, 68
CELL = 16                      # 16x16 sprites
ATTR = 0x28                    # pal 4, priority 2
DEFAULT_CENTER = (163, 109)   # on-screen center of the SHURA (over the BG1 shadow)


def _hex(v):
    if v is None:
        return None
    s = str(v).strip().replace("_", "")
    if s.startswith("$"):
        return int(s.replace(":", "")[1:], 16)
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def load_pal4(root="."):
    cg = Path(root, "assets/title_cgram.bin").read_bytes()
    pal = []
    for i in range(16):
        lo, hi = cg[(192+i)*2], cg[(192+i)*2+1]
        w = lo | (hi << 8)
        r = (w & 0x1F) << 3; g = ((w >> 5) & 0x1F) << 3; b = ((w >> 10) & 0x1F) << 3
        pal.append((r | r >> 5, g | g >> 5, b | b >> 5))
    return pal


def encode(png_path, center=DEFAULT_CENTER, root="."):
    """PNG -> (char 8 KiB OBJ tiles, meta metasprite bytes, pal, placed).
    `center` = on-screen pixel center of the SHURA word (tune to nudge)."""
    pal = load_pal4(root)
    im = Image.open(png_path).convert("RGBA")
    cols = (im.width + CELL - 1) // CELL
    rows = (im.height + CELL - 1) // CELL
    canvas = Image.new("RGBA", (cols*CELL, rows*CELL), (0, 0, 0, 0))
    canvas.paste(im, (0, 0)); px = canvas.load()
    X0 = center[0] - cols*CELL // 2
    Y0 = center[1] - rows*CELL // 2

    def quant(p):
        if p[3] == 0:
            return 0
        best, bd = 0, 1 << 30
        for i in range(1, 16):
            d = sum((a-b)**2 for a, b in zip(p[:3], pal[i]))
            if d < bd:
                bd, best = d, i
        return best

    def enc_tile(cx, cy):
        out = bytearray(32)
        for y in range(8):
            b0 = b1 = b2 = b3 = 0
            for x in range(8):
                v = quant(px[cx+x, cy+y]); bit = 7-x
                b0 |= ((v >> 0) & 1) << bit; b1 |= ((v >> 1) & 1) << bit
                b2 |= ((v >> 2) & 1) << bit; b3 |= ((v >> 3) & 1) << bit
            out[y*2] = b0; out[y*2+1] = b1; out[16+y*2] = b2; out[16+y*2+1] = b3
        return out

    char = bytearray(8192)              # 256 OBJ tiles
    meta = bytearray()
    block = 0                            # packed 2x2-block index
    placed = 0
    for r in range(rows):
        for c in range(cols):
            ox, oy = c*CELL, r*CELL
            # skip fully transparent cells
            if all(px[ox+x, oy+y][3] == 0 for y in range(CELL) for x in range(CELL)):
                continue
            # pack this 2x2 block into the 16-wide OBJ tile grid
            tl = (block // 8) * 32 + (block % 8) * 2   # top-left tile id
            if tl + 17 >= 256:
                raise SystemExit("OBJ tile budget (256) exceeded")
            for (dx, dy, tid) in ((0, 0, tl), (8, 0, tl+1), (0, 8, tl+16), (8, 8, tl+17)):
                t = enc_tile(ox+dx, oy+dy)
                char[tid*32:tid*32+32] = t
            block += 1
            xoff = (X0 + ox) - BASE_X
            yoff = (Y0 + oy) - BASE_Y
            meta += bytes([yoff & 0xFF, xoff & 0xFF, tl & 0xFF, ATTR, 0x01])
            placed += 1
    meta += b"\xFF\xFF"
    return bytes(char), bytes(meta), pal, placed, block


def build(rom, section, root, ctx=None):
    """retrotool kind="graphics" encoder entry. Writes the 8 KiB OBJ tiles at
    `offset` and the metasprite table at `meta-offset`. `center-x`/`center-y`
    attrs override the on-screen SHURA center (default DEFAULT_CENTER)."""
    from retrotool.build.handlers import WriteRange
    png = Path(root) / str(section.files[0])
    tiles_off = section.offset
    meta_off = _hex(section.attrs.get("meta-offset"))
    if tiles_off is None or meta_off is None:
        raise SystemExit("title kanji encoder: needs offset (tiles) + meta-offset")
    cx = _hex(section.attrs.get("center-x")) if section.attrs.get("center-x") else DEFAULT_CENTER[0]
    cy = _hex(section.attrs.get("center-y")) if section.attrs.get("center-y") else DEFAULT_CENTER[1]
    char, meta, *_ = encode(png, (cx, cy), root)
    rom[tiles_off:tiles_off+len(char)] = char
    rom[meta_off:meta_off+len(meta)] = meta
    return [WriteRange(tiles_off, len(char)), WriteRange(meta_off, len(meta))]


def main():
    png = sys.argv[1] if len(sys.argv) > 1 else "export/title_kanji_en_proposed_size.png"
    char, meta, pal, placed, block = encode(png)
    Path("assets/title_kanji.bin").write_bytes(char)
    Path("assets/title_kanji_meta.bin").write_bytes(meta)
    print(f"placed {placed} 16x16 sprites ({block} tile-blocks, {block*4} tiles); meta {len(meta)} B")
    # validate: composite the metasprite (engine emulation)
    out = Image.new("RGB", (256, 224), (30, 15, 15)); op = out.load()
    i = 0
    while i+5 <= len(meta) and meta[i] != 0xFF:
        yoff = meta[i] if meta[i] < 128 else meta[i]-256
        xoff = meta[i+1] if meta[i+1] < 128 else meta[i+1]-256
        tl = meta[i+2]
        sx, sy = BASE_X + xoff, BASE_Y + yoff
        for (dx, dy, tid) in ((0, 0, tl), (8, 0, tl+1), (0, 8, tl+16), (8, 8, tl+17)):
            t = char[tid*32:tid*32+32]
            for y in range(8):
                b0, b1, b2, b3 = t[y*2], t[y*2+1], t[16+y*2], t[16+y*2+1]
                for x in range(8):
                    bit = 7-x
                    v = ((b0>>bit)&1)|(((b1>>bit)&1)<<1)|(((b2>>bit)&1)<<2)|(((b3>>bit)&1)<<3)
                    if v:
                        X, Y = sx+dx+x, sy+dy+y
                        if 0 <= X < 256 and 0 <= Y < 224:
                            op[X, Y] = pal[v]
        i += 5
    out.save("export/_kanji_meta_validate.png")
    print("wrote export/_kanji_meta_validate.png")


if __name__ == "__main__":
    main()
