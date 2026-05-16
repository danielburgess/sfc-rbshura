#!/usr/bin/env python3
"""Dump all 14 translatable scenarios' string-pointer tables to .txt files
using retrotool's `extract_script()` as a library.

Bypasses `retrotool extract` (the CLI) because the build pipeline's pointer-
resolution is currently LoROM-hardcoded; rbshura is HiROM. The dump format
matches what `retrotool extract` would emit so the same files can drive
the build/encode pipeline once mapping-awareness lands upstream.

Output: `data/jp/scenario_NN.txt`, UTF-16 LE BOM, with per-entry headers
`<<$PTRTBL:IDX[$PC]>>` matching `build/extract.py::_extract_script_pointer_table`.
"""
from __future__ import annotations

from pathlib import Path

from retrotool import Rom
from retrotool.core.address import SFCAddressType
from retrotool.project.datadef import (
    DataDef,
    DataSection,
    EncodingSection,
    PointersSection,
)
from retrotool.script.extractor import extract_script
from retrotool.script.table import Table


# 14 scenarios: (id, bank, ptr_table_snes_addr_low16, pointer_count, data_end_pc)
# Counts verified empirically against the live ROM (see project memory).
# Scenario 28 (bank $7E WRAM) is dynamic — excluded.
SCENARIOS: list[tuple[int, int, int, int]] = [
    (0,  0x85, 0x86E4, 59),
    (2,  0x85, 0x8FD0, 42),
    (4,  0x85, 0x95B5, 63),
    (6,  0x85, 0xA09D, 46),
    (8,  0x85, 0xA70C, 33),
    (10, 0x87, 0x879C, 32),
    (12, 0x87, 0x8C5A, 29),
    (14, 0x87, 0x9062, 46),
    (16, 0x85, 0xAE5C, 73),
    (18, 0x85, 0xB8EF, 45),
    (20, 0x85, 0xBFA1, 43),
    (22, 0x85, 0xC7B7, 50),
    (24, 0x85, 0xD073, 101),
    (26, 0x85, 0xE170, 71),
]


def hirom_to_pc(bank: int, addr: int) -> int:
    """SNES HiROM $bb:aaaa → ROM file PC offset, using the bank-mirror form
    rbshura uses ($85/$87 mirror $C5/$C7)."""
    return ((bank & 0x7F) << 16) | addr


def dump_scenario(rom_bytes: bytes, table: Table, scen: int, bank: int,
                  ptr_addr: int, count: int) -> list[str]:
    """Produce the .txt body for one scenario. Matches the per-entry header
    style emitted by `build/extract.py::_extract_script_pointer_table`."""
    ptr_table_pc = hirom_to_pc(bank, ptr_addr)
    # Bank-wide data window so strings shared across scenarios resolve.
    bank_base_pc = (bank & 0x7F) << 16
    bank_end_pc = bank_base_pc + 0x10000

    datadef = DataDef(
        name=f"scenario_{scen:02d}",
        type="pointer",
        encoding=EncodingSection(
            table_file=Path("tables/rbshura.tbl"),
            terminator=0xFF,
        ),
        pointers=PointersSection(offset=ptr_table_pc, count=count, size=2),
        data=DataSection(offset=bank_base_pc, end=bank_end_pc),
    )
    script = extract_script(
        rom_bytes, datadef, table, address_type=SFCAddressType.PC
    )

    lines: list[str] = []
    for idx, entry in enumerate(script.entries):
        lines.append(f"<<${ptr_table_pc}:{idx}[${entry.data_addr}]>>")
        lines.append(entry.text)
    return lines


def main() -> None:
    rom = Rom.load("rbshura.sfc")
    table = Table("tables/rbshura.tbl")
    out_dir = Path("data/jp")
    out_dir.mkdir(parents=True, exist_ok=True)

    total_entries = 0
    for scen, bank, ptr_addr, count in SCENARIOS:
        lines = dump_scenario(rom.data, table, scen, bank, ptr_addr, count)
        out_path = out_dir / f"scenario_{scen:02d}.txt"
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-16")
        print(f"  scenario_{scen:02d}: {count:3d} entries → {out_path}")
        total_entries += count

    print(f"\nDumped {total_entries} pointer slots across {len(SCENARIOS)} scenarios.")


if __name__ == "__main__":
    main()
