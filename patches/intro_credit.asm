; -----------------------------------------------------------------------------
; intro_credit.asm — G2: add a Brazilian-Portuguese translation credit line to
; the "RUSHING BEAT 修羅" copyright splash, beneath "ALL RIGHTS RESERVED".
; -----------------------------------------------------------------------------
; The splash copyright text is an ASCII string table at $DF:E594, drawn by an
; inline renderer ($DF:E55F): for each entry `[u16 VMADD pos][ASCII...][$00]`
; (terminated by FFFF) it sets VMADD and writes each char to the BG tilemap as
; `tile = char` (the font is ASCII-indexed; char base = VRAM byte $8000), high
; byte (palette/attr) hardcoded to $2C (palette 3 = CGRAM $0C = yellow).
;
; To add ONE line in a different palette without disturbing the existing table
; or renderer, we hook the point where the renderer finishes (table hit FFFF)
; and is about to set the brightness shadow: at $DF:E587 it does
;   LDA #$0F : STA $0080   (5 bytes: A9 0F 8D 80 00)
; We replace that with `JSL DrawCredit` (+NOP). DrawCredit draws our credit line
; into the same tilemap (still forced-blank here, so VRAM is writable), using
; palette 4 (CGRAM $10 = blue; tilemap attr $30 = palette 4 + priority, matching
; the existing lines' priority bit), then redoes the brightness set it replaced.
;
; Position $6302 = tilemap word $6000 + row 24*32 + col 2 (directly below
; "ALL RIGHTS RESERVED" at $62E7 = row 23; row 25 clipped at the screen edge).
; Up to 28 chars (cols 2..29) fit the 32-wide map. The splash font is
; ASCII-indexed and uppercase-only (glyphs A-Z, 0-9, space, '-'=$2D) — it has
; NO accented letters, so the pt-BR credit must be unaccented uppercase ASCII
; (e.g. "VERSAO", not "VERSÃO").
; -----------------------------------------------------------------------------

hirom

; --- shift "©JALECO 1993" and "ALL RIGHTS RESERVED" up one row (-$20 words) so
;     there's room for a blank-row gap + the credit, all within the title-safe
;     area (row <=24). These are the u16 position words in the existing table. ---
org $DFE5A3
    dw $628A                ; ©JALECO 1993:        $62AA -> $628A (row 21 -> 20)
org $DFE5B3
    dw $62C7                ; ALL RIGHTS RESERVED: $62E7 -> $62C7 (row 23 -> 22)

; --- hook: replace LDA #$0F / STA $0080 at $DF:E587 with JSL DrawCredit + NOP ---
org $DFE587
    JSL DrawCredit          ; 22 40 A3 E1
    NOP                     ; pad (was the 5th byte of LDA #$0F / STA $0080)

org $E1A340
DrawCredit:
    PHP
    REP #$10                ; X/Y 16-bit
    SEP #$20                ; A 8-bit
    LDA #$80 : STA $2115    ; VRAM inc after $2119, step 1 (match renderer; safety)
    LDX #$6302             ; tilemap pos: row 24, col 2 (blank row 23 gap below ALL RIGHTS RESERVED@row22)
    STX $2116              ; VMADD  (DBR=$9F here -> $21xx are PPU regs)
    LDX #$0000
.loop:
    LDA.L CreditStr,X      ; char from $E1:CreditStr+X (long -> DBR-independent)
    BEQ .done
    STA $2118              ; tilemap low = tile index (= ASCII char)
    LDA #$30              ; tilemap high = palette 4 (CGRAM $10, blue) + priority
    STA $2119
    INX
    BRA .loop
.done:
    LDA #$0F : STA $0080   ; (replaced) brightness shadow = full -> screen on
    PLP
    RTL

CreditStr:
    ; pt-BR credit. ASCII uppercase only (no accents — see note above), <= 28
    ; chars. Edit the translator/attribution text as needed.
    db "VERSAO PT-BR - DACKR 2026", $00

assert pc() <= $E1A3C0, "DrawCredit overflowed its reserved slot"
