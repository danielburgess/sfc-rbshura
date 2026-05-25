; -----------------------------------------------------------------------------
; intro_dest_bank.asm — finish the intro/ending narrative relocation.
; -----------------------------------------------------------------------------
; The intro/ending story text (intro.txt part1 + part2) was relocated to bank
; $E0 (tables/intro.toml [data].offset $20C8F1). patches/intro_double_render.asm
; flipped the RENDERER's text-read DBR to $E0 so the glyph bytes come from the
; relocated copy. But the engine's text-SETUP — at $05:F309-F345, the $00C9==4
; path that reads each block's leading VRAM-dest word into $1E9D — was left
; reading from bank $1F (DBR=$DF). Three DBR-load blocks live there:
;
;   $05:F30F  LDA #$DF  → reads the pointer table  $C57F,X   (stays in $1F)
;   $05:F324  LDA #$DF  → reads the dest word  ($1E9F),Y=0   (← must be $E0)
;   $05:F338  LDA #$DF  → reads the progression $AAA4,X       (stays in $1F)
;
; Because the setup read the dest from $1F, it only worked for part1 (idx 0):
; part1's offset never moved, so $1F:C8F1 still held a valid dest ($2020).
; part2 (idx 20-44) was repointed by tables/intro.toml's ptr_writes from the
; JP offset $CD35 to the relocated $D110, so the setup read $1F:D110 = $B3A0
; (unrelated JP bytes) instead of part2's intended dest $2010. That garbage
; dest base made the Maria ending (part2) lap VRAM and fill the screen with
; garbage glyph tiles.
;
; Fix: flip ONLY the dest-word read's DBR operand to $E0, so the dest comes
; from the SAME relocated data as the text. Each block's leading 2-byte word
; (skipped by the renderer, which starts at Y=2) is now the authoritative VRAM
; dest and travels with the data — robust to future text edits.
;
; Canary: data/en/intro.txt part1's leading word is [20][20] ($2020) so the
; intro reads the exact dest it does today; part2's is $2010 (= pristine JP's
; $1F:CD35), so the ending gets its intended dest. Verify in the built ROM:
;   $C5:F325 == $E0 ; $E0:C8F1 == $2020 ; $E0:D110 == $2010
; -----------------------------------------------------------------------------
hirom
org $C5F325
    db $E0      ; was $DF — dest-word read now targets relocated bank $E0
