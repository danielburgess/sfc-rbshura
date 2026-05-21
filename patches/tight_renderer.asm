; -----------------------------------------------------------------------------
; Rushing Beat Shura — tight-8 text renderer patch
; -----------------------------------------------------------------------------
; Patches the dialog text renderer at $05:839F so each character occupies a
; SINGLE tile column (8×16 effective glyph) instead of the vanilla 2×2 (16×16)
; layout. With the PK 8-wide font in tables, this yields 32 chars per line at
; the engine's original tilemap geometry.
;
; All edits are byte-count preserving — the renderer's body length is
; unchanged, so callers' relative offsets remain valid.
;
; Vanilla renderer head (sanity-check anchor — left untouched):
;   $0583A0: C2 30           REP #$30
;   $0583A2: AC 22 0F        LDY $0F22
;   $0583A5: A9 80 00        LDA #$0080
;   $0583A8: 99 22 0E        STA $E22,Y
;
; Three architectural changes vs vanilla rbshura:
;   1. DMA byte count: $40 (64B / 4 tiles) → $20 (32B / 2 tiles).
;   2. Tilemap tail: 4 entries (TL/TR/BL/BR) → 2 entries (TL/BL). The two
;      `STA $001542,X` / `STA $001582,X` stores for TR/BR are NOPed, along
;      with the bridging `INC A` that bumped the tile# for each.
;   3. Column / tile-slot advance: ×4 → ×2 per char. Two of each
;      `INC $1C4C` / `INC $1C58` are NOPed.
;
; Font layout requirement (satisfied by fonts/rbshura_en.bin): each 64-byte
; slot holds the PK 32B glyph (top tile + bottom tile) in the first half;
; bytes 32-63 are zeroed (never DMA'd at the new $20 size).
; -----------------------------------------------------------------------------

hirom

; 1. DMA byte count literal: $40 → $20 (the imm byte after `LDA #imm`).
org $C583D8 : db $20

; 2a. Kill TR tilemap store: `STA $001542,X` + bridging `INC A` (5 bytes).
org $C58403 : NOP : NOP : NOP : NOP : NOP

; 2b. Kill BR tilemap store: `INC A` + `STA $001582,X` (5 bytes).
org $C5840C : NOP : NOP : NOP : NOP : NOP

; 3a. Drop 2 of 4 `INC $1C4C` (column advance ×4 → ×2). 6 bytes.
org $C58417 : NOP : NOP : NOP : NOP : NOP : NOP

; 3b. Drop 2 of 4 `INC $1C58` (tile-slot advance ×4 → ×2). 6 bytes.
org $C58423 : NOP : NOP : NOP : NOP : NOP : NOP
