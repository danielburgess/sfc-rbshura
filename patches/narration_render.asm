; -----------------------------------------------------------------------------
; narration_render.asm — post-intro-scroll character-narration screens as
; HALF-WIDTH, RENDER-AT-ONCE text. Ported from Peacekeepers (the official EN
; release of this game), pk-disassembly-alpha/peacekeepers_bank45.asm CODE_45CBAF.
; -----------------------------------------------------------------------------
; rbshura's `fadeScreenIn` ($05:F18C) renders the $1F:C57F idx-1-19 character
; screens by DMAing FULL-WIDTH (8x16, 2 tiles wide) glyph tiles from the kana
; font in bank $D0. The EN PK Latin font overwrote that region -> garbled.
;
; Peacekeepers solved this by keeping the SAME glyph-DMA loop but reading the
; stream as HALF-WIDTH text:
;   - 1-byte char index per glyph (not a 2-byte tile src), $FF terminator
;   - src = index * (font slot size); DMA 1 tile top + 1 tile bottom (8x16)
;   - dest advance +$08 words (one tile column) instead of +$10
; It is still a tight DMA loop = render-at-once (no typewriter), exactly as
; desired. PK uses *32 (its font is 32 B/glyph); our PK font is laid out in
; 64 B slots (top tile @ +0, bot tile @ +$10, +$20..$3F pad), so we use *64.
;
; The $00C9 render dispatch at $05:F182 is UNTOUCHED (no Site A/B). Only the
; $00C9!=4 branch target ($05:F18C, fadeScreenIn) is replaced. The intro main
; scroll (part1/part2) renders via the $00C9==4 path and is unaffected. The
; idx-1-19 screens are the SAME content whether shown after the intro scroll or
; later, so converting this one renderer fixes every showing.
;
; Bank $05 has no >128 B free run, so the routine is relocated to bank $E0 and
; called as a JSL subroutine. JSL/RTL preserves the caller's PBR (the engine
; runs at PBR=$85); a cross-bank JML return would shift PBR to $C5 and risk
; later PHK/PLB landing DBR in ROM. The internal DBR=$DF/ambient juggling is
; kept verbatim from the original: $DF for the ($00),Y stream reads, ambient
; (a register-mapping bank) for the $21xx/$43xx/$420B DMA writes.
; -----------------------------------------------------------------------------

hirom

!FONT_BANK = $00D0          ; PK font source bank (file $100000 = $D0:0000)

; =========================================================================
; Entry hook: replace fadeScreenIn ($05:F18C, the $00C9!=4 dispatch target)
; with `JSL renderer / JMP processPlayerMovement`. The original 165-byte
; glyph-DMA routine ($F18C-$F230) becomes dead code (no external refs;
; processPlayerMovement at $F231 is preserved and reached here). 7 bytes.
; =========================================================================
org $C5F18C
    JSL NarrationHalfWidth
    JMP $F231                   ; processPlayerMovement (shared continuation)

; =========================================================================
; Relocated half-width text renderer (bank $E0 carved hole; see project.toml
; freespace split). Faithful copy of fadeScreenIn with PK's loop body.
; Entry: DBR = ambient (engine default, a register-mapping bank). A/X/Y per
; the dispatch (mixed; we set widths explicitly).
; =========================================================================
org $E0DC91
NarrationHalfWidth:
    REP #$20
    LDA #$40C4
    STA $0320                   ; sprite/DMA descriptor base (unchanged from orig)
    LDX $1E94                   ; screen index*2 into $1F:C57F

    ; --- read screen pointer: $1F:C57F[$1E94] -> $00 ---
    SEP #$20
    PHB
    LDA #$DF
    PHA
    PLB                         ; DBR = $DF (bank $1F) for table read
    REP #$20
    LDA $C57F,X
    PLB                         ; restore ambient DBR
    STA $00
    LDY #$0000

    ; --- read initial VRAM dest word -> $02 ---
    SEP #$20
    PHB
    LDA #$DF
    PHA
    PLB
    REP #$20
    LDA ($00),Y
    PLB
    INY
    INY
    STA $02

.loop:
    ; --- read one 1-byte char index (PK-style) ---
    SEP #$20
    PHB
    LDA #$DF
    PHA
    PLB                         ; DBR = $DF for stream read
    LDA ($00),Y                 ; 8-bit char index (M=8)
    PLB                         ; restore ambient DBR
    CMP #$FF
    BNE .chk_fe
    JMP .done                   ; $FF = end of screen (JMP: .done is out of BEQ range)
.chk_fe:
    CMP #$FE
    BNE .render
    JMP .newpos                 ; $FE = reposition: next 2 bytes are a new dest
.render:
    INY                         ; advance 1 byte (not 2)
    XBA                         ; A_hi = index
    LDA #$00                    ; A_lo = 0  (8-bit)
    REP #$20                    ; A = index*256
    LSR A                       ; index*128
    LSR A                       ; index*64  (our 64 B font slots)
    STA $04                     ; $04 = font byte offset (src)

    ; --- DMA top tile: $D0:src -> VRAM[$02], 1 tile (16 B) ---
    LDA $02
    STA $2116
    STZ $420B
    LDA #$0001
    STA $4300                   ; DMAP0 = 1 (2-byte unit), BBAD0 low byte
    LDA #$0018
    STA $4301                   ; BBAD0 = $18 ($2118 VRAM data)
    LDX #$0000
    STX $4302                   ; A1T0 low/high
    LDA #!FONT_BANK
    STA $4304                   ; A1B0 = $D0 (font bank)
    LDX #$0010
    STX $4305                   ; DAS0 = $10 (16 B = 1 tile) -- HALF-WIDTH
    LDA $04
    STA $4302                   ; A1T0 = src
    LDA #$0001
    STA $420B                   ; trigger DMA ch0

    ; --- DMA bottom tile: $D0:src+$10 -> VRAM[$02+$100] ---
    LDA $02
    CLC
    ADC #$0100                  ; +$100 words = one tilemap row below
    STA $2116
    LDA $04
    CLC
    ADC #$0010                  ; bottom tile @ src+$10 (our slot layout)
    STA $4302
    LDA #$0010
    STA $4305                   ; size 16 B
    LDA #$0001
    STA $420B

    ; --- advance VRAM dest by one half-width column ($08 words) ---
    LDA $02
    CLC
    ADC #$0008                  ; HALF-WIDTH advance (was +$10 full-width)
    BIT #$0100
    BEQ .nowrap
    CLC
    ADC #$0100                  ; row-boundary fixup (skip the bot-tile row)
.nowrap:
    STA $02
    JMP .loop

; --- $FE reposition: read the next 2 bytes as an absolute VRAM dest -> $02.
;     Lets the build place each line of text at its own row/column (line
;     breaks + per-line indent). M=8 on entry (from the byte read). ---
.newpos:
    INY                         ; skip the $FE byte
    PHB
    LDA #$DF
    PHA
    PLB                         ; DBR = $DF for the dest read
    REP #$20
    LDA ($00),Y                 ; new dest word
    PLB
    INY
    INY
    STA $02
    JMP .loop

.done:
    RTL                         ; DBR restored to ambient; PBR preserved by JSL
