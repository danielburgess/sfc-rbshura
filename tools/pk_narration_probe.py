#!/usr/bin/env python3
"""Compare how Peacekeepers (official EN release of Rushing Beat Shura) renders
the post-intro-scroll character-narration screens vs rbshura (JP), to port PK's
"render-at-once half-width text" logic into the rbshura translation.

Shared engine, so the relevant differences are localized:
  - the $1F:C57F screen pointer table (idx 1-19 = the character screens)
  - the data those pointers reach (glyph-DMA stream vs text?)
  - the bank-$05 render dispatch + renderer ($05:EE00..$05:F2B0)

Usage:
    python tools/pk_narration_probe.py
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JP = ROOT / "rbshura.sfc"
PK = ROOT / "peacekeepers.sfc"

PTR_TABLE = 0x1FC57F      # file offset
BANK_1F = 0x1F0000


def u16(b: bytes, o: int) -> int:
    return b[o] | (b[o + 1] << 8)


def ptr_table(b: bytes, n: int = 46) -> list[int]:
    return [u16(b, PTR_TABLE + i * 2) for i in range(n)]


def hexdump(b: bytes, fo: int, n: int) -> str:
    return " ".join(f"{x:02X}" for x in b[fo:fo + n])


def classify(b: bytes, ptr: int) -> str:
    """Heuristic: FE present -> kanji-escape text; FFFF-terminated 16-bit runs in
    $0000-$7FFF -> glyph-DMA stream; otherwise raw."""
    fo = BANK_1F | ptr
    window = b[fo:fo + 256]
    if 0xFE in window[: window.find(b"\xff") + 1 if b"\xff" in window else 64]:
        return "TEXT? (has FE kanji-escape)"
    # look for FFFF terminator within 256 b
    for i in range(0, 254, 2):
        if window[i] == 0xFF and window[i + 1] == 0xFF:
            return f"glyph-DMA? (FFFF @ +{i})"
    if 0xFF in window:
        return f"TEXT? (FF terminator @ +{window.find(0xFF)})"
    return "raw/unknown"


def main() -> None:
    jp = JP.read_bytes()
    pk = PK.read_bytes()
    print(f"JP {JP.name}: {len(jp)} B   PK {PK.name}: {len(pk)} B\n")

    jt = ptr_table(jp)
    pt = ptr_table(pk)
    print("=== $1F:C57F pointer table (idx 0-45) ===")
    print(f"{'idx':>3} {'JP ptr':>7} {'PK ptr':>7}  same?")
    for i, (a, c) in enumerate(zip(jt, pt)):
        mark = "" if a == c else "  <-- DIFF"
        print(f"{i:>3}  ${a:04X}   ${c:04X}{mark}")

    # The 10 unique idx-1-19 character-screen pointers in JP
    jp_unique = []
    for i in range(1, 20):
        if jt[i] not in jp_unique:
            jp_unique.append(jt[i])
    print("\n=== idx 1-19 unique screen pointers: data classification ===")
    for ptr in jp_unique:
        fo = BANK_1F | ptr
        pk_ptr = None
        # find PK's pointer for the same idx
        idx = jt.index(ptr)
        pk_ptr = pt[idx]
        print(f"\n-- JP $1F:{ptr:04X} (idx {idx})  |  PK $1F:{pk_ptr:04X}")
        print(f"   JP class: {classify(jp, ptr)}")
        print(f"   JP bytes: {hexdump(jp, fo, 40)}")
        print(f"   PK class: {classify(pk, pk_ptr)}")
        print(f"   PK bytes: {hexdump(pk, BANK_1F | pk_ptr, 40)}")

    # Diff bank $05 renderer/dispatch region
    print("\n=== bank $05 diff $05:EE00..$05:F2B0 (renderer + dispatch) ===")
    base = 0x05EE00
    end = 0x05F2B0
    diffs = []
    i = base
    while i < end:
        if jp[i] != pk[i]:
            run_start = i
            while i < end and jp[i] != pk[i]:
                i += 1
            diffs.append((run_start, i))
        else:
            i += 1
    if not diffs:
        print("   (identical — renderer code is shared byte-for-byte)")
    else:
        for s, e in diffs:
            snes = 0xC50000 | (s & 0xFFFF)
            print(f"   ${snes:06X} (file ${s:05X}) len {e - s}")
            print(f"      JP: {hexdump(jp, s, min(e - s, 32))}")
            print(f"      PK: {hexdump(pk, s, min(e - s, 32))}")


if __name__ == "__main__":
    main()
