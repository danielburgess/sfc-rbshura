#!/usr/bin/env python3
"""
preview.py — Script preview app for Rushing Beat Shura translation.

Renders dialogue using the actual game fonts (16x16 2bpp tiles from ROM)
in a pywebview[qt] window. Shows JP and EN side-by-side with scene grouping.

Usage:
    python preview.py [rom_path]
    python preview.py --browser        # open in system browser instead
"""

import base64
import html as html_mod
import io
import os
import re
import sys
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROM_PATH = "rbshura.sfc"
DUMP_PATH = "text/dialogue_dump_translated.txt"
JP_TABLE_PATH = "tables/jp.tbl"
EN_TABLE_PATH = "tables/en.tbl"
EN_FONT_BIN = "fonts/en_font.bin"
FONT_PC = 0x100000
BYTES_PER_CHAR = 64   # 16x16 = 4 tiles x 16 bytes (2bpp)
CHARS_PER_PAGE = 247   # $00-$F6
CHAR_W, CHAR_H = 16, 16
MAX_LINE_CHARS = 14    # game text box width in characters
SCENE_GAP = 64         # byte gap threshold for scene boundaries

# Game palette for 2bpp text (dark background, light text)
# Indices 0-3: transparent, dark, mid, bright
PALETTE = [
    (0, 0, 0, 0),       # 0: transparent (background)
    (40, 40, 60, 255),   # 1: dark shadow
    (180, 180, 200, 255),# 2: mid
    (255, 255, 255, 255),# 3: bright (main text)
]

# Dialogue window background color (dark blue-ish, like game)
WIN_BG = (16, 16, 40, 230)

# ---------------------------------------------------------------------------
# ROM helpers
# ---------------------------------------------------------------------------

def load_rom(path: str) -> bytes:
    with open(path, "rb") as f:
        data = f.read()
    if len(data) % 0x10000 == 512:
        data = data[512:]
    return data


def decode_2bpp_tile(data: bytes, offset: int) -> list[int]:
    """Decode one 8x8 2bpp tile (16 bytes) into 64 palette indices."""
    pixels = [0] * 64
    for row in range(8):
        b0 = data[offset + row * 2]
        b1 = data[offset + row * 2 + 1]
        for col in range(8):
            bit = 7 - col
            p = ((b0 >> bit) & 1) | (((b1 >> bit) & 1) << 1)
            pixels[row * 8 + col] = p
    return pixels


def extract_char_image(rom: bytes, page: int, char_idx: int) -> Image.Image:
    """Extract a single 16x16 character as an RGBA PIL Image."""
    base = FONT_PC + page * (CHARS_PER_PAGE * BYTES_PER_CHAR) + char_idx * BYTES_PER_CHAR
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))

    # 4 tiles: TL(0), TR(1), BL(2), BR(3)
    for tile_idx in range(4):
        tile_col = tile_idx % 2  # 0=left, 1=right  (TL=0, TR=1, BL=2, BR=3)
        tile_row = tile_idx // 2
        pixels = decode_2bpp_tile(rom, base + tile_idx * 16)
        for py in range(8):
            for px in range(8):
                pi = pixels[py * 8 + px]
                x = tile_col * 8 + px
                y = tile_row * 8 + py
                img.putpixel((x, y), PALETTE[pi])

    return img


# ---------------------------------------------------------------------------
# Font atlas builder
# ---------------------------------------------------------------------------

def build_font_atlas(rom: bytes, page: int) -> Image.Image:
    """Build a 256-wide atlas of all characters for one font page.
    Each char occupies a 16x16 cell. 16 chars per row, ~16 rows."""
    cols = 16
    rows = (CHARS_PER_PAGE + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * CHAR_W, rows * CHAR_H), (0, 0, 0, 0))

    for ci in range(CHARS_PER_PAGE):
        char_img = extract_char_image(rom, page, ci)
        cx = (ci % cols) * CHAR_W
        cy = (ci // cols) * CHAR_H
        atlas.paste(char_img, (cx, cy))

    return atlas


def build_en_font_atlas(font_bin_path: str) -> Image.Image:
    """Build atlas from the standalone EN font binary."""
    with open(font_bin_path, "rb") as f:
        data = f.read()

    n_chars = len(data) // BYTES_PER_CHAR
    cols = 16
    rows = (n_chars + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * CHAR_W, rows * CHAR_H), (0, 0, 0, 0))

    for ci in range(n_chars):
        base = ci * BYTES_PER_CHAR
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for tile_idx in range(4):
            tc = tile_idx % 2
            tr = tile_idx // 2
            pixels = decode_2bpp_tile(data, base + tile_idx * 16)
            for py in range(8):
                for px in range(8):
                    pi = pixels[py * 8 + px]
                    img.putpixel((tc * 8 + px, tr * 8 + py), PALETTE[pi])
        cx = (ci % cols) * CHAR_W
        cy = (ci // cols) * CHAR_H
        atlas.paste(img, (cx, cy))

    return atlas


def atlas_to_data_uri(atlas: Image.Image) -> str:
    buf = io.BytesIO()
    atlas.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Text rendering to image
# ---------------------------------------------------------------------------

def render_line_to_image(
    text: str,
    table: dict,
    atlas: Image.Image,
    is_english: bool,
    max_chars: int = MAX_LINE_CHARS,
) -> Image.Image | None:
    """Render a single dialogue entry (with control codes) into a PIL Image.
    Returns the cropped image or None if no displayable chars."""

    # Parse the text into a list of lines (split on {NL} and {PB})
    # Strip control codes that aren't display-related
    clean = re.sub(r"\{(?:PORT|SPD|FC|WIN):[^}]+\}", "", text)

    # Split into pages (PB) then lines (NL)
    pages = clean.split("{PB}")
    all_lines = []
    for page in pages:
        lines = page.split("{NL}")
        for line in lines:
            all_lines.append(line.strip())
        if page != pages[-1]:
            all_lines.append(None)  # page break marker

    # Convert text chars to tile indices
    rendered_lines: list[list[int] | None] = []
    for line in all_lines:
        if line is None:
            rendered_lines.append(None)
            continue

        indices = []
        if is_english:
            indices = text_to_indices_en(line, table)
        else:
            indices = text_to_indices_jp(line, table)
        rendered_lines.append(indices)

    # Calculate image size
    max_width = 0
    total_height = 0
    line_heights = []

    for rline in rendered_lines:
        if rline is None:
            # Page break - small gap
            line_heights.append(4)
            total_height += 4
        else:
            # Word-wrap into sub-lines
            sub_lines = wrap_indices(rline, max_chars)
            h = len(sub_lines) * CHAR_H
            line_heights.append(h)
            total_height += h
            for sl in sub_lines:
                w = len(sl) * CHAR_W
                if w > max_width:
                    max_width = w

    if max_width == 0 or total_height == 0:
        return None

    # Padding
    pad = 8
    img_w = max_width + pad * 2
    img_h = total_height + pad * 2

    img = Image.new("RGBA", (img_w, img_h), WIN_BG)

    y = pad
    cols = 16  # atlas columns

    for i, rline in enumerate(rendered_lines):
        if rline is None:
            # Draw page break line
            for x in range(pad, img_w - pad, 4):
                if x + 1 < img_w:
                    img.putpixel((x, y + 1), (100, 100, 140, 200))
                    img.putpixel((x + 1, y + 1), (100, 100, 140, 200))
            y += line_heights[i]
            continue

        sub_lines = wrap_indices(rline, max_chars)
        for sl in sub_lines:
            x = pad
            for ci in sl:
                # Get char from atlas
                ax = (ci % cols) * CHAR_W
                ay = (ci // cols) * CHAR_H
                char_tile = atlas.crop((ax, ay, ax + CHAR_W, ay + CHAR_H))
                img.paste(char_tile, (x, y), char_tile)
                x += CHAR_W
            y += CHAR_H

    return img


def wrap_indices(indices: list[int], max_chars: int) -> list[list[int]]:
    """Simple wrap: break at max_chars boundary."""
    if not indices:
        return [[]]
    lines = []
    for i in range(0, len(indices), max_chars):
        lines.append(indices[i:i + max_chars])
    return lines


def text_to_indices_jp(text: str, table: dict) -> list[int]:
    """Convert JP display text to font tile indices using the table."""
    reverse = {}
    for k, v in table.items():
        if v and v.strip():
            reverse[v] = k

    indices = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in reverse:
            val = reverse[c]
            if val > 0xFF:
                # Page 2 char (FA prefix) - use val & 0xFF as page 2 index
                indices.append(CHARS_PER_PAGE + (val & 0xFF))
            else:
                indices.append(val)
            i += 1
        elif c == '[':
            # Hex literal [XX] or [FA:XX]. Be defensive: a stray '[' or a
            # non-hex token must not crash the whole preview build.
            end = text.find(']', i)
            if end == -1:
                indices.append(0x00)   # unmatched '[' → render as blank
                i += 1
                continue
            hex_content = text[i + 1:end]
            try:
                if ':' in hex_content:
                    _, val_s = hex_content.split(':')
                    indices.append(CHARS_PER_PAGE + int(val_s, 16))
                else:
                    indices.append(int(hex_content, 16))
            except ValueError:
                indices.append(0x00)   # not a hex token → render as blank
            i = end + 1
        else:
            # Unknown - try direct lookup
            if c != ' ':
                # Look for fullwidth space ($CC)
                if 0xCC in table and table[0xCC] == '':
                    indices.append(0xCC)
                else:
                    indices.append(0x00)
            else:
                indices.append(0xCC)
            i += 1
    return indices


def text_to_indices_en(text: str, table: dict) -> list[int]:
    """Convert EN display text to font tile indices."""
    reverse = {}
    for k, v in table.items():
        if isinstance(k, int) and k < 0xF7 and v:
            reverse[v] = k

    indices = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in reverse:
            indices.append(reverse[c])
            i += 1
        elif c == ' ':
            indices.append(0x00)  # space
            i += 1
        elif c == '[':
            end = text.find(']', i)
            if end == -1:
                indices.append(0x00)   # unmatched '[' → render as blank
                i += 1
                continue
            hex_content = text[i + 1:end]
            try:
                if ':' in hex_content:
                    _, val_s = hex_content.split(':')
                    indices.append(int(val_s, 16))
                else:
                    indices.append(int(hex_content, 16))
            except ValueError:
                indices.append(0x00)   # not a hex token → render as blank
            i = end + 1
        else:
            indices.append(0x00)  # fallback to space
            i += 1
    return indices


def render_to_data_uri(img: Image.Image, scale: int = 2) -> str:
    """Scale and encode image as data URI."""
    if scale != 1:
        img = img.resize(
            (img.width * scale, img.height * scale),
            Image.Resampling.NEAREST,
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Parse dialogue dump (same as before)
# ---------------------------------------------------------------------------

def load_table(path: str) -> dict:
    table = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            try:
                table[int(key, 16)] = val
            except ValueError:
                continue
    return table


def parse_dialogue_dump(path: str) -> list[dict]:
    entries = []
    current = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            if line.startswith("#"):
                continue

            if line.startswith("@"):
                if current:
                    entries.append(current)
                m = re.match(
                    r"@(\d+)\s+PC=\$([0-9A-Fa-f]+)\s+BANK=(\S+)\s+END=([0-9A-Fa-f]+)",
                    line,
                )
                if m:
                    current = {
                        "id": int(m.group(1)),
                        "pc": int(m.group(2), 16),
                        "bank": m.group(3),
                        "end_param": m.group(4),
                        "raw_hex": "",
                        "jp_text": "",
                        "en_text": "",
                    }
                continue

            if current is None:
                continue

            if line.startswith(";raw:"):
                current["raw_hex"] = line[5:].strip()
            elif line.startswith(">"):
                current["en_text"] = line[1:]
            elif line == "":
                if current:
                    entries.append(current)
                    current = None
            elif not current["jp_text"]:
                current["jp_text"] = line

    if current:
        entries.append(current)
    return entries


def group_into_scenes(entries: list[dict]) -> list[dict]:
    if not entries:
        return []

    scenes = []
    current = {
        "scene_id": 0,
        "bank": entries[0]["bank"],
        "start_pc": entries[0]["pc"],
        "entries": [0],
    }

    for i in range(1, len(entries)):
        gap = entries[i]["pc"] - entries[i - 1]["pc"]
        new_bank = entries[i]["bank"] != entries[i - 1]["bank"]
        if gap > SCENE_GAP or new_bank:
            current["end_pc"] = entries[i - 1]["pc"]
            scenes.append(current)
            current = {
                "scene_id": len(scenes),
                "bank": entries[i]["bank"],
                "start_pc": entries[i]["pc"],
                "entries": [i],
            }
        else:
            current["entries"].append(i)

    current["end_pc"] = entries[-1]["pc"]
    scenes.append(current)
    return scenes


# ---------------------------------------------------------------------------
# Portrait names
# ---------------------------------------------------------------------------

# Left empty until portrait IDs are visually verified. The previous mapping
# (Dick/Spider/Kythring/McCoy/Jimmy/Dag) was confirmed WRONG by the user on
# 2026-05-17; script_editor.py is the source of truth and keeps this empty.
PORTRAIT_NAMES: dict[int, str] = {}


def extract_portrait(text: str) -> str | None:
    m = re.search(r"\{PORT:([0-9A-Fa-f]+)\}", text)
    if m:
        pid = int(m.group(1), 16)
        return PORTRAIT_NAMES.get(pid, f"Char #{pid:02X}")
    return None


# ---------------------------------------------------------------------------
# Build HTML with rendered font images
# ---------------------------------------------------------------------------

def build_html(
    entries: list[dict],
    scenes: list[dict],
    jp_table: dict,
    en_table: dict,
    jp_atlas_p0: Image.Image,
    jp_atlas_p1: Image.Image,
    en_atlas: Image.Image,
) -> str:
    # Combine JP page 0 + page 1 into one tall atlas
    # Page 0: chars 0x00-0xF6 (247 chars)
    # Page 1: chars accessed via FA prefix
    jp_combined_h = jp_atlas_p0.height + jp_atlas_p1.height
    jp_atlas = Image.new("RGBA", (jp_atlas_p0.width, jp_combined_h), (0, 0, 0, 0))
    jp_atlas.paste(jp_atlas_p0, (0, 0))
    jp_atlas.paste(jp_atlas_p1, (0, jp_atlas_p0.height))

    print("  Rendering dialogue images...")
    total = len(entries)
    translated_count = 0
    entry_html_parts = []
    scene_nav_parts = []

    # Pre-render all entries
    rendered_entries = []
    for i, e in enumerate(entries):
        jp_clean = re.sub(r"\{(?:PORT|SPD|FC|WIN):[^}]+\}", "", e["jp_text"])
        en_clean = re.sub(r"\{(?:PORT|SPD|FC|WIN):[^}]+\}", "", e["en_text"])

        jp_img = render_line_to_image(jp_clean, jp_table, jp_atlas, False)
        en_img = None
        has_en = bool(en_clean.strip())
        if has_en:
            en_img = render_line_to_image(en_clean, en_table, en_atlas, True)
            translated_count += 1

        rendered_entries.append((jp_img, en_img, has_en))

        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{total}...")

    pct = int(100 * translated_count / total) if total else 0
    print(f"  {translated_count}/{total} translated ({pct}%)")

    # Build scene nav + entry HTML
    for sc in scenes:
        first_e = entries[sc["entries"][0]]
        last_e = entries[sc["entries"][-1]]
        n = len(sc["entries"])
        speakers = set()
        sc_translated = 0
        for idx in sc["entries"]:
            p = extract_portrait(entries[idx]["jp_text"])
            if p:
                speakers.add(p)
            if rendered_entries[idx][2]:
                sc_translated += 1

        sp_str = ", ".join(sorted(speakers))
        sc_pct = int(100 * sc_translated / n) if n else 0
        prog_cls = "complete" if sc_pct == 100 else "partial" if sc_pct > 0 else "none"

        scene_nav_parts.append(f"""
            <div class="snav {prog_cls}" onclick="scrollTo('scene-{sc['scene_id']}')">
                <b>Scene {sc['scene_id']}</b>
                <span class="sm">#{first_e['id']:04d}–#{last_e['id']:04d} ({n})</span>
                {"<span class='sp'>" + sp_str + "</span>" if sp_str else ""}
                <div class="pb"><div class="pf" style="width:{sc_pct}%"></div></div>
            </div>
        """)

        entry_html_parts.append(f"""
            <div class="sh" id="scene-{sc['scene_id']}">
                <h2>Scene {sc['scene_id']}</h2>
                <span class="sm">#{first_e['id']:04d}–#{last_e['id']:04d} | {sc['bank']} | {sp_str if sp_str else 'no portraits'} | {sc_translated}/{n}</span>
            </div>
        """)

        for idx in sc["entries"]:
            e = entries[idx]
            jp_img, en_img, has_en = rendered_entries[idx]
            portrait = extract_portrait(e["jp_text"])

            jp_uri = render_to_data_uri(jp_img, 2) if jp_img else ""
            en_uri = render_to_data_uri(en_img, 2) if en_img else ""

            jp_html = f'<img src="{jp_uri}" class="ti">' if jp_uri else '<span class="empty">—</span>'
            en_html = f'<img src="{en_uri}" class="ti">' if en_uri else '<span class="empty">(not translated)</span>'

            row_cls = "tr" if has_en else "ut"
            sp_badge = f'<span class="spk">{portrait}</span>' if portrait else ""

            # Clean text for search data attributes and tooltips
            jp_plain = re.sub(r"\{[^}]+\}", " ", e["jp_text"]).strip()
            en_plain = re.sub(r"\{[^}]+\}", " ", e["en_text"]).strip()
            jp_esc = html_mod.escape(jp_plain, quote=True)
            en_esc = html_mod.escape(en_plain, quote=True)

            entry_html_parts.append(f"""
                <div class="ent {row_cls}" id="entry-{e['id']}" data-jp="{jp_esc}" data-en="{en_esc}">
                    <div class="eh">
                        <span class="eid">@{e['id']:04d}</span>
                        <span class="epc">PC ${e['pc']:06X}</span>
                        {sp_badge}
                    </div>
                    <div class="eb">
                        <div class="cj"><div class="cl">Japanese</div>{jp_html}<div class="tt">{jp_esc}</div></div>
                        <div class="ce"><div class="cl">English</div>{en_html}<div class="tt">{en_esc}</div></div>
                    </div>
                </div>
            """)

    nav_html = "\n".join(scene_nav_parts)
    main_html = "\n".join(entry_html_parts)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Rushing Beat Shura — Script Preview</title>
<style>
:root{{--bg:#101028;--bg2:#161638;--bg3:#0f3460;--fg:#e0e0e0;--fg2:#8888a0;
--acc:#e94560;--acc2:#533483;--grn:#4ecca3;--yel:#f0c040;--brd:#2a2a4e;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Segoe UI',sans-serif;background:var(--bg);color:var(--fg);
display:flex;height:100vh;overflow:hidden;}}
.side{{width:280px;min-width:280px;background:var(--bg2);border-right:1px solid var(--brd);
display:flex;flex-direction:column;overflow:hidden;}}
.shdr{{padding:14px 16px;border-bottom:1px solid var(--brd);}}
.shdr h1{{font-size:13px;color:var(--acc);margin-bottom:6px;}}
.stats{{font-size:12px;color:var(--fg2);}}
.pb{{margin-top:5px;height:5px;background:var(--brd);border-radius:3px;}}
.pf{{height:100%;background:var(--grn);border-radius:3px;}}
.jbox,.sbox{{padding:6px 14px;border-bottom:1px solid var(--brd);}}
.jbox input,.sbox input{{width:100%;padding:5px 8px;background:var(--bg);
border:1px solid var(--brd);border-radius:4px;color:var(--fg);font-size:12px;outline:none;}}
.jbox input:focus,.sbox input:focus{{border-color:var(--acc);}}
.fbar{{padding:5px 14px;border-bottom:1px solid var(--brd);display:flex;gap:5px;}}
.fb{{padding:2px 7px;font-size:11px;border:1px solid var(--brd);border-radius:3px;
background:transparent;color:var(--fg2);cursor:pointer;}}
.fb.act{{background:var(--acc);border-color:var(--acc);color:#fff;}}
.slist{{flex:1;overflow-y:auto;padding:6px;}}
.snav{{padding:6px 8px;margin-bottom:3px;border-radius:4px;cursor:pointer;
border-left:3px solid transparent;font-size:12px;}}
.snav:hover{{background:var(--bg3);}}
.snav.act{{background:var(--bg3);border-left-color:var(--acc);}}
.snav.complete{{border-left-color:var(--grn);}}
.snav.partial{{border-left-color:var(--yel);}}
.snav.none{{border-left-color:var(--brd);}}
.snav .pb{{margin-top:3px;height:3px;}}
.sm{{font-size:11px;color:var(--fg2);}}
.sp{{font-size:11px;color:var(--acc);display:block;}}
.main{{flex:1;overflow-y:auto;padding:16px 20px;scroll-behavior:smooth;}}
.sh{{margin:20px 0 10px 0;padding-bottom:6px;border-bottom:2px solid var(--acc);}}
.sh:first-child{{margin-top:0;}}
.sh h2{{font-size:15px;color:var(--acc);}}
.ent{{margin-bottom:10px;border:1px solid var(--brd);border-radius:5px;
overflow:hidden;background:var(--bg2);}}
.ent.ut{{border-left:3px solid var(--yel);}}
.ent.tr{{border-left:3px solid var(--grn);}}
.eh{{padding:4px 10px;background:rgba(0,0,0,.25);display:flex;gap:10px;
align-items:center;font-size:11px;}}
.eid{{font-weight:700;color:var(--acc);font-family:monospace;}}
.epc{{color:var(--fg2);font-family:monospace;}}
.spk{{background:var(--acc2);padding:1px 7px;border-radius:3px;font-size:10px;}}
.eb{{display:flex;}}
.cj,.ce{{flex:1;padding:8px 10px;}}
.cj{{border-right:1px solid var(--brd);}}
.cl{{font-size:9px;text-transform:uppercase;color:var(--fg2);margin-bottom:4px;letter-spacing:.5px;}}
.ti{{display:block;image-rendering:pixelated;max-width:100%;}}
.empty{{color:var(--fg2);font-style:italic;font-size:13px;}}
.tt{{font-size:11px;color:var(--fg2);margin-top:4px;line-height:1.4;word-break:break-all;}}
::-webkit-scrollbar{{width:7px;}}
::-webkit-scrollbar-track{{background:var(--bg);}}
::-webkit-scrollbar-thumb{{background:var(--brd);border-radius:4px;}}
</style></head><body>
<div class="side">
    <div class="shdr">
        <h1>RUSHING BEAT SHURA</h1>
        <div class="stats">{translated_count}/{total} translated ({pct}%)
            <div class="pb"><div class="pf" style="width:{pct}%"></div></div>
        </div>
    </div>
    <div class="jbox"><input id="ji" placeholder="Jump to @ID (e.g. 42)"
        onkeydown="if(event.key==='Enter')jump()"></div>
    <div class="sbox"><input id="si" placeholder="Search text..." oninput="filt()"></div>
    <div class="fbar">
        <button class="fb act" onclick="sf('all',this)">All</button>
        <button class="fb" onclick="sf('ut',this)">Untranslated</button>
        <button class="fb" onclick="sf('tr',this)">Translated</button>
    </div>
    <div class="slist">{nav_html}</div>
</div>
<div class="main" id="ms">{main_html}</div>
<script>
let cf='all';
function scrollTo(id){{document.getElementById(id)?.scrollIntoView({{behavior:'smooth',block:'start'}});}}
function jump(){{
    let v=document.getElementById('ji').value.replace(/^@/,'').trim();
    let id=parseInt(v,10);
    if(!isNaN(id)){{
        let el=document.getElementById('entry-'+id);
        if(el){{el.scrollIntoView({{behavior:'smooth',block:'center'}});
            el.style.outline='2px solid var(--acc)';setTimeout(()=>el.style.outline='',2000);}}
    }}
    document.getElementById('ji').value='';
}}
function filt(){{
    let q=document.getElementById('si').value.toLowerCase();
    document.querySelectorAll('.ent').forEach(el=>{{
        let jp=(el.dataset.jp||'').toLowerCase();
        let en=(el.dataset.en||'').toLowerCase();
        let t=el.textContent.toLowerCase();
        let ms=!q||jp.includes(q)||en.includes(q)||t.includes(q);
        let mf=cf==='all'||(cf==='ut'&&el.classList.contains('ut'))||(cf==='tr'&&el.classList.contains('tr'));
        el.style.display=(ms&&mf)?'':'none';
    }});
}}
function sf(f,btn){{cf=f;document.querySelectorAll('.fb').forEach(b=>b.classList.remove('act'));
    btn.classList.add('act');filt();}}
const ms=document.getElementById('ms');
const shs=document.querySelectorAll('.sh');
const nvs=document.querySelectorAll('.snav');
ms.addEventListener('scroll',()=>{{
    let ai=0,st=ms.scrollTop+40;
    shs.forEach((h,i)=>{{if(h.offsetTop<=st)ai=i;}});
    nvs.forEach((n,i)=>n.classList.toggle('act',i===ai));
}});
</script></body></html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rom_path = args[0] if args else ROM_PATH

    print(f"Loading ROM: {rom_path}")
    rom = load_rom(rom_path)

    print("Building font atlases...")
    jp_atlas_p0 = build_font_atlas(rom, 0)
    jp_atlas_p1 = build_font_atlas(rom, 1)

    if Path(EN_FONT_BIN).exists():
        en_atlas = build_en_font_atlas(EN_FONT_BIN)
        print(f"  EN font loaded from {EN_FONT_BIN}")
    else:
        # Fallback: use JP page 0 for EN too
        print(f"  WARNING: {EN_FONT_BIN} not found, using JP font for EN")
        en_atlas = jp_atlas_p0

    print("Loading tables...")
    jp_table = load_table(JP_TABLE_PATH)
    en_table = load_table(EN_TABLE_PATH)

    print(f"Parsing dialogue from {DUMP_PATH}...")
    entries = parse_dialogue_dump(DUMP_PATH)
    print(f"  {len(entries)} entries")

    print("Grouping into scenes...")
    scenes = group_into_scenes(entries)
    print(f"  {len(scenes)} scenes")

    print("Building HTML...")
    html_content = build_html(entries, scenes, jp_table, en_table, jp_atlas_p0, jp_atlas_p1, en_atlas)

    use_browser = "--browser" in sys.argv

    if not use_browser:
        try:
            import tempfile
            import webview

            # Write to temp file — inline HTML too large for Qt WebEngine
            tmp = tempfile.NamedTemporaryFile(
                suffix=".html", delete=False, mode="w", encoding="utf-8"
            )
            tmp.write(html_content)
            tmp.close()

            window = webview.create_window(
                "Rushing Beat Shura — Script Preview",
                url=f"file://{tmp.name}",
                width=1200,
                height=800,
                min_size=(800, 600),
            )
            webview.start(debug=True)

            os.unlink(tmp.name)
            return
        except Exception as exc:
            print(f"pywebview failed: {exc}, falling back to browser...")

    # Serve via local HTTP (browsers handle large pages better than file://)
    import subprocess
    from http.server import HTTPServer, BaseHTTPRequestHandler

    html_bytes = html_content.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)
        def log_message(self, *a):
            pass  # silence logs

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"

    print(f"Serving at {url}")
    print("Press Ctrl+C to stop.")

    subprocess.Popen(["xdg-open", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
