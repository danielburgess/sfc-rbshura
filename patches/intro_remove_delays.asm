; -----------------------------------------------------------------------------
; intro_remove_delays.asm — convert rbshura intro from typewriter → static
; -----------------------------------------------------------------------------
; Jaleco wrapped PK's intro renderer with a typewriter cadence by inserting
; `JSL $80:D8E8` calls at 17 sites in bank $1F. $80:D8E8 is a VBlank-wait
; routine (parameterized by $1288 set just before each call).
;
; PK's same code has zero of these calls (it uses its own integrated renderer).
;
; This patch NOPs all 17 JSL sites in bank $1F (the intro/title path) so
; rbshura renders the intro instantly like PK. Each JSL is 4 bytes → 4 NOPs.
; -----------------------------------------------------------------------------

hirom

org $9FD207 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD207
org $9FD21C : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD21C
org $9FD5A0 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD5A0
org $9FD7BD : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD7BD
org $9FD7E1 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD7E1
org $9FD805 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD805
org $9FD823 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD823
org $9FD841 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FD841
org $9FDAB0 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FDAB0
org $9FDAC5 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FDAC5
org $9FEE22 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FEE22
org $9FF58B : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FF58B
org $9FFAD9 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FFAD9
org $9FFB0A : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FFB0A
org $9FFB45 : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FFB45
org $9FFBCD : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FFBCD
org $9FFBEC : NOP : NOP : NOP : NOP    ; was JSL $80:D8E8 at file $1FFBEC
