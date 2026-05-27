#!/usr/bin/env python3
"""Split translations from text/dialogue_dump_translated.txt into per-scenario
data/en/scenario_NN.txt files.

Strategy:
  1. Resolve git merge conflicts in the translated dump (keep "Stashed changes"
     side — preserves {NL}/{SPD}/{FC} control codes).
  2. Parse each entry: ;raw bytes + JP mnemonic + EN translation.
  3. Convert each entry's JP and EN mnemonics to retrotool bracket form, with
     the terminating [F7][XX] from the raw bytes appended.
  4. For each data/jp/scenario_NN.txt, do literal substring replacement of
     each JP bracketed-segment with its EN substitute. Untranslated entries
     fall through unchanged.

Mapping by substring (not address) sidesteps the off-by-one between
text_tool's PC and retrotool's data_addr.
"""
from __future__ import annotations

import re
from pathlib import Path

from retrotool.script.table import Table

from _paths import ROOT, TEXT, DATA_JP, DATA_EN, TABLES

DUMP_TRANSLATED = TEXT / "dialogue_dump_translated.txt"
RBSHURA_TBL = TABLES / "rbshura.tbl"

# ---------------------------------------------------------------------------
# Merge-conflict resolution
# ---------------------------------------------------------------------------

CONFLICT_RE = re.compile(
    r"<<<<<<< [^\n]*\n(?:.*?\n)*?=======\n((?:.*?\n)*?)>>>>>>> [^\n]*\n",
    re.MULTILINE,
)


def resolve_conflicts(text: str) -> str:
    """Replace each conflict block with the 'Stashed changes' side."""
    return CONFLICT_RE.sub(lambda m: m.group(1), text)


# ---------------------------------------------------------------------------
# Mnemonic → bracket conversion
# ---------------------------------------------------------------------------

MNEMONIC_RE = re.compile(
    r"\{(NL|PB|SPD|PORT|WIN|FC):?([^}]*)\}|\[([^\]]+)\]"
)


def mnemonic_to_bracket(text: str) -> str:
    """Convert text_tool mnemonics to retrotool bracket form.

    Mappings:
      {NL}            -> [FD]
      {PB}            -> [FE]
      {SPD:XX}        -> [F8][XX]
      {PORT:XX}       -> [F9][XX]
      {WIN:XX}        -> [FB][XX]
      {FC:XX,YY}      -> [FC][XX][YY]
      {FC:XX,YY,ZZ}   -> [FC][XX][YY][ZZ]
      [FA:XX]         -> [FA][XX]
      [XX]            -> [XX]
    Plain characters pass through.
    """
    out: list[str] = []
    pos = 0
    for m in MNEMONIC_RE.finditer(text):
        out.append(text[pos:m.start()])
        tag = m.group(1)
        param = m.group(2)
        bracket_body = m.group(3)
        if tag == "NL":
            out.append("[FD]")
        elif tag == "PB":
            out.append("[FE]")
        elif tag == "SPD":
            out.append(f"[F8][{param.upper()}]")
        elif tag == "PORT":
            out.append(f"[F9][{param.upper()}]")
        elif tag == "WIN":
            out.append(f"[FB][{param.upper()}]")
        elif tag == "FC":
            parts = [p.strip().upper() for p in param.split(",") if p.strip()]
            out.append("[FC]" + "".join(f"[{p}]" for p in parts))
        elif bracket_body is not None:
            if ":" in bracket_body:
                pre, val = bracket_body.split(":", 1)
                out.append(f"[{pre.upper()}][{val.upper()}]")
            else:
                out.append(f"[{bracket_body.upper()}]")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Translated-dump parser
# ---------------------------------------------------------------------------

ENTRY_HEADER_RE = re.compile(
    r"@(\d+)\s+PC=\$([0-9A-Fa-f]+)\s+BANK=(\S+)\s+END=([0-9A-Fa-f]+)"
)


def parse_translated_dump(text: str) -> list[dict]:
    """Parse the conflict-resolved translated dump into a list of entries."""
    entries: list[dict] = []
    current: dict | None = None
    have_jp = False

    for raw_line in text.split("\n"):
        line = raw_line.rstrip("\r")
        if line.startswith("#") or line == "":
            if current is not None:
                entries.append(current)
                current = None
                have_jp = False
            continue
        if line.startswith("@"):
            if current is not None:
                entries.append(current)
            m = ENTRY_HEADER_RE.match(line)
            current = {
                "id": int(m.group(1)),
                "pc": int(m.group(2), 16),
                "bank": m.group(3),
                "end_param": int(m.group(4), 16),
                "raw": "",
                "jp": "",
                "en": "",
            }
            have_jp = False
        elif current is None:
            continue
        elif line.startswith(";raw:"):
            current["raw"] = line[5:].strip()
        elif line.startswith(">"):
            current["en"] = line[1:]
        elif not have_jp:
            current["jp"] = line
            have_jp = True
    if current is not None:
        entries.append(current)
    return entries


def raw_hex_to_bytes(raw_hex: str) -> bytes:
    """Convert text_tool's space-separated hex string to bytes."""
    flat: list[int] = []
    for t in raw_hex.split():
        for i in range(0, len(t), 2):
            flat.append(int(t[i:i+2], 16))
    return bytes(flat)


def raw_hex_to_terminator_bytes(raw_hex: str) -> str | None:
    """Return the [F7][XX] tail from a ;raw: hex string, or None if missing."""
    flat = raw_hex_to_bytes(raw_hex)
    if len(flat) >= 2 and flat[-2] == 0xF7:
        return f"[F7][{flat[-1]:02X}]"
    return None


# ---------------------------------------------------------------------------
# Splitter
# ---------------------------------------------------------------------------

def build_substitutions(
    entries: list[dict], table: Table
) -> list[tuple[str, str]]:
    """Return list of (jp_bracket_segment, en_bracket_segment) pairs ready
    for substring replacement. Skips entries with empty/whitespace translations.

    JP segment is decoded directly from ;raw: bytes via retrotool's table —
    byte-faithful to data/jp output. EN segment is mnemonic→bracket converted
    + the trailing [F7][XX] from the raw bytes.
    """
    subs: list[tuple[str, str]] = []
    for e in entries:
        en = (e["en"] or "").strip()
        if not en:
            continue
        terminator = raw_hex_to_terminator_bytes(e["raw"])
        if terminator is None:
            continue
        raw_bytes = raw_hex_to_bytes(e["raw"])
        # text_tool's scanner sometimes prepends the previous entry's
        # F7-XX continuation marker. Strip leading [F7][XX] so the JP
        # segment aligns with data/jp (where each entry starts at a
        # pointer-table target).
        if len(raw_bytes) >= 2 and raw_bytes[0] == 0xF7:
            raw_bytes = raw_bytes[2:]
        # JP segment as retrotool would render it. No trim_bytes — we want
        # the trailing terminator preserved so the substring match is
        # anchored at the entry boundary.
        jp_bracket = table.interpret_binary_data(
            list(raw_bytes), max_bytes=3
        )
        en_bracket = mnemonic_to_bracket(e["en"]) + terminator
        if jp_bracket == en_bracket:
            continue
        subs.append((jp_bracket, en_bracket))
    return subs


def apply_substitutions(text: str, subs: list[tuple[str, str]]) -> tuple[str, int]:
    """Apply all substitutions; return (new_text, hit_count). Longest JP
    segments first so shorter ones can't pre-match inside a longer one."""
    hits = 0
    subs_sorted = sorted(subs, key=lambda p: -len(p[0]))
    for jp, en in subs_sorted:
        if jp in text:
            count = text.count(jp)
            text = text.replace(jp, en)
            hits += count
    return text, hits


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    raw = DUMP_TRANSLATED.read_text(encoding="utf-8")
    resolved = resolve_conflicts(raw)
    n_conflict_markers = sum(
        resolved.count(s) for s in ("<<<<<<<", "=======", ">>>>>>>")
    )
    if n_conflict_markers:
        raise RuntimeError(
            f"Unresolved conflict markers remain after sanitize: {n_conflict_markers}"
        )

    entries = parse_translated_dump(resolved)
    translated = [e for e in entries if (e["en"] or "").strip()]
    print(f"Parsed {len(entries)} entries; {len(translated)} have translations.")

    table = Table(str(RBSHURA_TBL))
    subs = build_substitutions(entries, table)
    print(f"Built {len(subs)} JP→EN substitutions.")

    DATA_EN.mkdir(parents=True, exist_ok=True)
    total_hits = 0
    for jp_file in sorted(DATA_JP.glob("scenario_*.txt")):
        body = jp_file.read_text(encoding="utf-16")
        new_body, hits = apply_substitutions(body, subs)
        out = DATA_EN / jp_file.name
        out.write_text(new_body, encoding="utf-16")
        total_hits += hits
        print(f"  {jp_file.name}: {hits} substitutions")

    print(f"\nTotal substitutions applied across all scenarios: {total_hits}")


if __name__ == "__main__":
    main()
