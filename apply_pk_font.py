#!/usr/bin/env python3
"""Apply Peacekeepers' Latin font to rbshura — CORRECTED PADDING APPROACH.

Architecture discovery (2026-05-16):
  The buffer at $0E22-$0E31 is NOT OAM sprite data — it's a VRAM DMA upload
  queue. The consumer at $009BC2 reads each entry and:
    - $0E22 → $2115 (VMAIN: VRAM increment mode)
    - $0E23 → $4302 (DMA source address low)
    - $0E25 → $4304 (DMA source bank)
    - $0E26 → $4305 (DMA byte count)
    - $0E28 → $2116 (VRAM destination word address)
    - $420B trigger

  rbshura's original renderer queues ONE 64-byte DMA per char that uploads
  4 consecutive 16-byte tiles to consecutive VRAM slots. The tilemap-write
  tail then references those 4 tile slots in a 2x2 arrangement
  (TL=A, TR=A+1, BL=A+2, BR=A+3), rendering a 16x16 char.

  Font byte layout in rbshura's slots (per the tilemap arrangement):
    bytes  0-15  = TL tile (top-left 8x8)
    bytes 16-31  = TR tile (top-right 8x8)
    bytes 32-47  = BL tile (bottom-left 8x8)
    bytes 48-63  = BR tile (bottom-right 8x8)
  i.e. row-major TL/TR/BL/BR — confirmed by the +$40 tilemap RAM stride
  between entry 1/2 (top row) and entry 3/4 (bottom row).

Why earlier patches were wrong:
  - My first padding put PK 32 bytes into rbshura bytes 0-31 (= TL+TR) →
    PK's top and bottom tiles ended up rendered SIDE-BY-SIDE as a 16x8
    char. That's the "side-by-side" the user saw.
  - The Option B renderer port emitted 2 DMA entries per char but kept the
    4-entry tilemap tail, leaving 2 of the 4 tile slots referencing stale
    VRAM. Letters broke for the same reason.

Correct padding:
  - bytes  0-15 = PK top tile (becomes rbshura TL — top-left of cell)
  - bytes 16-31 = ZEROS (TR — top-right is blank)
  - bytes 32-47 = PK bottom tile (becomes rbshura BL — bottom-left)
  - bytes 48-63 = ZEROS (BR — bottom-right is blank)

  Result: each PK 8x16 Latin glyph displays in the LEFT 8 pixels of a
  16x16 rbshura cell, with blank padding on the right and bottom-right.
  Letters read normally; text appears spaced (16 px per char) but the
  glyphs themselves are correctly oriented (top-on-top, bottom-on-bottom).

This script also RESTORES the renderer at $05839F to vanilla rbshura
bytes (reverting my earlier broken in-place and full-port patches).

A pure Option B port that ALSO patches the tilemap arrangement (so chars
render at 8-px spacing using only 2 tile slots per char in a single
column) is a deeper change — would need to (a) change the renderer to
emit 1 DMA of 32 bytes per char, (b) change the tilemap tail to write
only 2 entries (TL position and BL position), (c) adjust the column-
advance from 4 to 1. Tracked as future work after we visually confirm
the padded font renders correctly.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).parent
PK_ROM = ROOT / "peacekeepers.sfc"
JP_ROM = ROOT / "rbshura.sfc"
OUT_ROM = ROOT / "rbshura_pkfont.sfc"

FONT_PC = 0x100000
PK_CHAR_BYTES = 32          # PK 8x16 glyph (top tile + bottom tile)
JP_CHAR_BYTES = 64          # rbshura 16x16 slot (4 tiles TL/TR/BL/BR)
N_GLYPHS = 80               # cover PK chars $00-$4F
PK_FONT_BYTES = N_GLYPHS * PK_CHAR_BYTES  # 2560 bytes read from PK
JP_FONT_BYTES = N_GLYPHS * JP_CHAR_BYTES  # 5120 bytes written into rbshura


LATIN_MAP: dict[int, str] = {
    0x00: ' ',
    **{0x01 + i: chr(ord('a') + i) for i in range(26)},  # 01-1A = a-z
    **{0x20 + i: chr(ord('0') + i) for i in range(10)},  # 20-29 = 0-9 (tentative)
    **{0x30 + i: chr(ord('A') + i) for i in range(26)},  # 30-49 = A-Z (tentative)
}


def patch_font(jp_rom: bytes, pk_rom: bytes) -> bytes:
    """Pad PK glyphs into rbshura's TL/TR/BL/BR slot layout.

    PK glyph layout (32 bytes):
      bytes  0-15 = top tile (8x8)
      bytes 16-31 = bottom tile (8x8)

    rbshura slot layout (64 bytes, row-major):
      bytes  0-15 = TL tile
      bytes 16-31 = TR tile
      bytes 32-47 = BL tile
      bytes 48-63 = BR tile

    Map PK top → rbshura TL, PK bottom → rbshura BL, leave TR/BR zero.
    """
    out = bytearray(jp_rom)
    for n in range(N_GLYPHS):
        pk_off = FONT_PC + n * PK_CHAR_BYTES
        jp_off = FONT_PC + n * JP_CHAR_BYTES
        out[jp_off:jp_off + 16]       = pk_rom[pk_off:pk_off + 16]      # TL = PK top
        out[jp_off + 16:jp_off + 32]  = b'\x00' * 16                     # TR = blank
        out[jp_off + 32:jp_off + 48]  = pk_rom[pk_off + 16:pk_off + 32] # BL = PK bottom
        out[jp_off + 48:jp_off + 64]  = b'\x00' * 16                     # BR = blank
    return bytes(out)


def write_en_table(path: Path) -> None:
    lines = [
        "; Rushing Beat Shura — ENGLISH encoding table (PK font padded for",
        "; rbshura's TL/TR/BL/BR 16x16 renderer).",
        ";",
        "; Each PK 8x16 glyph occupies the LEFT half of its 16x16 rbshura slot",
        "; (TL = PK top tile, BL = PK bottom tile, TR/BR blank).",
        "",
        "@ctrl_prefix F7 F8 F9 FB FC FD FE FF",
        "@ctrl F7=2",
        "@ctrl F8=2",
        "@ctrl F9=2",
        "@ctrl FB=2",
        "@ctrl FC=3",
        "@ctrl FC.02=4",
        "@ctrl FD=1",
        "@ctrl FE=1",
        "@ctrl FF=1",
        "",
        "; --- Latin character set (from Peacekeepers font) ---",
    ]
    for byte_val, ch in sorted(LATIN_MAP.items()):
        lines.append(f"{byte_val:02X}={ch}")
    lines.append("")
    lines.append("**=[**]")
    path.write_text("\n".join(lines), encoding="utf-8")


def inspect() -> None:
    pk = PK_ROM.read_bytes()
    print(f"PK font: $100000-${FONT_PC + PK_FONT_BYTES - 1:06X} ({PK_FONT_BYTES}B, {N_GLYPHS}×{PK_CHAR_BYTES}B 8x16 glyphs)")
    print(f"After padding into rbshura's TL/TR/BL/BR format:")
    print(f"  $100000-${FONT_PC + JP_FONT_BYTES - 1:06X} ({JP_FONT_BYTES}B, {N_GLYPHS}×{JP_CHAR_BYTES}B 16x16 slots)")
    print(f"\nPK top tile → rbshura TL  (left 8px of top row)")
    print(f"rbshura TR  = zeros        (right 8px of top row)")
    print(f"PK bot tile → rbshura BL  (left 8px of bottom row)")
    print(f"rbshura BR  = zeros        (right 8px of bottom row)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args()

    if args.inspect:
        inspect()
        return

    pk = PK_ROM.read_bytes()
    jp = JP_ROM.read_bytes()

    out_bytes = patch_font(jp, pk)
    OUT_ROM.write_bytes(out_bytes)

    en_table_path = ROOT / "tables" / "rbshura_en.tbl"
    write_en_table(en_table_path)

    # Verify: only the font region changed (no renderer code patched — vanilla rbshura)
    expected = bytearray(jp)
    expected[FONT_PC:FONT_PC + JP_FONT_BYTES] = out_bytes[FONT_PC:FONT_PC + JP_FONT_BYTES]
    assert bytes(expected) == out_bytes, "patch corrupted bytes outside font region!"

    # Verify each padded slot has the correct TL/TR/BL/BR structure
    for n in range(N_GLYPHS):
        pk_off = FONT_PC + n * PK_CHAR_BYTES
        jp_off = FONT_PC + n * JP_CHAR_BYTES
        assert out_bytes[jp_off:jp_off + 16] == pk[pk_off:pk_off + 16], f"slot {n} TL"
        assert out_bytes[jp_off + 16:jp_off + 32] == b'\x00' * 16, f"slot {n} TR"
        assert out_bytes[jp_off + 32:jp_off + 48] == pk[pk_off + 16:pk_off + 32], f"slot {n} BL"
        assert out_bytes[jp_off + 48:jp_off + 64] == b'\x00' * 16, f"slot {n} BR"

    # Confirm renderer is back to vanilla rbshura (no code patches)
    assert out_bytes[0x05839F:0x058430] == jp[0x05839F:0x058430], "renderer is not vanilla!"

    print(f"Wrote {OUT_ROM} ({len(out_bytes)} bytes)")
    print(f"Wrote {en_table_path}")
    print(f"\nPadding: PK 8x16 glyphs in TL+BL of rbshura's 16x16 slots (vertical stack in left half).")
    print(f"Renderer: vanilla rbshura (reverted from prior broken patches).")
    print(f"\nNext: load {OUT_ROM} in Mesen2. Each Latin letter should appear")
    print(f"as a correctly-oriented 8-wide glyph in the LEFT half of its")
    print(f"16-pixel cell — top tile on top, bottom tile on bottom.")


if __name__ == "__main__":
    main()
