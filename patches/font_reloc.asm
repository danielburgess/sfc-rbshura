; -----------------------------------------------------------------------------
; Rushing Beat Shura — font relocation: $D0:0000 -> $E2:0000
; -----------------------------------------------------------------------------
; The English PK font lived ROM-direct at $100000 ($D0:0000) as 80 x 64 B slots
; (5120 B). That region is full: slots 0x4C..0x4F are the only free ones, and
; file $101400+ holds live game graphics, so the 13 Brazilian-Portuguese
; accented glyphs (Éáéíóúâêôàãõç, slots 0x4C..0x58) do not fit in place.
;
; The EXTENDED font (fonts/rbshura_font_ext.bin, 89 slots = PK Latin + the 13
; accents) is placed at $E2:0000 (file $220000) by project.toml. This patch
; repoints every renderer that DMAs glyphs from the font so they read $E2
; instead of $D0. The on-screen result is byte-identical for the existing Latin
; text (slots 0x00..0x4B match the old font exactly); the new high slots only
; render when a script emits them via tables/rbshura_br_pt.tbl.
;
; Renderers repointed (each loads the font source BANK as #$00D0 -> change to
; #$00E2; only the low operand byte is poked):
;
;   * Dialogue typewriter ($05:839F). Two branches set the DMA-descriptor source
;     bank ($0E25,Y): branch 1 (page base $0000) at $05:83BC, branch 2 (page
;     base $4000) at $05:83D1. The page selector $1C81 is only ever STZ'd
;     ($05:8100), so branch 2 is dead, but both banks are repointed for safety.
;   * Intro / fadeScreenIn body ($05:F1E8) — STA $4304 source bank for the
;     idx-0 / idx-20+ (intro scroll) glyph DMA.
;
; The half-width narration renderer (idx 1..19) is OUR relocated copy at
; $E0:DC91; it reads !FONT_BANK, which patches/narration_render.asm sets to
; $00E2 — see that file (NOT poked here).
;
; The original font at $100000 is deliberately LEFT in place (project.toml still
; ships it) as a safety net: any font-DMA site not repointed here keeps reading
; the correct Latin glyphs (just without accents) instead of garbage.
;
; All three are single-byte operand pokes (D0 -> E2), byte-count preserving.
; -----------------------------------------------------------------------------

hirom

org $C583BD : db $E2    ; dialogue branch 1: LDA #$00D0 -> #$00E2 (font bank)
org $C583D2 : db $E2    ; dialogue branch 2: LDA #$00D0 -> #$00E2 (dead, kept consistent)
org $C5F1E9 : db $E2    ; intro/fadeScreenIn: LDA #$00D0 -> #$00E2 ($4304 src bank)
