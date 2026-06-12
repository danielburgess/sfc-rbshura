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

!FONT_BANK = $00E2          ; relocated EN+PT font ($E2:0000 = file $220000).
                            ; Was $00D0 ($100000); moved so the 13 Brazilian-
                            ; Portuguese accents (slots 0x4C..0x58) fit past the
                            ; full 80-slot region. See patches/font_reloc.asm.

; =========================================================================
; Entry hook: replace the fadeScreenIn entry ($05:F18C, the $00C9!=4 render
; dispatch target) with a JML to NarrationGate. fadeScreenIn is the GENERIC
; screen renderer (reads $1F:C57F[$1E94] and DMAs the screen) — used by the
; intro-narration screens AND by gameplay/other screens. The original hook
; replaced it WHOLESALE (`JSL renderer / JMP processPlayerMovement`), so the
; half-width PK renderer hijacked EVERY screen, corrupting the in-game BG
; (the stage-1 wall). NarrationGate restores the original fadeScreenIn for
; non-narration screens and only runs our renderer for narration (idx 1-19).
; 7 bytes (JML + 3 NOP pad), same footprint as the old hook.
; =========================================================================
org $C5F18C
    JML NarrationGate
    NOP : NOP : NOP             ; pad to the original 7-byte footprint

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

    ; --- DMA top tile: !FONT_BANK:src -> VRAM[$02], 1 tile (16 B) ---
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
    STA $4304                   ; A1B0 = !FONT_BANK ($E2, extended EN+PT font)
    LDX #$0010
    STX $4305                   ; DAS0 = $10 (16 B = 1 tile) -- HALF-WIDTH
    LDA $04
    STA $4302                   ; A1T0 = src
    LDA #$0001
    STA $420B                   ; trigger DMA ch0

    ; --- DMA bottom tile: !FONT_BANK:src+$10 -> VRAM[$02+$100] ---
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

; Build-time guard: stub must stay within its 256 B reservation
; ($20DC91..$20DD91; project.toml freespace resumes at $20DDD0 = $E0:DDD0).
assert pc() <= $E0DD91, "NarrationHalfWidth overflowed its 256B reservation ($E0DD91)"

; =========================================================================
; NarrationGate — gate the half-width renderer to the NARRATION SCREENS only.
; fadeScreenIn ($05:F18C) is the generic screen renderer for the $00C9!=4
; render path, reached by gameplay too; the un-gated hook hijacked it and
; corrupted the in-game BG. The narration screens are $1F:C57F idx 1-19; the
; renderer indexes that table with $1E94, so idx 1-19 => $1E94 $02..$26.
;   - narration ($1E94 in $02..$26): run NarrationHalfWidth, continue to
;     processPlayerMovement ($F231) exactly as the old hook did.
;   - everything else (intro part1 idx 0, intro part2/screens idx 20-44,
;     gameplay): fall through to the ORIGINAL fadeScreenIn body at $F194.
; Entry (via the JML hook): PBR=$E0, DBR=$85 (set by processGameMode's
; PHK/PLB, so $1E94 reads WRAM), M=8, X=16. We REP #$20 for the 16-bit index
; compare, then JML the continuation back to PBR=$85 (the engine bank) so any
; later PHK/PLB keeps DBR on the $85 WRAM-mirror, NOT $C5 (pure ROM). There is
; no PHK between fadeScreenIn entry and processPlayerMovement, so the bank flip
; is otherwise transparent (same ROM data via the mirror).
; =========================================================================
org $E0DD91
NarrationGate:
    REP #$20
    LDA $1E94                   ; screen index (DBR=$85 -> WRAM $1E94)
    CMP #$0002
    BCC .original               ; idx 0 (intro part1) / low -> not narration
    CMP #$0028
    BCS .original               ; idx 20+ (intro part2 / gameplay) -> not narration
    ; --- narration screen (idx 1-19): half-width render-at-once ---
    JSL NarrationHalfWidth
    JML $85F231                  ; processPlayerMovement (old hook continuation)
.original:
    ; --- replicate fadeScreenIn's entry (REP #$20 already done) then continue ---
    LDA #$40C4
    STA $0320
    JML $85F194                  ; original fadeScreenIn body (LDX $1E94 ...)

assert pc() <= $E0DDD0, "NarrationGate overflowed its reservation ($E0DDD0)"
