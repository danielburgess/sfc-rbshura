#!/usr/bin/env python3
"""Encode a UTF-16 script file (intro / scen 28 / etc.) back into ROM bytes.

Source format (matches what `tools/charnames.py extract` and the intro/scen-28
extractors produce):
  <<$BASE:N.label>>    or    <<$BASE:N[$PTR]>>
  body text with [XX] and [XX YY] bracket escapes for raw bytes,
  kana from tables/rbshura_jp.tbl, kanji from tables/intro_kanji.tbl
  (only when --kanji-escape is set; emitted as `FE XX` pairs).

Two encoding modes (controlled by --kanji-escape):

  off (default — dialog convention used by scens 0-13 and 28):
    All chars must be in the main table. `FE` is a 1-byte control.
  on (intro renderer convention):
    Chars not in the main table are looked up in tables/intro_kanji.tbl
    (reverse). When found, emitted as `FE XX` (2-byte kanji escape).

Usage:
    python tools/encode_jp_script.py data/jp/intro.txt --kanji-escape \\
        --out export/intro.bin
    python tools/encode_jp_script.py data/jp/scenario_28.txt --out export/scenario_28.bin
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
MAIN_TABLE = ROOT / "tables" / "rbshura_jp.tbl"
KANJI_TABLE = ROOT / "tables" / "intro_kanji.tbl"


def load_table(path: Path) -> dict[str, int]:
    """Parse a tbl file → {char: byte}. Multi-char entries (aliases) supported.
    Comments (`;`), `@ctrl_prefix`, `@ctrl X=N` declarations are ignored."""
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(";", 1)[0].strip()
        if not line or line.startswith("@"):
            continue
        m = re.match(r"([0-9A-Fa-f]{2})=(.+)$", line)
        if not m:
            continue
        byte_val = int(m.group(1), 16)
        ch = m.group(2).strip()
        # First mapping wins (don't clobber an earlier entry); skip empty.
        if ch and ch not in out:
            out[ch] = byte_val
    return out


HEADER_RE = re.compile(r"<<\$[0-9A-Fa-f]+:\d+(?:\[\$\d+\]|\.\w+)>>")
BRACKET_RE = re.compile(r"\[((?:[0-9A-Fa-f]{2}\s*)+)\]")


def encode_body(
    body: str,
    main: dict[str, int],
    kanji: dict[str, int] | None,
) -> bytes:
    """Encode one body string (between two `<<...>>` headers) into bytes."""
    out = bytearray()
    i = 0
    while i < len(body):
        # Bracketed raw byte(s): [XX] or [XX YY ...]
        m = BRACKET_RE.match(body, i)
        if m:
            for tok in m.group(1).split():
                out.append(int(tok, 16))
            i = m.end()
            continue
        ch = body[i]
        if ch in "\r\n":
            i += 1
            continue
        if ch in main:
            out.append(main[ch])
            i += 1
            continue
        if kanji is not None and ch in kanji:
            out.append(0xFE)
            out.append(kanji[ch])
            i += 1
            continue
        raise SystemExit(
            f"encode error: char {ch!r} (U+{ord(ch):04X}) at position {i} "
            f"not found in {'main + kanji' if kanji else 'main'} table"
        )
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path,
                    help="Source .txt (UTF-16, retrotool dump format)")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output binary path")
    ap.add_argument("--table", type=Path, default=MAIN_TABLE,
                    help=f"Primary char→byte table (default {MAIN_TABLE.name})")
    ap.add_argument("--kanji-escape", action="store_true",
                    help="Emit FE XX for chars not in the main table, "
                         f"looking them up in {KANJI_TABLE.name}")
    ap.add_argument("--entry", type=int, default=None,
                    help="Encode only entry N (default: concatenate all entries)")
    args = ap.parse_args()

    main_map = load_table(args.table)
    kanji_map = load_table(KANJI_TABLE) if args.kanji_escape else None

    text = args.input.read_text(encoding="utf-16")
    # Split on headers; even indices are bodies between/around headers.
    parts = HEADER_RE.split(text)
    # parts[0] is leading text (usually empty); subsequent entries are bodies,
    # ONE per header. Keep them positionally — do NOT drop whitespace-only
    # bodies, or `--entry N` would index the wrong entry (an empty body simply
    # encodes to zero bytes). Terminators are NOT appended here: the source
    # dumps already carry the entry terminator as a literal `[FF]` token.
    bodies = parts[1:]

    out = bytearray()
    if args.entry is not None:
        if args.entry >= len(bodies):
            sys.exit(f"entry {args.entry} out of range ({len(bodies)} bodies)")
        out += encode_body(bodies[args.entry], main_map, kanji_map)
    else:
        for body in bodies:
            out += encode_body(body, main_map, kanji_map)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(bytes(out))
    try:
        shown = args.out.relative_to(ROOT)
    except ValueError:
        shown = args.out
    print(f"wrote {shown} — {len(out)} bytes "
          f"from {len(bodies)} entries (main: {len(main_map)} chars"
          f"{f', kanji: {len(kanji_map)} chars' if kanji_map else ''})")


if __name__ == "__main__":
    main()
