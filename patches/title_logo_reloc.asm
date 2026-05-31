; -----------------------------------------------------------------------------
; title_logo_reloc.asm — relocate the MAIN-TITLE graphics to bank $E1, gated to
; the title only ($00C8==2). Three DMAs in the shared `updateContinueMenu` ($5F)
; push routine are hooked (each runs for splash $00C8=0 + narration $00C8=6 too,
; so each is gated):
;   1. BG1 logo CHAR  $DF:DE73  $7F:4000 -> VRAM $2000  — EXPANDED 8K->16K
;   2. OBJ kanji tiles $DF:DE9C $7F:2000 -> VRAM $0000  (8K, unchanged)
;   3. BG1/2/3 TILEMAP $DF:DE4A $7F:8800 -> VRAM $5000  (12K combined blob)
;
; The EN logo needs ~346 unique tiles, so the BG1 char is expanded from 8 KiB
; (256 tiles, VRAM word $2000..$3000) to 16 KiB (512 tiles, word $2000..$4000;
; byte $4000..$8000 — the upper half was unused). The char DMA's SIZE is gated
; too ($2000 for non-title, $4000 for title) so other screens are untouched.
;
; The tilemap blob (assets/title_tilemap.bin) = new BG1 map spliced over the
; original BG2(flame)+BG3(text) maps, so only BG1 changes.
;
; $E1 layout (reserved in project.toml freespace):
;   $E1:1000..$E1:5000   title_logo.bin    (16 KiB BG1 char, 512 tiles)
;   $E1:5000..$E1:7000   title_kanji.bin   (8 KiB OBJ kanji tiles)
;   $E1:7000..$E1:A000   title_tilemap.bin (12 KiB BG1+BG2+BG3 maps)
;   $E1:A000..$E1:A0FF   these stubs
;
; Reg state at all three hook sites: M=1 (8-bit A), X=16-bit. Stubs preserve it.
; (VMADD $2116 is set BEFORE each DMA block, so A1T operands are off-by-one from
; VMADD order — verified by which VMADD each $420B trigger actually uses.)
; -----------------------------------------------------------------------------

hirom

; --- hook 1: BG1 logo char source + SIZE ($DF:DE73 A1T..A1B + $DE7E size) ---
; replace 17 bytes ($DE73..$DE83: LDX#$4000/STX$4302/LDA#$7F/STA$4304/
;                   LDX#$2000/STX$4305) with JSL + 13 NOP.
org $DFDE73
    JSL LogoCharSrc
    NOP : NOP : NOP : NOP : NOP : NOP : NOP : NOP : NOP : NOP : NOP : NOP : NOP

; --- hook 2: OBJ kanji source ($DF:DE9C A1T=$2000) ---
org $DFDE9C
    JSL KanjiSrc
    NOP : NOP : NOP : NOP : NOP : NOP : NOP

; --- hook 3: tilemap source ($DF:DE4A A1T=$8800) ---
org $DFDE4A
    JSL TilemapSrc
    NOP : NOP : NOP : NOP : NOP : NOP : NOP

; --- hook 4: kanji METASPRITE pointer ($DF:D72D in SetupSpriteAndUI) ---
; replace 10 bytes (LDA #$EC86/STA $00/LDA #$009F/STA $02) with JSL + 6 NOP.
; Gated: title ($00C8==2) -> new EN "SHURA" metasprite @ $E1:A200; else the
; original 修羅 table @ $9F:EC86 (consistent with the gated kanji tile DMA).
org $DFD72D
    JSL KanjiPtr
    NOP : NOP : NOP : NOP : NOP : NOP

org $E1A000
LogoCharSrc:
    LDA.W $00C8
    CMP #$02
    BNE .orig
    LDX #$1000 : STX $4302       ; A1T -> $E1:1000
    LDA #$E1   : STA $4304
    LDX #$4000 : STX $4305       ; size = 16 KiB (title, 512 tiles)
    RTL
.orig:
    LDX #$4000 : STX $4302       ; original $7F:4000
    LDA #$7F   : STA $4304
    LDX #$2000 : STX $4305       ; size = 8 KiB
    RTL

KanjiSrc:
    LDA.W $00C8
    CMP #$02
    BNE .orig
    LDX #$5000 : STX $4302       ; A1T -> $E1:5000
    LDA #$E1   : STA $4304
    RTL
.orig:
    LDX #$2000 : STX $4302       ; original $7F:2000
    LDA #$7F   : STA $4304
    RTL

TilemapSrc:
    LDA.W $00C8
    CMP #$02
    BNE .orig
    LDX #$7000 : STX $4302       ; A1T -> $E1:7000
    LDA #$E1   : STA $4304
    RTL
.orig:
    LDX #$8800 : STX $4302       ; original $7F:8800
    LDA #$7F   : STA $4304
    RTL

; Kanji metasprite pointer (DP $00 low/high, $02 bank). Called with 16-bit A
; (REP #$20 in SetupSpriteAndUI); returns 16-bit A for the following LDA $1E04.
KanjiPtr:
    SEP #$20
    LDA.L $7E00C8               ; DBR-independent (SetupSpriteAndUI's DBR varies)
    CMP #$02
    REP #$20
    BNE .orig
    ; Table @ $E1:A200, but the engine uses DBR for EVERYTHING (table read AND
    ; the WRAM cursor $00C4 / OAM buffer $0100). DBR must be a $80-$BF bank so
    ; low addrs mirror WRAM. $A1 = $E1's mirror: $A1:A200 = same ROM file offset
    ; ($21A200), while $A1:00C4 = $7E:00C4 (WRAM). (The original $9F works the
    ; same way.) NB: the table low16 must be >= $8000 to land in the ROM half.
    LDA #$A200 : STA $00         ; -> $A1:A200 (= file $21A200 = $E1:A200)
    LDA #$00A1 : STA $02
    RTL
.orig:
    LDA #$EC86 : STA $00         ; original 修羅 table $9F:EC86
    LDA #$009F : STA $02
    RTL

assert pc() <= $E1A200, "title reloc stubs overflowed into the metasprite slot"
