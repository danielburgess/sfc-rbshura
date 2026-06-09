#!/usr/bin/env python3
"""Generate the Brazilian-Portuguese accented glyphs (Éáéíóúâêôàãõç).

The PK Latin font (roms/peacekeepers.sfc @ $100000, 32 B/glyph = 8x16) has no
accented characters. This tool builds them by compositing diacritics onto the
PK base letterforms, so the accents share the exact stroke style of the rest of
the font. Output:

  fonts/pt_accents.bin   13 glyphs x 32 B (top tile + bottom tile, SNES 2bpp),
                         in the slot order 0x4C..0x58 used by
                         tables/rbshura_br_pt.tbl.

The PK lowercase letters leave rows 0-3 blank above the x-height, which is where
the diacritics land; 'i' has its tittle removed before the acute is added;
uppercase 'E' is shifted down two rows to make room for the acute (É).

NOTE: this only produces the glyph *bitmaps*. Wiring them into the build means
extending the font past its current 80-slot / 5120 B region at $100000 — slots
0x50..0x58 fall beyond it, where live game graphics sit — so the font must be
relocated to expansion space and the renderers' font-base ($D0) repointed first.
See readme "Status" / project.toml.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PK_ROM = ROOT / "roms" / "peacekeepers.sfc"
OUT_BIN = ROOT / "fonts" / "pt_accents.bin"
BASE_FONT = ROOT / "fonts" / "rbshura_en.bin"          # 80-slot EN font ($100000)
EXT_FONT = ROOT / "fonts" / "rbshura_font_ext.bin"     # 89-slot relocated font ($E2)

PK_FONT_BASE = 0x100000      # PK font at file $100000 ($D0:0000)
PK_CHAR_BYTES = 32           # 8x16 glyph = top tile (16 B) + bottom tile (16 B)
SLOT_STRIDE = 64             # font slot stride (32 B glyph + 32 B zero pad)
FIRST_ACCENT_SLOT = 0x4C     # accents occupy slots 0x4C..0x58 (13 glyphs)
SPACE_SLOT = 0x20            # PK font has a COLON glyph here — blanked to a space
COLON_SLOT = 0x59            # relocated ':' glyph (just past the accents)

# PK base-glyph slot indices (from tables/rbshura_en.tbl).
SLOT = {
    'a': 0x01, 'c': 0x03, 'e': 0x05, 'i': 0x09, 'o': 0x0F, 'u': 0x15,
    'E': 0x25,
}

# --- Diacritic shapes (8 px wide), drawn in stroke value 3 ('#') ------------
# Lowercase accents occupy rows 1-3 (blank area above the x-height at row 4).
ACUTE = ['....##..', '...##...', '..##....']
GRAVE = ['..##....', '...##...', '....##..']
CIRCUMFLEX = ['...##...', '..#..#..', '.#....#.']
TILDE = ['........', '..##.##.', '.##.##..']
# Cedilla hangs below the letter (rows 14-15).
CEDILLA = ['...##...', '..##....']
# Uppercase acute for É: tight 2-row mark at rows 0-1 (base shifted down 2).
ACUTE_UPPER = ['....##..', '...##...']


def decode_glyph(b: bytes) -> list[list[int]]:
    """32 B PK glyph -> 8x16 grid (16 rows x 8 cols) of 2bpp values 0-3."""
    grid = []
    for tile in (b[0:16], b[16:32]):
        for r in range(8):
            bp0, bp1 = tile[2 * r], tile[2 * r + 1]
            grid.append([((bp0 >> (7 - x)) & 1) | (((bp1 >> (7 - x)) & 1) << 1)
                         for x in range(8)])
    return grid


def encode_glyph(grid: list[list[int]]) -> bytes:
    """8x16 grid -> 32 B (top tile rows 0-7, bottom tile rows 8-15)."""
    out = bytearray()
    for tile_rows in (grid[0:8], grid[8:16]):
        for row in tile_rows:
            bp0 = bp1 = 0
            for x, v in enumerate(row):
                if v & 1:
                    bp0 |= 0x80 >> x
                if v & 2:
                    bp1 |= 0x80 >> x
            out += bytes((bp0, bp1))
    return bytes(out)


def overlay(grid, shape, start_row, value=3):
    """Paint `shape` (list of '#'/'.' rows) into grid at start_row."""
    for i, srow in enumerate(shape):
        r = start_row + i
        if 0 <= r < 16:
            for c, ch in enumerate(srow):
                if ch == '#' and c < 8:
                    grid[r][c] = value


def clear_rows(grid, rows):
    for r in rows:
        grid[r] = [0] * 8


def shift_down(grid, n):
    """Shift the whole glyph down by n rows (top rows become blank)."""
    blank = [[0] * 8 for _ in range(n)]
    return blank + grid[:16 - n]


def build_glyphs(pk: bytes) -> "list[tuple[str, str, list[list[int]]]]":
    def base(letter):
        off = PK_FONT_BASE + SLOT[letter] * PK_CHAR_BYTES
        return decode_glyph(pk[off:off + PK_CHAR_BYTES])

    glyphs = []

    def lower(ch, letter, shape, start=1):
        g = base(letter)
        overlay(g, shape, start)
        glyphs.append((ch, letter, g))

    lower('á', 'a', ACUTE)
    lower('é', 'e', ACUTE)
    # í: drop the tittle (rows 0-3) before adding the acute.
    gi = base('i')
    clear_rows(gi, [0, 1, 2, 3])
    overlay(gi, ACUTE, 1)
    glyphs.append(('í', 'i', gi))
    lower('ó', 'o', ACUTE)
    lower('ú', 'u', ACUTE)
    lower('â', 'a', CIRCUMFLEX)
    lower('ê', 'e', CIRCUMFLEX)
    lower('ô', 'o', CIRCUMFLEX)
    lower('à', 'a', GRAVE)
    lower('ã', 'a', TILDE)
    lower('õ', 'o', TILDE)
    # ç: cedilla hook below the 'c'.
    gc = base('c')
    overlay(gc, CEDILLA, 14)
    glyphs.append(('ç', 'c', gc))
    # É: shift the capital down 2 rows, acute at the top.
    ge = shift_down(base('E'), 2)
    overlay(ge, ACUTE_UPPER, 0)
    glyphs.append(('É', 'E', ge))

    return glyphs


def ascii_preview(glyphs) -> str:
    lines = []
    for ch, letter, g in glyphs:
        lines.append(f"--- 0x{0x4C + glyphs.index((ch, letter, g)):02X} '{ch}' (base '{letter}') ---")
        for row in g:
            lines.append(''.join('#' if v == 3 else ('+' if v else '.') for v in row))
    return '\n'.join(lines)


def main() -> None:
    if not PK_ROM.exists():
        sys.exit(f"PK reference ROM not found: {PK_ROM}")
    pk = PK_ROM.read_bytes()
    glyphs = build_glyphs(pk)
    assert len(glyphs) == 13, f"expected 13 glyphs, got {len(glyphs)}"

    encoded = [encode_glyph(g) for _, _, g in glyphs]   # 13 x 32 B
    blob = b''.join(encoded)
    OUT_BIN.parent.mkdir(parents=True, exist_ok=True)
    OUT_BIN.write_bytes(blob)

    # Build the relocated, EXTENDED font ($E2): the committed 80-slot EN font
    # with the accent glyphs spliced into slots 0x4C..0x58 (32 B glyph + 32 B
    # pad per slot). slots 0x4C..0x4F overwrite the EN font's blank tail slots;
    # 0x50..0x58 are new. This is the font project.toml loads at $E2:0000.
    if not BASE_FONT.exists():
        sys.exit(f"base font not found: {BASE_FONT} (run tools/apply_pk_font.py first)")
    base = BASE_FONT.read_bytes()
    n_slots = max(FIRST_ACCENT_SLOT + len(glyphs), COLON_SLOT + 1)   # 0x5A = 90
    ext = bytearray(n_slots * SLOT_STRIDE)
    ext[:len(base)] = base
    for i, g32 in enumerate(encoded):
        off = (FIRST_ACCENT_SLOT + i) * SLOT_STRIDE
        ext[off:off + 32] = g32                          # glyph; pad stays zero
    # The PK font ships a COLON glyph at slot 0x20, but the engine treats 0x20 as
    # a space — so blank slot 0x20 and relocate the ':' glyph to COLON_SLOT.
    # tables/rbshura_br_pt.tbl maps 0x20 -> space and COLON_SLOT -> ':'.
    pk_colon = pk[PK_FONT_BASE + SPACE_SLOT * PK_CHAR_BYTES:
                  PK_FONT_BASE + SPACE_SLOT * PK_CHAR_BYTES + 32]
    ext[SPACE_SLOT * SLOT_STRIDE:SPACE_SLOT * SLOT_STRIDE + 32] = b'\x00' * 32
    ext[COLON_SLOT * SLOT_STRIDE:COLON_SLOT * SLOT_STRIDE + 32] = pk_colon
    EXT_FONT.write_bytes(ext)

    if '--preview' in sys.argv:
        print(ascii_preview(glyphs))
    chars = ''.join(ch for ch, _, _ in glyphs)
    print(f"Wrote {OUT_BIN.relative_to(ROOT)} ({len(blob)} bytes, "
          f"{len(glyphs)} glyphs: {chars}) for slots 0x4C..0x58")
    print(f"Wrote {EXT_FONT.relative_to(ROOT)} ({len(ext)} bytes, {n_slots} slots) "
          f"— relocated EN+PT font for $E2:0000 (0x20=space, 0x{COLON_SLOT:02X}=':')")


if __name__ == "__main__":
    main()
