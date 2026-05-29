# Rushing Beat Shura — Reverse Engineering Notes

## ROM Info
- File: `rbshura.sfc`
- Size: 2 MB (2,097,152 bytes) — 32 banks × 64 KB
- Mapping: **HiROM / FastROM** (`hirom` in Asar)
- SNES banks used: `$C0–$DF` (slow mirrors: `$40–$5F`, fast mirrors: `$80–$9F`)

## HiROM Address Conversion

```
PC offset = (bank & 0x3F) × 0x10000 + offset_within_bank
```

Valid bank ranges that map to ROM:
- `$40–$7F` (slow mirror): `PC = (bank − 0x40) × 0x10000 + offset`
- `$80–$BF` (fast mirror, offset ≥ $8000): `PC = (bank − 0x80) × 0x10000 + offset`
- `$C0–$FF` (full 64 KB): `PC = (bank − 0xC0) × 0x10000 + offset`

Effectively: `PC = (bank & 0x3F) × 0x10000 + offset` for any valid bank.

---

## Compression System

All data compression uses a single LZSS variant:

### Format
```
[2 bytes: compressed_size (little-endian)]
[compressed_size bytes: LZSS stream]
```

### LZSS Parameters
| Parameter | Value |
|-----------|-------|
| Window size | 4096 bytes (12-bit offset) |
| Initial window position | `0x0FEE` |
| Min match length | 3 |
| Max match length | 18 |
| Control bit meaning | 1 = literal, 0 = back-reference |

### Back-reference encoding (2 bytes)
```
byte1 = offset & 0xFF
byte2 = ((offset >> 8) << 4) | (length − 3)
```
Offset is 12-bit (AND 0x0FFF), length is 4-bit + 3.

### Decompression routine
- **PC**: `0x05409` (SNES `$C05409`, label: `DecompressData`)
- **Input pointer**: `[$B4]` + Y (bank in `$B6`)
- **Output pointer**: `[$B8]` (bank in `$BA`)
- **Compressed bytes remaining**: `$BC` (counts DOWN; terminates when negative)
- **Window buffer**: WRAM `$7E:EFFF–$EFFF+0x0FFF`
- **Window position**: `$00B0`

---

## Dialogue / Text System

### Korean ROM Comparison Method

The text system was fully mapped by comparing the JP ROM against the Korean translation ROM (`Rushing Beat Shura (Korean).sfc`, same size + 512-byte copier header).

Binary diff summary:
| Bank | PC Range | Changed Bytes | Purpose |
|------|----------|---------------|---------|
| $C0 | `$007FDC` | 4 | ROM header (checksum) |
| $C5 | `$058000–$05FFFF` | 7,206 | Text engine + dialogue strings |
| $C7 | `$070000–$07FFFF` | 1,116 | Additional dialogue strings |
| $D0 | `$100000–$107FFF` | 23,724 | **Font tile data** (2bpp) |
| $D8 | `$18E000–$18FFFF` | 69 | Cutscene/battle text |
| $DF | `$1FC800–$1FD020` | 1,173 | Additional text (credits?) |

### Font

- **Location**: PC `$100000` (SNES bank `$D0`)
- **Format**: 2bpp SNES tiles, 16×16 pixels per character (4 × 8×8 tiles each)
- **Layout**: 2 pages × 247 characters ($00–$F6) = 494 character slots
  - Page 1: direct byte values — hiragana, katakana, numbers, Latin, punctuation, kanji
  - Page 2: accessed via `FA xx` control code — additional kanji
- **Size**: 32 KB total (2048 × 8×8 tiles × 16 bytes/tile)
- **Tile arrangement per character**: top-left, top-right, bottom-left, bottom-right (each 8×8 2bpp tile = 16 bytes, 64 bytes per character)

Page 1 encoding:
| Range | Content |
|-------|---------|
| `$00–$2C` | Hiragana (あ–ん) |
| `$2D–$35` | Small hiragana (ぁ–っ) |
| `$36–$4F` | Dakuten/handakuten hiragana (が–ぽ) |
| `$50–$7C` | Katakana (ア–ン) |
| `$7D–$85` | Small katakana (ァ–ッ) |
| `$86–$9F` | Dakuten/handakuten katakana (ガ–ポ) |
| `$A0–$A9` | Fullwidth digits (０–９) |
| `$AA–$C3` | Fullwidth Latin (Ａ–Ｚ) |
| `$C4–$CB` | Punctuation (…？（）〜ー・！) |
| `$CC–$CF` | Blank/space |
| `$D0–$EF` | Common kanji (活医期奇立就…) |
| `$F0–$F1` | Japanese quote brackets (「」) |
| `$F2–$F6` | Blank |

See `tables/jp.tbl` for the complete character-by-character mapping.

### Text Encoding

Text strings use byte values `$00–$F6` as font tile indices, with control codes `$F7–$FF`:

| Code | Params | Function |
|------|--------|----------|
| `F7 xx` | 1 | End of displayed text line. Param stored for next section. |
| `F8 xx` | 1 | Text reveal speed |
| `F9 xx` | 1 | Character portrait selection |
| `FA xx` | 1 | Page 2 character (param = char index in page 2) |
| `FB xx` | 1 | Window/dialogue box type |
| `FC 00 xx` | 2 | Play sound effect |
| `FC 01 xx` | 2 | Text attribute/color |
| `FC 02 xx yy` | 3 | Character sprite/animation |
| `FD` | 0 | Newline |
| `FE` | 0 | Page break (clear text area) |
| `FF` | 0 | End of block / string separator |

### Text Data Locations

| Region | PC Range | Bank | Content |
|--------|----------|------|---------|
| Text engine code | `$058000–$0583FF` | $C5 | Text rendering engine |
| Main dialogue | `$058400–$05FFFF` | $C5 | ~407 strings |
| Secondary dialogue | `$070000–$07FFFF` | $C7 | ~87 strings |
| Battle/cutscene text | `$18E000–$18FFFF` | $D8 | ~11 strings |
| **Total** | | | **~512 strings, ~745 text lines, ~10,000 characters** |

### Text Pointer Structure

3-level hierarchy within the text engine:

1. **Master table** at PC `$058215`: 15 entries (2 bytes each), indexed by scenario ID
2. **Level 2 tables**: per-scenario, indexed by `$1C48` — pointers to L3 tables
3. **Level 3 tables**: indexed by `$1C83` — pointers to actual text strings

Bank selection via lookup at PC `$05807A`:
- Scenarios 0–9 → bank `$85` (PC `$05xxxx`)
- Scenarios 10–14 → bank `$87` (PC `$07xxxx`)

### Text String Format

Each string is delimited by `FF`:
```
FF [control codes] [text bytes] F7 xx     ← one text line
FF FB xx                                   ← wait-for-input marker
FF [control codes] [text bytes] F7 xx     ← next line
```

Multi-line blocks can chain through `F7` with non-$FF params:
```
FF FB 10 FE F7 08 [text] FD [more text] F7 xx
```

---

## Character Names

- **Location**: PC `0x00E15B` onward
- **Index table**: PC `0x00E119` (16-bit LE pointers to each name)
- **Format**: 12 bytes per name — 11 ASCII characters, padded with `0x20`, terminated by `0xFF`
- **Encoding**: plain ASCII (`0x20`–`0x7E`)
- **Count**: 30+ entries

### Names (0-indexed)
```
[ 0] "DICK       "  PC 0x00E15B
[ 1] "SPIDER     "  PC 0x00E167
[ 2] "KYTHRING   "  PC 0x00E173
[ 3] "MCCOY      "  PC 0x00E17F
[ 4] "JIMMY      "  PC 0x00E18B
[ 5] "DAG        "  PC 0x00E197
[ 6] "M-FRAME    "  PC 0x00E1A3
[ 7] "CELL       "  PC 0x00E1AF
[ 8] "ELFIN      "  PC 0x00E1BB
[ 9] "BART       "  PC 0x00E1C7
[10] "NORTON     "  PC 0x00E1D3
[11] "KULMBACH   "  PC 0x00E1DF
[12] "AXE        "  PC 0x00E1EB
[13] "BOB        "  PC 0x00E1F7
[14] "JOE        "  PC 0x00E203
[15] "JONY       "  PC 0x00E20F
[16] "YAMAOKA    "  PC 0x00E21B
[17] "???????????"  PC 0x00E227
[18] "DEAN       "  PC 0x00E233
[19] "VELK       "  PC 0x00E23F
[20] "EIJI       "  PC 0x00E24B
[21] "ONIDO      "  PC 0x00E257
[22] "BURNET     "  PC 0x00E263
[23] "CALSONIC   "  PC 0x00E26F
[24] "KIRA       "  PC 0x00E27B
[25] "HUNTER     "  PC 0x00E287
[26] "HELHEIM    "  PC 0x00E293
[27] "TOMY       "  PC 0x00E29F
[28] "DRUM       "  PC 0x00E2AB
[29] "BOX        "  PC 0x00E2B7
```

---

## Key WRAM Addresses

| Address | Purpose |
|---------|---------|
| `$7E:0000–$01FF` | Direct page / zero page registers |
| `$7E:0E22` | DMA job queue (8 bytes × N entries) |
| `$7E:0F22` | DMA queue length (byte count) |
| `$7E:2000` | Text tile display buffer |
| `$7E:2500` | Script data buffer (CopyDataToRAM destination) |
| `$7E:ECC0` | Character palette / state buffer |
| `$7F:0000` | LZSS decompression output (audio/graphics) |
| `$7F:9000+` | Pre-loaded sprite/tile graphics |
| `$7E:EFFF` | LZSS sliding window (4 KB) |

---

## Graphics Pipeline

1. Compressed graphics blocks are **LZSS-compressed** in ROM
2. Decompressed to **WRAM `$7F:xxxx`** at load time
3. Transferred from WRAM `$7F` → **VRAM** via DMA during vblank

### DMA queue
- Buffer: WRAM `$0E22–$0E22+(n×8)`, length in `$0F22`
- Processed by `UpdateLayerControlRegisters` (PC `0x04398`)
- **8-byte entry format**:

| Offset | Register | Description |
|--------|----------|-------------|
| +0 | `$2115` | VRAM increment mode (1 byte) |
| +1–+2 | `$4302` | DMA source address (16-bit LE) |
| +3 | `$4304` | DMA source bank |
| +4–+5 | `$4305` | DMA transfer length |
| +6–+7 | `$2116` | VRAM destination address |

---

## Key Code Locations

| Symbol | PC Offset | Description |
|--------|-----------|-------------|
| `DecompressData` | `0x05409` | Main LZSS decompression |
| `CopyTextString` | `0x181882` | Copies text string to display buffer |
| `ClearTextBuffer` | `0x181871` | Clears $7E2000 with spaces |
| `UploadVRAMData` | `0x04438` | DMA $7E2000 → VRAM |
| `UpdateLayerControlRegisters` | `0x04398` | Processes DMA queue ($0E22) |
| `InitHardware` | `0x05946` | SNES hardware init |
| Text engine entry | `0x058000` | Main text rendering code (bank $C5) |
| Master text table | `0x058215` | 15 scenario pointers |

---

## Translation Toolkit

### Files

| File | Purpose |
|------|---------|
| `rbshura.py` | ROM utilities (LZSS, address conversion, etc.) |
| `text_tool.py` | Text extraction/insertion/font tools |
| `tables/jp.tbl` | JP font table (byte → Japanese character) |
| `tables/en.tbl` | EN font table (byte → English character) |
| `text/dialogue_dump.txt` | Extracted JP dialogue (512 strings) |
| `fonts/jp_font_p0.bin` / `p1.bin` | Extracted JP font pages (2bpp binary) |
| `fonts/jp_font_p0_labeled.png` / `p1` | JP font grids with hex labels |
| `fonts/en_font.bin` | English 16×16 2bpp font |
| `fonts/en_font_preview.ppm` | EN font preview grid |
| `fonts/build_en_font.py` | EN font generator (editable pixel art) |

### Commands

```bash
# Extract all text
python text_tool.py dump rbshura.sfc text/dialogue_dump.txt tables/jp.tbl

# Show statistics
python text_tool.py stats rbshura.sfc

# Export JP font as image
python text_tool.py font-export-ppm rbshura.sfc 0 fonts/jp_font_p0.ppm

# Export JP font as binary
python text_tool.py font-export rbshura.sfc 0 fonts/jp_font_p0.bin

# Import EN font into ROM
python text_tool.py font-import rbshura.sfc fonts/en_font.bin output.sfc

# Insert translated text
python text_tool.py insert output.sfc text/dialogue_dump.txt final.sfc tables/en.tbl
```

### Translation Workflow

1. **Extract**: `python text_tool.py dump rbshura.sfc text/dialogue_dump.txt`
2. **Translate**: Edit `text/dialogue_dump.txt`, writing English on `>` lines
3. **Import font**: `python text_tool.py font-import rbshura.sfc fonts/en_font.bin output.sfc`
4. **Insert text**: `python text_tool.py insert output.sfc text/dialogue_dump.txt final.sfc`
5. **Test**: Load `final.sfc` in emulator

### English Font Encoding

| Range | Characters |
|-------|-----------|
| `$00` | Space |
| `$01–$1A` | A–Z |
| `$1B–$34` | a–z |
| `$35–$3E` | 0–9 |
| `$3F–$59` | Punctuation (!?.,'-:;()/…""&@#+=_~<>[]%*) |
| `$60–$76` | Accented uppercase (ÀÁÂÄÈÉÊËÌÍÎÏÒÓÔÖÙÚÛÜÑÇÝ) |
| `$80–$97` | Accented lowercase (àáâäèéêëìíîïòóôöùúûüñçýÿ) |

### Text Dump Format

```
@NNNN PC=$XXXXXX BANK=$XX END=$XX
;raw: XX XX XX ...
Japanese text with {NL} and {PORT:XX} etc.
>English translation here with {NL} for line breaks
```

Control codes to preserve in translations:
- `{NL}` — newline (place where you want line breaks)
- `{PB}` — page break
- `{PORT:XX}` — character portrait (keep as-is)
- `{SPD:XX}` — text speed (keep as-is)
- `{FC:XX,YY}` / `{FC:XX,YY,ZZ}` — misc controls (keep as-is)

---

## TODO

- [ ] Translate all 512 dialogue strings
- [ ] Verify EN font readability in-game
- [ ] Handle text length constraints (EN must fit in same byte space as JP)
- [ ] Test full insert pipeline with emulator
- [ ] Check for additional text in bank $DF (credits/ending)
- [ ] Fine-tune a few ambiguous kanji in `tables/jp.tbl` page 2
- [ ] Handle menu/HUD text (separate system from dialogue)
