; -----------------------------------------------------------------------------
; Rushing Beat Shura — ending narration -> half-width text renderer (option a)
; -----------------------------------------------------------------------------
; FIRST IMPLEMENTATION — needs in-emulator verification at the ending (see
; docs/ending_narration_plan.md "Verification"). Builds clean; gated to scen 14.
;
; The 4 character-ending narration screens ($1F:C57F idx 1-19) render via the
; full-width glyph-DMA path (`fadeScreenIn`), reading glyph tiles from the kana
; font region the EN PK font overwrote -> garbled. This re-routes them to the
; HALF-WIDTH text renderer used by the intro/dialog, keeping the narration in
; its native $00C9=2 phase (cutscene progression untouched: both render paths
; set $1E96 from $DFAAA4[$1E94] identically).
;
; Two hooks (RE in docs/ending_narration_plan.md):
;
; SITE B — once-per-screen render dispatch ($85:F182):
;   orig: LDA $00C9 / CMP #$04 / BNE $F18C(glyph) / JMP $F2A3(text setup)
;   `fadeScreenIn`($F18C) is narration-only and only $1F:C57F screens reach
;   here (intro idx0/20+ already take $00C9==4 -> $F2A3; ending idx1-19 are all
;   narration). So unconditionally take the text-setup path $F2A3 (which does
;   the Site-2 setup: $1E9F/$1E9B/$1E9D from $C57F[$1E94], $1E96 from $AAA4).
;
; SITE A — per-frame mode dispatch ($85:EDFC, the $00C9=2,3 branch -> $EE30):
;   $EE30 orig: JMP $EF24 (handleMode4Logic = narration per-frame state, NO
;   render). Redirect to a trampoline that ALSO invokes the per-frame text
;   render ($EFA8, paced internally by $1E02&3 = typewriter) before the state
;   logic. Gated on scen 14 ($00D0==$1C) so other scenarios at $00C9=2,3 are
;   unaffected.
;
; Trampoline lives at $05:F006 (orphaned by intro_double_render.asm: the old
; inline renderer prologue $05:F006-$F08B, ~134 B free, same bank as the JSR/JMP
; targets so no cross-bank issue).
; -----------------------------------------------------------------------------

hirom

; =========================================================================
; SITE B — force the once-per-screen render to the text-setup path.
; $85:F182 = file $05F182 = $C5:F182. Replace the 10-byte dispatch
; ($F182..$F18B: LDA $00C9 / CMP #$04 / BNE $F18C / JMP $F2A3) with an
; unconditional JMP $F2A3 + NOP pad. M=8 here (SEP #$20 at $F17D), which
; $F2A3 (updateTimerDisplay) expects.
; =========================================================================
org $C5F182
    JMP $F2A3
    NOP : NOP : NOP : NOP : NOP : NOP : NOP   ; pad to $F18C (fadeScreenIn now unreachable)

; =========================================================================
; SITE A — redirect the $00C9=2,3 per-frame target ($EE30) to the trampoline.
; $85:EE30 = file $05EE30 = $C5:EE30. Orig: 4C 24 EF (JMP $EF24).
; =========================================================================
org $C5EE30
    JMP NarrationPerFrame          ; 4C 06 F0

; =========================================================================
; Trampoline at $05:F006 (orphaned region). M=8, X/Y=16 on entry (from the
; processGameMode dispatch: SEP #$20 / REP #$10). $00D0 = scen*2 (WRAM via
; DBR=$85 $0000-$1FFF mirror). For scen 14 ($1C) run the text render, then
; fall through to the original handleMode4Logic ($EF24) for state/timing.
; =========================================================================
; Gate on $1E9F (the current screen pointer, set by Site B) being in the
; NARRATION range [$C5D9..$C883]. $00D0 is NOT reliable (it varies per
; ending: ELFIN=$00, KYTHRING=$1C — verified via SplitTrace 2026-05-23).
; Intro screens ($1E9F=$C8F1/$CD35) and non-narration scenes fall outside the
; range and skip the render (just the original handleMode4Logic state).
org $C5F006
NarrationPerFrame:
    REP #$20
    LDA $1E9F                      ; current screen pointer (16-bit)
    CMP #$C5D9 : BCC .skip         ; below narration block → not narration
    CMP #$C884 : BCS .skip         ; at/above intro ($C8F1) → not narration
    SEP #$20
    JSR $EFA8                      ; per-frame half-width text render (paced $1E02&3)
    JMP $EF24                      ; original: handleMode4Logic (narration state)
.skip:
    SEP #$20
    JMP $EF24

; =========================================================================
; TEST PLAN (docs/ending_narration_plan.md): build, load to the ending,
; confirm each character ending renders the (still-JP until translated)
; narration via the half-width PK renderer with correct typewriter + position,
; and that the ending still progresses/transitions normally. Risks to watch:
;   - $EFA8 may have $00C9-dependent behavior (it's normally entered at
;     $00C9=4,5); if it misbehaves at $00C9=2, gate it further or branch into
;     resetLevelState directly.
;   - screen position/layout (text renderer self-positions vs glyph-DMA dests).
;   - $1E9F/$1E9B must be set by SITE B before the first render frame.
; After it renders correctly, wire the EN TEXT via tables/intro.toml (idx 1-19
; fields + ptr_writes -> $E0) and translate data/en/narration.txt.
; =========================================================================
