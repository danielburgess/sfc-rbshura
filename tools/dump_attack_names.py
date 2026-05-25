#!/usr/bin/env python3
"""Dump the special-move "attack name" word-art graphics to superfamiconv-ready PNGs.

The names are uncompressed 2bpp BG3 word-art (furigana katakana + big kanji),
displayed near lower-center when a special move triggers. They are a single
shared pool indexed by every character.

Engine layout (HiROM rbshura):
  - Loader $82:DC2B builds a queued DMA per attack:
        tiles  : $200 bytes (32 tiles) from $CF:<tile_src> -> VRAM word $4700 (tile $E0)
        tilemap: $100 bytes (128 entries) from $CF:<map_src> -> VRAM word $5A28 (BG3 map)
  - Source-address table at $82:DC8C, 4-byte entries [tile_src(2)][map_src(2)],
    indexed by $12CE. Table runs until the next jump-table routine ($DCA0).

Each name -> one native-resolution INDEXED PNG (so superfamiconv reproduces the
2bpp tiles cleanly): index 0 = transparent backdrop, 1-3 = furigana palette
(CGRAM pal 4), 4-6 = kanji palette (CGRAM pal 5). superfamiconv -B 2 -C 4 -P 8
splits it back into two 4-colour sub-palettes + tiles + map.

Usage:
    python tools/dump_attack_names.py [--rom rbshura.sfc] [--cgram <snapshot cgram.bin>]
                                      [--out export/attack_names] [--scale N]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

# --- HiROM constants -------------------------------------------------------
BANK_CF = 0x0F0000            # file offset of SNES bank $CF
TABLE_OFF = 0x02DC8C          # $82:DC8C source-address table
TABLE_MAX = 0x02DCA0          # table end ($DCA0 = next routine)
TILES_PER_NAME = 32           # DMA count $200 / 16
MAP_ENTRIES = 128             # DMA count $100 / 2
VRAM_TILE_BASE = 0xE0         # tiles land at VRAM tile index $E0
MAP_LINEAR_START = (0x5A28 - 0x5800)  # 0x228 = entry 552 in 32-col BG3 map
MAP_STRIDE = 32

# Friendly slugs keyed by tile_src (romaji of the move name).
NAME_SLUGS = {
    0x3B98: "thunder_edge",   # 雷撃斬 / サンダーエッジ
    0x3A08: "assault_tiger",  # 猛虎裂破 / アサルトタイガー
    0x3758: "dragon_wave",    # 旋攻竜 / ドラゴンウェーブ
    0x38A8: "bird_storm",     # 鳳凰乱舞 / バードストーム
}

# Fallback palette (CGRAM pal4=furigana, pal5=kanji) if no snapshot cgram given.
# RGB888 expanded from the live BGR555 values.
FALLBACK_PAL4 = [(8, 74, 8), (231, 231, 0), (255, 255, 198), (82, 82, 0)]
FALLBACK_PAL5 = [(16, 82, 16), (255, 90, 8), (255, 198, 148), (82, 0, 0)]
TRANSPARENT = (255, 0, 255)   # index-0 key colour (backdrop; never drawn)


def bgr555_to_rgb(w: int) -> tuple[int, int, int]:
    r = (w & 31) << 3
    g = ((w >> 5) & 31) << 3
    b = ((w >> 10) & 31) << 3
    return (r | r >> 5, g | g >> 5, b | b >> 5)


def load_palettes(cgram_path: Path | None):
    if cgram_path is None:
        return FALLBACK_PAL4, FALLBACK_PAL5
    cg = cgram_path.read_bytes()
    def pal(base):
        return [bgr555_to_rgb(cg[(base + k) * 2] | (cg[(base + k) * 2 + 1] << 8)) for k in range(4)]
    return pal(16), pal(20)


def decode_2bpp(rom: bytes, off: int, n: int):
    out = []
    for t in range(n):
        b = rom[off + t * 16: off + t * 16 + 16]
        tile = [[0] * 8 for _ in range(8)]
        for r in range(8):
            p0, p1 = b[r * 2], b[r * 2 + 1]
            for c in range(8):
                bit = 7 - c
                tile[r][c] = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
        out.append(tile)
    return out


def read_table(rom: bytes):
    """Yield (entry_idx, $12CE value, tile_src, map_src) for each table entry."""
    entries = []
    off = TABLE_OFF
    idx = 0
    while off + 4 <= TABLE_MAX:
        tile_src = rom[off] | (rom[off + 1] << 8)
        map_src = rom[off + 2] | (rom[off + 3] << 8)
        entries.append((idx, idx * 2, tile_src, map_src))
        off += 4
        idx += 1
    return entries


def render_name(rom: bytes, tile_src: int, map_src: int, pal4, pal5):
    """Return an indexed PIL image cropped to the tile-aligned glyph bbox."""
    tiles = decode_2bpp(rom, BANK_CF + tile_src, TILES_PER_NAME)
    mo = BANK_CF + map_src
    # combined 7-colour palette: 0=bg, 1-3=furigana(pal4), 4-6=kanji(pal5)
    flat_pal = [TRANSPARENT, *pal4[1:], *pal5[1:]]
    grid_cols, grid_rows = MAP_STRIDE, 32
    img = Image.new("P", (grid_cols * 8, grid_rows * 8), 0)
    pal_bytes = []
    for rgb in flat_pal:
        pal_bytes += list(rgb)
    img.putpalette(pal_bytes + [0, 0, 0] * (256 - len(flat_pal)))
    px = img.load()
    minx = miny = 1 << 30
    maxx = maxy = -1
    for i in range(MAP_ENTRIES):
        ent = rom[mo + i * 2] | (rom[mo + i * 2 + 1] << 8)
        if ent == 0:
            continue
        tile_i = ent & 0x3FF
        pal_sel = (ent >> 10) & 7      # 4 = furigana, 5 = kanji
        hf = bool(ent & 0x4000)
        vf = bool(ent & 0x8000)
        k = tile_i - VRAM_TILE_BASE
        if k < 0 or k >= len(tiles):
            continue
        lin = MAP_LINEAR_START + i
        gx = (lin % MAP_STRIDE) * 8
        gy = (lin // MAP_STRIDE) * 8
        base_idx = 0 if pal_sel == 4 else 3   # furigana 1-3, kanji 4-6
        drew = False
        for ry in range(8):
            for cx in range(8):
                v = tiles[k][7 - ry if vf else ry][7 - cx if hf else cx]
                if v == 0:
                    continue
                px[gx + cx, gy + ry] = base_idx + v
                drew = True
        if drew:
            minx = min(minx, gx); maxx = max(maxx, gx + 7)
            miny = min(miny, gy); maxy = max(maxy, gy + 7)
    if maxx < 0:
        return None, None
    # tile-align the crop box
    cx0 = (minx // 8) * 8
    cy0 = (miny // 8) * 8
    cx1 = ((maxx // 8) + 1) * 8
    cy1 = ((maxy // 8) + 1) * 8
    crop = img.crop((cx0, cy0, cx1, cy1))
    return crop, (cx0, cy0, cx1 - cx0, cy1 - cy0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default="rbshura.sfc", help="source ROM (default: pristine rbshura.sfc)")
    ap.add_argument("--cgram", default=None, help="snapshot ram_NNN_cgram.bin for exact palette")
    ap.add_argument("--out", default="export/attack_names", help="output directory")
    ap.add_argument("--scale", type=int, default=1, help="also write an Nx preview PNG")
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    pal4, pal5 = load_palettes(Path(args.cgram) if args.cgram else None)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    table = read_table(rom)
    seen: dict[tuple[int, int], str] = {}
    manifest = {
        "rom": args.rom,
        "loader": "$82:DC2B",
        "table": "$82:DC8C",
        "bank": "$CF",
        "tile_dma": {"count": 0x200, "vram_word": 0x4700, "bpp": 2},
        "map_dma": {"count": 0x100, "vram_word": 0x5A28},
        "palettes": {"furigana_cgram": "16-19", "kanji_cgram": "20-23"},
        "entries": [],
    }

    for idx, reg12ce, tile_src, map_src in table:
        key = (tile_src, map_src)
        slug = NAME_SLUGS.get(tile_src, f"name_{tile_src:04X}")
        dup_of = seen.get(key)
        rec = {
            "index": idx,
            "reg_12CE": reg12ce,
            "tile_src": f"$CF:{tile_src:04X}",
            "map_src": f"$CF:{map_src:04X}",
            "slug": slug,
            "duplicate_of": dup_of,
        }
        if dup_of is None:
            img, box = render_name(rom, tile_src, map_src, pal4, pal5)
            if img is None:
                rec["error"] = "empty render"
                manifest["entries"].append(rec)
                continue
            png = out / f"{idx}_{slug}.png"
            img.save(png)
            rec["png"] = png.name
            rec["size"] = {"w": box[2], "h": box[3]}
            if args.scale > 1:
                big = img.convert("RGB").resize((box[2] * args.scale, box[3] * args.scale), Image.NEAREST)
                big.save(out / f"{idx}_{slug}@{args.scale}x.png")
            seen[key] = slug
            print(f"  entry {idx} $12CE={reg12ce}: {slug:14s} tile $CF:{tile_src:04X} map $CF:{map_src:04X} -> {png.name} ({box[2]}x{box[3]})")
        else:
            print(f"  entry {idx} $12CE={reg12ce}: {slug:14s} DUPLICATE of '{dup_of}'")
        manifest["entries"].append(rec)

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    uniq = len([e for e in manifest["entries"] if not e.get("duplicate_of")])
    print(f"\n{uniq} unique names, {len(table)} table entries -> {out}/")


if __name__ == "__main__":
    main()
