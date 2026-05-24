#!/usr/bin/env python3
"""Decode the static-narration screens (ending epilogues, etc.) that the
full-width renderer at $05:F18E draws by DMAing glyph tiles from the kanji/kana
font in bank $D0.

These screens live in the SAME pointer table as the intro narrative
($1F:C57F), at the indices dump_intro.py flagged as "non-text gibberish"
(idx 1-19). They are NOT character-encoded text — each screen is a glyph
SOURCE STREAM:

    [initial_VRAM_dest : 2]  [glyph_src : 2] x N  [FF FF]

The renderer reads the dest once, then streams one `glyph_src` per glyph,
auto-advancing the VRAM destination ($02 += $10, +$100 on a tile-row
boundary). Each `glyph_src` is a byte offset into bank $D0:

  * src >= $4000 -> KANJI font (file $104000 = $D0:4000), 64 B/glyph:
        index = (src - $4000) / 64  ->  tables/intro_kanji.tbl
  * src <  $4000 -> KANA/half font (file $100000 = $D0:0000), 64 B/glyph:
        index = src / 64            ->  tables/rbshura_jp.tbl single-byte

NOTE: the $D0:0000 region (file $100000) is where the EN PK Latin font now
lives (we overwrote it). That's why katakana in these screens render as
garbage in the EN build while kanji (untouched $D0:4000+) still render.

The glyph-stream order IS reading order (the renderer fills sequential VRAM
char slots that the screen's static tilemap displays in order).

Usage:
    python tools/dump_narration.py [--rom rbshura.sfc]
    python tools/dump_narration.py --raw     # also show src offsets per glyph

For RE-INSERTION (English): rebuild a screen's stream as
    [initial_dest] + [pk_index*64 for each EN char] + [FFFF]
where pk_index is the PK-font slot for each Latin glyph (src stays < $4000,
i.e. the $D0:0000 region = our PK font). See tables/rbshura_en.tbl for the
EN charmap. Layout/line-count is fixed by the screen's static tilemap, so
match the original glyph count per line where possible.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PTR_TABLE = 0x1FC57F          # intro/narration pointer table (file offset)
BANK_1F = 0x1F0000
FONT_KANJI_BASE = 0x4000      # $D0:4000 region (kanji)
GLYPH_BYTES = 64              # full-width glyph = 2 tiles = 64 B


def load_tables():
    sys.path.insert(0, str(ROOT / "tools"))
    import dump_intro as di
    single, fa = di.load_jp_table(ROOT / "tables/rbshura_jp.tbl")
    kanji = di.load_kanji_table(ROOT / "tables/intro_kanji.tbl")
    return single, kanji


def glyph_for(src: int, single, kanji) -> tuple[str, str]:
    if src >= FONT_KANJI_BASE:
        idx = (src - FONT_KANJI_BASE) // GLYPH_BYTES
        return kanji.get(idx, f"<K{idx:02X}>"), f"kanji[{idx:02X}]"
    idx = src // GLYPH_BYTES
    return single.get(idx, f"<k{idx:02X}>"), f"kana[{idx:02X}]"


def walk_ptr_table(rom: bytes) -> list[tuple[int, list[int]]]:
    seen: dict[int, list[int]] = {}
    for i in range(80):
        v = rom[PTR_TABLE + i * 2] | (rom[PTR_TABLE + i * 2 + 1] << 8)
        if not (0xC500 <= v <= 0xD400):
            break
        seen.setdefault(v, []).append(i)
    return sorted(seen.items())


def decode_screen(rom: bytes, ptr: int):
    """Returns (initial_dest, [(src, glyph, tag), ...], byte_len)."""
    fo = BANK_1F | ptr
    dest = rom[fo] | (rom[fo + 1] << 8)
    p = fo + 2
    glyphs = []
    cap = fo + 4096
    while p + 1 < cap:
        src = rom[p] | (rom[p + 1] << 8)
        if src == 0xFFFF:
            p += 2
            break
        glyphs.append(src)
        p += 2
    return dest, glyphs, (p - fo)


PAD_SRC = 0xCE * GLYPH_BYTES   # $3380 — the blank/padding glyph (kana idx $CE)


def render_lines(glyphs, single, kanji) -> list[str]:
    """Collapse runs of the $CE padding glyph into line breaks; return lines."""
    lines, cur = [], []
    run = 0
    for s in glyphs:
        if s == PAD_SRC:
            run += 1
            continue
        if run >= 1 and cur:        # padding run = phrase/line boundary
            lines.append("".join(cur)); cur = []
        run = 0
        cur.append(glyph_for(s, single, kanji)[0])
    if cur:
        lines.append("".join(cur))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", default="rbshura.sfc")
    ap.add_argument("--raw", action="store_true", help="show per-glyph src offsets")
    ap.add_argument("--write", action="store_true",
                    help="write data/jp/narration.txt (+ seed data/en/narration.txt)")
    args = ap.parse_args(argv)
    rom = (ROOT / args.rom).read_bytes()
    single, kanji = load_tables()

    out = ["; Static-narration screens (character endings) — decoded by",
           "; tools/dump_narration.py. Each screen is a glyph-source stream",
           "; in the $1F:C57F pointer table: [dest][src...][FFFF].",
           "; $CE padding runs shown as line breaks. To translate: replace the",
           "; JP under each <<...>> header with English; re-insertion encodes",
           "; each char as PK-font src = pk_index*64 (see tools/encode_narration).",
           ""]
    for ptr, indices in walk_ptr_table(rom):
        if ptr == 0xC8F1 or ptr >= 0xCD35:
            continue   # idx 0 / idx 20+ are FE-kanji intro narrative text, handled elsewhere
        dest, glyphs, blen = decode_screen(rom, ptr)
        lines = render_lines(glyphs, single, kanji)
        rng = f"{indices[0]}" if len(indices) == 1 else f"{indices[0]}-{indices[-1]}"
        hdr = f"<<idx={rng} ptr=${ptr:04X} dest=${dest:04X} glyphs={len(glyphs)}>>"
        print(f"=== $1F:{ptr:04X} (idx {rng}) dest=${dest:04X} {len(glyphs)} glyphs ===")
        for ln in lines:
            print("   " + ln)
        print()
        out.append(hdr)
        out.extend(lines)
        out.append("")
        if args.raw:
            for s in glyphs:
                g, tag = glyph_for(s, single, kanji)
                print(f"    src=${s:04X} {tag} -> {g}")

    if args.write:
        body = "\n".join(out)
        jp = ROOT / "data/jp/narration.txt"
        en = ROOT / "data/en/narration.txt"
        jp.write_bytes(b"\xff\xfe" + body.encode("utf-16-le"))
        print(f"wrote {jp}")
        if not en.exists():
            en.write_bytes(b"\xff\xfe" + body.encode("utf-16-le"))
            print(f"wrote {en} (translation seed)")
        else:
            print(f"NOT overwriting {en} (already exists)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
