#!/usr/bin/env python3
"""Structural validation of data/en/*.txt against data/jp/*.txt.

Checks:
  1. Same entry count per scenario.
  2. Each entry header `<<$ptr:idx[$data]>>` is identical between jp/en.
  3. Every EN body ends with `[F7][XX]` (terminator preserved).
  4. No leftover mnemonics ({SPD}, {NL}, {FC}, etc.) in EN bodies.
  5. Translated entries differ from JP; untranslated entries match JP exactly.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA_JP = ROOT / "data" / "jp"
DATA_EN = ROOT / "data" / "en"

HEADER_RE = re.compile(r"^<<\$\d+:\d+\[\$\d+\]>>$")
MNEMONIC_RE = re.compile(r"\{(NL|PB|SPD|PORT|WIN|FC)(?::|})")
TERMINATOR_RE = re.compile(r"\[F7\]\[[0-9A-F]{2}\]")


def parse_entries(text: str) -> list[tuple[str, str]]:
    """Return list of (header_line, body_line) pairs."""
    lines = text.split("\n")
    entries: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        if HEADER_RE.match(lines[i]):
            header = lines[i]
            body = lines[i + 1] if i + 1 < len(lines) else ""
            entries.append((header, body))
            i += 2
        else:
            i += 1
    return entries


def main() -> int:
    errors: list[str] = []
    translated_total = 0
    untranslated_total = 0

    for jp_file in sorted(DATA_JP.glob("scenario_*.txt")):
        en_file = DATA_EN / jp_file.name
        if not en_file.exists():
            errors.append(f"{en_file.name}: missing")
            continue
        jp_entries = parse_entries(jp_file.read_text(encoding="utf-16"))
        en_entries = parse_entries(en_file.read_text(encoding="utf-16"))

        if len(jp_entries) != len(en_entries):
            errors.append(
                f"{en_file.name}: entry count {len(en_entries)} != JP {len(jp_entries)}"
            )
            continue

        translated = 0
        untranslated = 0
        for idx, ((jp_h, jp_b), (en_h, en_b)) in enumerate(zip(jp_entries, en_entries)):
            if jp_h != en_h:
                errors.append(f"{en_file.name}: entry {idx} header mismatch")
                continue
            if jp_b == en_b:
                untranslated += 1
                continue
            translated += 1
            if not TERMINATOR_RE.search(en_b):
                errors.append(
                    f"{en_file.name}: entry {idx} EN body has no [F7][XX] terminator: {en_b[:80]!r}"
                )
            if MNEMONIC_RE.search(en_b):
                errors.append(
                    f"{en_file.name}: entry {idx} leftover mnemonic in EN: {en_b[:80]!r}"
                )

        translated_total += translated
        untranslated_total += untranslated
        print(f"  {en_file.name}: {translated:3d} translated, {untranslated:3d} untranslated")

    print(f"\nTotal: {translated_total} translated, {untranslated_total} untranslated")
    if errors:
        print(f"\n{len(errors)} errors:")
        for e in errors[:20]:
            print(f"  {e}")
        return 1
    print("\nAll structural checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
