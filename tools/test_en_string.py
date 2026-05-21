#!/usr/bin/env python3
"""Test patch: overwrite scenario_00 entry 16 with "hello world" in EN encoding
to verify rbshura_en.tbl's byte→letter mapping end-to-end.

Source ROM:  rbshura_pkfont.sfc (with PK font padded into rbshura's TL/BL slots)
Output ROM:  rbshura_pkfont_hello.sfc

Entry 16 location: PC $05877E, 22 bytes total
  Structure: F8 01 FC 01 02 [12 char bytes] F7 FF FB 15 FF
             ^^prefix^^^^^  ^^^^text^^^^^^  ^^^^^suffix^^^^

Replacement:
  F8 01 FC 01 02 08 05 0C 0C 0F 00 17 0F 12 0C 04 00 F7 FF FB 15 FF
                 h  e  l  l  o  _  w  o  r  l  d  _

(trailing $00 pads to 12 bytes = same length as original = pointer table needs no adjustment)
"""
from pathlib import Path

SRC = Path("rbshura_pkfont.sfc")
DST = Path("rbshura_pkfont_hello.sfc")

ENTRY_PC = 0x05877E
ORIGINAL_LEN = 22

NEW_ENTRY = bytes([
    0xF8, 0x01,                # SPD 01
    0xFC, 0x01, 0x02,          # FC 01 02
    # "hello world" + 1 trailing space (12 bytes text)
    0x08, 0x05, 0x0C, 0x0C, 0x0F,   # h e l l o
    0x00,                            # space
    0x17, 0x0F, 0x12, 0x0C, 0x04,   # w o r l d
    0x00,                            # padding space
    0xF7, 0xFF,                # END terminator
    0xFB, 0x15,                # next-entry separator (preserved from original)
    0xFF,                       # STOP
])

assert len(NEW_ENTRY) == ORIGINAL_LEN, f"replacement {len(NEW_ENTRY)}B != original {ORIGINAL_LEN}B"

rom = bytearray(SRC.read_bytes())

print(f"Source: {SRC}")
print(f"Original entry @${ENTRY_PC:06X}: {bytes(rom[ENTRY_PC:ENTRY_PC+ORIGINAL_LEN]).hex(' ').upper()}")

rom[ENTRY_PC:ENTRY_PC+ORIGINAL_LEN] = NEW_ENTRY

print(f"Patched  entry @${ENTRY_PC:06X}: {bytes(rom[ENTRY_PC:ENTRY_PC+ORIGINAL_LEN]).hex(' ').upper()}")

DST.write_bytes(bytes(rom))
print(f"\nWrote {DST} ({len(rom)} bytes)")
print(f"\nVerification:")
verify = DST.read_bytes()
assert verify[ENTRY_PC:ENTRY_PC+ORIGINAL_LEN] == NEW_ENTRY, "patch did not apply correctly"
assert verify[:ENTRY_PC] == rom[:ENTRY_PC], "bytes BEFORE entry were touched"
assert verify[ENTRY_PC+ORIGINAL_LEN:] == rom[ENTRY_PC+ORIGINAL_LEN:], "bytes AFTER entry were touched"
print(f"  Only ${ENTRY_PC:06X}-${ENTRY_PC+ORIGINAL_LEN-1:06X} changed; rest of ROM intact.")

print(f"\nNext: load {DST} in Mesen2, start scenario 1 (first stage).")
print(f"  Original opening dialog displayed Japanese 'Digeras Motor Factory'.")
print(f"  Patched ROM should display 'hello world' (lowercase) instead.")
