#!/usr/bin/env python3
"""Regenerate fonts/rbshura_en.bin + tables/rbshura_en.tbl.

The actual ROM insertion happens inside retrotool (project.toml ships
fonts/rbshura_en.bin as a `kind="bin"` section at $100000 and applies
the tight-8 renderer patch via `kind="asar"` on patches/tight_renderer.asm).
This script just rebuilds the source artifacts:

  fonts/rbshura_en.bin    Peacekeepers' 8x16 Latin font (80 × 64-byte
                          slots, bytes 0-31 = PK top+bottom tile, bytes
                          32-63 = zero pad). CUSTOM_GLYPHS (e.g. '*' at
                          0x4B) overlay specific slots. Sourced from
                          peacekeepers.sfc.
  tables/rbshura_en.tbl   Char ↔ byte map retrotool's encoder consumes
                          when packing data/en/scenario_*.txt. Built from
                          LATIN_MAP + ALIASES below; unmapped chars in
                          EN scripts fall through to $00 (space).

Re-run after editing LATIN_MAP, ALIASES, or CUSTOM_GLYPHS.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _paths import ROOT, PK_ROM, FONTS, TABLES, DATA_EN

FONT_BIN = FONTS / "rbshura_en.bin"

PK_CHAR_BYTES = 32          # PK native: 8x16 glyph = top tile + bottom tile
JP_CHAR_BYTES = 64          # rbshura slot stride (only first 32B DMA'd
                            # after the tight-8 renderer patch)
N_GLYPHS = 80               # cover PK chars $00-$4F
PK_FONT_BYTES = N_GLYPHS * PK_CHAR_BYTES
FONT_BIN_BYTES = N_GLYPHS * JP_CHAR_BYTES   # 5120 — matches retrotool bin section


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
    # 0x4B holds a hand-drawn asterisk (added 2026-05-19). PK font ships no
    # '*' glyph; without this, translations using *kahh* / *gasp* style
    # emphasis rendered as spaces.
    0x4B: '*',
}

# Custom glyphs painted into otherwise-empty PK slots. Each entry maps
# slot index → 32 bytes (16 B top tile + 16 B bottom tile, standard SNES
# 2bpp row-interleaved bp0/bp1).
CUSTOM_GLYPHS: dict[int, bytes] = {
    # 0x4B: '*' — 6-point asterisk shape, fits in the upper-mid portion of
    # an 8x16 glyph (rows 1-5 of top tile, bottom tile blank).
    #
    #   row 0: ........
    #   row 1: ..#..#..    diagonals upper
    #   row 2: ...##...    center bar start
    #   row 3: .######.    horizontal cross
    #   row 4: ...##...    center bar end
    #   row 5: ..#..#..    diagonals lower
    #   row 6: ........
    #   row 7: ........
    #
    # Encoded as value-3 pixels (both bitplanes set), matching the bright
    # stroke color used by the rest of the PK font's main glyph strokes.
    0x4B: bytes.fromhex(
        # Top tile — bp0 / bp1 per row, both identical for value-3 pixels.
        "0000"  # r0
        "2424"  # r1
        "1818"  # r2
        "7e7e"  # r3
        "1818"  # r4
        "2424"  # r5
        "0000"  # r6
        "0000"  # r7
        # Bottom tile — all blank (asterisk only uses the upper portion).
        "0000" "0000" "0000" "0000"
        "0000" "0000" "0000" "0000"
    ),
}

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
    for f in sorted(DATA_EN.glob("scenario_*.txt")):
        body = f.read_text(encoding="utf-16")
        body = re.sub(r"<<\$\d+:\d+\[\$\d+\]>>", "", body)
        body = re.sub(r"\[[0-9A-Fa-f]{2}\]", "", body)
        for ch in body:
            if ch not in mapped:
                found[ch] = None
    # Sorted so the generated .tbl tail is deterministic regardless of file
    # traversal order (avoids spurious diffs when EN scripts change). The
    # unmapped→$00 (space) fallback itself is intentional per user directive
    # 2026-05-16; this only stabilizes the ordering.
    return sorted(found.keys())


def build_font_bin(pk_rom: bytes) -> bytes:
    """Produce the 5120B font blob retrotool inserts at $100000.

    Layout: 80 × 64B slots. Bytes 0-31 of each slot = PK 32B glyph
    (top tile + bottom tile, native PK ordering). Bytes 32-63 = zero
    pad (never DMA'd at the post-patch $20 size). CUSTOM_GLYPHS overlay
    specific slots after the bulk PK copy.
    """
    out = bytearray(FONT_BIN_BYTES)
    for n in range(N_GLYPHS):
        pk_off = 0x100000 + n * PK_CHAR_BYTES
        jp_off = n * JP_CHAR_BYTES
        out[jp_off:jp_off + 32] = pk_rom[pk_off:pk_off + 32]
        # bytes 32-63 already zero from bytearray()
    for slot, glyph in CUSTOM_GLYPHS.items():
        if len(glyph) != 32:
            raise SystemExit(
                f"CUSTOM_GLYPHS[0x{slot:02X}] must be exactly 32 bytes "
                f"(got {len(glyph)})"
            )
        jp_off = slot * JP_CHAR_BYTES
        out[jp_off:jp_off + 32] = glyph
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


def main() -> None:
    argparse.ArgumentParser().parse_args()  # accept --help; no flags

    if not PK_ROM.exists():
        raise SystemExit(
            f"PK reference ROM not found: {PK_ROM}\n"
            "Expected the Peacekeepers ROM at roms/peacekeepers.sfc."
        )
    pk = PK_ROM.read_bytes()
    font_bin = build_font_bin(pk)

    # Sanity: per-slot bytes match the PK source (or the CUSTOM_GLYPHS
    # overlay), and the pad region is zero.
    for n in range(N_GLYPHS):
        pk_off = 0x100000 + n * PK_CHAR_BYTES
        jp_off = n * JP_CHAR_BYTES
        if n in CUSTOM_GLYPHS:
            assert font_bin[jp_off:jp_off + 32] == CUSTOM_GLYPHS[n], f"slot {n} custom glyph mismatch"
        else:
            assert font_bin[jp_off:jp_off + 32] == pk[pk_off:pk_off + 32], f"slot {n} top+bot"
        assert font_bin[jp_off + 32:jp_off + 64] == b'\x00' * 32, f"slot {n} pad zeros"

    FONT_BIN.parent.mkdir(parents=True, exist_ok=True)
    FONT_BIN.write_bytes(font_bin)
    print(f"Wrote {FONT_BIN.relative_to(ROOT)} ({len(font_bin)} bytes, "
          f"{N_GLYPHS} slots, {len(CUSTOM_GLYPHS)} custom glyphs)")

    en_table_path = TABLES / "rbshura_en.tbl"
    write_en_table(en_table_path)
    print(f"Wrote {en_table_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
