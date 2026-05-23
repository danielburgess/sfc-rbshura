; -----------------------------------------------------------------------------
; Rushing Beat Shura — 24-bit string-pointer engine patch
; -----------------------------------------------------------------------------
; Converts the text engine's L4 (per-scenario string pointer table) dereference
; from in-bank 16-bit pointers to 24-bit pointers, so EN text can live in any
; ROM bank (eliminates KEEPING_ORIGINAL by removing the [data].end ceiling).
;
; Per-scenario changes required IN ADDITION TO this patch:
;   - The L4 table at <L4_base> (e.g. $86E4 for scen_0) must be widened from
;     2-byte entries to 3-byte entries (low, high, bank).
;   - The L3 sequence blocks already store entry_idx * 2; this stub scales to
;     entry_idx * 3 at runtime, so L3 blocks do NOT need to change.
;
; Memory map dependencies (must match the engine's current layout):
;   $00:$01 — current text pointer (was 16-bit; becomes low/high of 24-bit)
;   $02     — bank byte of 24-bit text pointer (NEW — must be DP-safe)
;   $03     — temporary scratch (NEW — must be DP-safe)
;   $00D0   — current scenario × 2
;   $858233 — meta-table of L4 base addresses (16-bit per scen, unchanged)
;
; Engine state contract:
;   - DBR is the scenario data bank at the dispatch point ($85/$87/$7E).
;   - $00:$01:$02 must hold a valid 24-bit pointer to the current string
;     before any character read.
;   - Character reads use `LDA [$00],Y` (B7 00) instead of `LDA ($00),Y`
;     (B1 00). The stub leaves $02 set to the scenario-bank-respecting
;     bank byte of the current string.
;
; HiROM addressing:
;   - Engine is at $05:8000..$05:83FF (file 0x058000..0x0583FF).
;   - Stub lives in bank $08 freespace at $C8:7000 (file 0x087000).
;   - All `org` directives use 24-bit SNES addresses; asar resolves to file.
; -----------------------------------------------------------------------------

hirom                       ; rbshura is HiROM/fastrom (verified 2026-05-15).

; =========================================================================
; 1. Engine patch — replace the L4 deref at $05:81A1 with a JSL to stub.
; =========================================================================
;
; Original code at $0581A1..$0581AA (10 bytes total):
;   $0581A1: BF 33 82 85   LDA $858233,X    ; L4 base from meta-table
;   $0581A5: 85 00         STA $00          ; → DP $00
;   $0581A7: B1 00         LDA ($00),Y      ; read 16-bit string ptr from L4
;   $0581A9: 85 00         STA $00          ; → DP $00 (now the string ptr)
;
; After patch:
;   $0581A1: 22 00 70 C8   JSL L4_Deref_24    ; 4 bytes
;   $0581A5: EA × 6           NOPs              ; 6 bytes pad to keep offsets

org $C581A1                 ; HiROM $C5:81A1 = file $058 1A1
    JSL L4_Deref_24
    NOP : NOP : NOP : NOP : NOP : NOP

; =========================================================================
; 2. Character read sites — flip `LDA ($00),Y` (B1 00) to `LDA [$00],Y` (B7 00)
;    These read the current string's bytes; with 24-bit ptr in $00:$01:$02
;    they must use long-indirect addressing.
; =========================================================================
;
; Each site is a single-byte change ($B1 → $B7). The dp operand byte ($00)
; stays the same.

; =========================================================================
; 1b. ROM size header byte at $00:FFD7 — bump from $0E (16 Mbit/2 MB) to
;     $0F (32 Mbit/4 MB) so emulators recognize the expanded ROM. retrotool's
;     post-build _pad_to_next_size pads the file to 4 MB; retrotool's
;     _patch_checksum recomputes the checksum (it sees the updated size byte
;     in its sum). Without this, emulators may complain or treat the file as
;     a 2 MB ROM with garbage tail.
; =========================================================================

org $00FFD7 : db $0F

org $C581B3 : db $B7    ; main per-char dispatch read
org $C581FF : db $B7    ; FA-prefix param read
org $C58255 : db $B7    ; FC-handler read
org $C5826C : db $B7    ; FC-handler read
org $C58283 : db $B7    ; FC-handler read
org $C58293 : db $B7    ; FC-handler read
org $C582B8 : db $B7    ; FB-handler read
org $C582C7 : db $B7    ; F7-handler read
org $C582DB : db $B7    ; F8-handler read
org $C582EB : db $B7    ; F9-handler read

; =========================================================================
; 3. L4_Deref_24 stub — 24-bit L4 dereference & Y-stride scaling.
; =========================================================================
;
; Lives in bank $08 freespace (verified 2026-05-17: file 0x086FFE has 4098
; bytes of $00 → SNES $C8:6FFE..$C8:7FFF accessible via $C8 mirror).
;
; Stub responsibilities:
;   1. Load L4 base (16-bit) from meta-table at $858233.
;   2. Establish 24-bit ptr at $00:$01:$02 = L4_base : scen_bank.
;   3. Scale Y from entry_idx*2 (L3-sequence convention) to entry_idx*3.
;   4. Fetch 24-bit string ptr from L4_base + Y (3-byte entry).
;   5. Replace $00:$01:$02 with the string ptr.
;   6. RTL — caller proceeds with `LDA [$00],Y` to read chars.

; -----------------------------------------------------------------------------
; Per-scenario L4 table convention (verified 2026-05-19 via SplitTrace):
;   * Scens 0-13: L4 table written to ROM by retrotool as 24-bit entries.
;     Reachable via DBR-relative read; bank byte comes from the table.
;   * Scens 14, 15 (ending + credits): L4 table is constructed in WRAM at
;     boot/scenario-start. The bank lookup at $05:807A returns $7E (or $00)
;     for these. Their tables stay 16-bit (2-byte stride) because we don't
;     touch the WRAM blob. The stub MUST detect this and skip the *3 Y-scale
;     and the bank-byte fetch — otherwise it reads misaligned bytes from
;     WRAM and the pointer dereferences a garbage bank.
;
; Detection: bank-lookup table at $05:807A — one byte per scen. If that
; byte equals $7E, take the legacy 16-bit path.
; -----------------------------------------------------------------------------

org $C87000                 ; bank $08 freespace start
L4_Deref_24:
    REP #$10                ; X/Y → 16-bit (caller had X 8-bit, Y 8-bit)
    LDA $00D0
    AND #$00FF              ; A = scen × 2
    PHA                     ; save for the path that needs it
    LSR                     ; A = scen index (0..15)
    TAX

    ; Bank lookup: $05:807A + scen_index → ROM-side DBR for this scen.
    SEP #$20                ; A → 8-bit
    LDA $85807A,X
    STA $03                 ; STASH bank byte ($03 is free until used as
                            ;   entry_idx temp below — see comment there)

    ; ---------------------------------------------------------------
    ; Scen 14 override (added 2026-05-21):
    ; The bank-lookup table at $05:807A is shared by the engine's
    ; per-scenario state setup at $05:800D, so we MUST leave $05:8088
    ; at $7E for scen 14 (otherwise engine DBR setup hits ROM $E0:05xx
    ; instead of WRAM $7E:05xx and the dialog state machine breaks —
    ; see memory/project_wram_resident_scenarios.md 2026-05-21 entry).
    ;
    ; Detect scen 14 here in the stub and route it to the 24-bit ROM
    ; path with hardcoded $E0:F000 base. Engine state setup still
    ; reads $7E and works correctly; only the L4 STRING lookup is
    ; redirected to our EN-populated ROM table.
    ;
    ; X is 16-bit here (REP #$10 at top). CPX immediate compares 16-bit.
    ; ---------------------------------------------------------------
    CPX #$000E              ; scen 14?
    BEQ .scen14_rom_override

    CMP #$7E                ; otherwise: WRAM-resident (scen 15)?
    BEQ .legacy16
    REP #$20                ; restore 16-bit A for the 24-bit path

    ; --- 24-bit path (scens 0-13) ---
    PLA                     ; A = scen × 2
    TAX

    LDA $858233,X
    STA $00                 ; $00/$01 = L4 base (low 16-bit)
    BRA .common_24bit       ; share entry-decode tail with scen-14 path

.scen14_rom_override:
    ; Hardcoded override: bank $E0, L4 base $F000 (matches tables/scenario_28.toml).
    LDA #$E0
    STA $03                 ; override stashed bank
    REP #$20
    PLA                     ; discard saved scen × 2 — we don't use $858233 here
    LDA #$F000
    STA $00                 ; $00/$01 = L4 base for scen 14
    ; fall through

.common_24bit:
    SEP #$20
    LDA $03                 ; recall the bank we stashed above
    STA $02                 ; $02 = L4 table's bank (= $85, $87, or $E0).
                            ; Previously this was `PHB / PLA / STA $02`
                            ; which used the caller's DBR — coincidentally
                            ; right for $85/$87 banks but WRONG for our
                            ; relocated scen 14 in bank $E0.
    REP #$20

    TYA                     ; A = entry_idx*2
    AND #$00FF
    LSR                     ; A = entry_idx
    STA $03
    ASL                     ; A = entry_idx*2
    CLC
    ADC $03                 ; A = entry_idx*3
    TAY

    LDA [$00],Y             ; string_ptr_lo + string_ptr_hi
    TAX
    INY
    INY

    SEP #$20
    LDA [$00],Y             ; string_ptr_bank
    STA $02                 ; bank from the L4 entry itself
    REP #$20

    TXA
    STA $00                 ; $00/$01 = string ptr
    RTL

.legacy16:
    ; --- 16-bit legacy path (scens 14, 15 — WRAM-resident L4) ---
    ; A is 8-bit here; widen back to 16-bit for the rest.
    REP #$20
    PLA                     ; A = scen × 2
    TAX

    LDA $858233,X
    STA $00                 ; $00/$01 = L4 base (low 16-bit, in WRAM)

    SEP #$20
    PHB
    PLA
    STA $02                 ; $02 = DBR (= $7E for WRAM-resident scens)
    REP #$20

    ; Y stays at entry_idx*2 (engine convention) — no *3 scaling.
    TYA
    AND #$00FF
    TAY

    LDA [$00],Y             ; 16-bit string ptr from WRAM L4 table
    STA $00                 ; $00/$01 = string ptr; $02 keeps DBR
    RTL

; -----------------------------------------------------------------------------
; End of patch. Caller's next instruction at $0581AB (REP #$10) is a no-op
; with respect to X/Y width (we already set it inside the stub), and the
; subsequent `LDY $1C4A` re-establishes Y to the per-character index.
; -----------------------------------------------------------------------------

; =============================================================================
; Scen 14 redirect history — stub-side override (2026-05-21)
; =============================================================================
; FIRST ATTEMPT (broken, reverted): flipped two ROM bytes in the bank-lookup
; table to force scen 14 onto the 24-bit ROM path:
;   org $C58088 : db $E0       ; $7E → $E0
;   org $C58250 : db $F0       ; $C7 → $F0
; This worked for L4 deref BUT the table at $05:807A is shared with engine
; state setup at $05:800D (`PHA / PLB` to set DBR before reading scenario
; state at $0560/$0600/$0700/etc.). The flip made the engine read state
; from ROM bank $E0 at those offsets — all zeros — and the dialog state
; machine never entered dialog state. Dialog boxes themselves stopped
; rendering. Reverted.
;
; CURRENT APPROACH: stub-side override inside L4_Deref_24 (see CPX #$000E
; check above). The ROM byte at $05:8088 stays $7E so the engine's state
; setup keeps using DBR=$7E (correct). The L4 stub detects scen 14 from
; the scen index, sets bank/base to hardcoded $E0:F000, and routes through
; the standard 24-bit string-lookup path. EN bytes from tables/scenario_28.toml
; are read from ROM; engine state still lives in WRAM as the loader expects.
