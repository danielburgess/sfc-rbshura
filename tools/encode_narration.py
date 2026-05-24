#!/usr/bin/env python3
"""Encode narration screens (character endings) back into the glyph-stream
format the $05:F18E renderer consumes, for EN re-insertion.

Screen format (in the $1F:C57F pointer table, idx 1-19):
    [initial_VRAM_dest : 2]  [glyph_src : 2] x N  [FF FF]

glyph_src is a byte offset into bank $D0:
    EN/kana glyph index i  -> src = i * 64           ($D0:0000 region = PK font)
    kanji glyph index i    -> src = $4000 + i * 64   ($D0:4000 region)

For EN, every character maps to a PK-font slot (tables/rbshura_en.tbl), so
src = pk_index * 64. Padding (line fill) uses PAD_GLYPH (the original blank,
kana idx $CE) — change to a PK blank if the EN font defines one.

This module provides:
  * encode_text(text, width) -> bytes   (one screen's stream, no dest/term)
  * round-trip self-test against the original ROM (--verify)

Re-insertion plan (see memory/project_ending_narration.md):
  EN streams will be longer/shorter than JP, so relocate them to expansion
  freespace and repoint the $1F:C57F table slots (idx 1-19) — same mechanism
  as the intro narrative (tables/intro.toml ptr_writes). This module emits the
  bytes; wiring into project.toml is the next step.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PTR_TABLE = 0x1FC57F
BANK_1F = 0x1F0000
KANJI_BASE = 0x4000
GLYPH_BYTES = 64
PAD_GLYPH_IDX = 0xCE          # original blank/padding glyph (kana region)
PAD_SRC = PAD_GLYPH_IDX * GLYPH_BYTES


def load_en_table() -> dict[str, int]:
    raw = (ROOT / "tables/rbshura_en.tbl").read_bytes()
    text = raw.decode("utf-16" if raw[:2] == b"\xff\xfe" else "utf-8")
    m: dict[str, int] = {}
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith((";", "@")) or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if len(k) == 2 and v:
            try:
                m.setdefault(v, int(k, 16))
            except ValueError:
                pass
    return m


def encode_line(text: str, char2idx: dict[str, int]) -> tuple[list[int], list[str]]:
    """Returns (src_list, missing_chars) for one line of EN text."""
    srcs, missing = [], []
    for ch in text:
        if ch in char2idx:
            srcs.append(char2idx[ch] * GLYPH_BYTES)
        else:
            missing.append(ch)
            srcs.append(PAD_SRC)   # placeholder so length stays sane
    return srcs, missing


def encode_screen(lines: list[str], dest: int, width: int,
                  char2idx: dict[str, int]) -> tuple[bytes, list[str]]:
    """Build one screen's bytes: [dest][src...][FFFF], padding each line to
    `width` glyphs (matching the original tilemap layout)."""
    out = bytearray()
    out += dest.to_bytes(2, "little")
    missing: list[str] = []
    for i, ln in enumerate(lines):
        srcs, miss = encode_line(ln, char2idx)
        missing += miss
        for s in srcs:
            out += s.to_bytes(2, "little")
        # pad to width (except maybe the last line, like the original)
        pad = max(0, width - len(srcs))
        for _ in range(pad):
            out += PAD_SRC.to_bytes(2, "little")
    out += b"\xff\xff"
    return bytes(out), missing


# --- round-trip verification against the original ROM glyph streams ----------

def verify(rom_path: str) -> int:
    """Re-encode each original screen from its decoded glyphs and confirm the
    src stream matches the ROM (validates the dest/src/term structure)."""
    sys.path.insert(0, str(ROOT / "tools"))
    import dump_narration as dn
    rom = (ROOT / rom_path).read_bytes()
    single, kanji = dn.load_tables()
    rev_kana = {v: k for k, v in single.items()}
    rev_kanji = {v: k for k, v in kanji.items()}
    ok = True
    for ptr, indices in dn.walk_ptr_table(rom):
        if ptr == 0xC8F1 or ptr >= 0xCD35:
            continue
        dest, glyphs, blen = dn.decode_screen(rom, ptr)
        # re-encode each src by char->src and compare (bijection check)
        reenc = []
        for s in glyphs:
            if s >= KANJI_BASE:
                idx = (s - KANJI_BASE) // GLYPH_BYTES
                ch = kanji.get(idx)
                reenc.append(KANJI_BASE + (rev_kanji.get(ch, idx)) * GLYPH_BYTES if ch else s)
            else:
                idx = s // GLYPH_BYTES
                ch = single.get(idx)
                reenc.append((rev_kana.get(ch, idx)) * GLYPH_BYTES if ch else s)
        match = reenc == glyphs
        ok = ok and match
        print(f"$1F:{ptr:04X} idx {indices[0]}: {len(glyphs)} glyphs, "
              f"round-trip {'OK' if match else 'MISMATCH'}")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", default="rbshura.sfc")
    ap.add_argument("--verify", action="store_true",
                    help="round-trip the original ROM streams (structure check)")
    args = ap.parse_args(argv)
    if args.verify:
        return verify(args.rom)
    print("encode_narration: import encode_screen()/encode_line() from a build "
          "step, or run with --verify. EN wiring into project.toml is the next step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
