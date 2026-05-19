#!/usr/bin/env python3
"""Apply Peacekeepers' Latin font to rbshura — TIGHT 8-px-per-char renderer.

OPTION B (true PK-style renderer):
  Patches rbshura's renderer at PC $05839F so that each char takes a SINGLE
  tile column (1 tile top, 1 tile bottom = 8x16 effective glyph) instead of
  the original 2x2 layout (16x16). Lower stride means 32 chars per line at
  the original tilemap geometry.

Three architectural changes vs vanilla rbshura (preserve byte count via NOPs):
  1. DMA byte count: $40 (64B = 4 tiles) → $20 (32B = 2 tiles).
     One-byte literal change at $0583D8.
  2. Tilemap tail: 4 entries (TL/TR/BL/BR) → 2 entries (TL/BL).
     5B NOP at $058403-$058407 kills `STA $001542,X` + the extra `INC A`
     that was bumping the tile# for the BL entry (BL now needs tile+1 from
     INC A at $058402, not tile+2).
     5B NOP at $05840C-$058410 kills `INC A` + `STA $001582,X`.
  3. Column / tile-slot advance: ×4 → ×2 per char.
     6B NOP at $058417-$05841C kills 2 of the 4 `INC $1C4C` instructions.
     6B NOP at $058423-$058428 kills 2 of the 4 `INC $1C58` instructions.

Font layout matches PK natively (32 bytes/glyph = top tile + bottom tile).
We copy PK's font directly into rbshura's 64-byte slots: bytes 0-31 = PK
glyph (top+bottom contiguous, which is PK's native format); bytes 32-63
are zeroed for cleanliness (never DMA'd at the new $20 size).

VRAM math (unchanged): VRAM_dest = $1C58 × 8 + $4000. With $1C58 += 2 per
char and DMA = 16 words/char, char 0 → $4000-$400F, char 1 → $4010-$401F,
etc — non-overlapping, 2 tiles per char.

Tilemap math (now 1-column-per-char):
  TL = tile# $1C58 at $1540,X
  BL = tile# $1C58 + 1 at $1580,X
  X = $1C4C, $1C4C += 2 per char → next char goes 1 tile column right.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).parent
PK_ROM = ROOT / "peacekeepers.sfc"
JP_ROM = ROOT / "rbshura.sfc"
OUT_ROM = ROOT / "rbshura_pkfont.sfc"

FONT_PC = 0x100000
PK_CHAR_BYTES = 32          # PK native: 8x16 glyph = top tile + bottom tile
JP_CHAR_BYTES = 64          # rbshura slot stride
N_GLYPHS = 80               # cover PK chars $00-$4F
PK_FONT_BYTES = N_GLYPHS * PK_CHAR_BYTES
JP_FONT_BYTES = N_GLYPHS * JP_CHAR_BYTES

# Renderer patch sites (PC offsets in rbshura.sfc)
RENDERER_START = 0x05839F
RENDERER_END = 0x058430  # one past last byte of the renderer body

# Sanity: the renderer must match the vanilla bytes we disassembled.
# If this fails after a future ROM edit, the patch sites moved.
VANILLA_RENDERER_HEAD = bytes([
    0xC2, 0x30,                       # REP #$30
    0xAC, 0x22, 0x0F,                 # LDY $0F22
    0xA9, 0x80, 0x00,                 # LDA #$0080
    0x99, 0x22, 0x0E,                 # STA $0E22,Y
])

# DMA byte-count literal site
DMA_SIZE_LITERAL_PC = 0x0583D8        # byte after the LDA opcode

# Tilemap NOP sites (start_pc, length)
NOP_SITES = [
    (0x058403, 5),   # STA $001542,X + the bridging INC A
    (0x05840C, 5),   # INC A + STA $001582,X
    (0x058417, 6),   # 2× INC $1C4C
    (0x058423, 6),   # 2× INC $1C58
]


LATIN_MAP: dict[int, str] = {
    0x00: ' ',
    **{0x01 + i: chr(ord('a') + i) for i in range(26)},
    0x1B: '.', 0x1C: '"', 0x1D: ',', 0x1E: '-', 0x1F: "'",
    # 0x20 is the COLON glyph in the PK source font — two stacked dots.
    # Previously mislabeled as '!' (verified 2026-05-17 via script_editor.py).
    0x20: ':',
    **{0x21 + i: chr(ord('A') + i) for i in range(26)},
    # The PK font's punctuation block at 0x3B..0x3F is shifted by one slot
    # from what the original apply_pk_font.py charmap claimed. Confirmed by
    # rendering each slot 2026-05-19 after user reported "(=! )=( " in
    # in-game preview. Actual layout:
    #   0x3B = '?'
    #   0x3C = '!'   ← was '(' (the real exclamation, no custom glyph needed)
    #   0x3D = '('   ← was ')'
    #   0x3E = ')'   ← was '/'
    #   0x3F = '/'   ← was unmapped
    0x3B: '?', 0x3C: '!', 0x3D: '(', 0x3E: ')', 0x3F: '/',
    **{0x40 + i: chr(ord('0') + i) for i in range(10)},
    0x4A: ';',
    # 0x4B previously held a hand-drawn '!' custom glyph (workaround for the
    # mis-labeled 0x3C). Removed 2026-05-19 now that the real '!' at 0x3C is
    # correctly mapped — the slot reverts to blank in the PK source.
}

# Custom glyphs painted into otherwise-empty PK slots. Empty for now — the
# '!' custom glyph at 0x4B was removed 2026-05-19 when the punctuation
# slot mapping was corrected. Mechanism stays in `patch_font` for future
# missing-char additions.
CUSTOM_GLYPHS: dict[int, bytes] = {}

ALIASES: list[tuple[str, bytes]] = [
    ('[', bytes([0x1C])),
    (']', bytes([0x1C])),
    ('—', bytes([0x1E])),
    ('…', bytes([0x1B, 0x1B, 0x1B])),
]


def _unmapped_chars_in_en_scripts() -> list[str]:
    import re
    mapped = set(LATIN_MAP.values()) | {ch for ch, _ in ALIASES} | {' ', '\n', '\t', '\r'}
    found: dict[str, None] = {}
    for f in sorted((ROOT / "data" / "en").glob("scenario_*.txt")):
        body = f.read_text(encoding="utf-16")
        body = re.sub(r"<<\$\d+:\d+\[\$\d+\]>>", "", body)
        body = re.sub(r"\[[0-9A-Fa-f]{2}\]", "", body)
        for ch in body:
            if ch not in mapped:
                found[ch] = None
    return list(found.keys())


def patch_font(jp_rom: bytes, pk_rom: bytes) -> bytes:
    """Copy PK 32B glyphs into the first 32B of each rbshura 64B slot.
    Bytes 32-63 of each slot are zeroed (never DMA'd at the new size).
    After the bulk copy, overlay any CUSTOM_GLYPHS (e.g. '!' at 0x4B) so
    chars missing from the PK source still have a usable rendering."""
    out = bytearray(jp_rom)
    for n in range(N_GLYPHS):
        pk_off = FONT_PC + n * PK_CHAR_BYTES
        jp_off = FONT_PC + n * JP_CHAR_BYTES
        out[jp_off:jp_off + 32] = pk_rom[pk_off:pk_off + 32]
        out[jp_off + 32:jp_off + 64] = b'\x00' * 32
    for slot, glyph in CUSTOM_GLYPHS.items():
        if len(glyph) != 32:
            raise SystemExit(
                f"CUSTOM_GLYPHS[0x{slot:02X}] must be exactly 32 bytes "
                f"(got {len(glyph)})"
            )
        jp_off = FONT_PC + slot * JP_CHAR_BYTES
        out[jp_off:jp_off + 32] = glyph
    return bytes(out)


def patch_renderer(rom: bytes) -> bytes:
    """Apply the tight-8 renderer patch in-place (byte-count preserving)."""
    # Verify the renderer head matches vanilla — guards against patching
    # an already-patched ROM or a different ROM.
    if rom[RENDERER_START:RENDERER_START + len(VANILLA_RENDERER_HEAD)] != VANILLA_RENDERER_HEAD:
        raise SystemExit(
            f"Renderer head at ${RENDERER_START:06X} does not match vanilla. "
            f"Aborting to avoid double-patching."
        )

    out = bytearray(rom)

    # 1. DMA byte count $40 → $20.
    assert out[DMA_SIZE_LITERAL_PC - 1] == 0xA9, "expected LDA #imm at DMA size site"
    assert out[DMA_SIZE_LITERAL_PC] == 0x40, "expected $40 at DMA size literal"
    assert out[DMA_SIZE_LITERAL_PC + 1] == 0x00, "expected $00 hi byte at DMA size literal"
    out[DMA_SIZE_LITERAL_PC] = 0x20

    # 2-3. NOP out the deleted bytes (kill TR/BR tilemap writes + extra advances).
    for start, length in NOP_SITES:
        out[start:start + length] = b'\xEA' * length

    return bytes(out)


def write_en_table(path: Path) -> None:
    lines = [
        "; Rushing Beat Shura — ENGLISH encoding table (PK font 8x16 with the",
        "; tight-8 renderer patch at $05839F — chars occupy a single tile column).",
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
    lines.append("; --- Aliases (chars without dedicated glyphs piggyback on existing slots) ---")
    for ch, byte_seq in ALIASES:
        hex_str = ''.join(f"{b:02X}" for b in byte_seq)
        lines.append(f"{hex_str}={ch}")
    lines.append("")
    lines.append("; --- Unmapped script chars → $00 (space) per user directive 2026-05-16 ---")
    unmapped = _unmapped_chars_in_en_scripts()
    for ch in unmapped:
        lines.append(f"00={ch}")
    lines.append("")
    lines.append("**=[**]")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  → table has {len(LATIN_MAP)} primary + {len(ALIASES)} aliases + {len(unmapped)} unmapped→space")


def inspect() -> None:
    pk = PK_ROM.read_bytes()
    print(f"PK font: $100000-${FONT_PC + PK_FONT_BYTES - 1:06X}")
    print(f"  ({PK_FONT_BYTES}B, {N_GLYPHS}×{PK_CHAR_BYTES}B 8x16 glyphs)")
    print(f"\nTight-8 layout (matches PK natively):")
    print(f"  bytes  0-15 = PK top tile (DMA'd as char's top row tile)")
    print(f"  bytes 16-31 = PK bottom tile (DMA'd as char's bottom row tile)")
    print(f"  bytes 32-63 = ZEROED (never DMA'd, slot stride still 64)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args()

    if args.inspect:
        inspect()
        return

    pk = PK_ROM.read_bytes()
    jp = JP_ROM.read_bytes()

    # 1. Font swap.
    out_bytes = patch_font(jp, pk)
    # 2. Renderer patch (tight-8).
    out_bytes = patch_renderer(out_bytes)
    OUT_ROM.write_bytes(out_bytes)

    en_table_path = ROOT / "tables" / "rbshura_en.tbl"
    write_en_table(en_table_path)

    # Sanity: only font region + renderer slot changed.
    expected = bytearray(jp)
    expected[FONT_PC:FONT_PC + JP_FONT_BYTES] = out_bytes[FONT_PC:FONT_PC + JP_FONT_BYTES]
    expected[RENDERER_START:RENDERER_END] = out_bytes[RENDERER_START:RENDERER_END]
    assert bytes(expected) == out_bytes, "patch corrupted bytes outside font + renderer regions!"

    # Verify font padding. Slots in CUSTOM_GLYPHS are intentionally
    # different from the PK source (they hold our hand-drawn glyphs);
    # check those against the custom bytes instead.
    for n in range(N_GLYPHS):
        pk_off = FONT_PC + n * PK_CHAR_BYTES
        jp_off = FONT_PC + n * JP_CHAR_BYTES
        if n in CUSTOM_GLYPHS:
            assert out_bytes[jp_off:jp_off + 32] == CUSTOM_GLYPHS[n], f"slot {n} custom glyph mismatch"
        else:
            assert out_bytes[jp_off:jp_off + 32] == pk[pk_off:pk_off + 32], f"slot {n} top+bot"
        assert out_bytes[jp_off + 32:jp_off + 64] == b'\x00' * 32, f"slot {n} pad zeros"

    # Verify renderer patches landed.
    assert out_bytes[DMA_SIZE_LITERAL_PC] == 0x20, "DMA size patch missing"
    for start, length in NOP_SITES:
        assert out_bytes[start:start + length] == b'\xEA' * length, f"NOP site ${start:06X} missing"

    print(f"Wrote {OUT_ROM} ({len(out_bytes)} bytes)")
    print(f"Wrote {en_table_path}")
    print()
    print("Renderer patches applied:")
    print(f"  ${DMA_SIZE_LITERAL_PC:06X}: DMA size $40 → $20 (32 bytes / 2 tiles per char)")
    for start, length in NOP_SITES:
        print(f"  ${start:06X}: NOPed {length} bytes")
    print()
    print("Expected behavior in emulator:")
    print(f"  Each Latin char now takes a single tile column (8 px wide).")
    print(f"  Top tile in row 0, bottom tile in row 1, same column.")
    print(f"  32 chars per line instead of 16.")


if __name__ == "__main__":
    main()
