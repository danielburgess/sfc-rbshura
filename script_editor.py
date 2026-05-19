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
EN_DATA_DIR = ROOT / "data" / "en"
EN_TABLE_PATH = ROOT / "tables" / "rbshura_en.tbl"
PORTRAIT_ASSETS = ROOT / "assets" / "portraits"

# Per-user editor state (last scenario / entry / cursor). Project-local so
# it travels with the checkout if someone re-clones. JSON, gitignored.
EDITOR_STATE_PATH = ROOT / ".editor-state.json"

# Source-of-truth ROM for the font preview. Must be patched with the PK font
# + half-width renderer (apply_pk_font.py) so the bytes at FONT_PC match
# what the in-game renderer actually DMAs to VRAM. We prefer the
# fully-built EN ROM (rbshura_en_24bit.sfc) because it ships in the user's
# tested build, falling back to rbshura_pkfont_24bit.sfc / rbshura_pkfont.sfc.
ROM_CANDIDATES = [
    ROOT / "rbshura_en_24bit.sfc",
    ROOT / "rbshura_pkfont_24bit.sfc",
    ROOT / "rbshura_pkfont.sfc",
]
FONT_PC = 0x100000
FONT_SLOT_STRIDE = 64        # rbshura's per-glyph slot in ROM
FONT_GLYPH_COUNT = 247       # $00..$F6

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
        f"run scripts/build_24bit.py first."
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
    rom: bytes, palette: list[tuple[int, int, int, int]]
) -> Image.Image:
    """Decode the half-width font from `rom` using the given 4-color palette.

    Pixel value 0 (palette[0]) is rendered transparent so the underlying
    dialog backdrop shows through — _draw_dialog_box fills that area with
    palette[0] separately. Values 1-3 take the speaker's outline/mid/bright
    colors.
    """
    cols = 16
    rows = (FONT_GLYPH_COUNT + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * GLYPH_W, rows * GLYPH_H), (0, 0, 0, 0))
    # Slot 0 is the dialog backdrop — render glyph pixel value 0 as transparent
    # so the per-page dialog box's own backdrop fill shows through (cleaner
    # compositing for letters with internal "holes").
    render_pal = [(0, 0, 0, 0)] + palette[1:]
    for gi in range(FONT_GLYPH_COUNT):
        base = FONT_PC + gi * FONT_SLOT_STRIDE
        if base + BYTES_PER_GLYPH > len(rom):
            break
        top = _decode_tile_2bpp(rom, base)
        bot = _decode_tile_2bpp(rom, base + TILE_BYTES)
        gx = (gi % cols) * GLYPH_W
        gy = (gi // cols) * GLYPH_H
        for py in range(8):
            for px in range(8):
                atlas.putpixel((gx + px, gy + py), render_pal[top[py * 8 + px]])
                atlas.putpixel((gx + px, gy + 8 + py), render_pal[bot[py * 8 + px]])
    return atlas


def load_font_atlases() -> tuple[bytes, list[list[tuple[int, int, int, int]]], dict[int, Image.Image]]:
    """Load ROM + extract palettes + pre-render one atlas per speaker.

    Returns (rom_bytes, palettes, atlas_by_portrait_id). Atlas building is
    eager because there are only ~16 portraits and each atlas is ~64 KB —
    cheap to cache, and per-glyph render is then a fast crop+paste.
    """
    rom_path = _pick_rom()
    print(f"  font source: {rom_path.name}")
    rom = rom_path.read_bytes()
    palettes = load_portrait_palettes(rom)
    print(f"  extracted {len(palettes)} per-portrait palettes from ${PALETTE_TABLE_PC:06X}")
    atlases: dict[int, Image.Image] = {}
    for pid, pal in enumerate(palettes):
        atlases[pid] = _build_atlas_for_palette(rom, pal)
    return rom, palettes, atlases


# Kept for backward compatibility (older test scaffolding) — uses portrait 0's
# palette as a default neutral atlas.
def load_font_atlas() -> Image.Image:
    rom_path = _pick_rom()
    print(f"  font source: {rom_path.name}")
    rom = rom_path.read_bytes()
    palettes = load_portrait_palettes(rom)
    return _build_atlas_for_palette(rom, palettes[0] if palettes else FALLBACK_PALETTE)


# ---------------------------------------------------------------------------
# rbshura_en.tbl — char ↔ byte mapping
# ---------------------------------------------------------------------------

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

ENTRY_HEADER_RE = re.compile(r"<<\$(\d+):(\d+)\[\$(\d+)\]>>")


class Scenario:
    """One scenario_NN.txt — list of (header_dec, idx, body) entries."""
    def __init__(self, path: Path):
        self.path = path
        self.raw: str = ""
        self.entries: list[dict] = []  # each: {idx, ptr_dec, body_dec, body}
        self.reload()

    def reload(self) -> None:
        self.raw = self.path.read_text(encoding="utf-16")
        self.entries = []
        # Split into chunks: header line + body until next header
        # Pattern: <<$DEC:DEC[$DEC]>>\nbody\n
        parts = re.split(r"(<<\$\d+:\d+\[\$\d+\]>>)\n", self.raw)
        # parts[0] is any text before the first header (usually empty)
        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            m = ENTRY_HEADER_RE.match(header)
            if not m:
                continue
            # Trim trailing newline so we round-trip cleanly
            body = body.rstrip("\n")
            self.entries.append({
                "ptr_tbl_dec": int(m.group(1)),
                "idx": int(m.group(2)),
                "ptr_dec": int(m.group(3)),
                "body": body,
            })

    def save_entry(self, entry_idx: int, new_body: str) -> None:
        """Rewrite one entry's body and write the full file atomically."""
        self.entries[entry_idx]["body"] = new_body
        # Rebuild the full content
        out: list[str] = []
        for e in self.entries:
            out.append(
                f"<<${e['ptr_tbl_dec']}:{e['idx']}[${e['ptr_dec']}]>>\n"
                f"{e['body']}\n"
            )
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
            for part in token.split(":"):
                part = part.strip()
                if len(part) == 2:
                    try:
                        out.append(("byte", int(part, 16)))
                    except ValueError:
                        out.append(("char", "[" + token + "]"))
                        break
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


def body_to_lines(body: str, char_to_byte: dict[str, int]) -> list:
    """Parse a body into renderable lines. Returns a list where each item is
    either a list[int] of glyph indices (a line) or None (page-break gutter).
    """
    pages: list[list[list[int]]] = [[[]]]
    def current_line() -> list[int]: return pages[-1][-1]
    def new_line(): pages[-1].append([])
    def new_page(): pages.append([[]])

    tokens = _tokenize_brackets(body)
    i = 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "nl":
            # Soft newline in source: not a game newline, just a wrap. Skip.
            i += 1
            continue
        if kind == "char":
            b = char_to_byte.get(val)
            if b is None:
                # Unknown char — render as space so the user sees something
                b = 0x00
            current_line().append(b)
            i += 1
            continue
        # byte
        b = val
        if b == 0xFD:
            new_line(); i += 1
        elif b == 0xFE:
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

    # Flatten + word-wrap to COLS_PER_LINE
    flat: list = []
    for pi, page in enumerate(pages):
        if pi > 0:
            flat.append(None)
        for ln in page:
            if not ln:
                flat.append([])
                continue
            for off in range(0, len(ln), COLS_PER_LINE):
                flat.append(ln[off:off + COLS_PER_LINE])
    return flat


def _draw_dialog_box(
    lines: list,                 # list of list[int] glyph rows for one page
    atlas: Image.Image,
    backdrop_rgba: tuple[int, int, int, int],
) -> Image.Image:
    """Render one page (already split — no None entries) to a bordered
    dialog box. `backdrop_rgba` is palette slot 0 of the active speaker —
    the actual in-game color behind the text. Returns an RGB Image at 1×."""
    pad = 12
    text_w = COLS_PER_LINE * GLYPH_W
    text_h = max(GLYPH_H, len(lines) * GLYPH_H)
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

    cols = 16  # atlas columns
    y = pad
    for line in lines:
        x = pad
        for gi in line:
            ax = (gi % cols) * GLYPH_W
            ay = (gi // cols) * GLYPH_H
            glyph = atlas.crop((ax, ay, ax + GLYPH_W, ay + GLYPH_H))
            img.paste(glyph, (x, y), glyph)
            x += GLYPH_W
        y += GLYPH_H
    return img


def render_preview(
    body: str,
    atlas: Image.Image,
    char_to_byte: dict[str, int],
    backdrop_rgba: tuple[int, int, int, int] = (8, 48, 8, 255),
) -> bytes:
    """Render an entry to a PNG matching the in-game 24-col layout.

    `atlas` and `backdrop_rgba` should come from the SAME speaker palette
    (see Bridge.get_entry / render_body for the lookup). Multi-page entries
    (containing [FE] page breaks) render as separate dialog boxes stacked
    vertically — same visual model as the game, which clears between pages.
    """
    lines = body_to_lines(body, char_to_byte)

    pages: list[list[list[int]]] = [[]]
    for ln in lines:
        if ln is None:
            pages.append([])
        else:
            pages[-1].append(ln)
    if not pages or all(not p for p in pages):
        pages = [[[]]]

    GAP = 10
    page_imgs = [_draw_dialog_box(p, atlas, backdrop_rgba) for p in pages]
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
        self.scenarios: dict[str, Scenario] = {}
        self._save_timer: Optional[threading.Timer] = None
        self._save_lock = threading.Lock()
        self._pending: dict[tuple[str, int], str] = {}
        # Save state: "idle" → "queued" → "saving" → "saved" / "error".
        # JS polls get_save_state() after queueing a save so the badge can
        # remain in "saving" until Python has actually flushed to disk.
        self._save_state = "idle"
        self._save_error: Optional[str] = None
        self._save_seq = 0  # monotonic; lets JS detect "this save completed"
        for p in sorted(EN_DATA_DIR.glob("scenario_*.txt")):
            self.scenarios[p.stem] = Scenario(p)

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

    def get_entry(self, scenario_name: str, entry_i: int) -> dict:
        sc = self.scenarios[scenario_name]
        e = sc.entries[entry_i]
        pid = extract_portrait_id(e["body"])
        atlas, backdrop = self._palette_for(pid)
        png = render_preview(e["body"], atlas, self.char_to_byte, backdrop)
        b64 = base64.b64encode(png).decode("ascii")
        return {
            "body": e["body"],
            "preview_png": f"data:image/png;base64,{b64}",
            "portrait_id": pid,
            "portrait_name": portrait_name(pid) if pid is not None else None,
            "portrait_image": portrait_image_uri(pid),
        }

    def render_body(self, body: str) -> str:
        """Cheap render-only call (no file write) for live preview."""
        pid = extract_portrait_id(body)
        atlas, backdrop = self._palette_for(pid)
        png = render_preview(body, atlas, self.char_to_byte, backdrop)
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

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
.text-area { flex: 1; display: flex; flex-direction: column; padding: 12px; gap: 8px; }
.text-area label { font-size: 11px; color: var(--fg2); text-transform: uppercase; letter-spacing: .5px; }
textarea { flex: 1; font-family: var(--code); font-size: 13px; line-height: 1.5;
           background: var(--bg2); color: var(--fg); border: 1px solid var(--brd);
           border-radius: 4px; padding: 10px; resize: none; outline: none; }
textarea:focus { border-color: var(--acc); }
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
      <span class="hint">Autosave on edit · live preview</span>
    </div>
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
        <label>BODY (control codes in brackets — preserved on save)</label>
        <textarea id="body" spellcheck="false" placeholder="select an entry"></textarea>
        <div class="hint">
          Codes: <code>[FD]</code>=newline · <code>[FE]</code>=page break ·
          <code>[F7:FF]</code>=end · <code>[FB:15]</code>=window ·
          <code>[F8:01]</code>=speed · <code>[F9:XX]</code>=portrait ·
          <code>[FC:01:02]</code>/<code>[FC:02:XX:YY]</code>=ctl
        </div>
      </div>
    </div>
    <div class="empty" id="empty">Pick a scenario → entry to start editing.</div>
  </div>

<script>
let CURRENT = { scenario: null, entry_i: null };
let DEBOUNCE = null;

async function loadScenarios() {
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
  document.getElementById('preview-img').src = e.preview_png;
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
      const png = await pywebview.api.render_body(body);
      document.getElementById('preview-img').src = png;
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
