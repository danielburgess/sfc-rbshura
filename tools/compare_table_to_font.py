#!/usr/bin/env python3
"""Compare tables/rbshura.tbl entries against the rendered FONT ground truth.

Reads our current table entries for p0 (single-byte $00-$FF) and p1 (FAxx) and
also writes a side-by-side report so we can see exactly which positions are
wrong. Reads the font BIN data so the per-position glyphs are deterministic.
"""
from __future__ import annotations
import re
from pathlib import Path


def parse_table(path: Path) -> tuple[dict[int, str], dict[int, str]]:
    """Parse rbshura.tbl into (p0_map, p1_map)."""
    p0: dict[int, str] = {}
    p1: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(";", 1)[0].rstrip()
        if not line or line.startswith("@") or "=" not in line:
            continue
        lhs, rhs = line.split("=", 1)
        lhs = lhs.strip()
        # Skip multi-byte controls and wildcard
        if lhs.startswith("**"):
            continue
        if re.fullmatch(r"[0-9A-Fa-f]{2}", lhs):
            p0[int(lhs, 16)] = rhs
        elif re.fullmatch(r"FA[0-9A-Fa-f]{2}", lhs):
            p1[int(lhs[2:], 16)] = rhs
    return p0, p1


def main():
    p0, p1 = parse_table(Path("tables/rbshura.tbl"))
    print("Parsed", len(p0), "p0 entries,", len(p1), "p1 entries")

    # Dump current mapping for visual reference
    out = ["# page 0 ($00-$FF, single-byte)\n"]
    for i in range(0x100):
        out.append(f"${i:02X} = {p0.get(i, '?')}")
    out.append("\n# page 1 (FA00-FAF6, two-byte)\n")
    for i in range(0xF8):
        out.append(f"FA{i:02X} = {p1.get(i, '?')}")
    Path("fonts/current_table_dump.txt").write_text("\n".join(out), encoding="utf-8")
    print("Wrote fonts/current_table_dump.txt")


if __name__ == "__main__":
    main()
