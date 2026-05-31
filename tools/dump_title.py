#!/usr/bin/env python3
"""Decode the main title screen's BG layers from a Mesen SplitTrace VRAM+CGRAM
snapshot into reference PNGs.

This is the *confirmation/reference* path (renders what is currently in VRAM).
The authoritative ROM-source dump (compression-aware, reading from
roms/rbshura.sfc) is added once the loader is located — see TITLE_INTRO_PLAN.md
Phase 1. Per project preference we dump from ROM for the final asset, but a
VRAM render is the fastest way to confirm layer composition + palette.

Title layout (from state_005.mss, BG Mode 1, mode1Bg3Priority):
  BG1  4bpp  char word $2000  map word $5000  32x64   main screen  (logo + 修羅)
  BG3  2bpp  char word $4000  map word $6000  32x64   main screen  (PUSH START / © / JALECO text)
  BG2  ----  char word $2000  map word $5800  32x32   sub screen   (color-math flame)

VRAM word address W -> byte offset 2*W in the 64 KiB VRAM bin.

Usage:
  python tools/dump_title.py SPLITTRACE_DIR/ram_005_vram.bin \
                             SPLITTRACE_DIR/ram_005_cgram.bin \
                             export/title
"""
import sys
from pathlib import Path
from PIL import Image


def read_bin(p):
    return Path(p).read_bytes()


def cgram_to_palette(cgram):
    """512-byte CGRAM -> list of 256 (r,g,b) from BGR555."""
    pal = []
    for i in range(256):
        lo, hi = cgram[2 * i], cgram[2 * i + 1]
        w = lo | (hi << 8)
        r = (w & 0x1F) << 3
        g = ((w >> 5) & 0x1F) << 3
        b = ((w >> 10) & 0x1F) << 3
        pal.append((r | r >> 5, g | g >> 5, b | b >> 5))
    return pal


def decode_tile(vram, char_byte_base, tile_idx, bpp):
    """Return 8x8 list of palette-index (0..2^bpp-1)."""
    bytes_per = 8 * bpp  # 16 (2bpp) / 32 (4bpp)
    base = char_byte_base + tile_idx * bytes_per
    px = [[0] * 8 for _ in range(8)]
    for y in range(8):
        planes = []
        # 2bpp: planes 0,1 interleaved per row (2 bytes/row)
        p0 = vram[base + y * 2]
        p1 = vram[base + y * 2 + 1]
        planes = [p0, p1]
        if bpp == 4:
            p2 = vram[base + 16 + y * 2]
            p3 = vram[base + 16 + y * 2 + 1]
            planes += [p2, p3]
        for x in range(8):
            bit = 7 - x
            val = 0
            for pi, pb in enumerate(planes):
                val |= ((pb >> bit) & 1) << pi
            px[y][x] = val
    return px


def render_layer(vram, pal, char_word, map_word, cols, rows, bpp,
                 pal_base_default=0):
    """Render a tilemap-composed BG layer to an RGBA image."""
    char_b = char_word * 2
    map_b = map_word * 2
    img = Image.new("RGBA", (cols * 8, rows * 8), (0, 0, 0, 0))
    px = img.load()
    for ty in range(rows):
        for tx in range(cols):
            ent_off = map_b + (ty * cols + tx) * 2
            entry = vram[ent_off] | (vram[ent_off + 1] << 8)
            tile = entry & 0x3FF
            palg = (entry >> 10) & 0x07
            xflip = (entry >> 14) & 1
            yflip = (entry >> 15) & 1
            t = decode_tile(vram, char_b, tile, bpp)
            colors = 1 << bpp
            pbase = palg * colors
            for y in range(8):
                sy = 7 - y if yflip else y
                for x in range(8):
                    sx = 7 - x if xflip else x
                    v = t[sy][sx]
                    if v == 0:
                        continue  # color 0 = transparent
                    r, g, b = pal[pbase + v]
                    px[tx * 8 + x, ty * 8 + y] = (r, g, b, 255)
    return img


def dump_from_rom(rom_path, cgram_path, tilemap_vram_path, outbase):
    """ROM-sourced dump: decompress the title BG1 logo char blocks from ROM
    (retrotool PARAMS_RBSHURA, verified byte-exact vs WRAM), compose with the
    BG1 tilemap, render a redraw-reference PNG, and emit the raw 4bpp char .bin
    for the recompress round-trip.

    Title manifest (selector table $C0:C075 -> records $C0:D2A9+). The RUSHING
    BEAT logo + 修羅 (BG1 4bpp char, VRAM word $2000) is three LZSS blocks that
    decompress contiguously to WRAM $7F:9000..$7F:C000 (12 KiB = 384 tiles):
        $C3:6000 (file 0x36000)  2 KiB
        $C3:6447 (file 0x36447)  8 KiB
        $C3:7298 (file 0x37298)  2 KiB
    Text (PUSH START / © / JALECO / menu, BG3 2bpp char) = $C9:0CFE -> 2 KiB.
    These blocks are shared across title-family manifests #0-4, so editing them
    updates the logo everywhere it appears.
    """
    sys.path.insert(0, "/mnt/crucial/projects/retrotool")
    from retrotool.compression import LZSSCodec, PARAMS_RBSHURA
    rom = read_bin(rom_path)
    codec = LZSSCodec(PARAMS_RBSHURA)

    def s2f(bank, addr):  # HiROM banks $C0-$FF
        return ((bank - 0xC0) & 0xFF) * 0x10000 + addr

    LOGO_BLOCKS = [(0xC3, 0x6000), (0xC3, 0x6447), (0xC3, 0x7298)]
    logo_char = b"".join(codec.decompress(rom, s2f(b, a)).data for b, a in LOGO_BLOCKS)
    Path(f"{outbase}_rom_bg1_logo_char.bin").write_bytes(logo_char)
    print(f"decompressed BG1 logo char: {len(logo_char)} B ({len(logo_char)//32} 4bpp tiles)"
          f" -> {outbase}_rom_bg1_logo_char.bin")

    pal = cgram_to_palette(read_bin(cgram_path))
    # Compose with the BG1 tilemap (word $5000 = byte $A000 in the VRAM snapshot).
    # The char is sourced from ROM; only the tilemap layout comes from the
    # snapshot (it is regenerated by superfamiconv on reinsert).
    vram = bytearray(read_bin(tilemap_vram_path))
    vram[0x4000:0x4000 + len(logo_char)] = logo_char  # splice ROM char into BG1 char slot
    img = render_layer(vram, pal, char_word=0x2000, map_word=0x5000,
                       cols=32, rows=64, bpp=4)
    img.save(f"{outbase}_rom_bg1_logo.png")
    print(f"wrote {outbase}_rom_bg1_logo.png  (ROM char + snapshot tilemap)")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--rom":
        # dump_title.py --rom ROM CGRAM TILEMAP_VRAM OUTBASE
        dump_from_rom(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        return
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    vram = read_bin(sys.argv[1])
    pal = cgram_to_palette(read_bin(sys.argv[2]))
    outbase = Path(sys.argv[3])
    outbase.parent.mkdir(parents=True, exist_ok=True)

    layers = {
        "bg1_logo": dict(char_word=0x2000, map_word=0x5000, cols=32, rows=64, bpp=4),
        "bg3_text": dict(char_word=0x4000, map_word=0x6000, cols=32, rows=64, bpp=2),
        "bg2_flame": dict(char_word=0x2000, map_word=0x5800, cols=32, rows=32, bpp=2),
    }
    for name, kw in layers.items():
        img = render_layer(vram, pal, **kw)
        out = f"{outbase}_{name}.png"
        img.save(out)
        print(f"wrote {out}  ({img.width}x{img.height})")

    # Palette strip (16x16 swatches, 256 colors)
    sw = 16
    pimg = Image.new("RGB", (16 * sw, 16 * sw))
    pp = pimg.load()
    for i, (r, g, b) in enumerate(pal):
        cx, cy = (i % 16) * sw, (i // 16) * sw
        for yy in range(sw):
            for xx in range(sw):
                pp[cx + xx, cy + yy] = (r, g, b)
    pimg.save(f"{outbase}_palette.png")
    print(f"wrote {outbase}_palette.png")


if __name__ == "__main__":
    main()
