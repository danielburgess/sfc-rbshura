"""Canonical project paths — single source of truth for the repo layout.

After the 2026-05-26 reorganization the tree is split into:
  * ``roms/``  — pristine source ROMs (build inputs, never written by tools)
  * ``out/``   — build artifacts (written by scripts/build_24bit.py)

Tools historically hardcoded ``Path(__file__).parent`` (which breaks the moment
a script moves between the repo root and ``tools/``) or bare cwd-relative paths
like ``"rbshura.sfc"`` (which broke when ROMs moved into ``roms/``). Import the
constants below instead so the layout lives in exactly one place.

Usage (tools run as ``python tools/<name>.py`` have ``tools/`` on ``sys.path``)::

    from _paths import ROOT, PRISTINE_ROM, BUILT_ROM, DATA_JP
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ROMS = ROOT / "roms"
OUT = ROOT / "out"
DATA = ROOT / "data"
DATA_JP = DATA / "jp"
DATA_EN = DATA / "en"
TABLES = ROOT / "tables"
FONTS = ROOT / "fonts"
TEXT = ROOT / "text"

# Common ROM files.
PRISTINE_ROM = ROMS / "rbshura.sfc"          # pristine JP source (build input)
PK_ROM = ROMS / "peacekeepers.sfc"           # Peacekeepers EN reference ROM
BUILT_ROM = OUT / "rbshura_en.sfc"           # default build artifact (from [rom].name + output_dir)
