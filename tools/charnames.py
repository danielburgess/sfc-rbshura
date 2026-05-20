#!/usr/bin/env python3
"""char_names extractor.

The HUD player-character name table at PC $00E15B is a fixed-stride
12-byte-per-record block: 11 bytes of ASCII name (space-padded to 11)
+ 1 byte 0xFF terminator. 32 entries; layout fully RE'd in
char_names.json at the project root.

Insertion is owned by retrotool via tables/char_names.toml
(kind="fixed-records"). This script handles extract only — emitting the
text format that the fixed-records handler ingests:

    <<$E15B:0.name>>
    DICK
    <<$E15B:1.name>>
    SPIDER
    ...

Header semantics (per retrotool): `$HEX` is purely a section marker
(we use the table offset); `N` is the record index; `name` is the
field label declared in tables/char_names.toml.

ENCODING NOTE: the HUD font uses raw ASCII, not the PK dialog font.
`D` here = byte 0x44 (not 0x24 like the dialog font). tables/ascii.tbl
holds the identity mapping retrotool's encoder uses.

Usage:
    python tools/charnames.py extract  # ROM → data/jp/char_names.txt
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROM = ROOT / "rbshura.sfc"                  # pristine source for extract
TABLE_PC = 0x00E15B
RECORD_LEN = 12
N_ENTRIES = 32
TERMINATOR = 0xFF
NAME_MAX = RECORD_LEN - 1

JP_OUT = ROOT / "data" / "jp" / "char_names.txt"
EN_OUT = ROOT / "data" / "en" / "char_names.txt"

# `$HEX` in the header is just a section marker — use the table address.
HEADER_HEX = f"{TABLE_PC:X}"
FIELD_LABEL = "name"


def extract_from_rom(rom_bytes: bytes) -> list[str]:
    """Pull 32 names from rom at TABLE_PC, ASCII-decoded and right-stripped."""
    out = []
    for i in range(N_ENTRIES):
        off = TABLE_PC + i * RECORD_LEN
        record = rom_bytes[off:off + RECORD_LEN]
        if TERMINATOR in record:
            content = record[:record.index(TERMINATOR)]
        else:
            content = record
        content = content.rstrip(b" \x00")
        try:
            out.append(content.decode("ascii"))
        except UnicodeDecodeError:
            # Non-printable bytes round-trip via `[XX]` escapes — the
            # fixed-records encoder honors them through the ascii.tbl
            # fallback path. No real entry hits this today.
            out.append("".join(
                chr(b) if 0x20 <= b < 0x7F else f"[{b:02X}]"
                for b in content
            ))
    return out


def write_script_file(path: Path, names: list[str]) -> None:
    """Write names in retrotool fixed-records UTF-16 format. Atomic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        f"<<${HEADER_HEX}:{i}.{FIELD_LABEL}>>\n{name}\n"
        for i, name in enumerate(names)
    ]
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                               prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write("".join(parts))
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise


def do_extract() -> None:
    rom = ROM.read_bytes()
    names = extract_from_rom(rom)
    write_script_file(JP_OUT, names)
    print(f"Extracted {len(names)} names → {JP_OUT.relative_to(ROOT)}")
    if not EN_OUT.exists():
        write_script_file(EN_OUT, names)
        print(f"Seeded {EN_OUT.relative_to(ROOT)} (already ASCII English).")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "extract":
        sys.exit("usage: charnames.py extract")
    do_extract()


if __name__ == "__main__":
    main()
