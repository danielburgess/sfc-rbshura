; -----------------------------------------------------------------------------
; Rushing Beat Shura — scen 28 cutscene-script L1-advance handshake fix
; -----------------------------------------------------------------------------
; Scen 14 (the ending) is driven by a frame-by-frame script player at $85:EDDF.
; It advances the renderer's L1 entry pointer ($1C48) on a per-step timer that
; was tuned to JP text length. EN text runs longer, so the advance fires before
; the renderer finishes the current entry.
;
; THE REAL HANDSHAKE (RE'd from SplitTrace 20260523_010824):
;   * Renderer signals "entry complete / idle" by setting $1C56 = $FFFF
;     (end-of-L3 handler at $05:8116 / $05:815D). The renderer prologue
;     ($05:8032: LDA $1C56 / BMI) reads $1C56's LOW byte 8-bit and idles when
;     bit7 is set ($FF).
;   * The PROPER L1-advance (bank-$04 gameplay path) always pairs the write
;     with a sentinel clear so the renderer re-engages for the new entry:
;         $04:AADE  STA $1C48 / STZ $1C56
;         $04:F015  LDA #$0012 / STA $1C48 / STZ $1C56
;   * The cutscene script player's $1C48 write at $85:EE85 does NOT clear
;     $1C56. So once an entry finishes ($1C56=$FFFF), the bare write advances
;     L1 but leaves the renderer idle → next entry never renders.
;
; Trace evidence (entry 22 → 23, $1C56 stuck at $FFFF after advance):
;   snap : $1C48  $1C4A  $1C56
;    s1  :  $24    39     1      (entry 22 rendering)
;    s2  :  $24    70     1      (still rendering)
;    s3  :  $26     0    $FFFF   (advanced, but renderer idle → blank box)
;    s4  :  $26     0    $FFFF
;    s5  :  $26     0    $FFFF
;
; FIX: hook the $1C48 write at $85:EE85. For $1C48 writes, gate on the
; done-sentinel — only advance when $1C56 indicates "entry complete"
; ($1C56 low byte negative, i.e. $FF). On advance, do STA $1C48 AND STZ $1C56
; (16-bit) to re-engage the renderer, exactly like the bank-$04 path. When the
; renderer is still busy ($1C56 low byte >= 0), skip the write and retry next
; frame. The ending FADE-OUT trigger ($00D5=$01) is gated the SAME way (added
; 2026-05-24) so the fade waits for the line to finish — but, unlike $1C48, it
; does NOT clear $1C56 (there is no new entry to render). All other writes
; (portrait / OAM / animation coordinates) pass through untouched, preserving
; their original timing.
;
; The $1C56 sentinel is self-limiting: STZ-ing it on advance means the gate
; blocks further advances until the renderer renders the new entry AND finishes
; it (end-of-L3 → $1C56=$FFFF again). Exactly one advance per entry completion.
;
; History of failed attempts (see memory/project_wram_resident_scenarios.md):
;   * $EE36 broad gate on $1C4A==0: froze concurrent animation steps → corrupt.
;   * $EE85 surgical gate on $1C4A==0: $1C4A==0 is a multi-frame window so
;     advances slipped through (skips); AND a stack bug (STA $01,S after PHA
;     without PLA) made the stall path fall to $EE8A, advancing the script
;     slot without writing $1C48 → entries dropped.
;
; See memory/reference_cutscene_script_player.md for the script-player format.
; -----------------------------------------------------------------------------

hirom

; =========================================================================
; 1. Patch $85:EE85 — replace (STA $00,X / JMP $EE65) with JSL into the stub.
; =========================================================================
;
; Original ($85:EE85..$85:EE89, 5 bytes):
;   $EE85: 95 00       STA $00,X        ; write value byte to DP+X (X=target)
;   $EE87: 4C 65 EE    JMP $EE65        ; back to write-loop top
;
; After patch (5 bytes):
;   $EE85: 22 00 E0 E0 JSL StallCheck
;   $EE89: EA          NOP
;
; JSL pushes return = $EE88 ($85). Stub rewrites the stacked return to:
;   $EE64 → RTL+1 = $EE65 (continue write loop)
;   $EEB5 → RTL+1 = $EEB6 (bail / stall — retry next frame)

org $C5EE85
    JSL StallCheck
    NOP

; =========================================================================
; 2. StallCheck stub at $E0:E000 (carve-out: project.toml $20E000..$20E040).
; =========================================================================
;
; On entry (from $85:EE85, just after the value-byte load at $EE81):
;   M=1 (A 8-bit) = value byte to write; X (16-bit) = target address;
;   DBR=$85 ($00-$1FFF mirrors WRAM); D=0.
;   Stack: [PCL=$88][PCH=$EE][PB=$85], S→PCL.
;   IMPORTANT: after PHA, the return PC is at $02,S — every path PLAs to
;   restore S→PCL BEFORE touching $01,S, so the return rewrite is correct.

org $E0E000
StallCheck:
    PHA                     ; save value byte; stack now [val][PCL][PCH][PB]
    REP #$20
    TXA                     ; A = target address (16-bit)
    CMP #$1C48              ; is this the L1-step (entry) advance?
    BEQ .gated
    CMP #$00D5              ; is this the ending FADE-OUT trigger ($00D5=$01)?
    BEQ .gated              ;   (gate it too — fade must wait for the line)
    SEP #$20

    ; --- not gated: original write, continue loop ---
    PLA                     ; restore value; S→PCL
    STA $00,X
    BRA .ret_loop

.gated:                     ; X = $1C48 (advance) or $00D5 (fade). A 16-bit here.
    SEP #$20                ; M=8
    LDA $1C56               ; done-sentinel, low byte (8-bit)
    BMI .do_write           ; bit7 set ($FF) = renderer idle/complete → write
    ; --- renderer still busy: skip write, retry next frame ---
    PLA                     ; restore S→PCL (discard value)
    STZ $1E95               ; $1E95=0 → next frame re-enters this step.
                            ; Both gated targets are the FIRST write of their
                            ; step ($1C48 is a lone slot; $00D5 leads the fade
                            ; step), so the retry re-runs cleanly with nothing
                            ; half-applied.
    REP #$20
    LDA #$EEB5
    STA $01,S               ; RTL+1 → $EEB6 (bail)
    SEP #$20
    RTL

.do_write:
    PLA                     ; value; S→PCL
    STA $00,X               ; perform the gated write ($1C48 or $00D5)
    REP #$20
    TXA
    CMP #$1C48              ; only the ENTRY advance re-engages the renderer;
    SEP #$20
    BNE .ret_loop           ; the FADE ($00D5) leaves $1C56=$FFFF (no new entry
                            ; to render — clearing it would stall later writes).
    REP #$20
    STZ $1C56               ; $1C48 path: clear sentinel (16-bit) → re-engage
    SEP #$20
    ; fall through to .ret_loop

.ret_loop:
    REP #$20
    LDA #$EE64
    STA $01,S               ; RTL+1 → $EE65 (continue write loop)
    SEP #$20
    RTL

; =========================================================================
; End. Stub ~$E0:E000..~$E0:E04x. project.toml reserves $20E000..$20E080
; (freespace line for $E0 resumes at $20E080 — keep them in sync if the stub
; grows). $00D5-gating added 2026-05-24: the ending fade-out (scen28_timing
; $DFB36C, shared across slots $308/$31A/$514) was firing on its JP-tuned wait
; while longer EN lines (e.g. entry 33 "Bart sent me packing…", entries 50/51)
; were still typing → screen cut to black mid-line. Now the fade waits for the
; same $1C56=$FFFF done-sentinel as the entry advance.
; CAUTION: this gates EVERY $00D5=$01 in the scen-28 script. It assumes each
; fade is preceded by text that completes (sets $1C56=$FFFF). If a text-less
; fade segment ever hangs, exclude it by value/context here.
;
; FIRST-ENTRY NOTE: if the very first dialog line of scen 28 (entry 0) fails
; to render, it means $1C56 is not $FFFF at dialog start so the first advance
; stalls forever. The fix would be a one-time `STZ`/`$FFFF`-init of $1C56 at
; scene setup. Trace evidence covers entries 22-23 only; entry 0 untested.
; =========================================================================
