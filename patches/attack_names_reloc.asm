; -----------------------------------------------------------------------------
; Rushing Beat Shura — relocate special-move "attack name" word-art to bank $E1
; -----------------------------------------------------------------------------
; The attack-name loader ($82:DC2B) DMAs, per move, a tile block + a 128-entry
; BG3 tilemap from a source-address table at $82:DC8C, indexed by $12CE. Stock
; layout: source bank $CF, tile DMA count $200 (32 tiles), map count $100;
; tiles -> VRAM $4700 (tile $E0), tilemap -> VRAM $5A28 (BG3 map, rows 17-21).
;
; Two stock limits block English plates:
;   1. ROM: the per-name source data is packed in bank $CF. Relocate the whole
;      pool to pristine expansion bank $E1 (source bank is hardcoded + shared,
;      so ALL names move together).
;   2. VRAM: the tile window is only 32 tiles ($E0-$FF); $100+ ($4800+) holds
;      live HUD/sprite graphics, so a >32-tile DMA at $4700 corrupts them.
;      Move the tile dest to $4400 (tile $80) — the DIALOG tile region, which is
;      never active while an attack name is shown (per user). 36 tiles land in
;      $4400-$4520, well inside the safe $4400-$4818 dialog window.
;
; The graphics data is encoded at build time by retrotool's kind="graphics" PNG
; sections in project.toml (SuperFamiconv tiles + projected tilemap), written to
; bank $E1: tiles[i] at $E1:(i*$240), maps[i] at $E1:($900 + i*$100). The
; tilemaps reference tiles $80+ (tile-base="$80" in the sections, matching the
; $4400 dest here).
;
; HiROM addressing: $82:xxxx loader code lives at file $02xxxx = $C2:xxxx.
; -----------------------------------------------------------------------------

hirom

; --- loader DMA-descriptor builder ($82:DC2B) ---
org $C2DC46 : db $E1        ; tile DMA source bank   ($CF -> $E1)
org $C2DC4D : dw $0240      ; tile DMA byte count    ($0200 -> $0240 = 36 tiles)
org $C2DC53 : dw $4400      ; tile DMA VRAM dest     ($4700 -> $4400 = tile $80, dialog region)
org $C2DC6A : db $E1        ; tilemap DMA source bank ($CF -> $E1)

; --- source-address table ($82:DC8C): 5 x [tile_src, map_src], bank-$E1 offsets ---
; (idx 4 duplicates idx 2 / dragon_wave, exactly as the stock table did.)
org $C2DC8C
  dw $0000, $0900   ; 0 thunder_edge
  dw $0240, $0A00   ; 1 assault_tiger
  dw $0480, $0B00   ; 2 dragon_wave
  dw $06C0, $0C00   ; 3 bird_storm
  dw $0480, $0B00   ; 4 dragon_wave (duplicate)
