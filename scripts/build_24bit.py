#!/usr/bin/env python3
"""Build the EN rbshura ROM via retrotool.

Everything — PK font binary, tight-8 renderer patch, 24-bit pointer engine
patch, char_names HUD table, and all 14 scenario string tables — is declared
in project.toml as a section. This script is a thin wrapper around
`retrotool build_project()` so the build pipeline is exactly one call.

Regeneration utilities (run only when their inputs change):
  - tools/charnames.py extract    — re-dump HUD names from rbshura.sfc
  - apply_pk_font.py              — rebuild fonts/rbshura_en.bin + tables/rbshura_en.tbl
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).parent.parent


def main() -> None:
    from retrotool.build import build_project
    # No explicit output= : the path is derived from [rom].name +
    # [rom.build].output_dir in project.toml (→ out/rbshura_en.sfc).
    # build_project() prints its own summary (resolved path + checksum).
    result = build_project(path=str(ROOT), no_cache=True)
    print(f"  → {result.rom_size:,} B · {len(result.sections)} sections "
          f"· ${result.checksum:04X}")


if __name__ == "__main__":
    main()
