#!/usr/bin/env python3
"""script_editor.py — Rushing Beat Shura EN script editor.

Lets you edit `data/en/scenario_NN.txt` files with a live preview that
matches the in-game dialog rendering:

  - Half-width font: each glyph is 8x16 (1 tile column wide × 2 tiles tall),
    matching the apply_pk_font.py tight renderer that ships in the build.
  - 24 chars per line (192 px wide text region — the in-game dialog box).
  - Control codes parsed and visualized: [FD]=newline, [FE]=page break,
    [F7:FF]=page-wait, [FB:XX]=window cmd, [FC:...] etc.

Autosave: debounced (~400 ms) per-entry; writes are atomic via temp+rename.

Portrait preview is a static placeholder showing the speaker name parsed
from the entry's [F9:XX] control code. Real sprite + animation is a
follow-up (needs portrait-table RE).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image

ROOT = Path(__file__).parent


def _load_project_config(root: Path) -> dict:
    """Pull editor defaults from project.toml so the editor follows the build.

    Reads `build_lang` + the `<lang>_data_dir` scalars to pick which language's
    script to edit, plus `jp_data_dir`, the matching `tables/rbshura_<lang>.tbl`,
    and the built ROM name (`[rom].name` under `[rom.build].output_dir`). Every
    value is optional — missing project.toml or keys fall back to the EN
    defaults below. Returns absolute Paths.
    """
    cfg: dict = {}
    pt = root / "project.toml"
    if not pt.exists():
        return cfg
    try:
        import tomllib
        with pt.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return cfg

    dirs = {
        k[: -len("_data_dir")].lower(): v
        for k, v in data.items()
        if isinstance(k, str) and k.endswith("_data_dir") and isinstance(v, str) and v
    }
    lang = data.get("build_lang")
    lang = lang.lower() if isinstance(lang, str) and lang else "en"
    cfg["lang"] = lang

    src = dirs.get(lang) or dirs.get("en")          # build language's script dir
    if src:
        cfg["data_dir"] = (root / src).resolve()
    if dirs.get("jp"):
        cfg["jp_dir"] = (root / dirs["jp"]).resolve()

    tbl = root / "tables" / f"rbshura_{lang}.tbl"
    if tbl.exists():
        cfg["table"] = tbl

    rom = data.get("rom") or {}
    name = rom.get("name")
    out_dir = (rom.get("build") or {}).get("output_dir", "out")
    if isinstance(name, str) and name:
        cfg["rom"] = (root / out_dir / f"{name}.sfc").resolve()
    return cfg


_PROJECT = _load_project_config(ROOT)

# Defaults follow project.toml's `build_lang` (the editor edits whatever the
# project currently builds — e.g. data/br_pt), with EN fallbacks for a bare
# checkout. All are overridable per-user via set_settings()/pick_folder().
DEFAULT_EN_DATA_DIR = _PROJECT.get("data_dir") or (ROOT / "data" / "en")
DEFAULT_JP_DATA_DIR = _PROJECT.get("jp_dir") or (ROOT / "data" / "jp")
EN_TABLE_PATH = _PROJECT.get("table") or (ROOT / "tables" / "rbshura_en.tbl")
PORTRAIT_ASSETS = ROOT / "assets" / "portraits"

# Per-user editor state (last scenario / entry / cursor + folder config).
# Project-local so it travels with the checkout if someone re-clones.
# JSON, gitignored.
EDITOR_STATE_PATH = ROOT / ".editor-state.json"

# Kept as a module-level constant for backward compatibility with any
# scripts that import this. Bridge instances use self.en_data_dir which
# may be overridden via set_settings().
EN_DATA_DIR = DEFAULT_EN_DATA_DIR

FONT_SLOT_STRIDE = 64        # rbshura's per-glyph slot
# Preview font: prefer the relocated/extended font (fonts/rbshura_font_ext.bin)
# — it carries the pt-BR accent glyphs (slots 0x4C..0x58), so accented text
# previews correctly. Fall back to the 80-slot base font (fonts/rbshura_en.bin,
# what the build pastes at $100000). Read directly so the preview reflects the
# current font without a full build. Palettes still come from the ROM ($058313).
_EXT_FONT = ROOT / "fonts" / "rbshura_font_ext.bin"
FONT_BIN_PATH = _EXT_FONT if _EXT_FONT.exists() else (ROOT / "fonts" / "rbshura_en.bin")
# Glyph count = however many 64-byte slots the chosen font actually has (89 for
# the extended font, 80 for the base) — drives the font-tile preview grid.
FONT_GLYPH_COUNT = (FONT_BIN_PATH.stat().st_size // FONT_SLOT_STRIDE
                    if FONT_BIN_PATH.exists() else 80)
ROM_CANDIDATES = [c for c in (_PROJECT.get("rom"),) if c] + [
    ROOT / "out/rbshura_br_pt.sfc",
    ROOT / "out/rbshura_en.sfc",
    ROOT / "out/rbshura_pkfont_24bit.sfc",
    ROOT / "out/rbshura_pkfont.sfc",
]
FONT_PC = 0x100000           # absolute ROM offset (kept for reference / extract logic)

# Kanji font (intro renderer's FE-escape table). 256 × 64 B = 16 KB at ROM
# $104000. Each glyph is 16x16 = 4 tiles in TL/TR/BL/BR order. See
# tables/intro_kanji.tbl for the byte→char mapping.
KANJI_FONT_OFFSET = 0x104000
KANJI_GLYPH_COUNT = 256

# Per-file rendering config. Files not listed default to dialog rendering
# (24 cols, FE=1-byte page break, in-game dialog box compositing).
SCENARIO_CONFIG: dict[str, dict] = {
    "intro": {
        # `cols_per_line` is in HALF-CELL UNITS (one 8-px tile column) so
        # the wrap math works for mixed half-width/full-width content:
        #   * Half-width glyph (Latin / dialog kana, 8 px wide) = 1 unit
        #   * Full-width glyph (kanji, 16 px wide)              = 2 units
        # 32 units = 256 px = SNES screen width, matching the in-game
        # intro renderer's pixel-wrap behavior.
        "cols_per_line": 32,
        # In the intro encoding, FE XX is a 2-byte kanji escape (XX
        # indexes the kanji font at $104000). The dialog engine treats
        # FE as a 1-byte page break — this flag flips the parse.
        "kanji_escape": True,
        # Render half-width and full-width glyphs at their natural pixel
        # widths instead of forcing every cell to 16 px. Lets Latin
        # translations stay legible (without 2× horizontal stretching)
        # and matches how the in-game intro lays out text.
        "mixed_width": True,
        # Intro is full-screen on a dark backdrop, not a bordered dialog
        # box. We still draw a thin frame around the preview for
        # legibility but skip the speaker-palette compositing.
        "dialog_box": False,
    },
    # Character-ending narration screens ($1F:C57F idx 1-19) — half-width,
    # render-at-once, 32 tile-columns wide like the intro. Pure Latin (no
    # kanji escape). See tables/narration.toml / patches/narration_render.asm.
    "narration_screens": {
        "cols_per_line": 32,
        "kanji_escape": False,
        "mixed_width": True,
        "dialog_box": False,
    },
}

# Half-width font geometry (matches apply_pk_font.py / the in-game renderer)
GLYPH_W = 8
GLYPH_H = 16
TILE_BYTES = 16              # 8x8 @ 2bpp = 16 B
BYTES_PER_GLYPH = 32         # top tile + bottom tile (game DMAs first 32B)
COLS_PER_LINE = 24           # in-game dialog box width
SCALE = 3                    # preview zoom

# Per-portrait text palette table in ROM. Discovered 2026-05-17 via
# SplitTrace CGRAM diff (see [[project_dialog_color_engine]]). The text
# uses BG3 in 2bpp Mode 1 → palette 7 → CGRAM colors 28-31. The 4 colors
# are loaded into CGRAM from this table when [F9:XX] fires.
#
# Layout: tables interleaved at stride 4 bytes per portrait_id. For
# portrait N, the 4 BGR555 colors are at file offsets:
#   $058313 + N*4   (color 0 — dialog backdrop)
#   $058315 + N*4   (color 1 — outline / "speaker tint" — most visible)
#   $058317 + N*4   (color 2 — mid tone)
#   $058319 + N*4   (color 3 — bright text)
# Adjacent portraits share 2 of their 4 colors (the stride is 4, not 8).
PALETTE_TABLE_PC = 0x058313

# Fallback palette when no F9 is parseable (off-white serif on dark backdrop,
# closest to portrait 0's approximate look). Used if ROM extraction fails.
FALLBACK_PALETTE = [
    (8, 48, 8, 255),         # 0: dark backdrop (unused — see DIALOG_BG)
    (16, 96, 144, 255),      # 1: blue outline
    (136, 184, 184, 255),    # 2: mid cyan
    (240, 248, 248, 255),    # 3: near-white
]

# Approximated in-game dialog window backdrop. The real backdrop is drawn
# by a separate BG layer (likely BG2) that we haven't extracted yet; this
# is a stand-in matching the dark blue-black tone visible in the SplitTrace
# screenshots. (Future: extract actual BG2 tilemap + palette per
# [[project_script_editor]] Step 2.)
DIALOG_BG = (16, 24, 48, 255)

# Portrait names (parsed from [F9][XX]). NAMES ARE NOT YET VERIFIED — the
# previous mapping (Dick/Spider/Kythring/McCoy/Jimmy/Dag) was inherited
# from an older preview script and confirmed wrong by user 2026-05-17.
# User direction: extract sprites first, identify names visually from those.
# Currently 2 portraits captured (assets/portraits/pid_00.png and
# pid_02.png from SplitTrace crops); rest are pending more captures.
PORTRAIT_NAMES: dict[int, str] = {}  # left empty until verified


# ---------------------------------------------------------------------------
# Font extraction
# ---------------------------------------------------------------------------

def _decode_tile_2bpp(buf: bytes, off: int) -> list[int]:
    """Decode one 8x8 2bpp tile (16 bytes) into 64 palette indices."""
    out = [0] * 64
    for r in range(8):
        b0 = buf[off + r * 2]
        b1 = buf[off + r * 2 + 1]
        for c in range(8):
            bit = 7 - c
            out[r * 8 + c] = ((b0 >> bit) & 1) | (((b1 >> bit) & 1) << 1)
    return out


def _pick_rom() -> Path:
    for c in ROM_CANDIDATES:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"none of {[str(c.name) for c in ROM_CANDIDATES]} found — "
        f"run retrotool build project.toml first."
    )


def _bgr555_to_rgba(word: int) -> tuple[int, int, int, int]:
    """SNES 15-bit BGR555 → 32-bit RGBA (3-bit-left-shift for the 5→8 expand)."""
    r = (word & 0x1F) << 3
    g = ((word >> 5) & 0x1F) << 3
    b = ((word >> 10) & 0x1F) << 3
    return (r, g, b, 255)


def load_portrait_palettes(rom_bytes: bytes, n_portraits: int = 16) -> list[list[tuple[int, int, int, int]]]:
    """Extract the per-portrait dialog text palettes from the ROM.

    Returns a list of 4-color RGBA palettes, indexed by portrait_id. Each
    palette is `[bg_backdrop, outline_tint, mid, bright]`.
    """
    out = []
    for pid in range(n_portraits):
        base = PALETTE_TABLE_PC + pid * 4
        if base + 8 > len(rom_bytes):
            break
        words = [
            rom_bytes[base + 0] | (rom_bytes[base + 1] << 8),
            rom_bytes[base + 2] | (rom_bytes[base + 3] << 8),
            rom_bytes[base + 4] | (rom_bytes[base + 5] << 8),
            rom_bytes[base + 6] | (rom_bytes[base + 7] << 8),
        ]
        out.append([_bgr555_to_rgba(w) for w in words])
    return out


def _build_atlas_for_palette(
    font_buf: bytes, palette: list[tuple[int, int, int, int]]
) -> Image.Image:
    """Decode the half-width font from `font_buf` (fonts/rbshura_en.bin
    layout: 80 × 64B slots, top tile + bottom tile in the first 32B of each).
    `palette` is the 4-color speaker palette; pixel value 0 is rendered
    transparent so the dialog backdrop shows through (palette[0] is filled
    separately by _draw_dialog_box).
    """
    cols = 16
    rows = (FONT_GLYPH_COUNT + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * GLYPH_W, rows * GLYPH_H), (0, 0, 0, 0))
    render_pal = [(0, 0, 0, 0)] + palette[1:]
    for gi in range(FONT_GLYPH_COUNT):
        base = gi * FONT_SLOT_STRIDE
        if base + BYTES_PER_GLYPH > len(font_buf):
            break
        top = _decode_tile_2bpp(font_buf, base)
        bot = _decode_tile_2bpp(font_buf, base + TILE_BYTES)
        gx = (gi % cols) * GLYPH_W
        gy = (gi // cols) * GLYPH_H
        for py in range(8):
            for px in range(8):
                atlas.putpixel((gx + px, gy + py), render_pal[top[py * 8 + px]])
                atlas.putpixel((gx + px, gy + 8 + py), render_pal[bot[py * 8 + px]])
    return atlas


# Each kanji glyph is rendered at 16×16 (4 × 8×8 tiles), distinct from the
# half-width kana glyph (8×16) used by the dialog font.
KANJI_W = KANJI_H = 16


def _build_kanji_atlas(rom: bytes, palette: list[tuple[int, int, int, int]]) -> Image.Image:
    """Decode the FE-escape kanji font from ROM at $104000 into a 16×16-cells
    grid atlas. Each glyph is 4 × 16 B 2bpp tiles in TL/TR/BL/BR order; the
    atlas is laid out 16 columns wide (so kanji byte index N → atlas cell
    (N%16, N//16))."""
    cols = 16
    rows = (KANJI_GLYPH_COUNT + cols - 1) // cols
    atlas = Image.new("RGBA",
                      (cols * KANJI_W, rows * KANJI_H),
                      (0, 0, 0, 0))
    render_pal = [(0, 0, 0, 0)] + palette[1:]
    base = KANJI_FONT_OFFSET
    for gi in range(KANJI_GLYPH_COUNT):
        off = base + gi * 64    # 4 tiles × 16 B
        if off + 64 > len(rom):
            break
        tl = _decode_tile_2bpp(rom, off)
        tr = _decode_tile_2bpp(rom, off + 16)
        bl = _decode_tile_2bpp(rom, off + 32)
        br = _decode_tile_2bpp(rom, off + 48)
        gx = (gi % cols) * KANJI_W
        gy = (gi // cols) * KANJI_H
        for py in range(8):
            for px in range(8):
                atlas.putpixel((gx + px,     gy + py),     render_pal[tl[py * 8 + px]])
                atlas.putpixel((gx + 8 + px, gy + py),     render_pal[tr[py * 8 + px]])
                atlas.putpixel((gx + px,     gy + 8 + py), render_pal[bl[py * 8 + px]])
                atlas.putpixel((gx + 8 + px, gy + 8 + py), render_pal[br[py * 8 + px]])
    return atlas


def load_font_atlases() -> tuple[bytes, list[list[tuple[int, int, int, int]]], dict[int, Image.Image]]:
    """Load font bin + extract palettes from ROM + pre-render one atlas per
    speaker.

    Returns (rom_bytes, palettes, atlas_by_portrait_id). rom_bytes is kept
    in the tuple for callers that still need ROM data (palette extraction,
    etc.) — font tiles themselves come from fonts/rbshura_en.bin.
    """
    rom_path = _pick_rom()
    if not FONT_BIN_PATH.exists():
        raise FileNotFoundError(
            f"{FONT_BIN_PATH} missing — regenerate with `python apply_pk_font.py`"
        )
    print(f"  font source:    {FONT_BIN_PATH.name}")
    print(f"  palette source: {rom_path.name}")
    font_buf = FONT_BIN_PATH.read_bytes()
    rom = rom_path.read_bytes()
    palettes = load_portrait_palettes(rom)
    print(f"  extracted {len(palettes)} per-portrait palettes from ${PALETTE_TABLE_PC:06X}")
    atlases: dict[int, Image.Image] = {}
    for pid, pal in enumerate(palettes):
        atlases[pid] = _build_atlas_for_palette(font_buf, pal)
    return rom, palettes, atlases


# Kept for backward compatibility (older test scaffolding) — uses portrait 0's
# palette as a default neutral atlas.
def load_font_atlas() -> Image.Image:
    rom_path = _pick_rom()
    font_buf = FONT_BIN_PATH.read_bytes()
    palettes = load_portrait_palettes(rom_path.read_bytes())
    return _build_atlas_for_palette(font_buf, palettes[0] if palettes else FALLBACK_PALETTE)


# ---------------------------------------------------------------------------
# rbshura_en.tbl — char ↔ byte mapping
# ---------------------------------------------------------------------------

def _load_jp_kana_table() -> dict[str, int]:
    """Parse tables/rbshura_jp.tbl into a {char: byte} reverse map.

    Used as a fallback in `body_to_lines` when the primary EN table doesn't
    know a character — lets us preview JP source files (with kana literals
    like サイバークローン) without showing them as blank cells.
    """
    path = ROOT / "tables" / "rbshura_jp.tbl"
    out: dict[str, int] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(";", 1)[0].strip()
        if not line or "=" not in line or line.startswith("@"):
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if len(k) != 2:
            continue
        try:
            byte = int(k, 16)
        except ValueError:
            continue
        if v and v not in out:
            out[v] = byte
    return out


def _load_kanji_table() -> dict[str, int]:
    """Parse tables/intro_kanji.tbl into a {kanji_char: byte_xx} map.

    The intro renderer encodes kanji as `FE XX` where XX indexes the kanji
    font at $104000. This reverse table lets us look up a kanji char back to
    its XX byte when rendering edited intro text.
    """
    path = ROOT / "tables" / "intro_kanji.tbl"
    out: dict[str, int] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        # Strip inline `;` comments + whitespace.
        line = line.split(";", 1)[0].strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(k) != 2:
            continue
        try:
            byte = int(k, 16)
        except ValueError:
            continue
        # First mapping wins (so AE=義 stays even if user later edits and
        # confuses the parser with a duplicate).
        if v and v not in out:
            out[v] = byte
    return out


def load_table() -> dict[str, int]:
    """Parse tables/rbshura_en.tbl into a {char: byte_value} map for EN text.

    Format: lines of `XX=c` where XX is hex byte and c is the character.
    Reverse direction (char→byte) is what we need to encode text into glyphs.
    """
    if not EN_TABLE_PATH.exists():
        raise FileNotFoundError(EN_TABLE_PATH)
    char_to_byte: dict[str, int] = {}
    for line in EN_TABLE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("@"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        # Reject multi-byte (XXYY=...) entries; we only want single-byte.
        if len(k) != 2:
            continue
        try:
            byte = int(k, 16)
        except ValueError:
            continue
        # Skip control-byte range (F7-FF) — those are opcodes, not chars.
        if byte >= 0xF7:
            continue
        if v and v not in char_to_byte:
            char_to_byte[v] = byte
    # Always allow literal space → 0x00 (half-width-font convention).
    char_to_byte.setdefault(" ", 0x00)
    return char_to_byte


# ---------------------------------------------------------------------------
# Scenario file model
# ---------------------------------------------------------------------------

# Two header forms in play:
#   * Pointer-table scripts (scenario_NN.txt) — `<<$DEC:idx[$DEC]>>`
#   * Fixed-records DataDefs (char_names.txt) — `<<$HEX:idx.label>>`
# Both share `<<$ANY:idx <suffix> >>`. We keep the suffix in the trailer
# group and replay the original header verbatim on save so each file
# round-trips to the form its handler expects.
ENTRY_HEADER_RE = re.compile(r"<<\$([0-9A-Fa-f]+):(\d+)(\[\$\d+\]|\.\w+)>>")


class Scenario:
    """One scenario_NN.txt — list of (header, idx, body) entries."""
    def __init__(self, path: Path):
        self.path = path
        self.raw: str = ""
        self.entries: list[dict] = []  # each: {header, idx, body}
        self.reload()

    def reload(self) -> None:
        self.raw = self.path.read_text(encoding="utf-16")
        self.entries = []
        parts = re.split(r"(<<\$[0-9A-Fa-f]+:\d+(?:\[\$\d+\]|\.\w+)>>)\n", self.raw)
        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            m = ENTRY_HEADER_RE.match(header)
            if not m:
                continue
            body = body.rstrip("\n")
            self.entries.append({
                "header": header,
                "idx": int(m.group(2)),
                "body": body,
            })

    def save_entry(self, entry_idx: int, new_body: str) -> None:
        """Rewrite one entry's body and write the full file atomically."""
        self.entries[entry_idx]["body"] = new_body
        out = [f"{e['header']}\n{e['body']}\n" for e in self.entries]
        content = "".join(out)
        # Atomic write: temp file in same dir → rename
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-16") as f:
                f.write(content)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise


# ---------------------------------------------------------------------------
# Body → glyph indices (with control-code handling)
# ---------------------------------------------------------------------------

def _tokenize_brackets(body: str) -> list:
    """Tokenize a body string into a stream of items:
      - ('byte', int)   — a [XX] bracketed byte
      - ('char', str)   — a non-bracket character (Latin letter, punctuation, etc.)
      - ('nl', None)    — a literal newline in the source file

    Bracket contents may be in `[XX]` form (single hex byte) or `[XX:YY...]`
    form (legacy retrotool dump). We accept both: `[XX:YY]` produces two
    'byte' tokens YY followed by XX (no — actually XX is the opcode and YY
    is its param, both as bytes).
    """
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "[":
            end = body.find("]", i)
            if end == -1:
                # Stray '[' — render as literal so user can see it
                out.append(("char", c))
                i += 1
                continue
            token = body[i + 1:end]
            # Accept any of: [XX], [XX:YY:ZZ] (legacy retrotool dump), or
            # [XX YY ZZ] (space-separated, what our extractors emit).
            # Walk the token splitting on either separator.
            parts = re.split(r"[:\s]+", token.strip())
            valid = all(len(p) == 2 for p in parts if p)
            if valid and parts:
                for part in parts:
                    if not part:
                        continue
                    try:
                        out.append(("byte", int(part, 16)))
                    except ValueError:
                        out.append(("char", "[" + token + "]"))
                        break
            else:
                # Not a hex-byte bracket — render literal so user sees it.
                out.append(("char", "[" + token + "]"))
            i = end + 1
        elif c == "\n":
            out.append(("nl", None))
            i += 1
        else:
            out.append(("char", c))
            i += 1
    return out


# Per [[rbshura-encoding-semantics]]: opcode byte → total length (incl. opcode)
# F7-FB are all 2-byte (opcode + param). FC is 3 or 4 depending on subcommand:
#   FC 00 XX, FC 01 XX, FC 02 XX YY. FD/FE/FF are 1-byte standalone.
_OPCODE_LEN = {
    0xF7: 2, 0xF8: 2, 0xF9: 2, 0xFA: 2, 0xFB: 2,
    0xFD: 1, 0xFE: 1, 0xFF: 1,
}


def body_byte_count(
    body: str,
    char_to_byte: dict[str, int],
    cfg: Optional[dict] = None,
) -> int:
    """Count the encoded byte length of a body — what would land in ROM
    after running the encoder. Matches the lookup in body_to_lines: chars
    in `char_to_byte` cost 1 byte; chars only in `cfg['kanji_char_to_byte']`
    (with kanji_escape enabled) cost 2 (FE XX). Bracket tokens contribute
    their literal byte count; soft newlines are 0.

    The caller picks which table to pass — `self.char_to_byte` for the
    editable side, `self.jp_char_to_byte` for a JP reference, etc.
    """
    cfg = cfg or {}
    kanji_escape = bool(cfg.get("kanji_escape"))
    kanji_map = cfg.get("kanji_char_to_byte", {})

    total = 0
    for kind, val in _tokenize_brackets(body):
        if kind == "byte":
            total += 1
        elif kind == "char":
            if val in char_to_byte:
                total += 1
            elif kanji_escape and val in kanji_map:
                total += 2  # FE XX
            else:
                # Unknown char — count as 1 (placeholder space) so the
                # number doesn't lie about an editable file. The encoder
                # will fail with a clear error at build time.
                total += 1
        # 'nl' contributes 0
    return total


def body_to_lines(
    body: str,
    char_to_byte: dict[str, int],
    cfg: Optional[dict] = None,
) -> list:
    """Parse a body into renderable lines. Returns a list where each item is
    either a list[int] of glyph indices (a line) or None (page-break gutter).

    `cfg` overrides parse behavior per-file:
      - `kanji_escape: True`  → FE XX is a 2-byte kanji index (emitted as
        256 + XX so the renderer can route to the kanji atlas). Defaults to
        False (dialog convention: FE = 1-byte page break).
      - `cols_per_line: N`    → soft-wrap width (defaults to COLS_PER_LINE).

    Kanji glyph indices in the returned lines are encoded as `256 + XX`;
    kana glyphs stay 0..255. Renderer must dispatch on `v >= 256`.
    """
    cfg = cfg or {}
    kanji_escape = bool(cfg.get("kanji_escape"))
    cols = int(cfg.get("cols_per_line", COLS_PER_LINE))

    pages: list[list[list[int]]] = [[[]]]
    def current_line() -> list[int]: return pages[-1][-1]
    def new_line(): pages[-1].append([])
    def new_page(): pages.append([[]])
    def append_kana(b: int): current_line().append(b)
    def append_kanji(xx: int): current_line().append(256 + xx)

    tokens = _tokenize_brackets(body)
    i = 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "nl":
            # Soft newline in source: not a game newline, just a wrap. Skip.
            i += 1
            continue
        if kind == "char":
            # Lookup chain: the script's own table (only). When kanji_escape
            # is on, kanji chars not in that table fall through to a 2-byte
            # FE XX emit via the kanji table. No cross-language fallback —
            # an EN edit shouldn't preview JP kana, and a JP source's kana
            # uses the JP table by being passed in via `char_to_byte`.
            b = char_to_byte.get(val)
            kanji_xx = None
            if b is None and kanji_escape:
                kanji_xx = cfg.get("kanji_char_to_byte", {}).get(val)
            if kanji_xx is not None:
                append_kanji(kanji_xx)
            else:
                if b is None:
                    b = 0x00
                append_kana(b)
            i += 1
            continue
        # byte
        b = val
        if b == 0xFD:
            new_line(); i += 1
        elif b == 0xFE:
            # Dialog FE = page break; intro FE = 2-byte kanji escape.
            if kanji_escape:
                i += 1
                if i < len(tokens) and tokens[i][0] == "byte":
                    append_kanji(tokens[i][1])
                    i += 1
            else:
                new_page(); i += 1
        elif b == 0xF7:
            # Line-end / page-wait — visualize as a hard break
            new_line()
            i += 1
            # Consume the param byte (the FF / 08 / etc.)
            if i < len(tokens) and tokens[i][0] == "byte":
                i += 1
        elif b == 0xFF:
            # Standalone terminator — stop rendering
            break
        elif b == 0xFC:
            # FC sub-cmd: read next byte to determine total length
            i += 1
            if i < len(tokens) and tokens[i][0] == "byte":
                sub = tokens[i][1]
                i += 1
                # Skip the param bytes — they're not rendered
                params = 2 if sub == 0x02 else 1
                for _ in range(params):
                    if i < len(tokens) and tokens[i][0] == "byte":
                        i += 1
        elif b in _OPCODE_LEN:
            # F8/F9/FA/FB: opcode + 1 param, nothing to render
            i += 1
            if i < len(tokens) and tokens[i][0] == "byte":
                i += 1
        else:
            # Plain printable byte (< 0xF7) → glyph
            current_line().append(b)
            i += 1

    # Flatten + word-wrap. With `mixed_width=True`, `cols` is in half-cell
    # units: half-width glyphs (kana, Latin) count as 1, full-width glyphs
    # (kanji, encoded as glyph index ≥ 256) count as 2. That mirrors how the
    # in-game intro renderer wraps by pixels rather than by char count.
    mixed_width = bool(cfg.get("mixed_width"))
    flat: list = []
    for pi, page in enumerate(pages):
        if pi > 0:
            flat.append(None)
        for ln in page:
            if not ln:
                flat.append([])
                continue
            if not mixed_width:
                for off in range(0, len(ln), cols):
                    flat.append(ln[off:off + cols])
                continue
            chunk: list[int] = []
            units = 0
            for g in ln:
                w = 2 if g >= 256 else 1
                if units + w > cols and chunk:
                    flat.append(chunk)
                    chunk, units = [], 0
                chunk.append(g)
                units += w
            if chunk:
                flat.append(chunk)
    return flat


def _draw_dialog_box(
    lines: list,                 # list of list[int] glyph rows for one page
    atlas: Image.Image,
    backdrop_rgba: tuple[int, int, int, int],
    kanji_atlas: Optional[Image.Image] = None,
    cols_per_line: int = COLS_PER_LINE,
    mixed_width: bool = False,
) -> Image.Image:
    """Render one page (already split — no None entries) to a bordered
    dialog box. `backdrop_rgba` is palette slot 0 of the active speaker —
    the actual in-game color behind the text. Returns an RGB Image at 1×.

    Glyph indices ≥ 256 are routed to `kanji_atlas[idx - 256]` (see
    body_to_lines). If `kanji_atlas` is None those positions render blank.

    With `mixed_width=True`, half-width glyphs (kana / Latin, 8×16) and
    full-width glyphs (kanji, 16×16) are drawn at their natural pixel
    widths — matching the in-game intro layout — and `cols_per_line` is
    interpreted in HALF-CELL UNITS. Without it, every cell is rendered at
    the dialog's 8×16 size.
    """
    pad = 12
    # text_w is the maximum possible line width when mixed; the actual
    # rendered row may be narrower depending on content.
    unit_w = GLYPH_W
    cell_h = KANJI_H if mixed_width else GLYPH_H
    text_w = cols_per_line * unit_w
    text_h = max(cell_h, len(lines) * cell_h)
    img_w = text_w + pad * 2
    img_h = text_h + pad * 2
    img = Image.new("RGB", (img_w, img_h), backdrop_rgba[:3])

    # 1 px border around the text area
    for x in range(pad - 2, pad + text_w + 2):
        if 0 <= pad - 2 < img_h:
            img.putpixel((x, pad - 2), (90, 110, 150))
        if 0 <= pad + text_h + 1 < img_h:
            img.putpixel((x, pad + text_h + 1), (90, 110, 150))
    for y in range(pad - 2, pad + text_h + 2):
        if 0 <= pad - 2 < img_w:
            img.putpixel((pad - 2, y), (90, 110, 150))
        if 0 <= pad + text_w + 1 < img_w:
            img.putpixel((pad + text_w + 1, y), (90, 110, 150))

    cols = 16  # atlas columns (same for both kana and kanji atlases)
    y = pad
    for line in lines:
        x = pad
        for gi in line:
            if gi >= 256:
                # Kanji glyph (intro FE-escape). Always full-width.
                if kanji_atlas is None:
                    x += KANJI_W
                    continue
                kx = gi - 256
                ax = (kx % cols) * KANJI_W
                ay = (kx // cols) * KANJI_H
                glyph = kanji_atlas.crop((ax, ay, ax + KANJI_W, ay + KANJI_H))
                img.paste(glyph, (x, y), glyph)
                x += KANJI_W
            else:
                # Half-width kana / Latin glyph (8×16) from the dialog atlas.
                ax = (gi % cols) * GLYPH_W
                ay = (gi // cols) * GLYPH_H
                glyph = atlas.crop((ax, ay, ax + GLYPH_W, ay + GLYPH_H))
                img.paste(glyph, (x, y), glyph)
                x += GLYPH_W
        y += cell_h
    return img


def render_preview(
    body: str,
    atlas: Image.Image,
    char_to_byte: dict[str, int],
    backdrop_rgba: tuple[int, int, int, int] = (8, 48, 8, 255),
    cfg: Optional[dict] = None,
    kanji_atlas: Optional[Image.Image] = None,
) -> bytes:
    """Render an entry to a PNG matching the in-game layout.

    `atlas` and `backdrop_rgba` should come from the SAME speaker palette
    (see Bridge.get_entry / render_body for the lookup). Multi-page entries
    (containing [FE] page breaks) render as separate dialog boxes stacked
    vertically — same visual model as the game, which clears between pages.

    `cfg` overrides per-file rendering (cols_per_line, kanji_escape — see
    body_to_lines). `kanji_atlas` is needed when cfg["kanji_escape"]=True.
    """
    cfg = cfg or {}
    cols = int(cfg.get("cols_per_line", COLS_PER_LINE))
    lines = body_to_lines(body, char_to_byte, cfg)

    pages: list[list[list[int]]] = [[]]
    for ln in lines:
        if ln is None:
            pages.append([])
        else:
            pages[-1].append(ln)
    if not pages or all(not p for p in pages):
        pages = [[[]]]

    GAP = 10
    mixed_width = bool(cfg.get("mixed_width"))
    page_imgs = [
        _draw_dialog_box(p, atlas, backdrop_rgba,
                         kanji_atlas=kanji_atlas, cols_per_line=cols,
                         mixed_width=mixed_width)
        for p in pages
    ]
    full_w = max(im.width for im in page_imgs)
    full_h = sum(im.height for im in page_imgs) + GAP * (len(page_imgs) - 1)
    canvas = Image.new("RGB", (full_w, full_h), (10, 10, 22))
    y = 0
    for im in page_imgs:
        canvas.paste(im, (0, y))
        y += im.height + GAP

    if SCALE != 1:
        canvas = canvas.resize(
            (canvas.width * SCALE, canvas.height * SCALE),
            Image.Resampling.NEAREST,
        )
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Portrait/speaker extraction (placeholder — no real sprites yet)
# ---------------------------------------------------------------------------

def extract_portrait_id(body: str) -> Optional[int]:
    """Find the most recent [F9][XX] in the entry body and return XX as int.
    Accepts both the canonical two-bracket form (`[F9][02]`) and the
    legacy colon form (`[F9:02]`) just in case."""
    # Two-bracket form: `[F9]` immediately followed by `[XX]` (optionally
    # with whitespace between).
    m = re.search(r"\[F9\]\s*\[([0-9A-Fa-f]{1,2})\]", body)
    if m:
        return int(m.group(1), 16)
    m = re.search(r"\[F9:([0-9A-Fa-f]+)\]", body)
    return int(m.group(1), 16) if m else None


def portrait_name(pid: int) -> str:
    return PORTRAIT_NAMES.get(pid, f"Portrait #{pid:02X}")


def portrait_image_uri(pid: Optional[int]) -> Optional[str]:
    """Return a `data:image/png;base64,...` URI for the portrait sprite of
    the given pid, or None if no asset is available yet. Assets live in
    assets/portraits/pid_XX.png (XX = uppercase hex). Currently sourced
    from SplitTrace screen crops; will move to ROM-direct extraction once
    we RE the sprite-data path."""
    if pid is None:
        return None
    candidate = PORTRAIT_ASSETS / f"pid_{pid:02X}.png"
    if not candidate.exists():
        return None
    data = candidate.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# Pywebview bridge
# ---------------------------------------------------------------------------

class Bridge:
    """Exposed to JS via pywebview. All methods return JSON-friendly types."""

    def __init__(self):
        self.rom, self.palettes, self.atlases = load_font_atlases()
        self.char_to_byte = load_table()
        # Kanji atlas + reverse table for intro-style FE-escape rendering.
        # Built once at startup using a neutral palette (intro is full-screen
        # narration, not speaker-tinted dialog).
        self.kanji_atlas = _build_kanji_atlas(self.rom, FALLBACK_PALETTE)
        self.kanji_char_to_byte = _load_kanji_table()
        # JP kana table — used as a fallback in body_to_lines so JP source
        # entries (data/jp/*.txt) preview with actual kana glyphs instead of
        # blank cells. EN edits still take precedence via self.char_to_byte.
        self.jp_char_to_byte = _load_jp_kana_table()
        self.scenarios: dict[str, Scenario] = {}
        self.jp_scenarios: dict[str, Scenario] = {}
        self._save_timer: Optional[threading.Timer] = None
        self._save_lock = threading.Lock()
        self._pending: dict[tuple[str, int], str] = {}
        # Save state: "idle" → "queued" → "saving" → "saved" / "error".
        # JS polls get_save_state() after queueing a save so the badge can
        # remain in "saving" until Python has actually flushed to disk.
        self._save_state = "idle"
        self._save_error: Optional[str] = None
        self._save_seq = 0  # monotonic; lets JS detect "this save completed"
        # Load folder config from session state (defaults if missing).
        st = self.load_session_state()
        self.en_data_dir = Path(st.get("en_dir") or str(DEFAULT_EN_DATA_DIR))
        self.jp_data_dir = Path(st.get("jp_dir") or str(DEFAULT_JP_DATA_DIR))
        self._reload_scenarios()

    def _reload_scenarios(self) -> None:
        """Re-scan EN + JP folders. JP is read-only reference.

        char_names.txt is the HUD name table (raw ASCII, not the PK dialog
        font) — its in-app preview renders with the wrong glyphs but the
        text is still editable. Insertion is via tools/charnames.py, not
        the retrotool pipeline.
        """
        self.scenarios = {}
        self.jp_scenarios = {}
        patterns = ("scenario_*.txt", "char_names.txt", "intro.txt",
                    "narration_screens.txt")
        for pat in patterns:
            for p in sorted(self.en_data_dir.glob(pat)):
                self.scenarios[p.stem] = Scenario(p)
        if self.jp_data_dir.exists():
            for pat in patterns:
                for p in sorted(self.jp_data_dir.glob(pat)):
                    self.jp_scenarios[p.stem] = Scenario(p)

    def _palette_for(self, portrait_id: Optional[int]) -> tuple[Image.Image, tuple[int,int,int,int]]:
        """Return (atlas, backdrop_rgba) for the given speaker. Defaults to
        portrait 0 if no F9 in the entry.

        Note: palette slot 0 in SNES BG layers is always transparent (the
        layer below shows through). The in-game dialog window backdrop
        comes from another BG layer (probably BG2). For the editor preview
        we use a fixed dark color approximating that — speaker palette
        slot 0's CGRAM value is irrelevant to what actually renders.
        """
        pid = portrait_id if portrait_id is not None else 0
        if pid not in self.atlases:
            pid = 0
        return self.atlases[pid], DIALOG_BG

    # ---- discovery ----
    def list_scenarios(self) -> list[dict]:
        out = []
        for name, sc in self.scenarios.items():
            translated = sum(
                1 for e in sc.entries
                if re.search(r"[A-Za-z]{2,}", e["body"])
            )
            out.append({
                "name": name,
                "entries": len(sc.entries),
                "translated": translated,
            })
        return out

    def list_entries(self, scenario_name: str) -> list[dict]:
        sc = self.scenarios.get(scenario_name)
        if sc is None:
            return []
        out = []
        for i, e in enumerate(sc.entries):
            preview = re.sub(r"\[[^\]]*\]", "", e["body"]).strip()[:60]
            translated = bool(re.search(r"[A-Za-z]{2,}", e["body"]))
            pid = extract_portrait_id(e["body"])
            out.append({
                "i": i,
                "idx": e["idx"],
                "preview": preview,
                "translated": translated,
                "portrait_id": pid,
                "portrait_name": portrait_name(pid) if pid is not None else None,
            })
        return out

    def _cfg_for(self, scenario_name: str) -> dict:
        """Merge per-file config from SCENARIO_CONFIG with the kanji reverse
        table so body_to_lines can fall through to FE XX for kanji in
        kanji_escape mode. No cross-language kana fallback — the editable
        body always renders with its own script's table."""
        cfg = dict(SCENARIO_CONFIG.get(scenario_name, {}))
        if cfg.get("kanji_escape"):
            cfg["kanji_char_to_byte"] = self.kanji_char_to_byte
        return cfg

    def get_entry(self, scenario_name: str, entry_i: int) -> dict:
        sc = self.scenarios[scenario_name]
        e = sc.entries[entry_i]
        pid = extract_portrait_id(e["body"])
        atlas, backdrop = self._palette_for(pid)
        cfg = self._cfg_for(scenario_name)
        ka = self.kanji_atlas if cfg.get("kanji_escape") else None
        png = render_preview(e["body"], atlas, self.char_to_byte, backdrop,
                             cfg=cfg, kanji_atlas=ka)
        b64 = base64.b64encode(png).decode("ascii")
        # Look up the JP counterpart by entry index when available.
        jp_body = ""
        if scenario_name in self.jp_scenarios:
            jp_sc = self.jp_scenarios[scenario_name]
            if entry_i < len(jp_sc.entries):
                jp_body = jp_sc.entries[entry_i]["body"]
        # Each side uses its own script table. EN (editable) → rbshura_en.tbl
        # via self.char_to_byte; JP (reference) → rbshura_jp.tbl via
        # self.jp_char_to_byte. Both share the kanji-escape config (kanji
        # round-trip semantics are identical on either side).
        byte_count = body_byte_count(e["body"], self.char_to_byte, cfg)
        jp_byte_count = (
            body_byte_count(jp_body, self.jp_char_to_byte, cfg) if jp_body else 0
        )
        return {
            "body": e["body"],
            "jp_body": jp_body,
            "preview_png": f"data:image/png;base64,{b64}",
            "portrait_id": pid,
            "portrait_name": portrait_name(pid) if pid is not None else None,
            "portrait_image": portrait_image_uri(pid),
            "byte_count": byte_count,
            "jp_byte_count": jp_byte_count,
        }

    def render_body(self, body: str, scenario_name: str = "") -> dict:
        """Cheap render-only call (no file write) for live preview.

        `scenario_name` lets us pick up per-file config (cols_per_line,
        kanji_escape). Omitted defaults to dialog rendering.

        Returns {png, byte_count} so the UI can update both the preview
        image and the byte-budget badge from a single round-trip.
        """
        pid = extract_portrait_id(body)
        atlas, backdrop = self._palette_for(pid)
        cfg = self._cfg_for(scenario_name) if scenario_name else {}
        ka = self.kanji_atlas if cfg.get("kanji_escape") else None
        png = render_preview(body, atlas, self.char_to_byte, backdrop,
                             cfg=cfg, kanji_atlas=ka)
        return {
            "png": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            "byte_count": body_byte_count(body, self.char_to_byte, cfg),
        }

    # ---- autosave (debounced) ----
    def queue_save(self, scenario_name: str, entry_i: int, body: str) -> None:
        with self._save_lock:
            self._pending[(scenario_name, entry_i)] = body
            self._save_state = "queued"
            self._save_error = None
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(0.4, self._flush_pending)
            self._save_timer.daemon = True
            self._save_timer.start()

    def _flush_pending(self) -> None:
        with self._save_lock:
            pending = dict(self._pending)
            self._pending.clear()
            self._save_timer = None
            self._save_state = "saving"
        # Group writes by scenario so each file is written once
        by_scen: dict[str, list[tuple[int, str]]] = {}
        for (name, i), body in pending.items():
            by_scen.setdefault(name, []).append((i, body))
        try:
            for name, items in by_scen.items():
                sc = self.scenarios[name]
                for i, body in items:
                    sc.entries[i]["body"] = body
                # Save once per scenario after applying all queued edits
                sc.save_entry(items[-1][0], items[-1][1])
        except Exception as exc:
            with self._save_lock:
                self._save_state = "error"
                self._save_error = f"{type(exc).__name__}: {exc}"
                self._save_seq += 1
            raise
        with self._save_lock:
            self._save_state = "saved"
            self._save_seq += 1

    # ---- forced sync save (used on window close, manual save) ----
    def flush_now(self) -> None:
        if self._save_timer is not None:
            self._save_timer.cancel()
            self._save_timer = None
        if self._pending:
            self._flush_pending()

    # ---- save state for the UI indicator ----
    def get_save_state(self) -> dict:
        """JS polls this to update the badge. Returns the current state,
        any error message, and a monotonic seq so JS can detect when a
        new save has completed."""
        with self._save_lock:
            return {
                "state": self._save_state,
                "error": self._save_error,
                "seq": self._save_seq,
            }

    # ---- folder settings (editable + reference) ----
    @staticmethod
    def _label_from_dir(path: Path) -> str:
        """Display label = folder basename uppercased. Empty string if the
        path is a root or unparseable. Used so the UI says 'EN' / 'JP' /
        'FR' / 'ES' depending on what the user set as their data folders."""
        name = path.name or path.parent.name
        return name.upper()[:8] or "—"

    def get_settings(self) -> dict:
        return {
            "en_dir": str(self.en_data_dir),
            "jp_dir": str(self.jp_data_dir),
            "en_dir_exists": self.en_data_dir.exists(),
            "jp_dir_exists": self.jp_data_dir.exists(),
            "default_en_dir": str(DEFAULT_EN_DATA_DIR),
            "default_jp_dir": str(DEFAULT_JP_DATA_DIR),
            # Display labels derived from folder basenames (uppercased).
            # The editor uses these wherever it used to say "EN" / "JP"
            # so the UI generalizes to other languages without code edits.
            "editable_label": self._label_from_dir(self.en_data_dir),
            "reference_label": self._label_from_dir(self.jp_data_dir),
        }

    def pick_folder(self, initial_path: str = "") -> Optional[str]:
        """Open the OS native folder picker. Returns the chosen path or None
        if the user cancelled. Called by the settings modal's Browse button."""
        try:
            import webview
        except ImportError:
            return None
        if not webview.windows:
            return None
        win = webview.windows[0]
        try:
            initial = initial_path or str(self.en_data_dir.parent
                                          if self.en_data_dir.exists()
                                          else ROOT)
            # FOLDER_DIALOG returns a tuple of paths (or None on cancel).
            result = win.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=initial,
                allow_multiple=False,
            )
        except Exception:
            return None
        if not result:
            return None
        # pywebview returns either a list/tuple of paths or a single string
        return result[0] if isinstance(result, (list, tuple)) else result

    def set_settings(self, en_dir: str, jp_dir: str) -> dict:
        """Update the active folder paths and reload scenarios. Persists the
        new paths into the session state file. Returns the new settings dict
        plus the list of scenarios under the new EN dir."""
        if en_dir:
            self.en_data_dir = Path(en_dir).expanduser()
        if jp_dir:
            self.jp_data_dir = Path(jp_dir).expanduser()
        # Persist into session-state (merge with existing fields)
        st = self.load_session_state()
        st["en_dir"] = str(self.en_data_dir)
        st["jp_dir"] = str(self.jp_data_dir)
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(EDITOR_STATE_PATH.parent),
                prefix=f".{EDITOR_STATE_PATH.name}.",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(st, f)
            os.replace(tmp, EDITOR_STATE_PATH)
        except Exception:
            pass
        self._reload_scenarios()
        return self.get_settings()

    # ---- cross-scenario find / find-and-replace ----
    def search_text(
        self,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        scope: str = "all",      # "all" or a specific scenario name
        side: str = "en",        # "en" (search editable) or "jp" (reference)
    ) -> dict:
        # NOTE: signature kept positional (no `*`) because pywebview's JS
        # bridge passes arguments positionally — kw-only args would 500.
        """Search entry bodies for `query`. Returns matches as a list of
        {scenario, entry_i, line, before, match, after} per hit.

        Up to 500 matches returned (UI hard-cap). `error` set if the regex
        was invalid."""
        try:
            if use_regex:
                pat = re.compile(query, 0 if case_sensitive else re.IGNORECASE)
            else:
                pat = re.compile(
                    re.escape(query), 0 if case_sensitive else re.IGNORECASE,
                )
        except re.error as e:
            return {"matches": [], "error": str(e)}

        scenarios = self.scenarios if side == "en" else self.jp_scenarios
        if scope != "all":
            scenarios = {k: v for k, v in scenarios.items() if k == scope}

        matches: list[dict] = []
        for name, sc in scenarios.items():
            for i, e in enumerate(sc.entries):
                body = e["body"]
                for m in pat.finditer(body):
                    s, ee = m.span()
                    matches.append({
                        "scenario": name,
                        "entry_i": i,
                        "start": s,
                        "end": ee,
                        "before": body[max(0, s - 24):s],
                        "match": body[s:ee],
                        "after": body[ee:min(len(body), ee + 24)],
                    })
                    if len(matches) >= 500:
                        return {"matches": matches, "truncated": True, "error": None}
        return {"matches": matches, "truncated": False, "error": None}

    def replace_text(
        self,
        scenario_name: str,
        entry_i: int,
        start: int,
        end: int,
        replacement: str,
    ) -> dict:
        """Replace bytes [start:end] of one entry's body with `replacement`,
        then queue the save. Returns the new full body. Used by JS for the
        find-and-replace path."""
        sc = self.scenarios[scenario_name]
        e = sc.entries[entry_i]
        new_body = e["body"][:start] + replacement + e["body"][end:]
        self.queue_save(scenario_name, entry_i, new_body)
        return {"body": new_body}

    # ---- session persistence (last scenario / entry / cursor) ----
    def load_session_state(self) -> dict:
        """Read the persisted editor state. Returns {} on first launch
        or if the file is missing / corrupt. Schema:
          {scenario: str, entry_i: int, cursor: int, scroll: int}
        """
        try:
            return json.loads(EDITOR_STATE_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_session_state(self, scenario: str, entry_i: int,
                            cursor: int = 0, scroll: int = 0) -> None:
        """Persist the current selection. Best-effort — failures are
        non-fatal (just lost state on next launch). Atomic via temp + rename."""
        payload = {
            "scenario": scenario,
            "entry_i": entry_i,
            "cursor": cursor,
            "scroll": scroll,
        }
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(EDITOR_STATE_PATH.parent),
                prefix=f".{EDITOR_STATE_PATH.name}.",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, EDITOR_STATE_PATH)
        except Exception:
            # Silent — losing session state shouldn't disrupt editing.
            pass


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>rbshura — Script Editor</title>
<style>
:root {
  --bg: #101028; --bg2: #161638; --bg3: #0f3460; --fg: #e8e8f0;
  --fg2: #8888a0; --acc: #e94560; --grn: #4ecca3; --yel: #f0c040;
  --brd: #2a2a4e; --code: 'Cascadia Mono', Consolas, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--fg);
       display: grid; grid-template-columns: 220px 280px 1fr; height: 100vh; overflow: hidden; }
.col { display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid var(--brd); }
.col:last-child { border-right: none; }
.col h2 { padding: 10px 12px; background: var(--bg2); font-size: 11px;
          text-transform: uppercase; letter-spacing: 1px; color: var(--acc);
          border-bottom: 1px solid var(--brd); }
.list { flex: 1; overflow-y: auto; }
.item { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid var(--brd); font-size: 13px; }
.item:hover { background: var(--bg2); }
.item.active { background: var(--bg3); color: #fff; border-left: 3px solid var(--acc); padding-left: 9px; }
.item .meta { color: var(--fg2); font-size: 11px; margin-top: 2px; }
.item.translated .marker { color: var(--grn); }
.item.untranslated .marker { color: var(--yel); }
.editor { flex: 1; display: flex; flex-direction: column; }
.toolbar { padding: 8px 12px; background: var(--bg2); border-bottom: 1px solid var(--brd);
           display: flex; align-items: center; gap: 12px; font-size: 12px; }

/* Save-status badge. Pill with a colored dot + text. */
.savebadge { display: inline-flex; align-items: center; gap: 6px;
             padding: 3px 10px; border-radius: 999px; font-size: 11px;
             border: 1px solid var(--brd); background: var(--bg);
             color: var(--fg2); transition: background-color .15s, color .15s; }
.savebadge .dot { width: 8px; height: 8px; border-radius: 50%;
                  background: var(--fg2); transition: background-color .15s; }
.savebadge.idle    { color: var(--fg2); }
.savebadge.idle .dot    { background: var(--fg2); }
.savebadge.dirty   { color: var(--yel); border-color: var(--yel); }
.savebadge.dirty .dot   { background: var(--yel);
                          animation: dirty-pulse 1s ease-in-out infinite; }
.savebadge.saving  { color: var(--bg3-fg, #66a8ff); border-color: #66a8ff;
                     background: rgba(102,168,255,.08); }
.savebadge.saving .dot  { background: #66a8ff;
                          animation: saving-spin .8s linear infinite; }
.savebadge.saved   { color: var(--grn); border-color: var(--grn);
                     background: rgba(78,204,163,.08); }
.savebadge.saved .dot   { background: var(--grn); }
.savebadge.saved .check { color: var(--grn); font-weight: 700; }
.savebadge.error   { color: var(--acc); border-color: var(--acc);
                     background: rgba(233,69,96,.08); }
.savebadge.error .dot   { background: var(--acc); }

@keyframes dirty-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.35; }
}
@keyframes saving-spin {
  /* simple "breathing" pulse — easier to read than a CSS-only spinner */
  0%, 100% { transform: scale(1);   opacity: 1; }
  50%      { transform: scale(1.4); opacity: 0.6; }
}
.panes { flex: 1; display: grid; grid-template-rows: minmax(160px, 50vh) 1fr;
         overflow: hidden; }
.preview { padding: 16px; background: #050511; border-bottom: 1px solid var(--brd);
           display: flex; gap: 16px; align-items: flex-start;
           overflow-y: auto; overflow-x: auto; }
.preview img { display: block; }
.portrait-box { width: 110px; flex: 0 0 110px; display: flex; flex-direction: column;
                gap: 6px; align-items: center; }
.portrait { width: 96px; height: 120px; background: var(--bg2); border: 1px solid var(--brd);
            display: flex; align-items: center; justify-content: center;
            color: var(--fg2); font-size: 10px; text-align: center;
            image-rendering: pixelated; image-rendering: crisp-edges;
            overflow: hidden; }
.portrait img { width: 100%; height: 100%; object-fit: contain;
                image-rendering: pixelated; image-rendering: crisp-edges; }
.portrait-name { font-size: 11px; color: var(--fg); text-align: center; }
.portrait-pid { font-size: 10px; color: var(--fg2); font-family: var(--code); }
.preview img { image-rendering: pixelated; image-rendering: crisp-edges; }
.text-area { flex: 1; display: grid; grid-template-columns: 1fr 1fr;
             gap: 8px; padding: 12px; overflow: hidden; }
.text-col { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.text-col label { font-size: 11px; color: var(--fg2); text-transform: uppercase;
                  letter-spacing: .5px; display: flex; align-items: center; gap: 6px; }
.text-col label .ro { font-size: 10px; padding: 1px 6px; border-radius: 3px;
                      background: var(--bg3); color: var(--fg2); border: 1px solid var(--brd); }
textarea { flex: 1; font-family: var(--code); font-size: 13px; line-height: 1.5;
           background: var(--bg2); color: var(--fg); border: 1px solid var(--brd);
           border-radius: 4px; padding: 10px; resize: none; outline: none;
           min-width: 0; }
textarea:focus { border-color: var(--acc); }
textarea[readonly] { background: var(--bg); color: var(--fg2); cursor: default; }

/* Find/replace bar — slides down from the toolbar. */
.findbar { display: none; padding: 8px 12px; background: var(--bg2);
           border-bottom: 1px solid var(--brd);
           grid-template-columns: 1fr 1fr auto auto auto auto auto;
           gap: 6px; align-items: center; font-size: 12px; }
.findbar.open { display: grid; }
.findbar input[type=text] { background: var(--bg); color: var(--fg);
                             border: 1px solid var(--brd); border-radius: 3px;
                             padding: 4px 8px; font-family: var(--code); font-size: 12px;
                             outline: none; }
.findbar input[type=text]:focus { border-color: var(--acc); }
.findbar button { background: var(--bg3); color: var(--fg); border: 1px solid var(--brd);
                  border-radius: 3px; padding: 4px 9px; font-size: 11px; cursor: pointer; }
.findbar button:hover { background: var(--acc2); }
.findbar button.act { background: var(--acc); border-color: var(--acc); color: #fff; }
.findbar .count { color: var(--fg2); font-size: 11px; padding: 0 4px; }

/* Settings modal (folder paths). */
.modal-bg { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6);
            z-index: 100; align-items: center; justify-content: center; }
.modal-bg.open { display: flex; }
.modal { background: var(--bg2); border: 1px solid var(--brd); border-radius: 6px;
         padding: 18px; min-width: 460px; max-width: 600px; }
.modal h3 { color: var(--acc); font-size: 13px; margin-bottom: 12px; }
.modal .row { margin-bottom: 10px; }
.modal .row label { display: block; font-size: 11px; color: var(--fg2);
                    text-transform: uppercase; margin-bottom: 4px; }
.modal .row input { width: 100%; padding: 6px 9px; background: var(--bg); color: var(--fg);
                    border: 1px solid var(--brd); border-radius: 3px; font-family: var(--code);
                    font-size: 12px; outline: none; }
.modal .row .meta { color: var(--fg2); font-size: 10px; margin-top: 3px; }
.modal .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 14px; }
.modal .actions button { padding: 5px 14px; border-radius: 3px; cursor: pointer;
                         border: 1px solid var(--brd); background: var(--bg3); color: var(--fg);
                         font-size: 12px; }
.modal .actions button.primary { background: var(--acc); border-color: var(--acc); color: #fff; }

/* Cross-scenario search results panel. */
.search-results { display: none; position: absolute; top: 50px; right: 16px;
                  width: 480px; max-height: 60vh; overflow-y: auto;
                  background: var(--bg2); border: 1px solid var(--brd); border-radius: 4px;
                  z-index: 50; padding: 6px; box-shadow: 0 6px 24px rgba(0,0,0,.5); }
.search-results.open { display: block; }
.search-results .hit { padding: 5px 8px; cursor: pointer; border-bottom: 1px solid var(--brd);
                       font-size: 12px; }
.search-results .hit:hover { background: var(--bg3); }
.search-results .hit .where { color: var(--acc); font-family: var(--code); font-size: 10px; }
.search-results .hit .ctx { color: var(--fg2); font-family: var(--code); font-size: 11px;
                            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.search-results .hit .ctx b { color: var(--yel); background: rgba(240,192,64,.15); padding: 0 2px; }
.search-results .empty { padding: 10px; color: var(--fg2); font-size: 12px; text-align: center; }
.hint { font-size: 11px; color: var(--fg2); line-height: 1.5; }
.hint code { background: var(--bg2); padding: 1px 5px; border-radius: 3px;
             color: var(--fg); font-family: var(--code); font-size: 11px; }
::-webkit-scrollbar { width: 7px; height: 7px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--brd); border-radius: 4px; }
.empty { padding: 24px; color: var(--fg2); font-size: 13px; text-align: center; }
</style></head><body>
  <div class="col"><h2>Scenarios</h2><div class="list" id="scen-list"></div></div>
  <div class="col"><h2 id="ent-title">Entries</h2><div class="list" id="ent-list"></div></div>
  <div class="col editor">
    <div class="toolbar">
      <span id="ent-label">No entry selected</span>
      <span class="savebadge idle" id="savebadge" title="Save status">
        <span class="dot"></span>
        <span class="label" id="savebadge-label">idle</span>
      </span>
      <span style="flex:1"></span>
      <button onclick="toggleFindBar()" title="Find / replace (Ctrl+F)"
              style="background:var(--bg3);color:var(--fg);border:1px solid var(--brd);
                     border-radius:3px;padding:3px 9px;font-size:11px;cursor:pointer;">
        🔍 Find
      </button>
      <button onclick="openSettings()" title="Folder settings"
              style="background:var(--bg3);color:var(--fg);border:1px solid var(--brd);
                     border-radius:3px;padding:3px 9px;font-size:11px;cursor:pointer;">
        ⚙ Settings
      </button>
    </div>
    <div class="findbar" id="findbar">
      <input id="find-q" type="text" placeholder="Find…"
             onkeydown="if(event.key==='Enter'){event.shiftKey?findPrev():findNext()}; if(event.key==='Escape')toggleFindBar()">
      <input id="find-r" type="text" placeholder="Replace with…">
      <button id="find-case" onclick="toggleFindFlag('case', this)" title="Case-sensitive (Aa)">Aa</button>
      <button id="find-regex" onclick="toggleFindFlag('regex', this)" title="Regex">.*</button>
      <button onclick="findPrev()" title="Find previous (Shift+Enter)">◀</button>
      <button onclick="findNext()" title="Find next (Enter)">▶</button>
      <button onclick="replaceOne()" title="Replace one">Replace</button>
      <span class="count" id="find-count"></span>
    </div>
    <div class="search-results" id="search-results"></div>
    <div class="panes" id="panes" style="display:none">
      <div class="preview">
        <div class="portrait-box">
          <div class="portrait" id="portrait">no<br>portrait</div>
          <div class="portrait-pid" id="portrait-pid"></div>
          <div class="portrait-name" id="portrait-name"></div>
        </div>
        <img id="preview-img" alt="preview" />
      </div>
      <div class="text-area">
        <div class="text-col">
          <label><span id="lbl-editable">EN</span> BODY
            <span style="color:var(--grn);font-size:9px;">editable</span>
            <span id="body-bytes" style="color:var(--fg2);font-size:10px;
                                         margin-left:6px;font-family:var(--code);"
                  title="encoded byte length (what the build will write)"></span></label>
          <textarea id="body" spellcheck="false" placeholder="select an entry"></textarea>
        </div>
        <div class="text-col">
          <label><span id="lbl-reference">JP</span> REFERENCE
            <span class="ro">read-only</span>
            <span id="jp-body-bytes" style="color:var(--fg2);font-size:10px;
                                            margin-left:6px;font-family:var(--code);"
                  title="encoded byte length of the reference entry"></span></label>
          <textarea id="jp-body" readonly spellcheck="false"
                    placeholder="reference source not loaded"></textarea>
        </div>
      </div>
    </div>
    <div class="empty" id="empty">Pick a scenario → entry to start editing.</div>
  </div>

  <!-- Settings modal -->
  <div class="modal-bg" id="settings-modal">
    <div class="modal">
      <h3>Script folder settings</h3>
      <div class="row">
        <label>Editable folder (label: <span id="cfg-en-label">EN</span>)</label>
        <div style="display:flex;gap:6px;">
          <input id="cfg-en" type="text" placeholder="/path/to/data/en" style="flex:1">
          <button onclick="browseFolder('en')"
                  style="padding:6px 12px;background:var(--bg3);color:var(--fg);
                         border:1px solid var(--brd);border-radius:3px;
                         font-size:11px;cursor:pointer;">📁 Browse</button>
        </div>
        <div class="meta" id="cfg-en-meta"></div>
      </div>
      <div class="row">
        <label>Reference folder (label: <span id="cfg-jp-label">JP</span>, read-only)</label>
        <div style="display:flex;gap:6px;">
          <input id="cfg-jp" type="text" placeholder="/path/to/data/jp" style="flex:1">
          <button onclick="browseFolder('jp')"
                  style="padding:6px 12px;background:var(--bg3);color:var(--fg);
                         border:1px solid var(--brd);border-radius:3px;
                         font-size:11px;cursor:pointer;">📁 Browse</button>
        </div>
        <div class="meta" id="cfg-jp-meta"></div>
      </div>
      <div class="meta" style="margin-top:8px;color:var(--fg2);font-size:10px;">
        Labels in the editor (e.g. <span id="cfg-en-label2">EN</span> BODY /
        <span id="cfg-jp-label2">JP</span> REFERENCE) are derived from each
        folder's basename, uppercased. Use folder names like
        <code style="background:var(--bg);padding:1px 4px;border-radius:2px;">data/fr/</code>
        for a French translation, etc.
      </div>
      <div class="actions">
        <button onclick="closeSettings()">Cancel</button>
        <button class="primary" onclick="saveSettings()">Save &amp; reload</button>
      </div>
    </div>
  </div>

<script>
let CURRENT = { scenario: null, entry_i: null };
let DEBOUNCE = null;

async function loadScenarios() {
  // Apply current folder labels first so the textarea headers match the
  // active folder pair from the very first frame.
  await applyLabelsAtStartup();
  const items = await pywebview.api.list_scenarios();
  const list = document.getElementById('scen-list');
  list.innerHTML = '';
  items.forEach(it => {
    const div = document.createElement('div');
    div.className = 'item';
    div.dataset.name = it.name;
    const pct = it.entries ? Math.round(100 * it.translated / it.entries) : 0;
    div.innerHTML = `<div>${it.name.replace('scenario_', 'scen ')}</div>
                     <div class="meta">${it.translated}/${it.entries} translated · ${pct}%</div>`;
    div.onclick = () => selectScenario(it.name);
    list.appendChild(div);
  });
  // After listing, restore the previous session if any.
  const st = await pywebview.api.load_session_state();
  if (st && st.scenario) {
    await selectScenario(st.scenario);
    if (typeof st.entry_i === 'number') {
      await selectEntry(st.entry_i);
      // Defer cursor/scroll restore until after the textarea is populated
      // by selectEntry (which awaits get_entry).
      const ta = document.getElementById('body');
      if (typeof st.cursor === 'number') {
        try { ta.setSelectionRange(st.cursor, st.cursor); } catch (e) {}
      }
      if (typeof st.scroll === 'number') {
        ta.scrollTop = st.scroll;
      }
      // Scroll the entry into view in the middle pane.
      const item = document.querySelector(`#ent-list .item[data-i="${st.entry_i}"]`);
      if (item) item.scrollIntoView({ block: 'center', behavior: 'instant' });
    }
  }
}

// Debounced session-state save — fires on cursor/scroll/edit changes.
let SESSION_SAVE_TIMER = null;
function bumpSessionSave() {
  if (CURRENT.scenario === null || CURRENT.entry_i === null) return;
  if (SESSION_SAVE_TIMER) clearTimeout(SESSION_SAVE_TIMER);
  SESSION_SAVE_TIMER = setTimeout(() => {
    const ta = document.getElementById('body');
    pywebview.api.save_session_state(
      CURRENT.scenario, CURRENT.entry_i,
      ta.selectionStart || 0,
      ta.scrollTop || 0,
    );
  }, 500);
}

async function selectScenario(name) {
  document.querySelectorAll('#scen-list .item').forEach(d => {
    d.classList.toggle('active', d.dataset.name === name);
  });
  CURRENT.scenario = name;
  CURRENT.entry_i = null;
  document.getElementById('ent-title').textContent = name.replace('scenario_', 'Scen ');
  const entries = await pywebview.api.list_entries(name);
  const list = document.getElementById('ent-list');
  list.innerHTML = '';
  entries.forEach(e => {
    const div = document.createElement('div');
    div.className = 'item ' + (e.translated ? 'translated' : 'untranslated');
    div.dataset.i = e.i;
    const marker = e.translated ? '●' : '○';
    const speaker = e.portrait_name ? ` <span class="meta">${e.portrait_name}</span>` : '';
    div.innerHTML = `<div><span class="marker">${marker}</span> #${e.idx}${speaker}</div>
                     <div class="meta">${escapeHtml(e.preview) || '(empty)'}</div>`;
    div.onclick = () => selectEntry(e.i);
    list.appendChild(div);
  });
  document.getElementById('panes').style.display = 'none';
  document.getElementById('empty').style.display = 'block';
  document.getElementById('empty').textContent = `Pick an entry (${entries.length} in ${name}).`;
}

async function selectEntry(i) {
  document.querySelectorAll('#ent-list .item').forEach(d => {
    d.classList.toggle('active', Number(d.dataset.i) === i);
  });
  CURRENT.entry_i = i;
  const e = await pywebview.api.get_entry(CURRENT.scenario, i);
  document.getElementById('body').value = e.body;
  document.getElementById('jp-body').value = e.jp_body || '';
  document.getElementById('preview-img').src = e.preview_png;
  setBodyBytes(e.byte_count);
  setJpBodyBytes(e.jp_byte_count);
  const portraitBox = document.getElementById('portrait');
  const portraitPid = document.getElementById('portrait-pid');
  const portraitName = document.getElementById('portrait-name');
  if (e.portrait_id === null) {
    portraitBox.innerHTML = 'no<br>F9';
    portraitPid.textContent = '';
    portraitName.textContent = '';
  } else {
    portraitPid.textContent = 'PID 0x' + e.portrait_id.toString(16).toUpperCase().padStart(2,'0');
    portraitName.textContent = e.portrait_name || '';
    if (e.portrait_image) {
      portraitBox.innerHTML = `<img src="${e.portrait_image}" alt="portrait">`;
    } else {
      portraitBox.innerHTML = 'sprite<br>pending';
    }
  }
  document.getElementById('ent-label').textContent =
    `${CURRENT.scenario} · entry #${i}`;
  // Loading a new entry resets the badge to idle — any pending save from
  // the previous entry has already been queued via queue_save.
  if (SAVED_FADE_TIMER) { clearTimeout(SAVED_FADE_TIMER); SAVED_FADE_TIMER = null; }
  setBadge('idle', 'idle');
  document.getElementById('empty').style.display = 'none';
  document.getElementById('panes').style.display = 'grid';
  bumpSessionSave();
}

// Save-state machine:
//   user types         → setBadge('dirty', 'editing…')
//   debounce fires     → setBadge('saving', 'saving…')
//   bridge ack (poll)  → setBadge('saved', 'saved ✓')  (3s auto-fade to idle)
//   bridge error       → setBadge('error', 'save failed')
let SAVE_POLL = null;
let LAST_SEEN_SEQ = 0;
let SAVED_FADE_TIMER = null;

function setBadge(cls, text) {
  const el = document.getElementById('savebadge');
  el.className = 'savebadge ' + cls;
  document.getElementById('savebadge-label').textContent = text;
}

function setBodyBytes(n) {
  // Encoded byte length next to the BODY label. Hidden when null/undefined
  // (e.g. before any entry is loaded).
  const el = document.getElementById('body-bytes');
  if (!el) return;
  if (n == null) { el.textContent = ''; return; }
  el.textContent = n + ' B';
}

function setJpBodyBytes(n) {
  // Encoded byte length of the reference (JP) entry — read-only counterpart.
  const el = document.getElementById('jp-body-bytes');
  if (!el) return;
  if (n == null || n === 0) { el.textContent = ''; return; }
  el.textContent = n + ' B';
}

function startSavePolling() {
  if (SAVE_POLL) return;
  SAVE_POLL = setInterval(async () => {
    try {
      const s = await pywebview.api.get_save_state();
      if (s.state === 'queued' || s.state === 'saving') {
        setBadge('saving', 'saving…');
      } else if (s.state === 'saved' && s.seq !== LAST_SEEN_SEQ) {
        LAST_SEEN_SEQ = s.seq;
        setBadge('saved', 'saved ✓');
        clearInterval(SAVE_POLL); SAVE_POLL = null;
        if (SAVED_FADE_TIMER) clearTimeout(SAVED_FADE_TIMER);
        SAVED_FADE_TIMER = setTimeout(() => setBadge('idle', 'idle'), 3000);
      } else if (s.state === 'error') {
        setBadge('error', 'save failed: ' + (s.error || 'unknown'));
        clearInterval(SAVE_POLL); SAVE_POLL = null;
      }
    } catch (e) { /* swallow — keep polling */ }
  }, 120);
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

document.getElementById('body').addEventListener('input', () => {
  if (CURRENT.entry_i === null) return;
  const body = document.getElementById('body').value;
  setBadge('dirty', 'editing…');
  bumpSessionSave();
  if (DEBOUNCE) clearTimeout(DEBOUNCE);
  DEBOUNCE = setTimeout(async () => {
    try {
      const r = await pywebview.api.render_body(body, CURRENT.scenario);
      document.getElementById('preview-img').src = r.png;
      setBodyBytes(r.byte_count);
      await pywebview.api.queue_save(CURRENT.scenario, CURRENT.entry_i, body);
      // queue_save returns immediately; the file write happens ~400ms later
      // on a Python Timer. Poll get_save_state() to know when it lands.
      startSavePolling();
    } catch (err) {
      setBadge('error', 'save failed: ' + err);
    }
  }, 200);
});

// Cursor & scroll movements within the textarea also update session state.
document.getElementById('body').addEventListener('keyup', bumpSessionSave);
document.getElementById('body').addEventListener('click', bumpSessionSave);
document.getElementById('body').addEventListener('scroll', bumpSessionSave);

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    setBadge('saving', 'saving (manual)…');
    pywebview.api.flush_now();
    startSavePolling();
  }
});

window.addEventListener('beforeunload', () => {
  pywebview.api.flush_now();
});

// ---- Find / replace ----
const FIND_FLAGS = { case: false, regex: false };
let FIND_RESULTS = [];     // [{scenario, entry_i, start, end, ...}]
let FIND_INDEX = -1;       // current selection in FIND_RESULTS

function toggleFindBar() {
  const bar = document.getElementById('findbar');
  bar.classList.toggle('open');
  if (bar.classList.contains('open')) document.getElementById('find-q').focus();
  else { hideSearchResults(); }
}
function toggleFindFlag(name, btn) {
  FIND_FLAGS[name] = !FIND_FLAGS[name];
  btn.classList.toggle('act', FIND_FLAGS[name]);
  runSearch();  // rerun if query non-empty
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function showSearchResults(results, truncated) {
  const panel = document.getElementById('search-results');
  panel.innerHTML = '';
  if (!results.length) {
    panel.innerHTML = '<div class="empty">no matches</div>';
    panel.classList.add('open');
    return;
  }
  results.slice(0, 100).forEach((r, idx) => {
    const div = document.createElement('div');
    div.className = 'hit';
    div.innerHTML = `
      <div class="where">${r.scenario} · #${r.entry_i}</div>
      <div class="ctx">…${escapeHtml(r.before)}<b>${escapeHtml(r.match)}</b>${escapeHtml(r.after)}…</div>`;
    div.onclick = () => jumpToHit(idx);
    panel.appendChild(div);
  });
  if (truncated) {
    const note = document.createElement('div');
    note.className = 'empty';
    note.textContent = '(more matches not shown; refine query)';
    panel.appendChild(note);
  }
  panel.classList.add('open');
}
function hideSearchResults() {
  document.getElementById('search-results').classList.remove('open');
}

async function runSearch() {
  const q = document.getElementById('find-q').value;
  if (!q) { hideSearchResults(); FIND_RESULTS = []; FIND_INDEX = -1; updateFindCount(); return; }
  const res = await pywebview.api.search_text(
    q, FIND_FLAGS.case, FIND_FLAGS.regex,
    'all', 'en',
  );
  if (res.error) {
    document.getElementById('find-count').textContent = 'regex err';
    return;
  }
  FIND_RESULTS = res.matches;
  FIND_INDEX = -1;
  showSearchResults(res.matches, res.truncated);
  updateFindCount();
}

function updateFindCount() {
  const el = document.getElementById('find-count');
  if (!FIND_RESULTS.length) { el.textContent = ''; return; }
  el.textContent = `${FIND_INDEX < 0 ? 0 : FIND_INDEX + 1} of ${FIND_RESULTS.length}`;
}

async function jumpToHit(idx) {
  if (idx < 0 || idx >= FIND_RESULTS.length) return;
  const hit = FIND_RESULTS[idx];
  FIND_INDEX = idx;
  if (CURRENT.scenario !== hit.scenario) {
    await selectScenario(hit.scenario);
  }
  await selectEntry(hit.entry_i);
  const ta = document.getElementById('body');
  ta.focus();
  ta.setSelectionRange(hit.start, hit.end);
  // Scroll the selection into view
  const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 18;
  const before = ta.value.slice(0, hit.start);
  const lineNum = (before.match(/\n/g) || []).length;
  ta.scrollTop = Math.max(0, lineNum * lineHeight - 80);
  // Dismiss the results panel once we've jumped — the user wants the
  // textarea visible. They can re-open by editing the query.
  hideSearchResults();
  updateFindCount();
}

// Click-outside dismiss for the search-results panel. Listen on
// `mousedown` (not `click`) so we close BEFORE any text selection
// happens, which feels snappier.
document.addEventListener('mousedown', (e) => {
  const panel = document.getElementById('search-results');
  if (!panel.classList.contains('open')) return;
  // Keep the panel open if the click is inside it, inside the find-bar
  // (the find-bar drives it), or on the Find toolbar button itself.
  if (panel.contains(e.target)) return;
  if (document.getElementById('findbar').contains(e.target)) return;
  // The Find button has no id; match by its label text.
  if (e.target.closest('button') && e.target.closest('button').textContent.includes('Find')) return;
  hideSearchResults();
});

async function findNext() {
  if (!FIND_RESULTS.length) { await runSearch(); }
  if (!FIND_RESULTS.length) return;
  jumpToHit((FIND_INDEX + 1) % FIND_RESULTS.length);
}
async function findPrev() {
  if (!FIND_RESULTS.length) { await runSearch(); }
  if (!FIND_RESULTS.length) return;
  jumpToHit((FIND_INDEX - 1 + FIND_RESULTS.length) % FIND_RESULTS.length);
}

async function replaceOne() {
  if (FIND_INDEX < 0 || !FIND_RESULTS.length) {
    await findNext();
    return;
  }
  const hit = FIND_RESULTS[FIND_INDEX];
  const replacement = document.getElementById('find-r').value;
  await pywebview.api.replace_text(hit.scenario, hit.entry_i, hit.start, hit.end, replacement);
  // Refresh the entry in the editor — body changed
  if (CURRENT.scenario === hit.scenario && CURRENT.entry_i === hit.entry_i) {
    const e = await pywebview.api.get_entry(hit.scenario, hit.entry_i);
    document.getElementById('body').value = e.body;
    document.getElementById('preview-img').src = e.preview_png;
    setBodyBytes(e.byte_count);
    setJpBodyBytes(e.jp_byte_count);
  }
  // Re-run the search (offsets shifted after replacement)
  await runSearch();
}

// Debounced live search as user types in the query field
let SEARCH_DEBOUNCE = null;
document.getElementById('find-q').addEventListener('input', () => {
  if (SEARCH_DEBOUNCE) clearTimeout(SEARCH_DEBOUNCE);
  SEARCH_DEBOUNCE = setTimeout(runSearch, 200);
});

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault();
    if (!document.getElementById('findbar').classList.contains('open')) toggleFindBar();
    else document.getElementById('find-q').focus();
  }
});

// ---- Settings modal ----
function applyLabels(s) {
  // Drive every "EN" / "JP" UI label from the folder basename so the editor
  // generalizes to FR / ES / DE / KO / etc. without code changes.
  document.getElementById('lbl-editable').textContent = s.editable_label;
  document.getElementById('lbl-reference').textContent = s.reference_label;
  // Mirror in the settings modal too.
  document.getElementById('cfg-en-label').textContent = s.editable_label;
  document.getElementById('cfg-jp-label').textContent = s.reference_label;
  const l2a = document.getElementById('cfg-en-label2');
  const l2b = document.getElementById('cfg-jp-label2');
  if (l2a) l2a.textContent = s.editable_label;
  if (l2b) l2b.textContent = s.reference_label;
}

async function openSettings() {
  const s = await pywebview.api.get_settings();
  document.getElementById('cfg-en').value = s.en_dir;
  document.getElementById('cfg-jp').value = s.jp_dir;
  document.getElementById('cfg-en-meta').textContent =
    s.en_dir_exists ? `✓ exists  (default: ${s.default_en_dir})`
                    : `⚠ folder not found  (default: ${s.default_en_dir})`;
  document.getElementById('cfg-jp-meta').textContent =
    s.jp_dir_exists ? `✓ exists  (default: ${s.default_jp_dir})`
                    : `⚠ folder not found  (default: ${s.default_jp_dir})`;
  applyLabels(s);
  document.getElementById('settings-modal').classList.add('open');
}
function closeSettings() { document.getElementById('settings-modal').classList.remove('open'); }

async function browseFolder(which) {
  const inputId = which === 'en' ? 'cfg-en' : 'cfg-jp';
  const current = document.getElementById(inputId).value.trim();
  const chosen = await pywebview.api.pick_folder(current);
  if (chosen) {
    document.getElementById(inputId).value = chosen;
    // Update label preview live as the user picks
    const tmp = chosen.replace(/\/+$/, '').split('/').pop().toUpperCase().slice(0, 8) || '—';
    document.getElementById(which === 'en' ? 'cfg-en-label' : 'cfg-jp-label').textContent = tmp;
    const l2 = document.getElementById(which === 'en' ? 'cfg-en-label2' : 'cfg-jp-label2');
    if (l2) l2.textContent = tmp;
  }
}

async function saveSettings() {
  const en = document.getElementById('cfg-en').value.trim();
  const jp = document.getElementById('cfg-jp').value.trim();
  const s = await pywebview.api.set_settings(en, jp);
  applyLabels(s);
  closeSettings();
  // Reload scenarios from new paths
  await loadScenarios();
}

// On launch, apply labels once so the editor textareas show the right
// pair (e.g. EN/JP, FR/JP, etc.) before any settings change.
async function applyLabelsAtStartup() {
  try {
    const s = await pywebview.api.get_settings();
    applyLabels(s);
  } catch (e) { /* pywebview not ready yet — applyLabels will fire from loadScenarios */ }
}

window.addEventListener('pywebviewready', loadScenarios);
</script></body></html>"""


def main() -> None:
    if not EN_DATA_DIR.is_dir():
        sys.exit(f"missing {EN_DATA_DIR}")
    bridge = Bridge()
    print(f"Loaded {len(bridge.scenarios)} scenarios, "
          f"{sum(len(s.entries) for s in bridge.scenarios.values())} total entries.")

    # Write HTML to temp file (pywebview handles file:// URLs better than inline)
    tmp = tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    )
    tmp.write(HTML)
    tmp.close()

    try:
        import webview
    except ImportError:
        sys.exit("pywebview not installed; pip install pywebview[qt]")

    window = webview.create_window(
        "rbshura — Script Editor",
        url=f"file://{tmp.name}",
        js_api=bridge,
        width=1400,
        height=900,
        min_size=(900, 600),
    )
    try:
        webview.start(debug=False)
    finally:
        bridge.flush_now()  # final flush on exit
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
