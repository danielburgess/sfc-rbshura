#!/usr/bin/env python3
"""Render specific glyphs from jp_font_p0.bin / jp_font_p1.bin and save as PPM.

Used to verify what glyph is at each byte position in the actual ROM font,
so we can audit tables/rbshura.tbl against ground truth.

SNES 2bpp 8x8 tile = 16 bytes; 16x16 char = 4 tiles in TL/TR/BL/BR layout
(per renderer reverse-engineering in project_peacekeepers_diff memory).
"""
from __future__ import annotations
import sys
from pathlib import Path

PALETTE = [(0, 0, 64), (255, 255, 255), (180, 180, 180), (100, 100, 100)]


def render_tile_2bpp(data: bytes) -> list[list[int]]:
    """Render an 8x8 2bpp SNES tile to a 2D pixel-index array."""
    rows = []
    for y in range(8):
        bp0 = data[y * 2]
        bp1 = data[y * 2 + 1]
        row = []
        for x in range(8):
            shift = 7 - x
            c = ((bp0 >> shift) & 1) | (((bp1 >> shift) & 1) << 1)
            row.append(c)
        rows.append(row)
    return rows


def render_glyph_16x16(glyph_bytes: bytes) -> list[list[int]]:
    """Render a 16x16 glyph from 64 bytes in TL/TR/BL/BR order."""
    tl = render_tile_2bpp(glyph_bytes[0:16])
    tr = render_tile_2bpp(glyph_bytes[16:32])
    bl = render_tile_2bpp(glyph_bytes[32:48])
    br = render_tile_2bpp(glyph_bytes[48:64])
    pix = []
    for y in range(8):
        pix.append(tl[y] + tr[y])
    for y in range(8):
        pix.append(bl[y] + br[y])
    return pix


def render_grid(font: bytes, positions: list[int], out_path: Path, cols: int = 8, scale: int = 4) -> None:
    """Render selected glyph positions in a grid with hex labels above each."""
    label_h = 8  # one row of label text
    cell_w = 16 * scale
    cell_h = 16 * scale + label_h
    rows = (len(positions) + cols - 1) // cols
    img_w = cols * cell_w
    img_h = rows * cell_h
    img = [[(0, 0, 0)] * img_w for _ in range(img_h)]

    # 5x7 minimal hex digits
    DIGITS = {
        "0": ["111", "101", "101", "101", "111"],
        "1": ["010", "110", "010", "010", "111"],
        "2": ["111", "001", "111", "100", "111"],
        "3": ["111", "001", "111", "001", "111"],
        "4": ["101", "101", "111", "001", "001"],
        "5": ["111", "100", "111", "001", "111"],
        "6": ["111", "100", "111", "101", "111"],
        "7": ["111", "001", "010", "010", "010"],
        "8": ["111", "101", "111", "101", "111"],
        "9": ["111", "101", "111", "001", "111"],
        "A": ["010", "101", "111", "101", "101"],
        "B": ["110", "101", "110", "101", "110"],
        "C": ["011", "100", "100", "100", "011"],
        "D": ["110", "101", "101", "101", "110"],
        "E": ["111", "100", "110", "100", "111"],
        "F": ["111", "100", "110", "100", "100"],
    }

    for i, pos in enumerate(positions):
        gx = (i % cols) * cell_w
        gy = (i // cols) * cell_h
        # Draw label "XX" at top of cell
        label = f"{pos:02X}" if pos < 0x100 else f"{pos:04X}"
        for li, ch in enumerate(label):
            glyph = DIGITS.get(ch.upper(), ["000"] * 5)
            for ry, row in enumerate(glyph):
                for cx, c in enumerate(row):
                    if c == "1":
                        img[gy + ry][gx + li * 4 + cx] = (255, 255, 0)
        # Draw glyph below label
        glyph_off = (pos & 0xFF) * 64 if pos < 0x100 else (pos & 0xFF) * 64
        glyph_bytes = font[glyph_off:glyph_off + 64]
        if len(glyph_bytes) < 64:
            continue
        pixels = render_glyph_16x16(glyph_bytes)
        for py in range(16):
            for px in range(16):
                color = PALETTE[pixels[py][px]]
                for sy in range(scale):
                    for sx in range(scale):
                        oy = gy + label_h + py * scale + sy
                        ox = gx + px * scale + sx
                        img[oy][ox] = color

    # Write PPM (P6 binary)
    with open(out_path, "wb") as f:
        f.write(f"P6\n{img_w} {img_h}\n255\n".encode())
        for row in img:
            for r, g, b in row:
                f.write(bytes([r, g, b]))


def main():
    p0 = Path("fonts/jp_font_p0.bin").read_bytes()
    p1 = Path("fonts/jp_font_p1.bin").read_bytes()

    # Critical positions to verify in p0:
    # $10-$1F (hiragana row 2, where と should be at $13)
    # $40-$4F (hiragana dakuten, where ど vs ば)
    # $70-$7F (katakana row, where ヲ should be at $7C)
    # $80-$9F (katakana dakuten, where ズ vs ゼ)
    # Full p0 — kana, digits, Latin, punct, single-byte kanji
    p0_positions = list(range(0x00, 0xF8))
    render_grid(p0, p0_positions, Path("fonts/verify_p0_full.ppm"), cols=16)

    # Full p1 — all multi-byte kanji
    p1_positions = list(range(0x00, 0xF8))
    render_grid(p1, p1_positions, Path("fonts/verify_p1_full.ppm"), cols=16)

    print(f"Wrote fonts/verify_p0.ppm and fonts/verify_p1.ppm")


if __name__ == "__main__":
    main()
