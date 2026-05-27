#!/usr/bin/env python3
"""Decode the bank-$DF cutscene script player's step records (drives scen 14
ending). Each slot in the table at $DF:AB22 (16-bit ptr per slot, indexed by
$1E96) points to a script. A script is a sequence of STEPS:

    [wait_byte] [addr_lo addr_hi value]* [FF FF]

  * wait_byte  → stored to $1E95; frames to wait before this step's writes.
  * (addr,val) → STA val to WRAM addr (the animation / fade / $1C48 advance).
  * FF FF      → terminates the write list for this step.

After a step's `FF FF`, the player reads ONE more byte (verified against the
engine at $85:EE99):
  * if it is $FF  → end of this slot's script; advance $1E96 to the next slot.
  * otherwise     → that byte IS the next step's wait_byte (stay in this slot).

So a slot's script is a run of steps separated by `FF FF`, ended by a lone
`FF` (i.e. the run terminates on `FF FF FF`). The byte after `FF FF` is NOT a
separate control byte — do not skip it; it's the next wait.

This tool prints every step with the SNES address of its WAIT byte (for asar
`org $DFxxxx`) and file offset, so timing tweaks can target specific waits.

Usage:
    python tools/dump_scen28_script.py [rom.sfc] [--slots LO-HI]

Default ROM: rbshura_en_24bit.sfc. Default slot range: $196-$1FE.
The wait byte of a step printed as `@SNES=$DFxxxx` is patchable via:
    org $DFxxxx : db <new_wait>     (in an asar build section)
"""
from __future__ import annotations
import sys
from pathlib import Path

from _paths import BUILT_ROM

SLOT_TBL = 0xAB22          # $DF:AB22
DF_BANK_FILE = 0x1F0000    # HiROM: $DF:xxxx → file $1Fxxxx


def load(rom_path: str) -> bytes:
    p = Path(rom_path)
    if not p.exists():
        raise SystemExit(
            f"ROM not found: {p}\n"
            "This tool reads the BUILT EN ROM's cutscene script. "
            "Rebuild it first: python scripts/build_24bit.py"
        )
    return p.read_bytes()


def df(rom: bytes, addr: int) -> int:
    return rom[DF_BANK_FILE + addr]


def df16(rom: bytes, addr: int) -> int:
    return df(rom, addr) | (df(rom, addr + 1) << 8)


def decode_script(rom: bytes, base: int, max_steps: int = 64):
    off = 0
    steps = []
    for _ in range(max_steps):
        start = off
        p = base + off
        wait = df(rom, p)
        p += 1
        writes = []
        guard = 0
        while guard < 64:
            a = df16(rom, p)
            if a == 0xFFFF:
                p += 2
                break
            writes.append((a, df(rom, p + 2)))
            p += 3
            guard += 1
        else:
            print(f"# WARNING: step @$DF:{base + start:04X} hit the 64-write cap "
                  "with no FFFF terminator — output may be truncated", file=sys.stderr)
        # peek the byte after FF FF: $FF = slot end, else = next step's wait
        slot_end = df(rom, p) == 0xFF
        steps.append((start, wait, writes, slot_end))
        if slot_end:
            break
        off = p - base   # next step starts AT this byte (its wait)
    else:
        print(f"# WARNING: slot @$DF:{base:04X} hit the {max_steps}-step cap "
              "with no slot-end marker — output may be truncated", file=sys.stderr)
    return steps


def main() -> None:
    args = sys.argv[1:]
    rom_path = str(BUILT_ROM)
    lo, hi = 0x196, 0x1FE
    i = 0
    while i < len(args):
        if args[i] == "--slots":
            lo_s, hi_s = args[i + 1].split("-")
            lo, hi = int(lo_s, 16), int(hi_s, 16)
            i += 2
        else:
            rom_path = args[i]
            i += 1

    rom = load(rom_path)
    print(f"# {rom_path} — slot table $DF:{SLOT_TBL:04X}, slots ${lo:03X}..${hi:03X}\n")
    seen_bases = {}
    for idx in range(lo, hi + 1, 2):
        base = df16(rom, SLOT_TBL + idx)
        tag = ""
        if base in seen_bases:
            tag = f"  (same base as slot ${seen_bases[base]:03X})"
        else:
            seen_bases[base] = idx
        print(f"slot ${idx:03X} -> $DF:{base:04X}{tag}")
        for start, wait, writes, slot_end in decode_script(rom, base):
            snes = 0xDF0000 | (base + start)
            fileoff = DF_BANK_FILE + base + start
            wr = ", ".join(f"${a:04X}=${v:02X}" for a, v in writes)
            end = "  <slot-end>" if slot_end else ""
            print(f"    wait={wait:3d} @SNES=${snes:06X} (file ${fileoff:06X})  [{wr}]{end}")
        print()


if __name__ == "__main__":
    main()
