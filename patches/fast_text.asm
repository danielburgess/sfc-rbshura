; -----------------------------------------------------------------------------
; Rushing Beat Shura — Fast Text Patch (iteration 1: wait-gate bypass only)
; -----------------------------------------------------------------------------
; This is the minimal version — just bypass the per-character wait gate.
; No multi-char-per-call additions. If iteration 1 is insufficient, iteration 2
; layers 4 extra JSR $80FE calls at $058045 on top of these two NOP edits.
;
; Original dispatcher logic at $05:8055..$05:8067:
;
;     $058055:  AD 46 1C   LDA $1C46     ; load wait counter
;     $058058:  D0 09      BNE $8063     ; nonzero → skip the JSR (skip fetch)
;     $05805A:  A9 01 00   LDA #$0001
;     $05805D:  8D 56 1C   STA $1C56
;     $058060:  20 FE 80   JSR $80FE     ; fetch next char
;     $058063:  C2 20      REP #$20
;     $058065:  CE 46 1C   DEC $1C46     ; decrement counter
;
; Patch — two NOP-outs:
;
;   1. `BNE $8063` at $058058  →  `NOP NOP`
;      Always fall through to JSR $80FE (always fetch).
;
;   2. `DEC $1C46` at $058065  →  `NOP NOP NOP`
;      Prevent underflow churn after the renderer's STA $1C46 (from $1C44).
;
; $1C44/$1C46/$1CAC are still written by FC.01/F8/renderer, but the wait
; gate that reads $1C46 is no longer effective. Holding B for "fast text"
; was via $058052 STZ $1C46 — still wired but redundant.

hirom

; 1. Wait-gate at $05:8058 — BNE $8063 → NOP NOP
org $C58058
    db $EA, $EA

; 2. Counter decrement at $05:8065 — DEC $1C46 → NOP NOP NOP
org $C58065
    db $EA, $EA, $EA
