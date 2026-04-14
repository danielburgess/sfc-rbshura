# retrotool Merge Plan

Migrate local tooling in this project onto `retrotool` (user's own pip-installable SNES/SFC library, currently 0.8.1). Consolidate duplicated code, contribute gaps upstream.

## Module mapping

| Local | retrotool replacement | Notes |
|---|---|---|
| `lzss_old.py`, `rbshura.lzss_*` | `LZSSCodec(PARAMS_RBSHURA)` from `retrotool.compression` | Phase 1 |
| `mesen_ipc.py` | `retrotool.debugger.MesenClient` | Phase 1; use `derive_pipe_name` |
| `rbshura.snes_to_pc` / `read_u{8,16,24}_le` | `retrotool.core.address` + `core.binary` | Phase 1 |
| `rbshura.scan_compressed_blocks` | `retrotool.compression.detector.scan_lzss` | Phase 1 verify, then swap |
| `rbshura.snes_{2,4}bpp_to_indices` | `retrotool.graphics.tiles.decode_tile` | Returns `list[list[int]]`; flatten as needed |
| `text_tool.py` dump/insert | `retrotool.script.Table` + `extract_script` + `inserter` | Phase 2 (blocked on chained pointers) |
| `rbshura.CharName` + script ptr chain | datadef-driven extraction | Phase 2 (chained pointers) |
| `preview.py`, JSON exporters, font helpers | keep local | Project-specific glue |

## Phase 1 — Swaps (no risk)

1. Add `retrotool>=0.8.1` to `pyproject.toml` deps.
2. LZSS roundtrip test against a known compressed block. Compare `LZSSCodec(PARAMS_RBSHURA).decompress/compress` vs `rbshura.lzss_decompress_block` / `lzss_compress_block` byte-for-byte. If match → swap all call sites.
3. Detector comparison: diff `scan_lzss(..., [('rbshura', PARAMS_RBSHURA)])` offsets vs `rbshura.scan_compressed_blocks` output.
4. Replace `mesen_ipc.py` usage with `MesenClient`. Derive pipe name from ROM filename.
5. Delete `lzss_old.py`, `mesen_ipc.py`, and replaced helpers in `rbshura.py` after swap-tests pass.

## Phase 2 — Text pipeline + upstream fixes

### Chained pointers (Proposal B: local subclass first)

rbshura has a 4-level chain (scenario idx → bank table → config ptr → data ptr → string). Retrotool `DataDef.pointers` is single-level.

Prototype locally as `ChainedDataDef(DataDef)` + `extract_chained_script()`. Once shape settles, promote upstream as `[[pointers.chain]]` TOML array-of-tables:

```toml
[[pointers.chain]]
address = "$C0:8000"
count   = 15
size    = 1
emits   = "bank"         # bank / snes16 / snes24 / pc24
[[pointers.chain]]
address = "$ref"         # uses prior level output as base
size    = 3
emits   = "snes24"
```

### Retrotool bugs to fix upstream (in `/mnt/crucial/projects/retrotool/`)

Constraint: must not break single-ctrl-prefix existing projects.

**Bug A — `script/extractor.py::_read_until`** ignores `Table.find_entry_end()`. Param bytes equal to terminator (0x00) prematurely end strings. Fix: route through `find_entry_end` when a Table is available; keep raw `_read_until` as fallback for non-@ctrl tables.

**Bug B — `Table.interpret_binary_data()`** does longest-match decode without honoring `ctrl_lengths`. When `bin_data[i] == ctrl_prefix`, consume `ctrl_lengths[next_byte]` bytes as one bracketed token `[FF XX YY…]`. Back-compat: if no @ctrl entries loaded, behavior unchanged.

**Enhancement C — multi-prefix @ctrl.** Today only one `ctrl_prefix` per table. Extend to `ctrl_prefixes: set[int]` with per-prefix length tables. Back-compat: parse existing `@ctrl_prefix XX` as single-element set; existing tables keep working unchanged.

### Upstream contribution: generic PPM writer

`retrotool.graphics.tiles.composite_to_image()` returns `(w, h, rgba_bytes)` but has no serializer. Add `retrotool.graphics.ppm.write_ppm(path, w, h, buf, *, binary=True, has_alpha=True)` — P6 binary or P3 ASCII, strips alpha to RGB, no deps.

## What stays local

- `preview.py` (pywebview app — project-specific UI)
- JSON export helpers (char names, script blocks)
- Font bin/PPM import/export specific to rbshura tile layout
- Any per-scenario glue that encodes this ROM's quirks

## Status

- 2026-04-13: retrotool 0.8.1 installed, surveyed
- 2026-04-14: plan agreed, Phase 1 in progress
