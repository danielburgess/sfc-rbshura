; -----------------------------------------------------------------------------
; intro_skip.asm — press START on the RUSHING BEAT / JALECO splash screens to
; skip straight to the main title.
; -----------------------------------------------------------------------------
; The splash screens are shown by SEQUENTIAL boot code (not the $00C8 phase
; machine), via frame-count dwells: `LDX #N / loop: JSR WaitForVBlankStart /
; DEX / BNE`. WaitForVBlankStart ($80:DC32) busy-waits one vblank on $4210.
; During these waits $4200=0 — NMI AND auto-joypad are OFF — so the game never
; reads the controller here (these screens never had input). The SPC music
; upload uses its OWN $2140-handshake waits (NOT WaitForVBlankStart), so it is
; unaffected by this hook and still completes.
;
; We hook WaitForVBlankStart: on each call during the splash ($00C8==0) we do a
; manual controller-1 read of $4016 (clean — NMI is off here, so no collision
; with the NMI's own joypad strobing). If START is down we SKIP the vblank wait
; and return immediately. With START held, every dwell's WaitForVBlankStart
; returns instantly, so the boot fast-forwards through the splash screens to the
; title (which the game reaches naturally once the dwells collapse). The $00C8==0
; gate stops the skip at the title (phase 2) and in gameplay.
;
; Hook: replace the WaitForVBlankStart entry (`PHP / SEP #$20 / LDA $4210` —
; bytes 08 E2 20 AD at $80:DC32-DC35) with `JML WaitVBHook`. The stub redoes
; PHP/SEP, does the input check, then either skips or replicates the original
; vblank wait, and JMLs to the original PLP/RTS at $80:DC42 to return to caller.
; -----------------------------------------------------------------------------

hirom

org $C0DC32
    JML WaitVBHook          ; replaces PHP / SEP #$20 / LDA-opcode (08 E2 20 AD)

org $E1A310
WaitVBHook:
    PHP                     ; (replaced PHP)
    SEP #$20                ; (replaced SEP #$20)
    LDA.L $7E00C8           ; master phase (WRAM; DBR-independent)
    BNE .dowait             ; not the splash (phase != 0) -> normal vblank wait
    ; manual controller-1 read ($4016 bit0). NMI off during boot waits = clean.
    LDA #$01 : STA $4016    ; latch controllers
    STZ $4016               ; release -> serial data ready
    LDA $4016              ; bit0 = B
    LDA $4016              ; bit0 = Y
    LDA $4016              ; bit0 = Select
    LDA $4016              ; bit0 = START
    AND #$01
    BNE .done              ; START down -> skip this wait (collapse the dwell)
.dowait:
    LDA $4210 : BMI .dowait ; WaitForVBlankEnd  (wait while vblank flag set)
.dowait2:
    LDA $4210 : BPL .dowait2 ; WaitForVBlankActive (wait until vblank flag set)
    LDA $4210
.done:
    JML $80DC42            ; original PLP / RTS -> return to caller (bank $80)

assert pc() <= $E1A360, "WaitVBHook overflowed its reserved slot"
