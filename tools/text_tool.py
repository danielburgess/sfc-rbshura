#!/usr/bin/env python3
"""
text_tool.py — Rushing Beat Shura text extraction and insertion toolkit.

⚠ SUPERSEDED for INSERTION (codereview.md H5, 2026-05-26) — do NOT use the
`insert`/`font-import` commands to write ROMs. The live build is retrotool
`build_project()` (project.toml). The insert/encode paths here do lossy
control-code round-trips and ignore the 4-level pointer chain. `dump`/`stats`
remain usable for JP-source analysis.

Commands:
    python text_tool.py dump <rom> <output.txt>      — Dump all JP text
    python text_tool.py insert <rom> <input.txt> <output_rom>  — Insert translated text
    python text_tool.py stats <rom>                   — Show text statistics
    python text_tool.py diff <jp_rom> <kr_rom>        — Compare JP/KR text
"""

import struct, sys, os, re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FONT_PC = 0x100000
BYTES_PER_CHAR = 64  # 16x16 = 4 tiles × 16 bytes/tile (2bpp)

# Text regions in ROM
TEXT_REGIONS = [
    # (name, start_pc, end_pc, bank_label)
    ("bank_C5", 0x058400, 0x060000, "$C5"),
    ("bank_C7", 0x070000, 0x080000, "$C7"),
    ("bank_D8", 0x18E000, 0x190000, "$D8"),
]

# Master scenario pointer table
MASTER_TABLE_PC = 0x058215  # 15 entries × 2 bytes

# Control code definitions: byte → (name, param_count)
# param_count = -1 means variable (FC has sub-commands)
CONTROL_CODES = {
    0xF7: ("END", 1),      # end of text line + 1 param
    0xF8: ("SPD", 1),      # text speed + 1 param
    0xF9: ("PORT", 1),     # portrait + 1 param
    0xFA: ("P2", 1),       # page 2 char + 1 char byte
    0xFB: ("WIN", 1),      # window type + 1 param
    0xFC: ("FC", -1),      # variable: FC 00 xx, FC 01 xx, FC 02 xx yy
    0xFD: ("NL", 0),       # newline
    0xFE: ("PB", 0),       # page break
    0xFF: ("STOP", 0),     # end of block
}

# ---------------------------------------------------------------------------
# Table file parsing
# ---------------------------------------------------------------------------

def load_table(path: str) -> dict:
    """Load a .tbl file. Returns {byte_value: char_string}."""
    table = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            try:
                if len(key) == 2:
                    table[int(key, 16)] = val
                elif len(key) == 4:
                    # Multi-byte entry like "FA00"
                    table[int(key, 16)] = val
            except ValueError:
                continue
    return table


def load_reverse_table(path: str) -> dict:
    """Load a .tbl file as reverse lookup. Returns {char_string: byte_value}."""
    table = load_table(path)
    return {v: k for k, v in table.items() if v.strip()}

# ---------------------------------------------------------------------------
# ROM I/O
# ---------------------------------------------------------------------------

def load_rom(path: str) -> bytearray:
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    # Strip copier header if present
    if len(data) % 0x10000 == 512:
        data = data[512:]
    return data


def save_rom(data: bytes, path: str):
    with open(path, 'wb') as f:
        f.write(data)


def r16(data, off):
    return struct.unpack_from('<H', data, off)[0]

# ---------------------------------------------------------------------------
# Text tokenizer
# ---------------------------------------------------------------------------

@dataclass
class Token:
    type: str       # CH, P2, NL, PB, END, SPD, PORT, WIN, FC, STOP
    value: int = 0  # character byte or param
    params: tuple = ()  # additional params for FC
    raw: bytes = b''    # original bytes


def tokenize_string(data: bytes, pos: int, end: int) -> list:
    """Tokenize one text string starting at pos (after the leading FF).
    Returns list of Token objects."""
    tokens = []
    while pos < end:
        b = data[pos]

        if b == 0xFF:
            tokens.append(Token('STOP', raw=bytes([b])))
            break
        elif b == 0xFD:
            tokens.append(Token('NL', raw=bytes([b])))
            pos += 1
        elif b == 0xFE:
            tokens.append(Token('PB', raw=bytes([b])))
            pos += 1
        elif b == 0xF7:
            p = data[pos+1] if pos+1 < end else 0
            tokens.append(Token('END', value=p, raw=bytes([b, p])))
            pos += 2
            # F7 with param $FF = true end of block, otherwise may continue
            if p == 0xFF or pos >= end or data[pos] == 0xFF:
                break
            # Continue parsing — more text may follow (multi-line blocks)
        elif b == 0xF8:
            p = data[pos+1] if pos+1 < end else 0
            tokens.append(Token('SPD', value=p, raw=bytes([b, p])))
            pos += 2
        elif b == 0xF9:
            p = data[pos+1] if pos+1 < end else 0
            tokens.append(Token('PORT', value=p, raw=bytes([b, p])))
            pos += 2
        elif b == 0xFA:
            p = data[pos+1] if pos+1 < end else 0
            tokens.append(Token('P2', value=p, raw=bytes([b, p])))
            pos += 2
        elif b == 0xFB:
            p = data[pos+1] if pos+1 < end else 0
            tokens.append(Token('WIN', value=p, raw=bytes([b, p])))
            pos += 2
        elif b == 0xFC:
            sub = data[pos+1] if pos+1 < end else 0
            if sub == 0x02 and pos+3 < end:
                raw = bytes(data[pos:pos+4])
                tokens.append(Token('FC', value=sub,
                                    params=(data[pos+2], data[pos+3]),
                                    raw=raw))
                pos += 4
            elif pos+2 < end:
                raw = bytes(data[pos:pos+3])
                tokens.append(Token('FC', value=sub,
                                    params=(data[pos+2],),
                                    raw=raw))
                pos += 3
            else:
                pos += 1
        else:
            # Regular character (page 1)
            tokens.append(Token('CH', value=b, raw=bytes([b])))
            pos += 1

    return tokens

# ---------------------------------------------------------------------------
# Text scanner — find all text strings in a ROM region
# ---------------------------------------------------------------------------

@dataclass
class TextString:
    pc: int               # ROM offset of the leading FF
    bank: str             # bank label
    tokens: list          # list of Token
    raw_bytes: bytes      # complete raw bytes (FF ... F7 xx)
    string_id: int = 0    # sequential ID for the dump


def scan_text_region(data: bytes, start: int, end: int, bank: str) -> list:
    """Scan a ROM region for FF-delimited text strings."""
    strings = []
    pos = start

    while pos < end:
        if data[pos] != 0xFF:
            pos += 1
            continue

        block_start = pos
        pos += 1  # skip FF

        if pos >= end:
            break

        # Skip double FF
        if data[pos] == 0xFF:
            continue

        # Tokenize from here (handles FB, FE, multi-F7 blocks)
        tokens = tokenize_string(data, pos, end)

        # Only keep strings with actual displayable characters
        has_text = any(t.type in ('CH', 'P2') for t in tokens)
        has_end = any(t.type == 'END' for t in tokens)

        if has_text and has_end:
            # Compute raw bytes
            raw = bytearray()
            for t in tokens:
                raw.extend(t.raw)
            # Advance pos past the string
            pos = block_start + 1 + len(raw)

            strings.append(TextString(
                pc=block_start,
                bank=bank,
                tokens=tokens,
                raw_bytes=bytes(raw),
            ))
        else:
            # Skip non-text FF blocks (like FF FB xx)
            raw_len = sum(len(t.raw) for t in tokens)
            pos = block_start + 1 + max(raw_len, 1)
    return strings


def scan_all_text(data: bytes) -> list:
    """Scan all known text regions and return all text strings."""
    all_strings = []
    for name, start, end, bank in TEXT_REGIONS:
        region_strings = scan_text_region(data, start, end, bank)
        all_strings.extend(region_strings)
    # Assign sequential IDs
    for i, s in enumerate(all_strings):
        s.string_id = i
    return all_strings

# ---------------------------------------------------------------------------
# Text dump — export to structured text file
# ---------------------------------------------------------------------------

def tokens_to_dump_line(tokens: list, jp_table: dict = None) -> str:
    """Convert tokens to a human-readable dump line.
    Characters shown as table lookup or [XX] hex notation."""
    parts = []
    for t in tokens:
        if t.type == 'CH':
            if jp_table and t.value in jp_table:
                parts.append(jp_table[t.value])
            else:
                parts.append(f'[{t.value:02X}]')
        elif t.type == 'P2':
            key = 0xFA00 + t.value
            if jp_table and key in jp_table:
                parts.append(jp_table[key])
            else:
                parts.append(f'[FA:{t.value:02X}]')
        elif t.type == 'NL':
            parts.append('{NL}')
        elif t.type == 'PB':
            parts.append('{PB}')
        elif t.type == 'END':
            pass  # don't show END marker in text
        elif t.type == 'SPD':
            parts.append(f'{{SPD:{t.value:02X}}}')
        elif t.type == 'PORT':
            parts.append(f'{{PORT:{t.value:02X}}}')
        elif t.type == 'WIN':
            parts.append(f'{{WIN:{t.value:02X}}}')
        elif t.type == 'FC':
            if len(t.params) == 2:
                parts.append(f'{{FC:{t.value:02X},{t.params[0]:02X},{t.params[1]:02X}}}')
            elif len(t.params) == 1:
                parts.append(f'{{FC:{t.value:02X},{t.params[0]:02X}}}')
        elif t.type == 'STOP':
            pass
    return ''.join(parts)


def tokens_to_raw_hex(tokens: list) -> str:
    """Convert tokens to raw hex string for reference."""
    return ' '.join(t.raw.hex().upper() for t in tokens)


def dump_text(rom_data: bytes, output_path: str, table_path: str = None):
    """Dump all text strings to a structured text file."""
    jp_table = load_table(table_path) if table_path else None
    strings = scan_all_text(rom_data)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Rushing Beat Shura — Text Dump\n")
        f.write("# Generated by text_tool.py\n")
        f.write("#\n")
        f.write("# Format:\n")
        f.write("#   @NNNN PC=$XXXXXX BANK=$XX END_PARAM=$XX\n")
        f.write("#   ;raw: XX XX XX ...\n")
        f.write("#   Japanese text with control codes\n")
        f.write("#   >English translation goes here\n")
        f.write("#   (blank line separates entries)\n")
        f.write("#\n")
        f.write("# Control codes (preserve these in translation):\n")
        f.write("#   {NL}     = newline\n")
        f.write("#   {PB}     = page break (clear text area)\n")
        f.write("#   {SPD:XX} = text speed\n")
        f.write("#   {PORT:XX}= character portrait\n")
        f.write("#   {WIN:XX} = dialogue window type\n")
        f.write("#   {FC:XX,YY} or {FC:XX,YY,ZZ} = misc control\n")
        f.write("#   [XX] or [FA:XX] = JP char by hex code\n")
        f.write("#\n")
        f.write(f"# Total strings: {len(strings)}\n")
        f.write("#\n\n")

        for s in strings:
            # Get END param
            end_param = 0
            for t in s.tokens:
                if t.type == 'END':
                    end_param = t.value
                    break

            f.write(f"@{s.string_id:04d} PC=${s.pc:06X} BANK={s.bank} END={end_param:02X}\n")
            f.write(f";raw: {tokens_to_raw_hex(s.tokens)}\n")
            f.write(f"{tokens_to_dump_line(s.tokens, jp_table)}\n")
            f.write(f">\n")  # placeholder for English translation
            f.write(f"\n")

    print(f"Dumped {len(strings)} text strings to {output_path}")
    return strings

# ---------------------------------------------------------------------------
# Text insertion — parse translated text file and patch ROM
# ---------------------------------------------------------------------------

def parse_dump_file(path: str) -> list:
    """Parse a text dump file, extracting both original and translation lines."""
    entries = []
    current = None

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')

            if line.startswith('#') or line == '':
                if current and current.get('translation'):
                    entries.append(current)
                    current = None
                continue

            if line.startswith('@'):
                if current and current.get('translation'):
                    entries.append(current)
                # Parse header: @NNNN PC=$XXXXXX BANK=$XX END=$XX
                m = re.match(
                    r'@(\d+)\s+PC=\$([0-9A-Fa-f]+)\s+BANK=(\S+)\s+END=([0-9A-Fa-f]+)',
                    line)
                if m:
                    current = {
                        'id': int(m.group(1)),
                        'pc': int(m.group(2), 16),
                        'bank': m.group(3),
                        'end_param': int(m.group(4), 16),
                        'original': '',
                        'translation': '',
                        'raw_hex': '',
                    }
            elif line.startswith(';raw:') and current:
                current['raw_hex'] = line[5:].strip()
            elif line.startswith('>') and current:
                current['translation'] = line[1:]
            elif current and not current.get('original'):
                current['original'] = line

    if current and current.get('translation'):
        entries.append(current)
    return entries


def encode_translation(text: str, en_table_path: str) -> bytes:
    """Encode a translated English string to ROM bytes.
    Handles control codes in {TAG:PARAMS} format and plain characters."""
    reverse = load_reverse_table(en_table_path)
    result = bytearray()

    i = 0
    while i < len(text):
        c = text[i]

        if c == '{':
            # Parse control code
            end = text.index('}', i)
            tag_content = text[i+1:end]
            parts = tag_content.split(':')
            tag = parts[0]

            if tag == 'NL':
                result.append(0xFD)
            elif tag == 'PB':
                result.append(0xFE)
            elif tag == 'SPD':
                result.append(0xF8)
                result.append(int(parts[1], 16))
            elif tag == 'PORT':
                result.append(0xF9)
                result.append(int(parts[1], 16))
            elif tag == 'WIN':
                result.append(0xFB)
                result.append(int(parts[1], 16))
            elif tag == 'FC':
                result.append(0xFC)
                params = parts[1].split(',')
                for p in params:
                    result.append(int(p, 16))
            i = end + 1
        elif c == '[':
            # Hex literal: [XX] or [FA:XX]
            end = text.index(']', i)
            hex_content = text[i+1:end]
            if ':' in hex_content:
                # [FA:XX] = page 2 char
                prefix, val = hex_content.split(':')
                try:
                    result.append(int(prefix, 16))
                    result.append(int(val, 16))
                except ValueError:
                    pass  # skip non-hex bracket content
            else:
                try:
                    result.append(int(hex_content, 16))
                except ValueError:
                    pass  # skip non-hex bracket content like [Something]
            i = end + 1
        elif c in reverse:
            result.append(reverse[c])
            i += 1
        else:
            # Unknown char — skip or use space
            if c != '\n' and c != '\r':
                result.append(0x00)  # space
            i += 1

    return bytes(result)


def insert_text(rom_data: bytearray, dump_path: str, en_table_path: str,
                output_path: str):
    """Read translated dump file and patch ROM with new text."""
    entries = parse_dump_file(dump_path)
    patched = bytearray(rom_data)
    changes = 0
    errors = []

    for entry in entries:
        if not entry['translation'].strip():
            continue  # skip untranslated entries

        pc = entry['pc']
        end_param = entry['end_param']

        # Get original raw bytes to know the available space
        orig_raw = bytes.fromhex(entry['raw_hex'].replace(' ', ''))
        orig_len = len(orig_raw)

        # Encode the translation
        encoded = encode_translation(entry['translation'], en_table_path)

        # Add F7 end marker + param
        encoded_full = bytearray()
        # Keep the FF prefix
        encoded_full.append(0xFF)
        encoded_full.extend(encoded)
        encoded_full.append(0xF7)
        encoded_full.append(end_param)

        # The original block in ROM is: FF [orig_raw]
        # We need: FF [encoded] F7 param
        # Space available: 1 (FF) + orig_len bytes
        available = 1 + orig_len
        needed = len(encoded_full)

        if needed > available:
            errors.append(
                f"@{entry['id']:04d} PC=${pc:06X}: translation too long "
                f"({needed} > {available} bytes)")
            continue

        # Pad with FF if shorter
        while len(encoded_full) < available:
            encoded_full.append(0xFF)

        # Patch ROM
        patched[pc:pc + available] = encoded_full
        changes += 1

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  {e}")

    save_rom(bytes(patched), output_path)
    print(f"Patched {changes} strings → {output_path}")
    if errors:
        print(f"({len(errors)} strings skipped due to space constraints)")

# ---------------------------------------------------------------------------
# Font tools
# ---------------------------------------------------------------------------

def export_font_bin(rom_data: bytes, page: int, output_path: str):
    """Export font page as raw binary (for editing)."""
    start = FONT_PC + page * 0x4000
    end = start + 247 * BYTES_PER_CHAR
    with open(output_path, 'wb') as f:
        f.write(rom_data[start:end])
    print(f"Exported font page {page}: {end-start} bytes → {output_path}")


def import_font_bin(rom_data: bytearray, page: int, input_path: str) -> bytearray:
    """Import font binary back into ROM."""
    with open(input_path, 'rb') as f:
        font_data = f.read()
    start = FONT_PC + page * 0x4000
    rom_data[start:start + len(font_data)] = font_data
    print(f"Imported font page {page}: {len(font_data)} bytes from {input_path}")
    return rom_data


def export_font_ppm(rom_data: bytes, page: int, output_path: str, cols: int = 16):
    """Export font page as a PPM image grid."""
    chars = 247
    rows = (chars + cols - 1) // cols
    cell = 18  # 16px + 2px gap
    w = cols * cell
    h = rows * cell

    img = bytearray(w * h * 3)
    palette = [(0,0,0), (85,85,85), (170,170,170), (255,255,255)]

    for ci in range(chars):
        col = ci % cols
        row = ci // cols
        base = FONT_PC + page * 0x4000 + ci * BYTES_PER_CHAR

        x0 = col * cell + 1
        y0 = row * cell + 1

        for tile_row in range(2):
            for py in range(8):
                for tile_col in range(2):
                    off = base + (tile_row*2 + tile_col) * 16
                    if off + 15 >= len(rom_data):
                        continue
                    b0 = rom_data[off + py*2]
                    b1 = rom_data[off + py*2 + 1]
                    for px in range(8):
                        bit = 7 - px
                        p = ((b0 >> bit) & 1) | (((b1 >> bit) & 1) << 1)
                        ix_x = x0 + tile_col * 8 + px
                        ix_y = y0 + tile_row * 8 + py
                        ix = (ix_y * w + ix_x) * 3
                        r, g, b = palette[p]
                        img[ix] = r; img[ix+1] = g; img[ix+2] = b

    with open(output_path, 'wb') as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(img)
    print(f"Font page {page} → {output_path} ({w}x{h})")

# ---------------------------------------------------------------------------
# Stats command
# ---------------------------------------------------------------------------

def show_stats(rom_data: bytes):
    """Show text statistics."""
    strings = scan_all_text(rom_data)

    p1_chars = set()
    p2_chars = set()
    total_chars = 0
    total_lines = 0

    for s in strings:
        for t in s.tokens:
            if t.type == 'CH':
                p1_chars.add(t.value)
                total_chars += 1
            elif t.type == 'P2':
                p2_chars.add(t.value)
                total_chars += 1
            elif t.type == 'END':
                total_lines += 1

    print(f"Text strings:     {len(strings)}")
    print(f"Text lines (F7):  {total_lines}")
    print(f"Total characters: {total_chars}")
    print(f"Unique page 1:    {len(p1_chars)} (${min(p1_chars):02X}-${max(p1_chars):02X})")
    print(f"Unique page 2:    {len(p2_chars)} (${min(p2_chars):02X}-${max(p2_chars):02X})")

    # Per-bank breakdown
    banks = {}
    for s in strings:
        banks.setdefault(s.bank, []).append(s)
    for bank, strs in sorted(banks.items()):
        print(f"  {bank}: {len(strs)} strings")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'dump':
        rom_path = sys.argv[2]
        out_path = sys.argv[3] if len(sys.argv) > 3 else 'text/dialogue_dump.txt'
        table_path = None
        if len(sys.argv) > 4:
            table_path = sys.argv[4]
        elif os.path.exists('tables/jp.tbl'):
            table_path = 'tables/jp.tbl'
        rom = load_rom(rom_path)
        dump_text(rom, out_path, table_path)

    elif cmd == 'insert':
        if len(sys.argv) < 5:
            print("Usage: text_tool.py insert <rom> <input.txt> <output_rom> [en.tbl]")
            sys.exit(1)
        rom_path = sys.argv[2]
        txt_path = sys.argv[3]
        out_path = sys.argv[4]
        tbl_path = sys.argv[5] if len(sys.argv) > 5 else 'tables/en.tbl'
        rom = load_rom(rom_path)
        insert_text(rom, txt_path, tbl_path, out_path)

    elif cmd == 'stats':
        rom = load_rom(sys.argv[2])
        show_stats(rom)

    elif cmd == 'font-export':
        rom = load_rom(sys.argv[2])
        page = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        out = sys.argv[4] if len(sys.argv) > 4 else f'fonts/jp_font_p{page}.bin'
        export_font_bin(rom, page, out)

    elif cmd == 'font-export-ppm':
        rom = load_rom(sys.argv[2])
        page = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        out = sys.argv[4] if len(sys.argv) > 4 else f'fonts/jp_font_p{page}.ppm'
        export_font_ppm(rom, page, out)

    elif cmd == 'font-import':
        if len(sys.argv) < 5:
            print("Usage: text_tool.py font-import <rom> <font.bin> <output_rom> [page]")
            sys.exit(1)
        rom = load_rom(sys.argv[2])
        font_path = sys.argv[3]
        out_path = sys.argv[4]
        page = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        rom = import_font_bin(rom, page, font_path)
        save_rom(bytes(rom), out_path)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
