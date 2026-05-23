#!/usr/bin/env python3
"""Dump the intro pointer table at $1F:C57F to data/{jp,en}/intro.txt,
including ALL distinct pointers — not just the long narrative blocks
(part1 = idx 0, part2 = idx 20+) but also the 10 shorter screens that
idx 1-19 reference.

Decoder uses the intro renderer's conventions:
  * FE XX = 2-byte kanji escape; XX indexes `tables/intro_kanji.tbl`
            (256 entries × 64 B at file $104000)
  * FA XX = 2-byte page-2 kanji prefix; XX indexes the `FAxx` subtable
            in `tables/rbshura_jp.tbl`
  * F7 / F8 / F9 / FB / FC.* / FD = standard control prefixes (emitted
            as bracket tokens, same shape as `tools/text_tool.py`)
  * Other bytes = single-byte chars via `tables/rbshura_jp.tbl`
  * FF = entry terminator (preceded by FE makes it a kanji index byte
         instead — see `truncate_at_terminator`-style logic below)

NOTE: empirically, several of the idx-1..19 pointer targets ($C5D9,
$C65D, $C6D5, $C7DB, ...) decode to **gibberish** under the standard
intro decoder — they're 16-bit-paired data structures, not text. Likely
tilemap entries / kanji-offset tables / title-screen graphics indices
for a different renderer path. We dump them anyway as `[raw XX YY ZZ]`
markers so the user can see the bytes and decide whether to keep or
delete each new field.

Field naming:
  * `part1` (idx 0, pointer $C8F1) — Cyber-Clone Incident backstory
  * `screen_<hex>` (idx 1-19) — keyed by pointer value to disambiguate
    duplicates (e.g. idx 1,2,3 all point to $C5D9 → one field
    `screen_c5d9` covers them all)
  * `part2` (idx 20+, pointer $CD35) — Maria Norton narration

Usage:
    python tools/dump_intro.py                    # writes both JP+EN
    python tools/dump_intro.py --check            # show what'd land, no write
    python tools/dump_intro.py --rom rbshura.sfc  # alt source ROM
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------------------
# Table loaders — share the same .tbl format as the rest of the project.
# ----------------------------------------------------------------------------

def _read_text(p: Path) -> str:
    raw = p.read_bytes()
    return raw.decode("utf-16" if raw.startswith(b"\xff\xfe") else "utf-8")


def load_jp_table(p: Path) -> tuple[dict[int, str], dict[int, str]]:
    """Returns (single_byte → char, FAxx → kanji)."""
    text = _read_text(p)
    single: dict[int, str] = {}
    fa: dict[int, str] = {}
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("@") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip()
        if len(k) == 2 and v:
            try:
                if int(k, 16) not in single:
                    single[int(k, 16)] = v
            except ValueError:
                pass
        elif len(k) == 4 and k.upper().startswith("FA"):
            try:
                fa[int(k[2:], 16)] = v
            except ValueError:
                pass
    return single, fa


def load_kanji_table(p: Path) -> dict[int, str]:
    """Single-byte → kanji glyph (for the FE-prefixed intro kanji font)."""
    text = _read_text(p)
    kanji: dict[int, str] = {}
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith(";") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip()
        if len(k) == 2 and v:
            try:
                kanji[int(k, 16)] = v
            except ValueError:
                pass
    return kanji


# ----------------------------------------------------------------------------
# Decoder
# ----------------------------------------------------------------------------

# Control-prefix byte widths, matching the intro renderer's escape conventions.
# These are emitted as bracket tokens so the encoder can round-trip them.
_CTRL_WIDTHS = {
    0xF7: 2,  # F7 XX
    0xF8: 2,  # F8 XX
    0xF9: 2,  # F9 XX
    0xFB: 2,  # FB XX
    0xFD: 1,  # FD (line break)
}


def decode_block(data: bytes, single: dict[int, str],
                 fa: dict[int, str], kanji: dict[int, str]) -> tuple[str, int]:
    """Decode one FF-terminated block. Returns (decoded_str, consumed_bytes).
    Consumed includes the trailing `[FF]`. FE-prefixed bytes are recognized
    so `FE FF` reads as a kanji-index byte, not a terminator."""
    out: list[str] = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        # Terminator (but only when not the XX of an FE/FA escape — which
        # are handled in their own branches before reaching here).
        if b == 0xFF:
            out.append("[FF]")
            i += 1
            return "".join(out), i
        # FE XX kanji escape (intro-only).
        if b == 0xFE and i + 1 < n:
            xx = data[i + 1]
            k = kanji.get(xx)
            out.append(k if k else f"[FE {xx:02X}]")
            i += 2
            continue
        # FA XX page-2 kanji escape.
        if b == 0xFA and i + 1 < n:
            xx = data[i + 1]
            k = fa.get(xx)
            out.append(k if k else f"[FA {xx:02X}]")
            i += 2
            continue
        # FC control with variable arg shapes.
        if b == 0xFC and i + 1 < n:
            sub = data[i + 1]
            if sub == 0x01 and i + 2 < n:
                out.append(f"[FC 01 {data[i + 2]:02X}]")
                i += 3
                continue
            if sub == 0x02 and i + 3 < n:
                out.append(f"[FC 02 {data[i + 2]:02X} {data[i + 3]:02X}]")
                i += 4
                continue
            if i + 2 < n:
                out.append(f"[FC {sub:02X} {data[i + 2]:02X}]")
                i += 3
                continue
        # Other fixed-width control prefixes.
        if b in _CTRL_WIDTHS:
            w = _CTRL_WIDTHS[b]
            if w == 1:
                out.append(f"[{b:02X}]")
                i += 1
            elif i + 1 < n:
                out.append(f"[{b:02X} {data[i + 1]:02X}]")
                i += 2
            else:
                out.append(f"[{b:02X}]")
                i += 1
            continue
        # Single-byte char or fallback to literal hex.
        c = single.get(b)
        out.append(c if c else f"[{b:02X}]")
        i += 1
    return "".join(out), i


def looks_like_text(block: bytes) -> bool:
    """Heuristic: is this likely meaningful text vs. a non-text data block?

    The intro's narrative blocks (part1 / part2) always contain at least
    one `FE XX` kanji escape — that's how the renderer switches from the
    kana font to the 256-entry kanji font for proper rendering. Non-text
    blocks (the title-screen / logo tilemap data at idx 1-19) never have
    a byte `$FE` because the renderer treats them differently.

    Checking the raw byte stream for `$FE` (and accounting for it being
    a kanji-prefix that takes a following arg, not a standalone byte) is
    more reliable than checking the decoded string, since the decoder
    consumes FE during glyph resolution."""
    i = 0
    while i < len(block):
        b = block[i]
        if b == 0xFE and i + 1 < len(block):
            return True
        if b == 0xFA and i + 1 < len(block):
            # FA also indicates a multi-byte char prefix — present in
            # both text blocks and (rarely) non-text. Skip past its arg
            # so we don't mistakenly hit a `$FE` that's actually an FA-arg.
            i += 2
            continue
        if b == 0xFF:
            return False  # terminator without seeing FE → not text
        i += 1
    return False


# ----------------------------------------------------------------------------
# Pointer-table walker
# ----------------------------------------------------------------------------

PTR_TABLE_PC = 0x1FC57F  # file offset of the intro pointer table
DATA_BANK = 0x1F          # pointer values are offsets within this bank
INTRO_LO = 0xC500          # heuristic: valid intro pointers fall in this band
INTRO_HI = 0xD300


def walk_pointer_table(rom: bytes) -> list[tuple[int, list[int]]]:
    """Returns [(pointer_value, [list_of_indices])] in ascending pointer order.
    Stops at the first value outside the intro range (= end of table)."""
    seen: dict[int, list[int]] = {}
    for i in range(80):  # safety cap
        addr = PTR_TABLE_PC + i * 2
        if addr + 1 >= len(rom):
            break
        val = rom[addr] | (rom[addr + 1] << 8)
        if not (INTRO_LO <= val <= INTRO_HI):
            break
        seen.setdefault(val, []).append(i)
    return sorted(seen.items())


def extract_block(rom: bytes, ptr: int) -> bytes:
    """Read bytes from $1F:<ptr> until FE-aware FF terminator (4 KB cap).
    FE XX = kanji escape (consumes 2 bytes), so FE FF is a kanji index byte
    rather than a terminator."""
    fo = (DATA_BANK << 16) | ptr
    i = 0
    end = min(fo + 4096, len(rom))
    while fo + i < end:
        b = rom[fo + i]
        if b == 0xFE and fo + i + 1 < end:
            i += 2
            continue
        if b == 0xFF:
            return rom[fo:fo + i + 1]
        i += 1
    return rom[fo:end]


def field_name_for(ptr: int, indices: list[int]) -> str:
    """Stable field name for one pointer. Preserves `part1` / `part2` for
    the existing narrative blocks so the existing translation seed survives
    a re-dump; everything else gets a `screen_<hex>` name."""
    if ptr == 0xC8F1:
        return "part1"
    if ptr == 0xCD35:
        return "part2"
    return f"screen_{ptr:04x}"


# ----------------------------------------------------------------------------
# Output writer
# ----------------------------------------------------------------------------

def to_raw_hex(data: bytes) -> str:
    """Emit `[XX YY ZZ ...]` style — clearer than mixed-glyph fallback for
    blocks that aren't actually text. Wraps every 16 bytes for readability."""
    rows = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        rows.append("[" + " ".join(f"{b:02X}" for b in chunk) + "]")
    return "".join(rows) if len(rows) == 1 else "\n".join(rows)


def render_file(rom: bytes, single, fa, kanji) -> tuple[str, list[dict]]:
    """Build the .txt body + a list of per-field summary dicts.

    Text blocks (part1, part2) → decoded with glyphs + control tokens.
    Non-text blocks (the other 10 unique pointers, which appear to be SNES
    BG tilemap entries based on their byte structure) → raw hex so they're
    clearly distinguishable from translatable text and don't accidentally
    invite translation of meaningless kana fragments.
    """
    fields_summary: list[dict] = []
    out_lines: list[str] = [
        "; Auto-generated by tools/dump_intro.py — DO NOT hand-edit headers.",
        "; The intro renderer at $05:F010 reads from the pointer table at",
        "; $1F:C57F. Each unique pointer is dumped here as one field.",
        ";",
        "; Only `part1` and `part2` are translatable text. The 10 `screen_*`",
        "; fields are non-text data (SNES BG tilemap entries / per-screen",
        "; coordinate tables) used by the intro's static title/logo screens.",
        "; They're dumped as raw hex so you can see the bytes without being",
        "; misled by the standard text decoder falling back to literal kana.",
        ";",
        "; tables/intro.toml's [[fields]] entries drive insertion. Today only",
        "; part1 and part2 are wired up; if you want to localize a screen_*",
        "; block, add a [[fields]] entry with matching label and a `ptr_writes`",
        "; targeting that screen's pointer-table slot(s).",
        "",
    ]
    for ptr, indices in walk_pointer_table(rom):
        block = extract_block(rom, ptr)
        decoded, _consumed = decode_block(block, single, fa, kanji)
        likely_text = looks_like_text(block)
        name = field_name_for(ptr, indices)
        rng = (f"{indices[0]}" if len(indices) == 1
               else f"{indices[0]}-{indices[-1]}")
        # Pick the body representation: glyph-decoded for text, raw-hex for
        # binary blocks. The trailing [FF] is left visible in both cases so
        # the encoder gets the right terminator without needing the `[encoding]
        # .terminator` config (also future-proofs against round-tripping).
        if likely_text:
            body = decoded
            tag = ""
        else:
            body = to_raw_hex(block)
            tag = "  (binary block — likely BG tilemap data, not text)"
        out_lines.append(
            f"; idx {rng} → $1F:{ptr:04X}  ({len(block)} B raw){tag}"
        )
        out_lines.append(f"<<${PTR_TABLE_PC:X}:0.{name}>>")
        out_lines.append(body)
        out_lines.append("")
        fields_summary.append({
            "ptr": ptr, "indices": indices, "name": name,
            "raw_bytes": len(block), "decoded_chars": len(decoded),
            "likely_text": likely_text,
        })
    return "\n".join(out_lines), fields_summary


def write_utf16(p: Path, text: str) -> None:
    p.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", default="rbshura.sfc",
                    help="source ROM (default: rbshura.sfc — pristine)")
    ap.add_argument("--check", action="store_true",
                    help="show what would be written, don't update files")
    ap.add_argument("--jp-out", default="data/jp/intro.txt",
                    help="JP dump destination")
    ap.add_argument("--en-out", default="data/en/intro.txt",
                    help="EN translation-seed destination (gets the same JP "
                         "text; user translates over it)")
    args = ap.parse_args(argv)

    rom = (ROOT / args.rom).read_bytes()
    single, fa = load_jp_table(ROOT / "tables/rbshura_jp.tbl")
    kanji = load_kanji_table(ROOT / "tables/intro_kanji.tbl")

    body, summary = render_file(rom, single, fa, kanji)

    print(f"Pointer-table walk @ ${PTR_TABLE_PC:X}: {len(summary)} unique blocks")
    for s in summary:
        rng = (f"idx {s['indices'][0]}"
               if len(s['indices']) == 1
               else f"idx {s['indices'][0]}-{s['indices'][-1]}")
        flag = "" if s["likely_text"] else "  ⚠ likely non-text"
        print(f"  ${s['ptr']:04X}  {s['name']:>14}  "
              f"{s['raw_bytes']:>4} B  ({rng}){flag}")

    if args.check:
        print(f"\n--check: dump would write {len(body):,} chars to JP+EN")
        return 0

    jp_path = (ROOT / args.jp_out).resolve()
    en_path = (ROOT / args.en_out).resolve()
    write_utf16(jp_path, body)
    print(f"\nwrote {jp_path}  ({len(body):,} chars)")
    if not en_path.exists():
        write_utf16(en_path, body)
        print(f"wrote {en_path}  (new translation seed)")
    else:
        # Don't trample the user's translation work. Print a hint instead.
        print(f"NOT overwriting {en_path}  (already has translations)")
        print(f"  → manually merge new fields into the EN file if you want them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
