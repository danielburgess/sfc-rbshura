#!/usr/bin/env python3
"""Minimal 65816 disassembler for engine analysis.

Tracks M/X flags through REP/SEP. Outputs PC, bytes, mnemonic.
Usage: quick_disasm.py <rom> <start_pc_hex> <length_hex>
"""
from __future__ import annotations
import sys

# Each entry: (mnemonic, addressing_mode_bytes_func_or_int)
# bytes_func takes (m_flag, x_flag) and returns operand bytes for that mode.
# Modes:
#   "imp"  → 1 byte (just opcode)
#   "imm_m"→ 1 + (2 if m=0 else 1)
#   "imm_x"→ 1 + (2 if x=0 else 1)
#   "imm8" → 2 bytes
#   "abs"  → 3 bytes
#   "abs_long" → 4 bytes
#   "dp"   → 2 bytes
#   "dp_ind"→ 2 bytes
#   "dp_ind_long" → 2 bytes
#   "sr"   → 2 bytes
#   "rel8" → 2 bytes (PC-relative)
#   "rel16"→ 3 bytes
#   "blkmv"→ 3 bytes

OPCODES = {
    # Loads / stores
    0xA9: ("LDA", "imm_m"), 0xA5: ("LDA", "dp"), 0xAD: ("LDA", "abs"),
    0xAF: ("LDA", "abs_long"), 0xB5: ("LDA", "dp,X"), 0xBD: ("LDA", "abs,X"),
    0xBF: ("LDA", "abs_long,X"), 0xB9: ("LDA", "abs,Y"),
    0xB2: ("LDA", "(dp)"), 0xA1: ("LDA", "(dp,X)"), 0xB1: ("LDA", "(dp),Y"),
    0xA7: ("LDA", "[dp]"), 0xB7: ("LDA", "[dp],Y"),
    0xA3: ("LDA", "sr,S"), 0xB3: ("LDA", "(sr,S),Y"),

    0xA2: ("LDX", "imm_x"), 0xA6: ("LDX", "dp"), 0xAE: ("LDX", "abs"),
    0xB6: ("LDX", "dp,Y"), 0xBE: ("LDX", "abs,Y"),
    0xA0: ("LDY", "imm_x"), 0xA4: ("LDY", "dp"), 0xAC: ("LDY", "abs"),
    0xB4: ("LDY", "dp,X"), 0xBC: ("LDY", "abs,X"),

    0x85: ("STA", "dp"), 0x8D: ("STA", "abs"), 0x8F: ("STA", "abs_long"),
    0x95: ("STA", "dp,X"), 0x9D: ("STA", "abs,X"), 0x9F: ("STA", "abs_long,X"),
    0x99: ("STA", "abs,Y"), 0x92: ("STA", "(dp)"), 0x81: ("STA", "(dp,X)"),
    0x91: ("STA", "(dp),Y"), 0x87: ("STA", "[dp]"), 0x97: ("STA", "[dp],Y"),
    0x83: ("STA", "sr,S"), 0x93: ("STA", "(sr,S),Y"),

    0x86: ("STX", "dp"), 0x8E: ("STX", "abs"), 0x96: ("STX", "dp,Y"),
    0x84: ("STY", "dp"), 0x8C: ("STY", "abs"), 0x94: ("STY", "dp,X"),
    0x64: ("STZ", "dp"), 0x9C: ("STZ", "abs"), 0x74: ("STZ", "dp,X"),
    0x9E: ("STZ", "abs,X"),

    # Arith
    0x69: ("ADC", "imm_m"), 0x65: ("ADC", "dp"), 0x6D: ("ADC", "abs"),
    0x7D: ("ADC", "abs,X"), 0x79: ("ADC", "abs,Y"), 0x71: ("ADC", "(dp),Y"),
    0xE9: ("SBC", "imm_m"), 0xE5: ("SBC", "dp"), 0xED: ("SBC", "abs"),
    0xC9: ("CMP", "imm_m"), 0xC5: ("CMP", "dp"), 0xCD: ("CMP", "abs"),
    0xD5: ("CMP", "dp,X"), 0xDD: ("CMP", "abs,X"), 0xD9: ("CMP", "abs,Y"),
    0xD1: ("CMP", "(dp),Y"),
    0xE0: ("CPX", "imm_x"), 0xE4: ("CPX", "dp"), 0xEC: ("CPX", "abs"),
    0xC0: ("CPY", "imm_x"), 0xC4: ("CPY", "dp"), 0xCC: ("CPY", "abs"),
    0xE6: ("INC", "dp"), 0xEE: ("INC", "abs"), 0xF6: ("INC", "dp,X"),
    0xFE: ("INC", "abs,X"), 0x1A: ("INC", "A"),
    0xC6: ("DEC", "dp"), 0xCE: ("DEC", "abs"), 0xD6: ("DEC", "dp,X"),
    0xDE: ("DEC", "abs,X"), 0x3A: ("DEC", "A"),
    0xE8: ("INX", "imp"), 0xC8: ("INY", "imp"),
    0xCA: ("DEX", "imp"), 0x88: ("DEY", "imp"),

    # Logic
    0x29: ("AND", "imm_m"), 0x25: ("AND", "dp"), 0x2D: ("AND", "abs"),
    0x3D: ("AND", "abs,X"), 0x39: ("AND", "abs,Y"),
    0x09: ("ORA", "imm_m"), 0x05: ("ORA", "dp"), 0x0D: ("ORA", "abs"),
    0x1D: ("ORA", "abs,X"), 0x19: ("ORA", "abs,Y"),
    0x49: ("EOR", "imm_m"), 0x45: ("EOR", "dp"), 0x4D: ("EOR", "abs"),
    0x89: ("BIT", "imm_m"), 0x24: ("BIT", "dp"), 0x2C: ("BIT", "abs"),
    0x34: ("BIT", "dp,X"), 0x3C: ("BIT", "abs,X"),
    0x14: ("TRB", "dp"), 0x1C: ("TRB", "abs"),
    0x04: ("TSB", "dp"), 0x0C: ("TSB", "abs"),

    # Shifts
    0x0A: ("ASL", "A"), 0x06: ("ASL", "dp"), 0x0E: ("ASL", "abs"),
    0x16: ("ASL", "dp,X"), 0x1E: ("ASL", "abs,X"),
    0x4A: ("LSR", "A"), 0x46: ("LSR", "dp"), 0x4E: ("LSR", "abs"),
    0x2A: ("ROL", "A"), 0x26: ("ROL", "dp"), 0x2E: ("ROL", "abs"),
    0x6A: ("ROR", "A"), 0x66: ("ROR", "dp"), 0x6E: ("ROR", "abs"),

    # Branches
    0xF0: ("BEQ", "rel8"), 0xD0: ("BNE", "rel8"),
    0x90: ("BCC", "rel8"), 0xB0: ("BCS", "rel8"),
    0x30: ("BMI", "rel8"), 0x10: ("BPL", "rel8"),
    0x50: ("BVC", "rel8"), 0x70: ("BVS", "rel8"),
    0x80: ("BRA", "rel8"), 0x82: ("BRL", "rel16"),

    # Jumps / calls
    0x4C: ("JMP", "abs"), 0x6C: ("JMP", "(abs)"), 0x7C: ("JMP", "(abs,X)"),
    0x5C: ("JML", "abs_long"), 0xDC: ("JML", "[abs]"),
    0x20: ("JSR", "abs"), 0xFC: ("JSR", "(abs,X)"),
    0x22: ("JSL", "abs_long"),
    0x60: ("RTS", "imp"), 0x6B: ("RTL", "imp"), 0x40: ("RTI", "imp"),

    # Stack
    0x48: ("PHA", "imp"), 0x68: ("PLA", "imp"),
    0xDA: ("PHX", "imp"), 0xFA: ("PLX", "imp"),
    0x5A: ("PHY", "imp"), 0x7A: ("PLY", "imp"),
    0x08: ("PHP", "imp"), 0x28: ("PLP", "imp"),
    0x8B: ("PHB", "imp"), 0xAB: ("PLB", "imp"),
    0x0B: ("PHD", "imp"), 0x2B: ("PLD", "imp"),
    0x4B: ("PHK", "imp"),
    0xF4: ("PEA", "abs"), 0xD4: ("PEI", "dp"), 0x62: ("PER", "rel16"),

    # Transfers
    0xAA: ("TAX", "imp"), 0x8A: ("TXA", "imp"),
    0xA8: ("TAY", "imp"), 0x98: ("TYA", "imp"),
    0xBA: ("TSX", "imp"), 0x9A: ("TXS", "imp"),
    0x5B: ("TCD", "imp"), 0x7B: ("TDC", "imp"),
    0x1B: ("TCS", "imp"), 0x3B: ("TSC", "imp"),
    0x9B: ("TXY", "imp"), 0xBB: ("TYX", "imp"),
    0xEB: ("XBA", "imp"), 0xFB: ("XCE", "imp"),

    # Flags
    0x18: ("CLC", "imp"), 0x38: ("SEC", "imp"),
    0x58: ("CLI", "imp"), 0x78: ("SEI", "imp"),
    0xB8: ("CLV", "imp"),
    0xD8: ("CLD", "imp"), 0xF8: ("SED", "imp"),
    0xC2: ("REP", "imm8"), 0xE2: ("SEP", "imm8"),

    # Block move
    0x54: ("MVN", "blkmv"), 0x44: ("MVP", "blkmv"),

    # Misc
    0xEA: ("NOP", "imp"), 0xDB: ("STP", "imp"), 0xCB: ("WAI", "imp"),
    0x00: ("BRK", "imm8"), 0x02: ("COP", "imm8"), 0x42: ("WDM", "imm8"),
}


def fmt_operand(mode: str, data: bytes, pc: int) -> tuple[str, int]:
    """Return (operand_str, total_instr_bytes_including_opcode)."""
    if mode == "imp" or mode == "A":
        return ("A" if mode == "A" else "", 1)
    if mode == "imm8":
        return (f"#${data[1]:02X}", 2)
    if mode == "imm_m":  # caller must pre-resolve width
        return (f"#${int.from_bytes(data[1:3], 'little'):04X}", 3)  # placeholder; resolved below
    if mode == "imm_x":
        return (f"#${int.from_bytes(data[1:3], 'little'):04X}", 3)
    if mode == "abs":
        return (f"${data[1] | (data[2] << 8):04X}", 3)
    if mode == "abs_long":
        return (f"${data[1] | (data[2] << 8) | (data[3] << 16):06X}", 4)
    if mode == "dp":
        return (f"${data[1]:02X}", 2)
    if mode == "dp,X":
        return (f"${data[1]:02X},X", 2)
    if mode == "dp,Y":
        return (f"${data[1]:02X},Y", 2)
    if mode == "(dp)":
        return (f"(${data[1]:02X})", 2)
    if mode == "(dp,X)":
        return (f"(${data[1]:02X},X)", 2)
    if mode == "(dp),Y":
        return (f"(${data[1]:02X}),Y", 2)
    if mode == "[dp]":
        return (f"[${data[1]:02X}]", 2)
    if mode == "[dp],Y":
        return (f"[${data[1]:02X}],Y", 2)
    if mode == "abs,X":
        return (f"${data[1] | (data[2] << 8):04X},X", 3)
    if mode == "abs,Y":
        return (f"${data[1] | (data[2] << 8):04X},Y", 3)
    if mode == "abs_long,X":
        return (f"${data[1] | (data[2] << 8) | (data[3] << 16):06X},X", 4)
    if mode == "(abs)":
        return (f"(${data[1] | (data[2] << 8):04X})", 3)
    if mode == "(abs,X)":
        return (f"(${data[1] | (data[2] << 8):04X},X)", 3)
    if mode == "[abs]":
        return (f"[${data[1] | (data[2] << 8):04X}]", 3)
    if mode == "sr,S":
        return (f"${data[1]:02X},S", 2)
    if mode == "(sr,S),Y":
        return (f"(${data[1]:02X},S),Y", 2)
    if mode == "rel8":
        off = data[1] if data[1] < 0x80 else data[1] - 0x100
        target = (pc + 2 + off) & 0xFFFF
        return (f"${target:04X}", 2)
    if mode == "rel16":
        off = data[1] | (data[2] << 8)
        if off >= 0x8000:
            off -= 0x10000
        target = (pc + 3 + off) & 0xFFFF
        return (f"${target:04X}", 3)
    if mode == "blkmv":
        return (f"${data[1]:02X},${data[2]:02X}", 3)
    return ("???", 1)


def disasm(rom: bytes, start_pc: int, length: int, file_offset: int) -> None:
    """Disassemble. start_pc is SNES PC, file_offset is file byte offset into rom."""
    m_flag = 1  # assume 8-bit A on entry (REP/SEP will update)
    x_flag = 1
    p = 0
    while p < length:
        opcode = rom[file_offset + p]
        if opcode not in OPCODES:
            print(f"  {start_pc + p:06X}  {opcode:02X}              ??? (unknown opcode)")
            p += 1
            continue
        mnem, mode = OPCODES[opcode]
        # Determine instruction length
        if mode == "imm_m":
            instr_len = 3 if m_flag == 0 else 2
        elif mode == "imm_x":
            instr_len = 3 if x_flag == 0 else 2
        elif mode in ("imp", "A"):
            instr_len = 1
        elif mode in ("rel8", "imm8", "dp", "dp,X", "dp,Y", "(dp)",
                      "(dp,X)", "(dp),Y", "[dp]", "[dp],Y", "sr,S", "(sr,S),Y"):
            instr_len = 2
        elif mode in ("abs", "abs,X", "abs,Y", "(abs)", "(abs,X)", "[abs]",
                      "rel16", "blkmv"):
            instr_len = 3
        elif mode in ("abs_long", "abs_long,X"):
            instr_len = 4
        else:
            instr_len = 1
        bytes_slice = rom[file_offset + p:file_offset + p + instr_len]
        # Format operand
        if mode == "imm_m":
            if m_flag == 0:
                val = bytes_slice[1] | (bytes_slice[2] << 8)
                operand = f"#${val:04X}"
            else:
                operand = f"#${bytes_slice[1]:02X}"
        elif mode == "imm_x":
            if x_flag == 0:
                val = bytes_slice[1] | (bytes_slice[2] << 8)
                operand = f"#${val:04X}"
            else:
                operand = f"#${bytes_slice[1]:02X}"
        else:
            operand, _ = fmt_operand(mode, bytes_slice, start_pc + p)
        # Track REP/SEP
        if mnem == "REP":
            mask = bytes_slice[1]
            if mask & 0x20: m_flag = 0
            if mask & 0x10: x_flag = 0
        elif mnem == "SEP":
            mask = bytes_slice[1]
            if mask & 0x20: m_flag = 1
            if mask & 0x10: x_flag = 1
        elif mnem == "XCE":
            pass  # could be entering native mode

        bytes_hex = ' '.join(f'{b:02X}' for b in bytes_slice)
        flags = f"M{m_flag}X{x_flag}"
        print(f"  {start_pc + p:06X}  {bytes_hex:<14}  {mnem} {operand:<20}  [{flags}]")
        p += instr_len


if __name__ == "__main__":
    rom_path = sys.argv[1]
    start_pc = int(sys.argv[2], 16)
    length = int(sys.argv[3], 16)
    # HiROM: PC same as file offset for bank $00-$7D upper half / $C0-$FF
    # For PC range $058000..$05FFFF this is bank $85 (or $C5) data.
    # File offset for our disassembly target = start_pc directly (since rbshura is HiROM and bank $85 = file offset $050000+)
    file_offset = start_pc  # PC-as-file-offset assumption (correct for our $05xxxx range in HiROM)
    rom = open(rom_path, 'rb').read()
    disasm(rom, start_pc, length, file_offset)
