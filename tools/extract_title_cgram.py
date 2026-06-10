#!/usr/bin/env python3
"""Extract assets/title_cgram.bin DIRECTLY from ROM data (retrotool LZSS).

The title encoders quantize against four CGRAM palette groups:
    group  4  (colors  64-79)   BG1 logo yellow   (encode_title_logo)
    group  5  (colors  80-95)   BG1 logo orange   (encode_title_logo)
    group  6  (colors  96-111)  BG1 logo          (encode_title_logo)
    group 12  (colors 192-207)  OBJ kanji/SHURA   (encode_title_kanji_meta)

ROM source: the LZSS palette block at $D8:3D30 (a 512 B CGRAM image staged to
$7F:5000 by screen-manifest #10 — selector table $C0:C075, 6-byte records of
src-long -> WRAM-dest-long). The title screen composes its CGRAM at runtime
from shared palette blocks, so no single ROM block matches the title's CGRAM
layout; this block holds the SAME 16-color groups at different positions:

    title group 4 = block group 8, 5 = 9, 6 = 7, 12 = 13

(verified byte-exact against the title-screen CGRAM capture / v1.1 build —
see tools/validate_title_assets.py). Groups the encoders never read are left
zero: the rest of the title CGRAM (text/flame palettes) is runtime-composed
and not stored as title-layout data in ROM.

The BG2 flame tiles/map and the composed 12 KiB tilemap blob are runtime-
GENERATED (the flame by an effect generator, BG3 text from ASCII strings at
$C0:E684) — they do not exist in ROM as extractable data, which is why
assets/title_flame.bin + title_tilemap_orig.bin remain captures of the
composed output (see tools/reconstruct_title_assets.py).

Usage:  python tools/extract_title_cgram.py [rom]   (default roms/rbshura.sfc)
"""
import sys
from pathlib import Path

from retrotool.compression import LZSSCodec, PARAMS_RBSHURA

ROOT = Path(__file__).resolve().parent.parent

PAL_BLOCK = 0xD83D30          # LZSS block: 512 B CGRAM image (manifest #10)
GROUP_MAP = {4: 8, 5: 9, 6: 7, 12: 13}   # title CGRAM group <- block group


def snes_to_file(lng):        # HiROM $C0-$FF long -> file offset
    return ((lng >> 16) - 0xC0) * 0x10000 + (lng & 0xFFFF)


def main():
    rom_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "roms/rbshura.sfc"
    rom = rom_path.read_bytes()
    block = LZSSCodec(PARAMS_RBSHURA).decompress(rom, snes_to_file(PAL_BLOCK)).data
    assert len(block) == 512, f"palette block decompressed to {len(block)} B, expected 512"

    cg = bytearray(512)
    for dst, src in GROUP_MAP.items():
        cg[dst * 32:(dst + 1) * 32] = block[src * 32:(src + 1) * 32]

    out = ROOT / "assets/title_cgram.bin"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(cg)
    print(f"wrote {out} (512 B; groups {sorted(GROUP_MAP)} from ROM ${PAL_BLOCK:06X})")


if __name__ == "__main__":
    main()
