#!/usr/bin/env python3
"""encode_vs_names.py — generate the VS-screen name plates FROM char_names.

The VS (2P battle) screen does not read the HUD char_names table at $00E15B —
it has its own pre-built BG tilemap block in bank $1F: six 8-character slots
of 16-bit tilemap words (low byte = ASCII tile index, high byte = attr $30)
at PC $1FD9A3..$1FDA02, one per playable character, names centered with
space ($20) padding. The stock block even disagreed with the rest of the
game: Jaleco spelled "M-FLAME" there (an L/R romanization slip present in
the pristine JP ROM) while the HUD and character-select tables say M-FRAME.

Instead of hand-patching bytes, this retrotool `kind="python"` section
REGENERATES the whole block from the active language's char_names source
(data/<lang>/char_names.txt) every build — so the VS screen always shows the
same names as the rest of the game, in every translation, with char_names.txt
as the single source of truth.

VS roster (block slot order) -> char_names entry index:
    slot 0  NORTON    -> 10
    slot 1  KYTHRING  ->  2
    slot 2  DICK      ->  0
    slot 3  ELFIN     ->  8
    slot 4  JIMMY     ->  4
    slot 5  M-FRAME   ->  6

Build fails loudly if a name exceeds the 8-character slot or contains a
character outside printable ASCII (the VS plate font is ASCII-indexed).
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


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    data = encode_block(load_names(root), "char_names.txt")
    for s in range(6):
        words = data[s * SLOT_CHARS * 2:(s + 1) * SLOT_CHARS * 2]
        print(f"slot {s}: '" + "".join(chr(b) for b in words[::2]) + "'",
              "attrs", {words[i] for i in range(1, len(words), 2)})
