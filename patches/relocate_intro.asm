; -----------------------------------------------------------------------------
; Relocate intro narrative bank: $DF → $E0
; -----------------------------------------------------------------------------
; The intro/story-screen renderer at SNES $85:F010 reads its text from
; DBR:$00:$01 + Y. DBR is hardcoded to $DF (HiROM mirror of bank $1F) by:
;
;   $05:F023: 8B          PHB           ; save current DBR
;   $05:F024: A9          LDA #imm      ; opcode
;   $05:F025:    DF       (immediate)   ; ← the byte we patch ($DF → $E0)
;   $05:F026: 48          PHA
;   $05:F027: AB          PLB           ; DBR = $E0 after patch
;
; By flipping the immediate from $DF to $E0, the renderer reads from
; bank $E0 instead — putting the intro text in the expansion-bank
; freespace pool (file $200000+) and leaving the original $1F:C8F1 /
; $1F:CD35 ROM space untouched (which is where the JP source lives).
;
; The low-16 text-pointer values in $7E:1E9F ($C8F1 and $CD35) stay the
; same — we just relocate the SAME relative offsets into a different
; bank. tables/intro.toml writes the encoded text at file $20:C8F1 /
; $20:CD35; project.toml carves that region out of [rom.build].freespace
; so no other section claims it.
;
; For real "more room" growth beyond the original 1092+746 budget, we'd
; ALSO need to patch the code that sets $7E:1E9F to use new offsets —
; that's a follow-up if the EN translation outgrows the original gap.
; -----------------------------------------------------------------------------

hirom

org $C5F025 : db $E0
