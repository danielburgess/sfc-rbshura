; -----------------------------------------------------------------------------
; intro_dialog_port.asm — render intro through the dialog tilemap pipeline
; -----------------------------------------------------------------------------
; The intro renderer at $05:F040 was originally:
;   $F03B: XBA / LDA #$00 / REP #$20 / LSR LSR    (A = byte * 64)
;   $F042: ORA $02                                ($02 is 0, no-op)
;   $F044: STA $0E23,X                            (TL → intro staging)
;   $F047: CLC : ADC #$0020                       (BL = TL + $20)
;   $F04B: STA $0E2B,X                            (BL → intro staging)
;   $F04E: LDA #$0020 / STA $0E26,X / STA $0E2E,X (TR/BR with constant $20)
;
; Problems with this for our PK font + dialog tilemap pipeline:
;   - byte * 64 produces tile numbers that overrun our 160-tile PK font
;     in VRAM. PK glyph N has its TOP at VRAM tile 2N, BOTTOM at 2N+1
;     (sequential pairs, since the dialog tight-8 patch DMAs 32 B per
;     glyph = 2 tiles consecutively).
;   - The intro's tilemap at $0E23 lives under a mask and isn't visible.
;     Only the dialog tilemap at $00:1540/$00:1580 makes it to screen,
;     and entries there need palette bits ($3C00 = palette 7 + priority).
;
; This patch:
;   1) Replaces the `byte * 64` math with `byte * 2`.
;   2) Redirects TL/BL writes through stubs at $C8:7040 / $C8:7050 that
;      ALSO write to $1540 / $1580 with palette $3C00 OR'd in.
;   3) Changes the BL offset from +$20 to +$01 (PK glyph N's bottom is
;      at tile 2N+1, immediately after the top).
;   4) NOPs the now-pointless TR/BR writes ($0E26 / $0E2E).
;
; Byte-count preserving — all inline replacements match the original
; segment lengths. Stubs live in bank-$08 freespace after the 24-bit-ptr
; engine stub.
; -----------------------------------------------------------------------------

hirom

; -----------------------------------------------------------------------------
; Stub WriteTL @ $C8:7040 — preserve A across an extra dialog tilemap write
; -----------------------------------------------------------------------------
; In:  A (16-bit) = TL tile number (byte * 2)
;      X (16-bit) = intro's per-char staging index
; Out: A unchanged so the caller's CLC + ADC #$0001 computes BL cleanly.
org $C87040
WriteTL:
    PHA               ; save bare tile_num for caller's BL math
    ORA #$3C00        ; palette 7 + priority (dialog convention)
    STA $0E23,x       ; intro's OWN staging — now carries palette bits so
                      ; the intro's existing DMA → VRAM $5800 brings them
                      ; along
    STA $1540,x       ; also dialog tilemap (helpful if dialog DMA runs)
    PLA               ; restore bare A so caller's CLC + ADC #$0001 works
    RTL

; -----------------------------------------------------------------------------
; Stub WriteBL @ $C8:7050
; -----------------------------------------------------------------------------
org $C87050
WriteBL:
    ORA #$3C00
    STA $0E2B,x       ; intro's own BL staging with palette bits
    STA $1580,x       ; also dialog tilemap BL row
    RTL

; -----------------------------------------------------------------------------
; Replace the per-char setup + TL write at $05:F03B..F046 (12 bytes)
; -----------------------------------------------------------------------------
; Old: XBA + LDA #$00 + REP #$20 + LSR + LSR + ORA $02 + STA $0E23,X
; New: NOP + REP #$20 + AND #$00FF + ASL + JSL WriteTL + NOP
;      (1 + 2 + 3 + 1 + 4 + 1 = 12 bytes)
; The XBA is dropped — A.lo already holds the byte from the $F028 read,
; and the intervening CMPs don't modify A.
org $C5F03B
    NOP               ; was XBA
    REP #$20          ; 16-bit A
    AND #$00FF        ; clear A.hi (stale bytes from earlier code)
    ASL               ; A = byte * 2 (matches 2-tile-per-glyph PK font)
    JSL WriteTL       ; writes intro staging + dialog tilemap; returns A
    NOP               ; padding to keep $F047 lined up with the original CLC

; -----------------------------------------------------------------------------
; BL offset: change ADC #$0020 → ADC #$0001 (single-byte patch)
; -----------------------------------------------------------------------------
org $C5F049 : db $01  ; was $20 — low byte of `ADC #$0020`

; -----------------------------------------------------------------------------
; Replace BL write + TR/BR garbage at $05:F04B..F056 (12 bytes)
; -----------------------------------------------------------------------------
; Old: STA $0E2B,X + LDA #$0020 + STA $0E26,X + STA $0E2E,X (3+3+3+3 = 12 B)
; New: JSL WriteBL + 8 NOPs (4 + 8 = 12 B)
org $C5F04B
    JSL WriteBL
    NOP : NOP : NOP : NOP : NOP : NOP : NOP : NOP
