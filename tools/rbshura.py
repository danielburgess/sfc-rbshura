"""
rbshura.py — Rushing Beat Shura ROM extraction/insertion toolkit
HiROM (FastROM), SNES banks $C0–$DF (2 MB)

All functions accept a `rom: bytes` parameter.
Offsets are raw PC file offsets unless noted as SNES addresses.
"""

import os
import struct
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# HiROM address conversion
# ---------------------------------------------------------------------------

def snes_to_pc(addr: int) -> int:
    """Convert a 24-bit SNES HiROM address to a ROM file offset.

    Valid for ROM banks $40–$7D (slow mirror), $80–$BF (upper-half mirror),
    and $C0–$FF (full banks, incl. the $E0–$FF expansion region). Raises
    ValueError for unmapped addresses, incl. WRAM banks $7E/$7F.
    """
    bank   = (addr >> 16) & 0xFF
    offset = addr & 0xFFFF

    # Normalize to the ROM bank index (0–63 for a 4 MB cart). $7E/$7F are
    # WRAM, not ROM, so the slow-mirror range stops at $7D.
    if 0x40 <= bank <= 0x7D:
        rom_bank = bank - 0x40
    elif 0x80 <= bank <= 0xBF:
        if offset < 0x8000:
            raise ValueError(f"SNES ${addr:06X} is in the system area of bank ${bank:02X}")
        rom_bank = bank - 0x80
    elif 0xC0 <= bank <= 0xFF:
        rom_bank = bank - 0xC0
    else:
        raise ValueError(f"SNES ${addr:06X} is not a ROM address")

    return rom_bank * 0x10000 + offset


def pc_to_snes(pc: int, fast: bool = True) -> int:
    """Convert a ROM file offset to a 24-bit SNES HiROM address.

    fast=True  → banks $C0–$FF  (FastROM; $C0–$DF base ROM, $E0–$FF expansion)
    fast=False → banks $40–$7D  (slow mirror)

    Covers the full 4 MB expanded ROM (was 2 MB before 2026-05-26 — the EN
    build relocates text/graphics into expansion banks $E0–$FF).
    """
    if pc < 0 or pc >= 0x400000:
        raise ValueError(f"PC offset 0x{pc:06X} is outside the 4 MB ROM")
    bank_idx = pc >> 16
    offset   = pc & 0xFFFF
    base     = 0xC0 if fast else 0x40
    return ((base + bank_idx) << 16) | offset


# ---------------------------------------------------------------------------
# ROM utilities
# ---------------------------------------------------------------------------

def load_rom(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def read_u8(rom: bytes, pc: int) -> int:
    return rom[pc]


def read_u16_le(rom: bytes, pc: int) -> int:
    return struct.unpack_from("<H", rom, pc)[0]


def read_u24_le(rom: bytes, pc: int) -> int:
    lo, mid, hi = rom[pc], rom[pc + 1], rom[pc + 2]
    return (hi << 16) | (mid << 8) | lo


def read_at_snes(rom: bytes, snes_addr: int, count: int) -> bytes:
    pc = snes_to_pc(snes_addr)
    return rom[pc : pc + count]


# ---------------------------------------------------------------------------
# LZSS decompression — delegates to retrotool.compression (PARAMS_RBSHURA)
# ---------------------------------------------------------------------------
from retrotool.compression import LZSSCodec, PARAMS_RBSHURA

_LZSS_CODEC = LZSSCodec(PARAMS_RBSHURA)


def lzss_decompress(data: bytes, start: int = 0) -> bytes:
    """Decompress a raw LZSS stream (no size header).

    Wraps the decompressor around a synthetic 2-byte size header so callers
    that hand in pre-sliced streams still work.
    """
    framed = len(data[start:]).to_bytes(2, "little") + data[start:]
    return _LZSS_CODEC.decompress(framed, 0).data


def lzss_decompress_block(rom: bytes, pc: int) -> tuple[bytes, int]:
    """Read the 2-byte compressed-size header at `pc`, then decompress.

    Returns (decompressed_bytes, pc_after_block).
    """
    r = _LZSS_CODEC.decompress(rom, pc)
    return r.data, pc + r.consumed


# ---------------------------------------------------------------------------
# LZSS compression — delegates to retrotool.compression
# ---------------------------------------------------------------------------

def lzss_compress(data: bytes) -> bytes:
    """Compress `data`. Returns the raw compressed stream (no size header)."""
    r = _LZSS_CODEC.compress(data)
    # LZSSCodec emits the 2-byte header per PARAMS_RBSHURA; strip it.
    return r.data[2:]


def lzss_compress_block(data: bytes) -> bytes:
    """Compress and prepend the 2-byte little-endian compressed-size header."""
    return _LZSS_CODEC.compress(data).data


# ---------------------------------------------------------------------------
# Character name extraction
# ---------------------------------------------------------------------------

# Index table for character names (16-bit LE pointers, all in bank $80 = PC bank 0)
_CHAR_NAME_INDEX_PC  = 0x00E119   # table of 16-bit pointers
_CHAR_NAME_INDEX_END = 0x00E15B   # first actual name (= end of pointer table)
_CHAR_NAME_STRIDE    = 12         # 11 chars + $FF terminator


@dataclass
class CharName:
    index: int
    pc_offset: int
    snes_addr: int
    raw: bytes
    text: str


def get_char_name_count(rom: bytes) -> int:
    """Return the number of entries in the character name index table."""
    start = _CHAR_NAME_INDEX_PC
    end   = _CHAR_NAME_INDEX_END
    return (end - start) // 2


def extract_char_names(rom: bytes) -> list[CharName]:
    """Read all character names from the fixed table at PC 0x00E119."""
    count  = get_char_name_count(rom)
    names  = []
    for i in range(count):
        ptr_pc  = _CHAR_NAME_INDEX_PC + i * 2
        name_off = read_u16_le(rom, ptr_pc)        # 16-bit offset in bank $80
        name_pc  = name_off                         # bank $80/$00 → PC = offset
        raw      = rom[name_pc : name_pc + _CHAR_NAME_STRIDE]
        # Trim at $FF terminator, decode as ASCII
        body = raw[:raw.index(0xFF)] if 0xFF in raw else raw
        text = body.rstrip(b"\x20").decode("ascii", errors="replace")
        names.append(CharName(
            index     = i,
            pc_offset = name_pc,
            snes_addr = pc_to_snes(name_pc),
            raw       = raw,
            text      = text,
        ))
    return names


# ---------------------------------------------------------------------------
# Compressed block scanner
# ---------------------------------------------------------------------------

@dataclass
class CompressedBlock:
    pc_offset: int
    snes_addr: int
    comp_size: int
    decomp_size: int


def scan_compressed_blocks(
    rom: bytes,
    start_pc:   int = 0,
    end_pc:     Optional[int] = None,
    min_decomp: int = 256,
    max_decomp: int = 0x20000,   # 128 KB upper bound — avoids false positives
    max_comp:   int = 0xFFFF,
) -> list[CompressedBlock]:
    """Heuristically scan `rom[start_pc:end_pc]` for LZSS blocks.

    A candidate block is accepted when:
      - 2-byte LE header value is plausible (1 ≤ comp_size ≤ max_comp)
      - Block does not extend past end of ROM
      - min_decomp ≤ decompressed size ≤ max_decomp

    The decompressor is run only on the exact compressed_size bytes, so
    the decompressed size is bounded by the compression ratio (~8×).
    """
    if end_pc is None:
        end_pc = len(rom)

    results: list[CompressedBlock] = []
    pc = start_pc

    while pc + 3 < end_pc:
        comp_size = read_u16_le(rom, pc)
        if 1 <= comp_size <= max_comp and pc + 2 + comp_size <= len(rom):
            try:
                # Only decompress the declared number of bytes
                chunk  = rom[pc + 2 : pc + 2 + comp_size]
                decomp = lzss_decompress(chunk)
                if min_decomp <= len(decomp) <= max_decomp:
                    results.append(CompressedBlock(
                        pc_offset   = pc,
                        snes_addr   = pc_to_snes(pc),
                        comp_size   = comp_size,
                        decomp_size = len(decomp),
                    ))
                    pc += 2 + comp_size   # skip to after this block
                    continue
            except Exception:
                pass
        pc += 1

    return results


# ---------------------------------------------------------------------------
# SNES tile conversion
# ---------------------------------------------------------------------------

def snes_2bpp_to_indices(tile: bytes) -> list[int]:
    """Convert one 16-byte SNES 2bpp 8×8 tile to 64 palette indices (0–3).

    SNES 2bpp layout: 2 bytes per row (bitplanes 0+1 interleaved) × 8 rows = 16 bytes.
    """
    if len(tile) < 16:
        tile = tile + bytes(16 - len(tile))
    pixels = [0] * 64
    for row in range(8):
        b0 = tile[row * 2]
        b1 = tile[row * 2 + 1]
        for col in range(8):
            bit = 7 - col
            p   = ((b0 >> bit) & 1) | (((b1 >> bit) & 1) << 1)
            pixels[row * 8 + col] = p
    return pixels


def snes_4bpp_to_indices(tile: bytes) -> list[int]:
    """Convert one 32-byte SNES 4bpp 8×8 tile to 64 palette indices (0–15).

    SNES 4bpp layout:
      bytes  0–15: row 0..7, bitplanes 0+1 interleaved (2 bytes/row)
      bytes 16–31: row 0..7, bitplanes 2+3 interleaved (2 bytes/row)
    """
    if len(tile) < 32:
        tile = tile + bytes(32 - len(tile))
    pixels = [0] * 64
    for row in range(8):
        b0 = tile[row * 2]
        b1 = tile[row * 2 + 1]
        b2 = tile[row * 2 + 16]
        b3 = tile[row * 2 + 17]
        for col in range(8):
            bit = 7 - col
            p   = ((b0 >> bit) & 1)
            p  |= ((b1 >> bit) & 1) << 1
            p  |= ((b2 >> bit) & 1) << 2
            p  |= ((b3 >> bit) & 1) << 3
            pixels[row * 8 + col] = p
    return pixels


def export_tileset_as_ppm(
    tile_data:     bytes,
    output_path:   str,
    bpp:           int = 4,    # 2 or 4
    tiles_per_row: int = 16,
    scale:         int = 2,
) -> None:
    """Write a PPM greyscale sprite-sheet of all tiles in `tile_data`.

    bpp=2 → 16-byte tiles (Mode 0 BG, 4 shades of grey)
    bpp=4 → 32-byte tiles (sprites / Mode 1 BG, 16 shades of grey)
    """
    bytes_per_tile = 16 if bpp == 2 else 32
    max_index      = 3 if bpp == 2 else 15
    decoder        = snes_2bpp_to_indices if bpp == 2 else snes_4bpp_to_indices

    n_tiles = len(tile_data) // bytes_per_tile
    if n_tiles == 0:
        return

    rows  = (n_tiles + tiles_per_row - 1) // tiles_per_row
    img_w = tiles_per_row * 8 * scale
    img_h = rows * 8 * scale
    buf   = bytearray(img_w * img_h * 3)

    grey = [int(i * 255 / max_index) for i in range(max_index + 1)]

    for t in range(n_tiles):
        tile   = tile_data[t * bytes_per_tile : (t + 1) * bytes_per_tile]
        idxmap = decoder(tile)
        tx     = (t % tiles_per_row) * 8 * scale
        ty     = (t // tiles_per_row) * 8 * scale
        for py in range(8):
            for px in range(8):
                v = grey[idxmap[py * 8 + px]]
                for sy in range(scale):
                    for sx in range(scale):
                        base = ((ty + py * scale + sy) * img_w + tx + px * scale + sx) * 3
                        buf[base] = buf[base + 1] = buf[base + 2] = v

    with open(output_path, "wb") as fh:
        fh.write(f"P6\n{img_w} {img_h}\n255\n".encode())
        fh.write(buf)


# ---------------------------------------------------------------------------
# Script data block reader (CopyDataToRAM format)
# ---------------------------------------------------------------------------

@dataclass
class ScriptDataEntry:
    dest_offset: int    # destination offset within $7E:2500+
    data: bytes         # raw bytes to copy


def read_script_data_block(rom: bytes, pc: int) -> list[ScriptDataEntry]:
    """Parse a CopyDataToRAM-format data block starting at `pc`.

    Format:
        [u16 dest_offset] [u16 count] [count bytes] ...
        [FFFF end marker]
    """
    entries: list[ScriptDataEntry] = []
    pos = pc
    while pos + 4 <= len(rom):
        dest = read_u16_le(rom, pos)
        if dest == 0xFFFF:
            break
        count = read_u16_le(rom, pos + 2)
        data  = rom[pos + 4 : pos + 4 + count]
        entries.append(ScriptDataEntry(dest_offset=dest, data=data))
        pos += 4 + count
    return entries


# ---------------------------------------------------------------------------
# Script pointer tables
# ---------------------------------------------------------------------------

# All in bank $81 (PC bank 0x01)
_SCRIPT_BANK_TABLE_PC  = 0x01A85B   # 1 byte per entry: bank number
_SCRIPT_PTR_TABLE_PC   = 0x01A91E   # 2 bytes per entry: 16-bit offset in that bank
_SCRIPT_A89C_TABLE_PC  = 0x01A89C   # 2 bytes per entry: display-config ptr in bank $41


def get_script_bank(rom: bytes, script_index: int) -> int:
    return rom[_SCRIPT_BANK_TABLE_PC + script_index]


def get_script_data_ptr(rom: bytes, script_index: int) -> int:
    """Return the PC offset of the script data block for `script_index`."""
    ptr16 = read_u16_le(rom, _SCRIPT_PTR_TABLE_PC + script_index * 2)
    bank  = get_script_bank(rom, script_index)
    # Convert SNES (bank, offset) → PC
    return snes_to_pc((bank << 16) | ptr16)


def get_script_config_ptr(rom: bytes, script_index: int) -> int:
    """Return the PC offset of the display-config sub-table for `script_index`."""
    ptr16 = read_u16_le(rom, _SCRIPT_A89C_TABLE_PC + script_index * 2)
    return snes_to_pc(0x410000 | ptr16)


# ---------------------------------------------------------------------------
# JSON export helpers
# ---------------------------------------------------------------------------

import json


def export_char_names_json(rom: bytes, output_path: str) -> None:
    """Export character name table to JSON."""
    names = extract_char_names(rom)
    data  = []
    for n in names:
        data.append({
            "index":    n.index,
            "pc":       f"0x{n.pc_offset:06X}",
            "snes":     f"0x{n.snes_addr:06X}",
            "text":     n.text,
            "raw_hex":  n.raw.hex(),
        })
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump({"char_names": data}, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {len(data)} character names to {output_path}")


def export_script_blocks_json(rom: bytes, output_path: str, max_scripts: int = 64) -> None:
    """Export script data blocks to JSON (uses CopyDataToRAM format)."""
    scripts = []
    for idx in range(max_scripts):
        try:
            pc   = get_script_data_ptr(rom, idx)
            bank = get_script_bank(rom, idx)
            entries = read_script_data_block(rom, pc)
            scripts.append({
                "script_index": idx,
                "bank":         f"0x{bank:02X}",
                "data_pc":      f"0x{pc:06X}",
                "entries": [
                    {
                        "dest_offset": f"0x{e.dest_offset:04X}",
                        "length":      len(e.data),
                        "data_hex":    e.data.hex(),
                    }
                    for e in entries
                ],
            })
        except Exception:
            break

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump({"scripts": scripts}, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {len(scripts)} script blocks to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    def usage():
        print(
            "Usage:\n"
            "  python rbshura.py names   <rom> [output.json]\n"
            "  python rbshura.py scripts <rom> [output.json]\n"
            "  python rbshura.py decomp  <rom> <pc_hex> [output.bin]\n"
            "  python rbshura.py scan    <rom> [start_pc_hex] [end_pc_hex]\n"
            "  python rbshura.py tiles   <input.bin> [output.ppm] [bpp=4]\n"
        )

    if len(sys.argv) < 3:
        usage()
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "names":
        rom_path = sys.argv[2]
        out_path = sys.argv[3] if len(sys.argv) > 3 else "char_names.json"
        rom = load_rom(rom_path)
        export_char_names_json(rom, out_path)

    elif cmd == "scripts":
        rom_path = sys.argv[2]
        out_path = sys.argv[3] if len(sys.argv) > 3 else "scripts.json"
        rom = load_rom(rom_path)
        export_script_blocks_json(rom, out_path)

    elif cmd == "decomp":
        rom_path = sys.argv[2]
        pc       = int(sys.argv[3], 16)
        out_path = sys.argv[4] if len(sys.argv) > 4 else f"decomp_{pc:06X}.bin"
        rom = load_rom(rom_path)
        decompressed, end = lzss_decompress_block(rom, pc)
        with open(out_path, "wb") as fh:
            fh.write(decompressed)
        print(f"Decompressed {len(decompressed)} bytes → {out_path}  (block ended at 0x{end:06X})")

    elif cmd == "scan":
        rom_path  = sys.argv[2]
        start_pc  = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0
        end_pc    = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
        rom = load_rom(rom_path)
        print(f"Scanning for LZSS blocks from 0x{start_pc:06X} ...")
        blocks = scan_compressed_blocks(rom, start_pc, end_pc)
        print(f"Found {len(blocks)} candidate blocks:")
        for b in blocks:
            print(f"  PC 0x{b.pc_offset:06X}  SNES 0x{b.snes_addr:06X}  "
                  f"comp={b.comp_size:5d}  decomp={b.decomp_size:6d}")

    elif cmd == "tiles":
        in_path  = sys.argv[2]
        out_path = sys.argv[3] if len(sys.argv) > 3 else in_path.replace(".bin", ".ppm")
        bpp      = int(sys.argv[4]) if len(sys.argv) > 4 else 4
        with open(in_path, "rb") as fh:
            tile_data = fh.read()
        bytes_per = 16 if bpp == 2 else 32
        export_tileset_as_ppm(tile_data, out_path, bpp=bpp)
        print(f"Wrote {len(tile_data) // bytes_per} tiles ({bpp}bpp) → {out_path}")

    else:
        usage()
        sys.exit(1)
