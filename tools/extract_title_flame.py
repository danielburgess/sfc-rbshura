#!/usr/bin/env python3
"""Extract the title-screen BG2 flame tiles that the EN BG1-logo expansion clobbers.

The title is BG Mode 1 with BG12NBA=$22, so BG1 (logo) and BG2 (flame) SHARE a
char base (VRAM word $2000 / byte $4000). The original 8 KiB char blob held both
the logo tiles and the flame's tiles (at fixed slots BG2's tilemap references).
The EN build regenerates that region as a 16 KiB logo-only char, overwriting the
flame slots -> corrupted flame.

This pulls those flame tiles out of a CLEAN (unpatched) title VRAM dump from a
Mesen SplitTrace ($00C8==2 title; e.g. the user's rbshura_20260530_221837 snap4
which captured BG2 in isolation) into assets/title_flame.bin, so
encode_title_logo.py can reserve their slots and bake them back in.

Run once when the flame source changes:
    python tools/extract_title_flame.py <clean_title_vram.bin>
"""
import sys
from pathlib import Path

# BG2 (flame) char base = word $2000 = byte $4000 (shares BG12NBA nibble w/ BG1).
CHAR_BASE = 0x4000
# Tile slots BG2's tilemap references, all within $000-$0FF — exactly the region
# the 16 KiB EN logo char overwrites. (tile $00 = blank, shared, not restored.)
FLAME_SLOTS = [0x7A, 0x7E, 0xAC, 0xAD, 0xAE, 0xDC, 0xEB, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF]


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: extract_title_flame.py <clean_title_vram.bin>")
    vram = Path(sys.argv[1]).read_bytes()
    out = bytearray()
    for slot in FLAME_SLOTS:
        o = CHAR_BASE + slot * 32          # 4bpp = 32 bytes/tile
        tile = vram[o:o + 32]
        assert any(tile), f"flame slot ${slot:02X} blank in {sys.argv[1]} (wrong dump?)"
        out += tile
    dst = Path(__file__).resolve().parent.parent / "assets" / "title_flame.bin"
    dst.write_bytes(out)
    print(f"wrote {dst} ({len(out)} B = {len(FLAME_SLOTS)} flame tiles, slots "
          f"{[f'${s:02X}' for s in FLAME_SLOTS]})")


if __name__ == "__main__":
    main()
