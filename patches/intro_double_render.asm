; -----------------------------------------------------------------------------
; intro_double_render.asm — match PK's "2 chars per outer invocation" cadence
; -----------------------------------------------------------------------------
; PK's intro outer driver at $05:CA20-$CA2C is structured as:
;
;   $CA23  EE 30 05       INC $0530           ; HDMA-driven scroll-Y += 1
;   $CA26  20 2D CA       JSR Renderer         ; render char 1
;   $CA29  20 2D CA       JSR Renderer         ; render char 2
;   $CA2C  60             RTS
;
; rbshura's equivalent at $05:EFEC-$F08C is byte-identical except it FALLS
; THROUGH into the renderer once (instead of JSRing twice). That cuts the
; per-frame typewriter throughput in half — exactly what makes the
; typewriter visible to the player.
;
; SplitTrace from PK confirmed: 102 hits of the renderer entry in trace_002
; matches the 102 chars rendered between snap 2 and snap 3 (Y went 18 → 120),
; with every active frame showing exactly 2 hits.
;
; This patch:
;   1. Copies rbshura's per-char renderer (originally inline at $05:EFFD-$F08B)
;      into bank-$08 freespace as a JSL-callable routine (RTL-terminated).
;      The DMA-descriptor constants from the previous intro_pk_dma.asm patch
;      are baked in (transfer size $10, +$10 bot-tile offset, +$08 per-char
;      VRAM dest advance) — see comments inline.
;   2. Replaces the original inline prologue at $05:EFFD-$F005 (9 bytes) with
;      `JSL NewRenderer / JSL NewRenderer / RTS` (9 bytes exactly).
;   3. Leaves $05:F006-$F08C orphaned (unreached, untouched). Verified: no
;      external caller targets that range (single false-positive in bank-$05
;      sprite data is byte-identical to PK and not code).
;
; Supersedes patches/intro_pk_dma.asm — disable that section in project.toml.
;
; Net change: typewriter throughput doubles to match PK's measured ~12
; chars/sec. The existing BG3VOFS HDMA scroll (channel 7 → $7E:0530,
; configured identically to PK at $1F:DFC1+) keeps incrementing once per
; outer invocation via the unchanged `INC $0530` at $05:EFFA.
; -----------------------------------------------------------------------------

hirom

; -----------------------------------------------------------------------------
; NewIntroRenderer @ $C8:7080 — RTL-callable copy of rbshura's per-char render
; (the $05:EFFD-$F08B sequence, with intro_pk_dma.asm constants baked in).
;
; Inputs (via WRAM, set up by surrounding driver state):
;   $7E:0F22  staging-buffer cursor (X reloaded from here)
;   $7E:1E9B  text Y cursor (Y reloaded from here)
;   $7E:1E9F  text source pointer (low+high; DBR=$DF supplies bank $1F)
;   $7E:1E9D  current VRAM tile-slot destination (word address)
;   $7E:0002  mode-flags ORed into tile_num
;   $7E:0003  kanji-mode flag (set by FE escape)
;
; Outputs: stages 2 DMA-descriptor records (top + bot tile) at $0E22+X for
; one character, advances X by $10 (in $0F22), advances Y by 1 or 2 (kanji),
; updates $1E9D for the next char. Returns via RTL.
; -----------------------------------------------------------------------------
org $C87080
NewIntroRenderer:
    SEP #$20                ; M=1 (8-bit A)
    LDA #$00 : XBA          ; A_hi = 0 (cleared for the later byte<<8 trick)
    LDX $0F22               ; X = staging-buffer cursor
    LDY $1E9B               ; Y = text cursor

    LDA #$80
    STA $0E22,X             ; VMAINC for record 0
    STA $0E2A,X             ; VMAINC for record 1
    LDA #$D0
    STA $0E25,X             ; DMA src bank for record 0 = $D0 (PK font)
    STA $0E2D,X             ; DMA src bank for record 1 = $D0

    REP #$20                ; M=0 (16-bit A)
    LDA $1E9F
    STA $00                 ; DP $00 = text low-word ptr
    STZ $02                 ; DP $02 = 0 (mode-flag accumulator init)
    SEP #$20                ; M=1

.read_byte:
    PHB
    LDA #$E0                ; DBR = $E0 (relocated intro narrative bank, was $DF)
                            ; — formerly patched in by relocate_intro.asm at
                            ; $05:F025. The orphaned bytes at $05:F006-$F08B
                            ; still receive that 1-byte patch but the code is
                            ; unreached; the live path is here and bakes in
                            ; the $E0 directly.
    PHA : PLB
    LDA ($00),Y             ; read 1 byte from text (from bank $E0)
    PLB                     ; restore caller's DBR
    CMP #$FF
    BEQ .done               ; FF = end of text
    CMP #$FE
    BNE .render             ; non-FE → render this byte
    LDA #$40
    STA $03                 ; flag kanji mode
    INY                     ; advance past FE
    JMP .read_byte          ; (mirrors original JMP $F023 — re-reads next byte)

.render:
    XBA                     ; A_hi <- byte (A_lo was 0)
    LDA #$00                ; A_lo = 0 → 8-bit A = $00, but with M=1
    REP #$20                ; M=0 → A = (A_hi<<8) | A_lo = byte * 256
    LSR : LSR               ; A = byte * 64 (matches PK font 64-B slots)
    ORA $02                 ; OR in mode flags
    STA $0E23,X             ; record 0 DMA src low+high

    CLC : ADC #$0010        ; +$10 bytes (PK bot tile starts at glyph+16)
    STA $0E2B,X             ; record 1 DMA src

    LDA #$0010              ; transfer size = 16 B = 1 tile of 2bpp
    STA $0E26,X
    STA $0E2E,X

    LDA $1E9D               ; current VRAM dest (word)
    STA $0E28,X             ; record 0 dest
    CLC : ADC #$0100        ; +$100 words = +$20 tile slots = next tilemap row
    STA $0E30,X             ; record 1 dest

    TXA                     ; A = X (staging cursor)
    CLC : ADC #$0010
    STA $0F22               ; advance staging-buffer end pointer by $10

    INY                     ; advance text cursor
    STY $1E9B

    LDA $1E9D
    CLC : ADC #$0008        ; +1 tile per char (PK font is 8-wide, not 16)
    BIT #$0100
    BEQ .skip_wrap          ; no row wrap
    CLC : ADC #$0100        ; cross-row wrap: skip the bot-tile row we used
    CMP #$4000
    BCC .skip_wrap          ; not past VRAM end
    SEC : SBC #$2000        ; VRAM wrap

.skip_wrap:
    STA $1E9D

.done:
    RTL                     ; long return (called via JSL)

; -----------------------------------------------------------------------------
; Outer driver patch — make rbshura's outer at $05:EFFA-$F005 emit two
; renderer calls instead of falling through once. The pre-existing
; `INC $0530` at $05:EFFA stays untouched (PK has the same instruction at
; $05:CA23). We overwrite $05:EFFD-$F005 (the original 9-byte prologue) with
; `JSL NewRenderer / JSL NewRenderer / RTS` = 9 bytes.
;
; Bytes at $05:F006-$F08B become orphaned but harmless — verified no external
; same-bank or cross-bank caller lands there. The RTS at $05:F08C is preserved
; because the alt-path at $EFEC/$EFF7 (`JMP $F08C`) still uses it.
; -----------------------------------------------------------------------------
org $C5EFFD
    JSL NewIntroRenderer    ; render char #1   (4 bytes)
    JSL NewIntroRenderer    ; render char #2   (4 bytes)
    RTS                     ; return to caller (1 byte)
; total = 9 bytes, exactly fills $EFFD-$F005.
