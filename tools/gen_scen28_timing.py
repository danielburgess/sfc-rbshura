#!/usr/bin/env python3
"""Generate an editable timing template for the scen 28 (ending) cutscene,
correlated to the dialog text.

The ending is driven by the bank-$DF script player (slot table $DF:AB22 indexed
by $1E96). Each script STEP starts with a one-byte WAIT count (frames to hold
before that step's writes fire). Walking the slots in execution order, the
$1C48 writes mark dialog-entry transitions:

    entry = 22 + ($1C48 - $24) / 2      (anchored from SplitTrace: $24 -> entry 22)

So every animation / sound / fade step can be labelled with the dialog entry it
plays under. The text of each entry comes from data/en/scenario_28.txt.

Output (stdout) is a list of `org $DFxxxx : db NN` lines, deduped by ROM
address (the same script is reused under several entries — editing its wait
affects ALL of them, which the annotation flags). Each line is COMMENTED;
uncomment + change the number to retime that step.

  python tools/gen_scen28_timing.py [rom.sfc] > docs/scen28_timings.txt

NOTE the wait bytes are SEPARATE from the text's own [F7]/[FB]/[FE]/[FF]
control codes — those pace the renderer; these pace the cutscene. They meet
only at the entry boundary (the gate waits for the entry's [FF] before letting
$1C48 advance).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

SLOT_TBL = 0xAB22
DF_FILE = 0x1F0000
SLOT_LO, SLOT_HI = 0x000, 0x520          # full scen-28 cutscene incl. ending fade + epilogue (slots $300+)
CLUSTER_LO, CLUSTER_HI = 0xB100, 0xC2FF   # widened to cover ending scripts $DFBDxx..$DFC2xx
EN_TXT = "data/en/scenario_28.txt"

TARGET_NOTES = {
    0x1C48: "ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)",
    0x1C56: "renderer re-engage — do NOT retime",
    0x1C57: "renderer re-engage — do NOT retime",
    0x2142: "APU port — sound trigger",
}


def load_snippets(path: str) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        txt = Path(path).read_text(encoding="utf-16").split("\n")
    except Exception:
        return out
    cur = None
    for line in txt:
        m = re.match(r"\s*<<\$\d+:(\d+)\[", line)
        if m:
            cur = int(m.group(1)); out[cur] = ""
        elif cur is not None and line.strip():
            out[cur] += line
    for k in out:
        s = re.sub(r"\[[0-9A-Fa-f ]+\]", "", out[k]).replace(" ", "")
        out[k] = s[:36]
    return out


def main() -> None:
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "rbshura_en_24bit.sfc"
    rom = Path(rom_path).read_bytes()
    snips = load_snippets(EN_TXT)

    def df(a): return rom[DF_FILE + a]
    def df16(a): return df(a) | (df(a + 1) << 8)

    def decode(base, max_steps=64):
        off, steps = 0, []
        for _ in range(max_steps):
            start = off; p = base + off
            wait = df(p); p += 1
            writes = []; g = 0
            while g < 64:
                a = df16(p)
                if a == 0xFFFF:
                    p += 2; break
                writes.append((a, df(p + 2))); p += 3; g += 1
            slot_end = df(p) == 0xFF
            steps.append((start, wait, writes, slot_end))
            if slot_end:
                break
            off = p - base
        return steps

    # walk execution order, track entry, collect per-wait-address contexts
    waits: dict[int, dict] = {}   # snes -> {wait, writes, entries:set}
    cur_entry = None
    for idx in range(SLOT_LO, SLOT_HI + 1, 2):
        base = df16(SLOT_TBL + idx)
        if not (CLUSTER_LO <= base <= CLUSTER_HI):
            continue
        for start, wait, writes, _ in decode(base):
            for a, v in writes:
                if a == 0x1C48:
                    cur_entry = 22 + (v - 0x24) // 2
            snes = 0xDF0000 | (base + start)
            rec = waits.setdefault(snes, {"wait": wait, "writes": writes, "entries": set()})
            if cur_entry is not None:
                rec["entries"].add(cur_entry)

    print("; =================================================================")
    print(f"; scen 28 timing template — generated from {rom_path}")
    print(f"; {len(waits)} unique wait bytes. entry N text from {EN_TXT}.")
    print("; Uncomment a line + change the number to retime that step.")
    print("; Bigger = hold longer / delay later; smaller = fire sooner.")
    print("; A wait shared across several entries retimes ALL of them.")
    print("; =================================================================")
    for snes in sorted(waits):
        r = waits[snes]
        wr = ", ".join(f"${a:04X}=${v:02X}" for a, v in r["writes"]) or "(no writes)"
        ents = sorted(e for e in r["entries"] if e is not None)
        ectx = "  ; @(scene setup, pre-dialog)"
        if ents:
            lo = ents[0]
            snip = snips.get(lo, "")
            span = f"entries {ents[0]}-{ents[-1]}" if len(ents) > 1 else f"entry {ents[0]}"
            ectx = f"  ; @{span}: \"{snip}\""
        note = ""
        for a, _ in r["writes"]:
            if a in TARGET_NOTES:
                note = "  ; ** " + TARGET_NOTES[a]; break
        print(f"; org ${snes:06X} : db {r['wait']:<3d}   ; [{wr}]{note}{ectx}")


if __name__ == "__main__":
    main()
