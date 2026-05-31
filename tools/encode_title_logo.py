#!/usr/bin/env python3
"""EN title BG1 logo encoder — a retrotool `kind="graphics"` custom encoder.

Encodes the EN title BG1 logo (256x512 PNG) -> 4bpp char (16 KiB / up to 512
tiles) + BG1 tilemap, quantized to the original CGRAM palette groups 4/5/6.

The title BG1 char is EXPANDED from 8 KiB (256 tiles) to 16 KiB (512 tiles) to
fit the EN art (~345 unique tiles). VRAM word $2000..$4000 (byte $4000..$8000;
the upper half was unused). The BG1 tilemap (32x64) is spliced into the original
combined tilemap blob (assets/title_tilemap_orig.bin = VRAM $A000..$D000 =
BG1|BG2|BG3 maps) so BG2 (flame) and BG3 (text) maps are preserved.

Build-time use (project.toml) — runs DURING `retrotool build`:
    [[rom.build.sections]]
    kind = "graphics"
    encoder = "tools/encode_title_logo.py:build"
    file = "export/title_bg1_logo_en.png"
    offset = "$211000"          # 16 KiB char dest ($E1:1000)
    map-offset = "$217000"      # 12 KiB combined tilemap dest ($E1:7000)

Standalone preview: `python -m tools.encode_title_logo [png]` writes the .bin
files + export/_encode_validate.png (the .bin files are NOT used by the build).

Palette: assets/title_cgram.bin (512B CGRAM). Groups 4/5/6 -> CGRAM 64/80/96.
Each cell picks the group with least quantization error; the tilemap entry
stores tile index (10b) | palette group (3b) | flip (2b). Char tiles are
deduplicated across H/V/HV flips.
"""
import sys
from pathlib import Path
from PIL import Image

GROUPS = (4, 5, 6)
CHAR_TILES = 512          # 16 KiB / 32 B
BG1_MAP_BYTES = 0x1000    # 32x64 entries * 2 B = first 4 KiB of the combined blob

# BG1 (logo) and BG2 (flame) SHARE this char region (title BG12NBA=$22). BG2's
# (preserved) tilemap references these fixed tile slots; we must NOT hand them to
# logo tiles, and must bake the original flame tiles into them (assets/title_flame.bin,
# from tools/extract_title_flame.py). Must match FLAME_SLOTS there.
FLAME_SLOTS = [0x7A, 0x7E, 0xAC, 0xAD, 0xAE, 0xDC, 0xEB, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF]


def _hex(v):
    """Parse a retrotool numeric attr ($/0x hex, $BB:AAAA, or decimal)."""
    if v is None:
        return None
    s = str(v).strip().replace("_", "")
    if s.startswith("$"):
        return int(s.replace(":", "")[1:], 16)
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def load_palettes(cgram_path):
    cg = Path(cgram_path).read_bytes()
    pals = {}
    for g in GROUPS:
        cols = []
        for i in range(16):
            lo, hi = cg[(g*16+i)*2], cg[(g*16+i)*2+1]
            w = lo | (hi << 8)
            r = (w & 0x1F) << 3; gr = ((w >> 5) & 0x1F) << 3; b = ((w >> 10) & 0x1F) << 3
            cols.append((r | r >> 5, gr | gr >> 5, b | b >> 5))
        pals[g] = cols
    return pals


def quantize_cell(px, c, r, pal):
    """Return (indices[64], total_error) quantizing an 8x8 cell to one palette."""
    idx = []; err = 0
    for y in range(8):
        for x in range(8):
            p = px[c*8+x, r*8+y]
            if p[3] == 0:
                idx.append(0); continue
            best = 0; bd = 1 << 30
            for i, col in enumerate(pal):
                if i == 0:
                    continue  # color 0 = transparent; only for fully-transparent px
                d = (p[0]-col[0])**2 + (p[1]-col[1])**2 + (p[2]-col[2])**2
                if d < bd:
                    bd = d; best = i
            idx.append(best); err += bd
    return idx, err


def flip_variants(t):
    g = [t[i*8:(i+1)*8] for i in range(8)]
    h = tuple(v for row in g for v in row[::-1])
    vv = tuple(v for row in g[::-1] for v in row)
    hv = tuple(v for row in g[::-1] for v in row[::-1])
    return {t: (0, 0), h: (1, 0), vv: (0, 1), hv: (1, 1)}


def tile_to_4bpp(idx):
    """64 nibble indices -> 32-byte SNES 4bpp tile."""
    out = bytearray(32)
    for y in range(8):
        b0 = b1 = b2 = b3 = 0
        for x in range(8):
            v = idx[y*8+x]; bit = 7-x
            b0 |= ((v >> 0) & 1) << bit
            b1 |= ((v >> 1) & 1) << bit
            b2 |= ((v >> 2) & 1) << bit
            b3 |= ((v >> 3) & 1) << bit
        out[y*2] = b0; out[y*2+1] = b1
        out[16+y*2] = b2; out[16+y*2+1] = b3
    return bytes(out)


def encode(png_path, root="."):
    """PNG -> (char_bin 16 KiB, tilemap_blob 12 KiB, pals, char, tilemap).
    Reads palette + the original combined tilemap blob from <root>/assets."""
    root = Path(root)
    pals = load_palettes(root / "assets/title_cgram.bin")
    im = Image.open(png_path).convert("RGBA"); px = im.load()
    assert im.size == (256, 512), f"expected 256x512, got {im.size}"

    # Fixed 512-slot char, all blank. Reserve tile 0 (shared blank) + the flame
    # slots, and bake the original flame tiles in. Logo tiles get the remaining
    # free slots (the BG1 tilemap we emit references those, so it stays correct).
    flame = Path(root, "assets/title_flame.bin").read_bytes()
    assert len(flame) == len(FLAME_SLOTS) * 32, \
        f"title_flame.bin is {len(flame)} B, expected {len(FLAME_SLOTS)*32}"
    char = [bytes(32) for _ in range(CHAR_TILES)]
    reserved = {0}
    for i, slot in enumerate(FLAME_SLOTS):
        char[slot] = flame[i*32:(i+1)*32]
        reserved.add(slot)
    canon = {tuple([0]*64): 0}         # logo index-pattern -> char tile id (w/ flips)
    tilemap = bytearray(32*64*2)
    blank = tuple([0]*64)
    nxt = 1                            # next free logo slot (skips reserved)

    for r in range(64):
        for c in range(32):
            best_g = GROUPS[0]; best_idx = None; best_err = 1 << 60
            for g in GROUPS:
                idx, err = quantize_cell(px, c, r, pals[g])
                if err < best_err:
                    best_err = err; best_idx = idx; best_g = g
            t = tuple(best_idx)
            ent = r*32 + c
            if t == blank:
                continue  # tile 0, palette 0, no flip -> entry stays 0
            tile_id = None; fx = fy = 0
            for variant, (vx, vy) in flip_variants(t).items():
                if variant in canon:
                    tile_id = canon[variant]; fx, fy = vx, vy; break
            if tile_id is None:
                while nxt in reserved:
                    nxt += 1
                if nxt >= CHAR_TILES:
                    raise SystemExit(f"OVER BUDGET: >{CHAR_TILES} tiles at cell ({c},{r})")
                tile_id = nxt; nxt += 1
                char[tile_id] = tile_to_4bpp(best_idx)
                canon[t] = tile_id
            word = (tile_id & 0x3FF) | (best_g << 10) | (fx << 14) | (fy << 15)
            tilemap[ent*2] = word & 0xFF; tilemap[ent*2+1] = word >> 8

    char_bin = b"".join(char)
    # splice the new BG1 map over the original combined blob (preserve BG2/BG3)
    blob = bytearray(Path(root, "assets/title_tilemap_orig.bin").read_bytes())
    blob[0:BG1_MAP_BYTES] = tilemap[0:BG1_MAP_BYTES]
    _set_subtitle(blob)
    return char_bin, bytes(blob), pals, char, tilemap, len(canon)


# EN subtitle: replace the JP katakana (BG3 row 17, tiles $02-$0E) with English
# text drawn from the BG3 font (ASCII-indexed, uppercase only). Screen-centered,
# palette 4 ($3000 = blue/white) to match the katakana it replaces.
SUBTITLE = "THE ETERNAL CONFLICT"
SUB_ROW, SUB_ATTR = 17, 0x3000    # original katakana row (capture source)
EN_ROW = 18                       # EN subtitle text, one row below the logo
TM_ROW, TM_COL = 16, 28           # ™ (2 tiles) at the logo's top-right
BG3_MAP_OFF = 0x2000              # BG3 map (VRAM word $6000) in the combined blob
KANA_ROW = 4                      # re-place the JP katakana above the logo;
                                  # its dakuten goes on KANA_ROW-1, as in the original
KANA_COL = 3                      # left-align the katakana's leftmost glyph here (logo left edge)

def _set_subtitle(blob):
    def off(rr): return BG3_MAP_OFF + rr * 32 * 2
    def read_row(rr):
        o = off(rr); return [blob[o+i*2] | (blob[o+i*2+1] << 8) for i in range(32)]
    def write_row(rr, ents):
        o = off(rr)
        for i, e in enumerate(ents):
            blob[o+i*2] = e & 0xFF; blob[o+i*2+1] = (e >> 8) & 0xFF
    # Capture original JP katakana (SUB_ROW) + dakuten (SUB_ROW-1) + the ™ tiles.
    kana, daku = read_row(SUB_ROW), read_row(SUB_ROW - 1)
    tm_tiles = [kana[27], kana[28]]          # two-tile ™ on the katakana row
    for c in (27, 28):
        kana[c] = 0                          # ™ is not part of the katakana
    # Clear the original katakana rows + the target EN row.
    for rr in (SUB_ROW - 1, SUB_ROW, EN_ROW):
        write_row(rr, [0]*32)
    # JP katakana above the logo, left-aligned to the logo's left edge (KANA_COL);
    # shift the kana AND its dakuten by the same amount to keep them aligned.
    shift = KANA_COL - min(c for c in range(32) if kana[c])
    def _shift(row):
        out = [0]*32
        for c in range(32):
            if row[c] and 0 <= c + shift < 32:
                out[c + shift] = row[c]
        return out
    write_row(KANA_ROW, _shift(kana)); write_row(KANA_ROW - 1, _shift(daku))
    # ™ at the logo's top-right.
    tmrow = [0]*32
    tmrow[TM_COL] = tm_tiles[0]; tmrow[TM_COL + 1] = tm_tiles[1]
    write_row(TM_ROW, tmrow)
    # EN subtitle below the logo, screen-centered.
    start = (32 - len(SUBTITLE)) // 2
    en = [0]*32
    for i, ch in enumerate(SUBTITLE):
        en[start + i] = SUB_ATTR | ord(ch)
    write_row(EN_ROW, en)


def build(rom, section, root, ctx=None):
    """retrotool kind="graphics" encoder entry. Writes the 16 KiB char at
    `offset` and the 12 KiB combined tilemap blob at `map-offset`."""
    from retrotool.build.handlers import WriteRange
    png = Path(root) / str(section.files[0])
    char_off = section.offset
    map_off = _hex(section.attrs.get("map-offset"))
    if char_off is None or map_off is None:
        raise SystemExit("title logo encoder: needs offset (char) + map-offset")
    char_bin, blob, *_ = encode(png, root)
    rom[char_off:char_off+len(char_bin)] = char_bin
    rom[map_off:map_off+len(blob)] = blob
    return [WriteRange(char_off, len(char_bin)), WriteRange(map_off, len(blob))]


def main():
    png = sys.argv[1] if len(sys.argv) > 1 else "export/title_bg1_logo_en.png"
    char_bin, blob, pals, char, tilemap, ntiles = encode(png)
    Path("assets/title_logo.bin").write_bytes(char_bin)
    Path("assets/title_tilemap.bin").write_bytes(blob)
    print(f"char: {ntiles} unique tiles (+flips), 16 KiB -> assets/title_logo.bin")
    print("tilemap -> assets/title_tilemap.bin (12 KiB)")
    out = Image.new("RGB", (256, 512), (20, 10, 10)); op = out.load()
    for r in range(64):
        for c in range(32):
            word = tilemap[(r*32+c)*2] | (tilemap[(r*32+c)*2+1] << 8)
            tid = word & 0x3FF; g = (word >> 10) & 7
            fx = (word >> 14) & 1; fy = (word >> 15) & 1
            tile = char[tid]
            for y in range(8):
                for x in range(8):
                    sx = 7-x if fx else x; sy = 7-y if fy else y
                    b0 = tile[sy*2]; b1 = tile[sy*2+1]; b2 = tile[16+sy*2]; b3 = tile[16+sy*2+1]
                    bit = 7-sx
                    v = (((b0>>bit)&1) | (((b1>>bit)&1)<<1) | (((b2>>bit)&1)<<2) | (((b3>>bit)&1)<<3))
                    if v:
                        op[c*8+x, r*8+y] = pals[g][v]
    out.save("export/_encode_validate.png")
    print("wrote export/_encode_validate.png")


if __name__ == "__main__":
    main()
