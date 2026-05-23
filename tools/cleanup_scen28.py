#!/usr/bin/env python3
"""Clean up data/{jp,en}/scenario_28.txt — repairs the dump that produced
this file with two known bugs:

  1. The dumper didn't apply `FA` as a 2-byte kanji escape: it emitted
     `[FA]<char>` literally, where <char> is the next byte decoded as a
     single-byte kana. We resolve each `[FA]<char>` to the actual kanji
     by reverse-mapping <char>→byte and looking up FA<byte> in the
     FAxx subtable in tables/rbshura_jp.tbl.

  2. The dumper walked past entry terminators for some entries (notably
     entry 75, where 520 chars of leaked WRAM pointer-table data followed
     the legit `[FB 20][FF]`). We truncate each entry's body at its first
     STANDALONE `[FF]` (one not preceded by `[FA]`, which would make FF a
     kanji index byte rather than a terminator).

Run after re-dumping or to retroactively fix existing dumps. Idempotent.

Usage:
    python tools/cleanup_scen28.py             # processes both JP + EN
    python tools/cleanup_scen28.py --check     # diff without writing
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_tables(table_path: Path) -> tuple[dict[str, int], dict[int, str]]:
    """Returns (char→byte, FAxx→kanji) from a `.tbl` file."""
    raw = table_path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8")

    char_to_byte: dict[str, int] = {}
    fa_table: dict[int, str] = {}
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("@") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        key = key.strip()
        value = value.strip()
        if len(key) == 4 and key.upper().startswith("FA"):
            try:
                fa_table[int(key[2:], 16)] = value
            except ValueError:
                pass
        elif len(key) == 2 and value:
            try:
                # First occurrence wins (matches the encoder's longest-match
                # heuristic for single-byte entries).
                if value not in char_to_byte:
                    char_to_byte[value] = int(key, 16)
            except ValueError:
                pass
    return char_to_byte, fa_table


def resolve_fa_escapes(body: str, char_to_byte: dict[str, int],
                       fa_table: dict[int, str]) -> tuple[str, int]:
    """Walk the body; replace `[FA]<X>` with the kanji from the FAxx table.
    `<X>` may be a single char or a `[FF]` token (the latter encodes the
    FAFF kanji index). Returns (new_body, replacements_made)."""
    out: list[str] = []
    i = 0
    n = len(body)
    replacements = 0
    while i < n:
        # Detect "[FA]" prefix
        if body.startswith("[FA]", i):
            j = i + 4  # past `[FA]`
            if j >= n:
                # Trailing [FA] with no arg — leave as-is.
                out.append(body[i:i + 4])
                i += 4
                continue
            # Next token: either `[XX]` (e.g. `[FF]`) or a single char.
            if body[j] == "[":
                end = body.find("]", j)
                if end == -1:
                    out.append(body[i:i + 4])
                    i += 4
                    continue
                tok = body[j + 1:end]
                # FA<bracket-token> — accept FF, others left as-is.
                if tok.strip().upper() == "FF":
                    arg_byte = 0xFF
                else:
                    # Don't recognize — preserve literally.
                    out.append(body[i:end + 1])
                    i = end + 1
                    continue
                arg_consumed = end + 1
            else:
                ch = body[j]
                arg_byte = char_to_byte.get(ch)
                if arg_byte is None:
                    # Char not in single-byte table — leave [FA]<ch> alone.
                    out.append(body[i:j + 1])
                    i = j + 1
                    continue
                arg_consumed = j + 1
            # Look up FA<arg_byte> in the kanji table.
            kanji = fa_table.get(arg_byte)
            if kanji is None:
                # Mapping missing — preserve as a hex marker so the user
                # can see exactly which FA-byte is unmapped.
                out.append(f"[FA {arg_byte:02X}]")
            else:
                out.append(kanji)
                replacements += 1
            i = arg_consumed
        else:
            out.append(body[i])
            i += 1
    return "".join(out), replacements


def truncate_at_terminator(body: str) -> tuple[str, int]:
    """Find the first STANDALONE `[FF]` (not preceded by `[FA]`) and
    truncate the body there, KEEPING the `[FF]`. Returns (new_body,
    trimmed_chars). If no terminator found, body returned unchanged."""
    # Walk token by token. Track whether the immediately preceding visible
    # token was `[FA]`. If we hit `[FF]` not preceded by `[FA]`, that's
    # the entry terminator.
    i = 0
    n = len(body)
    prev_was_fa = False
    while i < n:
        if body.startswith("[FF]", i):
            if prev_was_fa:
                # FF here is a kanji index byte (FA FF). Skip past.
                prev_was_fa = False
                i += 4
                continue
            # Found the terminator — KEEP `[FF]` in the body, trim the rest.
            end = i + 4
            trimmed = n - end
            return body[:end], trimmed
        if body.startswith("[FA]", i):
            prev_was_fa = True
            i += 4
            continue
        if body[i] == "[":
            # Skip past any other bracket token.
            close = body.find("]", i)
            if close == -1:
                # Malformed — just advance one char.
                i += 1
                prev_was_fa = False
                continue
            i = close + 1
            prev_was_fa = False
            continue
        i += 1
        prev_was_fa = False
    return body, 0


def process(path: Path, char_to_byte: dict[str, int],
            fa_table: dict[int, str], *, check_only: bool = False) -> dict:
    raw = path.read_bytes()
    is_utf16 = raw.startswith(b"\xff\xfe")
    text = raw.decode("utf-16" if is_utf16 else "utf-8")

    lines = text.split("\n")
    header_re = re.compile(r"^<<\$[0-9A-Fa-f]+:(\d+)\[")
    total_fa_replaced = 0
    total_chars_trimmed = 0
    entries_trimmed: list[tuple[str, int]] = []

    out_lines: list[str] = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        out_lines.append(line)
        m = header_re.match(line)
        if not m:
            continue
        # Next line is the entry body.
        if i + 1 >= len(lines):
            continue
        body = lines[i + 1]
        idx = m.group(1)

        new_body, fa_replaced = resolve_fa_escapes(body, char_to_byte, fa_table)
        new_body, trimmed = truncate_at_terminator(new_body)
        total_fa_replaced += fa_replaced
        total_chars_trimmed += trimmed
        if trimmed:
            entries_trimmed.append((idx, trimmed))
        out_lines.append(new_body)
        skip_next = True  # we already emitted the body via out_lines.append

    new_text = "\n".join(out_lines)
    new_raw = (
        (b"\xff\xfe" + new_text.encode("utf-16-le"))
        if is_utf16 else new_text.encode("utf-8")
    )
    summary = {
        "path": str(path),
        "fa_replaced": total_fa_replaced,
        "chars_trimmed": total_chars_trimmed,
        "entries_trimmed": entries_trimmed,
        "size_before": len(raw),
        "size_after": len(new_raw),
    }
    if not check_only:
        path.write_bytes(new_raw)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="don't write files, just report what would change")
    ap.add_argument("--table", default="tables/rbshura_jp.tbl",
                    help="table file holding FAxx kanji mappings")
    ap.add_argument("files", nargs="*",
                    default=["data/jp/scenario_28.txt",
                             "data/en/scenario_28.txt"],
                    help="dump files to clean")
    args = ap.parse_args(argv)

    table_path = (ROOT / args.table).resolve()
    char_to_byte, fa_table = load_tables(table_path)
    print(f"loaded {len(fa_table)} FAxx entries from {table_path.name}")
    print(f"loaded {len(char_to_byte)} single-byte char→byte mappings")

    for f in args.files:
        p = (ROOT / f).resolve()
        if not p.exists():
            print(f"  ⚠ {f} not found, skipping")
            continue
        s = process(p, char_to_byte, fa_table, check_only=args.check)
        verb = "would replace" if args.check else "replaced"
        verb2 = "would trim" if args.check else "trimmed"
        print(f"\n{s['path']}:")
        print(f"  {verb} {s['fa_replaced']} [FA]<X> → kanji")
        if s["entries_trimmed"]:
            for idx, trimmed in s["entries_trimmed"]:
                print(f"  {verb2} {trimmed} chars from entry {idx}")
        else:
            print(f"  no entries had garbage past terminator")
        print(f"  size {s['size_before']:,} → {s['size_after']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
