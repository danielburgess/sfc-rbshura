#!/usr/bin/env python3
"""encode_vs_names.py — generate the VS-roster name plates FROM char_names.

Besides the HUD char_names table at $00E15B, the game keeps TWO more
pre-built name-plate blocks for the six playable characters, neither of
which reads char_names:

  * VS-screen plates, bank $1F (PC $1FD9A3..$1FDA02): six 8-char slots of
    16-bit tilemap words (low byte = ASCII tile index, high byte = attr
    $30), names centered with space ($20) padding. The stock block even
    disagreed with the rest of the game: Jaleco spelled "M-FLAME" there (an
    L/R romanization slip present in the pristine JP ROM).
  * Bordered plates, bank $01 (ptr table $018AC8 -> six fixed 20-byte
    records at $018AD4 + 20*n): 10 words per record — `A8 14` pad words,
    `A5 14` left border, name chars with attr $10, `A6 14` right border —
    name+borders centered. Read at runtime (bank-41 disasm `LDA $8AC8,Y`
    indexed by character, queued as a $14-byte copy to tilemap $5B43/$5B53
    for the 1P/2P rows).

Instead of hand-patching bytes, two retrotool `kind="python"` sections
(`build` and `build_select`) REGENERATE both blocks from the active
language's char_names source (data/<lang>/char_names.txt) every build — so
every screen shows the same names, in every translation, with
char_names.txt as the single source of truth.

Roster (block slot order, same in both blocks) -> char_names entry index:
    slot 0  NORTON    -> 10
    slot 1  KYTHRING  ->  2
    slot 2  DICK      ->  0
    slot 3  ELFIN     ->  8
    slot 4  JIMMY     ->  4
    slot 5  M-FRAME   ->  6

Build fails loudly if a name exceeds the 8-character slot or contains a
character outside printable ASCII (the plate fonts are ASCII-indexed).
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

BLOCK_PC = 0x1FD9A3          # first slot's first word ('  NORTON ' area)
SLOT_CHARS = 8               # tilemap words per name slot
ATTR = 0x30                  # attr byte used by every stock plate word
ROSTER = [10, 2, 0, 8, 4, 6]  # char_names indices, block slot order (maps the char_name index to the vs roster idx)

ENTRY_RE = re.compile(r"<<\$[0-9A-Fa-f]+:(\d+)\.\w+>>\n([^\n]*)\n")


def _char_names_path(root: Path) -> Path:
    """Resolve the ACTIVE language's char_names.txt via project.toml
    (`build_lang` -> `<lang>_data_dir`, defaulting to en)."""
    cfg = tomllib.loads((root / "project.toml").read_text(encoding="utf-8"))
    lang = cfg.get("build_lang", "en")
    data_dir = cfg.get(f"{lang}_data_dir") or cfg.get("en_data_dir", "data/en")
    return root / data_dir / "char_names.txt"


def load_names(root: Path) -> dict[int, str]:
    path = _char_names_path(root)
    text = path.read_text(encoding="utf-16")
    return {int(m.group(1)): m.group(2).strip() for m in ENTRY_RE.finditer(text)}


def encode_block(names: dict[int, str], source: str) -> bytes:
    out = bytearray()
    for slot, idx in enumerate(ROSTER):
        name = names.get(idx, "")
        if not name:
            raise SystemExit(f"vs_names: {source} entry {idx} (VS slot {slot}) is empty")
        if len(name) > SLOT_CHARS:
            raise SystemExit(
                f"vs_names: '{name}' ({len(name)} chars, entry {idx}) does not fit "
                f"the {SLOT_CHARS}-char VS name plate — shorten it in char_names.txt")
        if not all(0x20 <= ord(c) < 0x7F for c in name):
            raise SystemExit(
                f"vs_names: '{name}' (entry {idx}) has a non-ASCII char — the VS "
                f"plate font is ASCII-indexed")
        pad = SLOT_CHARS - len(name)
        text = " " * (pad // 2) + name + " " * (pad - pad // 2)  # centered, like stock
        for ch in text:
            out += bytes((ord(ch), ATTR))
    return bytes(out)


def build(rom, section, root, ctx=None):
    """retrotool kind="python" entry: rewrite the VS name-plate block."""
    from retrotool.build.handlers import WriteRange
    root = Path(root)
    src = _char_names_path(root)
    data = encode_block(load_names(root), src.name)
    off = section.offset if section.offset is not None else BLOCK_PC
    rom[off:off + len(data)] = data
    return WriteRange(off, len(data))


# --- bordered plates (bank $01, char-index pointer table) -------------------

SELECT_PTR_PC = 0x018AC8     # 6 x 16-bit within-bank pointers ($8AD4 + 20*n)
SELECT_BLOCK_PC = 0x018AD4   # first record
SELECT_WORDS = 10            # words per record (fixed 20-byte stride)
TILE_PAD, TILE_L, TILE_R = 0xA8, 0xA5, 0xA6   # pad / left / right border tiles
ATTR_BORDER = 0x14           # attr of pad + border words
ATTR_NAME = 0x10             # attr of the name's character words


def encode_select_records(names: dict[int, str], source: str) -> bytes:
    out = bytearray()
    for slot, idx in enumerate(ROSTER):
        name = names.get(idx, "")
        max_chars = SELECT_WORDS - 2          # minus the two border tiles
        if not name:
            raise SystemExit(f"vs_names: {source} entry {idx} (select slot {slot}) is empty")
        if len(name) > max_chars:
            raise SystemExit(
                f"vs_names: '{name}' ({len(name)} chars, entry {idx}) does not fit "
                f"the {max_chars}-char bordered name plate — shorten it in char_names.txt")
        if not all(0x20 <= ord(c) < 0x7F for c in name):
            raise SystemExit(
                f"vs_names: '{name}' (entry {idx}) has a non-ASCII char — the "
                f"plate font is ASCII-indexed")
        pad = SELECT_WORDS - (len(name) + 2)
        words = ([(TILE_PAD, ATTR_BORDER)] * (pad // 2)
                 + [(TILE_L, ATTR_BORDER)]
                 + [(ord(c), ATTR_NAME) for c in name]
                 + [(TILE_R, ATTR_BORDER)]
                 + [(TILE_PAD, ATTR_BORDER)] * (pad - pad // 2))
        for tile, attr in words:
            out += bytes((tile, attr))
    return bytes(out)


def build_select(rom, section, root, ctx=None):
    """retrotool kind="python" entry: rewrite the bordered name-plate records.

    The pointer table at $018AC8 is left untouched — records are fixed-size
    and rewritten in place. Sanity-check the pointers first so a layout
    change in the source ROM fails the build instead of corrupting data."""
    from retrotool.build.handlers import WriteRange
    root = Path(root)
    ptrs = [rom[SELECT_PTR_PC + i * 2] | (rom[SELECT_PTR_PC + i * 2 + 1] << 8)
            for i in range(len(ROSTER))]
    expect = [(SELECT_BLOCK_PC & 0xFFFF) + SELECT_WORDS * 2 * n
              for n in range(len(ROSTER))]
    if ptrs != expect:
        raise SystemExit(
            f"vs_names: select-plate pointer table at ${SELECT_PTR_PC:06X} is "
            f"{[hex(p) for p in ptrs]}, expected {[hex(e) for e in expect]} — "
            f"ROM layout changed, refusing to write")
    src = _char_names_path(root)
    data = encode_select_records(load_names(root), src.name)
    off = section.offset if section.offset is not None else SELECT_BLOCK_PC
    rom[off:off + len(data)] = data
    return WriteRange(off, len(data))


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    names = load_names(root)
    data = encode_block(names, "char_names.txt")
    for s in range(6):
        words = data[s * SLOT_CHARS * 2:(s + 1) * SLOT_CHARS * 2]
        print(f"vs     slot {s}: '" + "".join(chr(b) for b in words[::2]) + "'",
              "attrs", {words[i] for i in range(1, len(words), 2)})
    sel = encode_select_records(names, "char_names.txt")
    for s in range(6):
        words = sel[s * SELECT_WORDS * 2:(s + 1) * SELECT_WORDS * 2]
        txt = "".join(chr(t) if a == ATTR_NAME else
                      {TILE_L: "[", TILE_R: "]", TILE_PAD: "_"}.get(t, "?")
                      for t, a in zip(words[::2], words[1::2]))
        print(f"select slot {s}: '{txt}'")
