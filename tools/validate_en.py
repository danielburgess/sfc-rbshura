#!/usr/bin/env python3
"""Structural validation of data/en/*.txt against data/jp/*.txt.

Checks:
  1. Same entry count per scenario.
  2. Each entry header `<<$ptr:idx[$data]>>` is identical between jp/en.
  3. Translated entries that carry an `[F7][XX]` terminator keep it intact.
     (Not every entry ends in `[F7][XX]` — ~40% legitimately don't — so this
     is only checked on translated entries that contain one in JP.)
  4. No leftover text_tool mnemonics ({SPD}, {NL}, {FC}, etc.) in any body.
  5. Reports translated vs untranslated counts (informational, not a pass/fail).
"""
from __future__ import annotations
import re
import sys

from _paths import DATA_JP, DATA_EN

HEADER_RE = re.compile(r"^<<\$\d+:\d+\[\$\d+\]>>$")
MNEMONIC_RE = re.compile(r"\{(NL|PB|SPD|PORT|WIN|FC)(?::|})")
# Case-insensitive: a hand-edited lowercase `[f7][ff]` is still a valid
# terminator and must not be misreported as missing.
TERMINATOR_RE = re.compile(r"\[F7\]\[[0-9A-F]{2}\]", re.IGNORECASE)


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

            # Leftover text_tool mnemonics are illegal in ANY retrotool-format
            # body (jp or en), so check every entry regardless of translation
            # state — an entry that regressed to JP bytes shouldn't escape this.
            if MNEMONIC_RE.search(en_b):
                errors.append(
                    f"{en_file.name}: entry {idx} leftover mnemonic in EN: {en_b[:80]!r}"
                )

            if jp_b == en_b:
                untranslated += 1
                continue
            translated += 1
            # Terminator check only where JP actually had one: ~40% of entries
            # legitimately end without [F7][XX], so requiring it everywhere
            # would be a false positive. If JP carried it, EN must keep it.
            if TERMINATOR_RE.search(jp_b) and not TERMINATOR_RE.search(en_b):
                errors.append(
                    f"{en_file.name}: entry {idx} dropped its [F7][XX] terminator: {en_b[:80]!r}"
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
