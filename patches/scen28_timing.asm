; -----------------------------------------------------------------------------
; Rushing Beat Shura — scen 28 (ending) animation / fade timing
; -----------------------------------------------------------------------------
; The ending cutscene is paced by the bank-$DF script player. Each STEP begins
; with a one-byte WAIT count (frames to hold before that step's writes fire).
; Animations, sound triggers, and screen fades are timed entirely by these
; wait bytes. They are SEPARATE from the dialog text's own [F7]/[FB]/[FE]/[FF]
; control codes (those pace the renderer); the two systems meet only at the
; entry boundary, where the gate (patches/scen28_script_gate.asm) makes the
; $1C48 entry-advance wait for the renderer to finish the line.
;
; HOW TO RETIME
;   * Find the step below by its "@entry N" label (the dialog line it plays
;     under) and its [writes].
;   * Uncomment the line (drop the leading ';') and change the number:
;       bigger = hold longer / delay later;  smaller = fire sooner.
;   * Lines left commented are no-ops. Do NOT touch lines flagged
;     "** do NOT retime" ($1C48 entry-advance / $1C56 renderer re-engage) —
;     those are handled by the gate and the renderer handshake.
;   * A wait whose label spans "entries X-Y" is a SHARED script reused under
;     several lines — changing it retimes ALL of them.
;
; BUILD IT BACK IN
;   retrotool build . --no-cache --output rbshura_en_24bit.sfc
;   cp rbshura_en_24bit.sfc rbshura_en.sfc      # then reload in Mesen
;
; REGENERATE THIS REFERENCE (overwrites manual edits — keep active tweaks in a
; copy or below the END marker first):
;   python tools/gen_scen28_timing.py > patches/scen28_timing.asm
;   (then re-add this header / your active tweaks)
;
; To map a step you can't identify, pause Mesen at that moment and read
; $1E96 (slot) / $1E99 (offset), or widen tools/dump_scen28_script.py --slots.
; -----------------------------------------------------------------------------

hirom

; org $DFB1A2 : db 0     ; [$1C48=$00]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB1A9 : db 0     ; [$1C48=$02]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 5: "...Listenwell,Dick.P...promiseme...Y"
; org $DFB1B0 : db 0     ; [$1C48=$04]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 6: "Fatherrr!!"
; org $DFB1B7 : db 0     ; [$1C48=$06]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 7: "?!"
; org $DFB1BE : db 0     ; [$1C48=$08]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 8: "Dick!"
; org $DFB1C5 : db 0     ; [$1C48=$0A]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 9: "Grraaaaagh!!"
; org $DFB1CC : db 0     ; [$1C48=$0C]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 10: "Stopit,Bart!Hehheh."
; org $DFB1D3 : db 0     ; [$1C48=$0E]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 11: "What'sallthis?"
; org $DFB1DA : db 0     ; [$1C48=$10]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB1E1 : db 0     ; [$1C48=$12]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 13: "I'msorry,Kythring.Thingshavetakenate"
; org $DFB1E8 : db 0     ; [$1C48=$14]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 14: "Jecusyn...SoDMCorp.hasfinallyshownit"
; org $DFB1EF : db 0     ; [$1C48=$16]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 15: "Quitstruggling!Bigbrother!Helpme!"
; org $DFB1F6 : db 0     ; [$1C48=$18]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 16: "Amy!Bigbrother!"
; org $DFB1FD : db 0     ; [$1C48=$1A]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB204 : db 0     ; [$1C48=$1C]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB20B : db 0     ; [$1C48=$1E]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 19: "Areyouallright,Amy?Thankyou,bigbroth"
; org $DFB212 : db 0     ; [$1C48=$20]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 20: "Amy...Amy?"
; org $DFB219 : db 0     ; [$1C48=$22]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 21: "!!Thisribbon-!It'sAmy's..."
; org $DFB220 : db 0     ; [$1C48=$24]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 22: "Krummbach'sambition...Wemustcrushit!"
; org $DFB227 : db 0     ; [$1C48=$26]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 23: "TheseareLordKrummbach'sorders.Todefy"
; org $DFB22E : db 0     ; [$1C48=$28]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 24: "Grandpa?"
; org $DFB235 : db 0     ; [$1C48=$2A]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFB23C : db 0     ; [$1C48=$2C]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 26: "Sniff...sniff..."
; org $DFB243 : db 0     ; [$1C48=$2E]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFB24A : db 0     ; [$1C48=$30]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 28: "Hm?!Mister-!Who'reyou?Anallyofjustic"
; org $DFB251 : db 0     ; [$1C48=$32]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 29: "Allrightthen,goodgirl.Let'sgo.Holdon"
; org $DFB25F : db 0     ; [$1C48=$36]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 31: "?!"
; org $DFB266 : db 0     ; [$1C48=$38]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 32: "Bigbrother!"
; org $DFB26D : db 0     ; [$1C48=$3A]  ; ** ENTRY ADVANCE — do NOT retime (gated by scen28_script_gate)  ; @entry 33: "Amy...isthatreallyyou?!"
; org $DFB2F2 : db 0     ; [$1C56=$00, $1C57=$00]  ; ** renderer re-engage — do NOT retime  ; @entries 4-33: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB326 : db 0     ; [$12C0=$0D]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB334 : db 0     ; [$12C0=$10]  ; @entry 24: "Grandpa?"
; org $DFB33B : db 0     ; [$12C0=$11]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB365 : db 0     ; [$2142=$01]  ; ** APU port — sound trigger  ; @entries 4-29: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB36C : db 254   ; [$00D5=$01, $00D4=$00, $05F0=$00, $05F1=$00]  ; @entries 8-32: "Dick!"
; org $DFB37C : db 10    ; [$0600=$01, $0602=$20, $0603=$01, $0605=$97, $060A=$36, $060B=$0A, $0630=$01, $0625=$30, $0610=$03, $0702=$80, $0705=$98, $0802=$50, $0805=$B0, $0900=$01, $0902=$14, $0903=$01, $0905=$A0, $0910=$09, $0A00=$01, $0A02=$54, $0A03=$01, $0A05=$94, $0A2A=$01, $0A10=$00, $1901=$80, $1268=$80, $126A=$80]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB3D0 : db 10    ; [$0910=$0A, $0A10=$05]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB3D9 : db 0     ; [$1288=$02]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB3E0 : db 1     ; [$0910=$0B, $0A10=$06, $0602=$21]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB3EC : db 1     ; [$0602=$1E]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB3F3 : db 1     ; [$0910=$0C, $0A10=$0D, $0602=$21]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB3FF : db 1     ; [$0602=$1F]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB406 : db 10    ; [$0912=$02, $0A12=$02, $0A2A=$00, $0910=$01, $0A10=$01]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB418 : db 10    ; [$0910=$02, $0A10=$02]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB421 : db 10    ; [$0910=$03, $0A10=$03]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB42A : db 10    ; [$0910=$04, $0A10=$04]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB434 : db 7     ; [$0700=$01, $0800=$01, $0712=$03, $0812=$03, $0900=$00, $0A00=$00, $0912=$00, $0A12=$00, $0810=$0F, $0710=$0F]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB455 : db 7     ; [$0810=$10, $0710=$10]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB45E : db 7     ; [$0810=$11, $0710=$11]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB467 : db 7     ; [$0810=$12, $0710=$12, $0610=$02]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB473 : db 6     ; [$0812=$02, $0712=$02, $0810=$01, $0710=$01]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB482 : db 6     ; [$0812=$01, $0712=$01, $0810=$07, $0710=$07]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB491 : db 80    ; [$0812=$00, $0712=$00]  ; @entry 4: "Iunderstand,father!Pleasesaveyourstr"
; org $DFB49B : db 228   ; [(no writes)]  ; @entries 5-31: "...Listenwell,Dick.P...promiseme...Y"
; org $DFB49F : db 224   ; [$0610=$03]  ; @entry 5: "...Listenwell,Dick.P...promiseme...Y"
; org $DFB4A6 : db 112   ; [$0710=$48]  ; @entry 6: "Fatherrr!!"
; org $DFB4AC : db 10    ; [$0710=$49]  ; @entry 6: "Fatherrr!!"
; org $DFB4B2 : db 1     ; [$0710=$4A, $0810=$43, $164B=$01, $00A2=$17]  ; @entry 6: "Fatherrr!!"
; org $DFB4C1 : db 16    ; [$0717=$C0, $0710=$51, $0752=$01, $0810=$09, $00A2=$00]  ; @entry 6: "Fatherrr!!"
; org $DFB4D4 : db 24    ; [$0717=$D0, $0718=$FF, $0719=$FF]  ; @entry 7: "?!"
; org $DFB4E0 : db 24    ; [$0717=$30, $0718=$00, $0719=$00]  ; @entry 7: "?!"
; org $DFB4ED : db 16    ; [$0717=$40, $0718=$FF, $0719=$FF, $0710=$2B]  ; @entry 7: "?!"
; org $DFB4FC : db 7     ; [$0717=$00, $0718=$00, $0719=$00, $0710=$34, $0752=$00, $1288=$07]  ; @entry 7: "?!"
; org $DFB511 : db 32    ; [$0710=$33]  ; @entry 7: "?!"
; org $DFB517 : db 7     ; [$0811=$30, $0815=$FF, $0816=$FF, $0810=$0A]  ; @entry 7: "?!"
; org $DFB526 : db 7     ; [$0810=$0B]  ; @entry 7: "?!"
; org $DFB52C : db 7     ; [$0810=$0C]  ; @entry 7: "?!"
; org $DFB532 : db 7     ; [$0810=$0D]  ; @entry 7: "?!"
; org $DFB538 : db 2     ; [$0810=$0E]  ; @entry 7: "?!"
; org $DFB53E : db 32    ; [$0811=$00, $0815=$00, $0816=$00, $0810=$35]  ; @entry 7: "?!"
; org $DFB54E : db 80    ; [(no writes)]  ; @entry 8: "Dick!"
; org $DFB552 : db 64    ; [$0600=$01, $0602=$C8, $0605=$A8, $060A=$36, $060B=$0A, $0630=$01, $062A=$01, $0610=$04, $0621=$00, $0622=$00, $0625=$30, $0700=$01, $0702=$C0, $0703=$FF, $0705=$9C, $0710=$00, $0721=$07, $0722=$70, $0800=$01, $0802=$70, $0805=$A7, $082A=$01, $0810=$01, $0821=$07, $0822=$70, $0825=$38, $0900=$01, $0902=$90, $0903=$01, $0905=$A6, $0927=$06, $092A=$01, $0912=$FE, $0913=$FF, $0910=$01, $0921=$0C, $0922=$C0, $0925=$3A, $0A00=$00]  ; @entry 9: "Grraaaaagh!!"
; org $DFB5CA : db 9     ; [$0910=$02]  ; @entry 9: "Grraaaaagh!!"
; org $DFB5D0 : db 9     ; [$0910=$1D]  ; @entry 9: "Grraaaaagh!!"
; org $DFB5D6 : db 9     ; [$0910=$17]  ; @entry 9: "Grraaaaagh!!"
; org $DFB5DC : db 6     ; [$0912=$00, $0913=$00, $0910=$18, $0612=$FD, $0613=$FF, $0610=$05, $1288=$03]  ; @entry 9: "Grraaaaagh!!"
; org $DFB5F4 : db 9     ; [$0910=$19, $0612=$FE]  ; @entry 9: "Grraaaaagh!!"
; org $DFB5FD : db 16    ; [$0910=$01, $0612=$FF, $0610=$07, $1288=$07]  ; @entry 9: "Grraaaaagh!!"
; org $DFB60C : db 32    ; [$082A=$00, $0612=$00, $0613=$00, $0610=$06]  ; @entry 9: "Grraaaaagh!!"
; org $DFB61B : db 0     ; [$0810=$08]  ; @entry 9: "Grraaaaagh!!"
; org $DFB622 : db 16    ; [$0910=$06]  ; @entry 10: "Stopit,Bart!Hehheh."
; org $DFB628 : db 16    ; [$0910=$07, $1288=$06]  ; @entry 10: "Stopit,Bart!Hehheh."
; org $DFB632 : db 16    ; [$0910=$06]  ; @entry 10: "Stopit,Bart!Hehheh."
; org $DFB638 : db 16    ; [$0812=$02, $0912=$FF, $0913=$FF, $0810=$0B, $0910=$07, $1288=$06]  ; @entry 10: "Stopit,Bart!Hehheh."
; org $DFB64D : db 9     ; [$0810=$0C, $0910=$0F]  ; @entry 10: "Stopit,Bart!Hehheh."
; org $DFB657 : db 11    ; [$0812=$01, $0911=$C0, $0912=$00, $0913=$00, $0810=$09, $0910=$1E]  ; @entries 10-13: "Stopit,Bart!Hehheh."
; org $DFB66C : db 11    ; [$0811=$E0, $0812=$00, $0911=$00, $0912=$01, $0810=$0A, $0910=$1C]  ; @entries 10-13: "Stopit,Bart!Hehheh."
; org $DFB681 : db 11    ; [$0811=$00, $0812=$01, $0810=$0B, $0910=$1E]  ; @entries 10-13: "Stopit,Bart!Hehheh."
; org $DFB690 : db 11    ; [$0810=$0C, $0910=$0F]  ; @entries 10-13: "Stopit,Bart!Hehheh."
; org $DFB69A : db 7     ; [$0712=$02, $0710=$0F]  ; @entry 11: "What'sallthis?"
; org $DFB6A3 : db 7     ; [$0710=$10]  ; @entry 11: "What'sallthis?"
; org $DFB6A9 : db 7     ; [$0710=$11]  ; @entry 11: "What'sallthis?"
; org $DFB6AF : db 7     ; [$0710=$12]  ; @entry 11: "What'sallthis?"
; org $DFB6B5 : db 7     ; [$0710=$13]  ; @entry 11: "What'sallthis?"
; org $DFB6BB : db 7     ; [$0710=$14]  ; @entry 11: "What'sallthis?"
; org $DFB6C2 : db 32    ; [$0712=$00, $0710=$07]  ; @entry 11: "What'sallthis?"
; org $DFB6CB : db 2     ; [$0605=$A7]  ; @entry 11: "What'sallthis?"
; org $DFB6D1 : db 64    ; [$0605=$A8]  ; @entry 11: "What'sallthis?"
; org $DFB6D8 : db 32    ; [$0610=$04]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB6DE : db 63    ; [$0912=$FA, $0913=$FF, $0910=$0F]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB6EA : db 6     ; [$0912=$FD, $0910=$06]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB6F3 : db 6     ; [$0912=$00, $0913=$00, $0910=$1D, $0612=$FA, $0613=$FF, $0610=$05, $1288=$30]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB70B : db 6     ; [$0910=$01, $0612=$FC]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB714 : db 6     ; [$0612=$FE, $0610=$07, $0710=$00, $1288=$07]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB723 : db 9     ; [$0612=$FF]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB729 : db 16    ; [$0612=$00, $0613=$00, $0610=$06]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB736 : db 1     ; [$0600=$01]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB73C : db 1     ; [$0600=$00]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB742 : db 1     ; [$0600=$01]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB748 : db 1     ; [$0600=$00, $0801=$00, $0802=$34, $0803=$01, $082A=$01]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB75B : db 7     ; [$0805=$A5, $0821=$00, $0822=$00, $0812=$FE, $0813=$FF, $0810=$02, $0910=$01]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB773 : db 7     ; [$0810=$03]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB779 : db 7     ; [$0810=$04]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB77F : db 7     ; [$0810=$05, $0910=$05]  ; @entry 12: "Kythring,sir!Bart,suddenly-"
; org $DFB789 : db 31    ; [$0805=$A7, $0812=$00, $0813=$00, $082A=$00, $0810=$08, $0910=$01]  ; @entry 13: "I'msorry,Kythring.Thingshavetakenate"
; org $DFB79E : db 11    ; [$0910=$05]  ; @entry 13: "I'msorry,Kythring.Thingshavetakenate"
; org $DFB7A5 : db 0     ; [$0600=$01, $0602=$B0, $0603=$FF, $0605=$B9, $0621=$10, $0623=$01, $0625=$30, $0700=$01, $0702=$CD, $0703=$FF, $0705=$B6, $070A=$36, $070B=$0E, $0730=$01, $0725=$32, $072A=$01, $0800=$01, $0802=$E0, $0803=$FF, $0805=$B8]  ; @entry 15: "Quitstruggling!Bigbrother!Helpme!"
; org $DFB7E5 : db 10    ; [$0711=$00, $0712=$01, $0812=$01, $0710=$01, $0810=$09]  ; @entry 15: "Quitstruggling!Bigbrother!Helpme!"
; org $DFB7F7 : db 10    ; [$0810=$0A]  ; @entry 15: "Quitstruggling!Bigbrother!Helpme!"
; org $DFB7FD : db 10    ; [$0711=$80, $0712=$00, $0710=$02, $0810=$0B]  ; @entry 15: "Quitstruggling!Bigbrother!Helpme!"
; org $DFB80C : db 10    ; [$0812=$00, $0810=$0C]  ; @entry 15: "Quitstruggling!Bigbrother!Helpme!"
; org $DFB816 : db 13    ; [$0812=$01, $082A=$01]  ; @entry 16: "Amy!Bigbrother!"
; org $DFB81F : db 80    ; [$0711=$00, $0812=$00, $0810=$00]  ; @entry 16: "Amy!Bigbrother!"
; org $DFB82C : db 10    ; [$0612=$01, $0610=$01]  ; @entries 16-21: "Amy!Bigbrother!"
; org $DFB835 : db 10    ; [$0610=$02]  ; @entries 16-21: "Amy!Bigbrother!"
; org $DFB83B : db 10    ; [$0610=$03]  ; @entries 16-21: "Amy!Bigbrother!"
; org $DFB841 : db 10    ; [$0610=$04]  ; @entries 16-21: "Amy!Bigbrother!"
; org $DFB847 : db 10    ; [$0610=$05]  ; @entries 16-21: "Amy!Bigbrother!"
; org $DFB84D : db 10    ; [$0610=$06]  ; @entries 16-21: "Amy!Bigbrother!"
; org $DFB854 : db 10    ; [$0612=$00, $0610=$00, $0810=$10]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB860 : db 10    ; [$0712=$FF, $0713=$FF, $0715=$FE, $0716=$FF, $0810=$06]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB872 : db 10    ; [$0715=$FF]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB878 : db 10    ; [$0711=$80, $0714=$80, $072A=$00, $0710=$03, $1288=$07]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB88A : db 32    ; [$0711=$00, $0712=$00, $0713=$00, $0714=$00, $0715=$00, $0716=$00, $0710=$04, $0810=$12]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8A5 : db 24    ; [$0810=$0D, $1288=$05]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8AF : db 10    ; [$0811=$80, $0812=$FE, $0813=$FF, $0810=$01]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8BE : db 10    ; [$0810=$02]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8C4 : db 10    ; [$0810=$03]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8CA : db 10    ; [$0810=$04]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8D1 : db 7     ; [$0811=$00, $0812=$00, $0813=$00, $0610=$15, $0810=$10]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8E3 : db 12    ; [$0610=$16, $0810=$27, $1288=$02]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8EF : db 7     ; [$0610=$19]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8F5 : db 7     ; [$0610=$20]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB8FB : db 10    ; [$0812=$03, $0610=$21, $0810=$23, $1288=$03]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB90A : db 10    ; [$0812=$02, $0810=$2B]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB913 : db 10    ; [$0812=$01, $0610=$00]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB91C : db 10    ; [$0810=$2F, $1288=$07]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB925 : db 96    ; [$0812=$00, $0810=$33]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB92E : db 32    ; [$0810=$34]  ; @entry 17: "Youthinkyoucantakemeon?!"
; org $DFB935 : db 24    ; [$0811=$20, $0810=$35]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB93E : db 24    ; [$0811=$40, $0810=$34]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB948 : db 10    ; [$0610=$48, $0811=$00, $082A=$00, $0810=$11]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB958 : db 7     ; [$0610=$49, $0812=$02, $0810=$01]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB964 : db 7     ; [$0810=$02]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB96A : db 7     ; [$0810=$03]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB970 : db 7     ; [$0810=$04]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB977 : db 7     ; [$0812=$00, $0612=$01, $0614=$80, $0615=$FF, $0616=$FF, $0610=$09]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB98C : db 7     ; [$0610=$0A]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB992 : db 7     ; [$0610=$0B]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB998 : db 7     ; [$0610=$0C]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB99E : db 7     ; [$0610=$0D]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB9A4 : db 7     ; [$0610=$0E]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB9AB : db 7     ; [$0614=$00, $0615=$00, $0616=$00, $0610=$09]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB9BA : db 7     ; [$0610=$0A]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB9C0 : db 5     ; [$0610=$0B]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB9C7 : db 48    ; [$0612=$00, $062A=$01, $0610=$40]  ; @entry 18: "CrossDouglasMotorandlivetotellofit?D"
; org $DFB9D4 : db 32    ; [(no writes)]  ; @entry 19: "Areyouallright,Amy?Thankyou,bigbroth"
; org $DFB9D7 : db 0     ; [$0710=$03]  ; @entry 19: "Areyouallright,Amy?Thankyou,bigbroth"
; org $DFB9DE : db 0     ; [$0600=$01, $0602=$D0, $0603=$FF, $0605=$A8, $0625=$30, $1670=$01, $1672=$D0, $1675=$A8, $167A=$14, $167D=$28, $1680=$00]  ; @entry 19: "Areyouallright,Amy?Thankyou,bigbroth"
; org $DFBA03 : db 10    ; [$0612=$FF, $0613=$FF, $062A=$01, $0610=$01]  ; @entry 20: "Amy...Amy?"
; org $DFBA12 : db 10    ; [$0610=$02]  ; @entry 20: "Amy...Amy?"
; org $DFBA18 : db 10    ; [$0610=$03]  ; @entry 20: "Amy...Amy?"
; org $DFBA1E : db 10    ; [$0612=$01, $0613=$00, $062A=$00, $0610=$04]  ; @entry 20: "Amy...Amy?"
; org $DFBA2D : db 10    ; [$0610=$05]  ; @entry 20: "Amy...Amy?"
; org $DFBA33 : db 10    ; [$0610=$06]  ; @entry 20: "Amy...Amy?"
; org $DFBA3A : db 80    ; [$0612=$00, $0613=$00, $0610=$00]  ; @entries 20-21: "Amy...Amy?"
; org $DFBA47 : db 128   ; [$0612=$00, $0613=$00, $0610=$40]  ; @entry 21: "!!Thisribbon-!It'sAmy's..."
; org $DFBA53 : db 10    ; [$0610=$44, $1672=$BE, $1675=$72]  ; @entry 21: "!!Thisribbon-!It'sAmy's..."
; org $DFBA5F : db 64    ; [$0610=$14, $1672=$E0, $1675=$5A]  ; @entry 21: "!!Thisribbon-!It'sAmy's..."
; org $DFBA6B : db 24    ; [$0625=$32, $1670=$00]  ; @entry 21: "!!Thisribbon-!It'sAmy's..."
; org $DFBA74 : db 64    ; [$0610=$21, $1288=$0D]  ; @entry 21: "!!Thisribbon-!It'sAmy's..."
; org $DFBA7E : db 0     ; [$0600=$01, $0602=$30, $0605=$B0, $060A=$36, $060B=$0E, $0630=$01, $0610=$07, $0700=$01, $0702=$94, $0705=$A0, $070A=$36, $070B=$04, $0730=$01, $0800=$01, $0802=$D4, $0805=$A1, $082A=$01, $0810=$01, $084F=$02, $0900=$01, $0902=$C8, $0903=$FF, $0905=$98, $0910=$01, $0A00=$01, $0A02=$E0, $0A03=$FF, $0A05=$B8, $0A10=$01]  ; @entry 21: "!!Thisribbon-!It'sAmy's..."
; org $DFBAD9 : db 56    ; [$0710=$09]  ; @entries 22-23: "Krummbach'sambition...Wemustcrushit!"
; org $DFBADF : db 70    ; [$0710=$0B]  ; @entries 22-23: "Krummbach'sambition...Wemustcrushit!"
; org $DFBAE6 : db 10    ; [$0810=$15]  ; @entry 23: "TheseareLordKrummbach'sorders.Todefy"
; org $DFBAEC : db 10    ; [$0810=$16]  ; @entry 23: "TheseareLordKrummbach'sorders.Todefy"
; org $DFBAF2 : db 12    ; [$0712=$FE, $0713=$FF, $0710=$0D, $0810=$17, $1288=$03]  ; @entry 23: "TheseareLordKrummbach'sorders.Todefy"
; org $DFBB04 : db 9     ; [$0712=$FF, $0713=$FF, $0710=$03, $1288=$07]  ; @entry 23: "TheseareLordKrummbach'sorders.Todefy"
; org $DFBB13 : db 32    ; [$0712=$00, $0713=$00, $0810=$45]  ; @entry 23: "TheseareLordKrummbach'sorders.Todefy"
; org $DFBB20 : db 1     ; [$0700=$01]  ; @entry 24: "Grandpa?"
; org $DFBB26 : db 1     ; [$0700=$00]  ; @entry 24: "Grandpa?"
; org $DFBB2D : db 7     ; [$0612=$01, $0614=$80, $0615=$FF, $0616=$FF, $0610=$08]  ; @entry 24: "Grandpa?"
; org $DFBB3F : db 7     ; [$0610=$09]  ; @entry 24: "Grandpa?"
; org $DFBB46 : db 56    ; [$0612=$00, $0614=$00, $0615=$00, $0616=$00, $0610=$07]  ; @entry 24: "Grandpa?"
; org $DFBB59 : db 7     ; [$0612=$01, $0610=$08]  ; @entries 24-28: "Grandpa?"
; org $DFBB62 : db 7     ; [$0610=$09]  ; @entries 24-28: "Grandpa?"
; org $DFBB69 : db 10    ; [$0612=$00, $0610=$0A]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBB72 : db 10    ; [$0610=$0B]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBB79 : db 10    ; [$0810=$05, $0612=$00, $0610=$0A]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBB85 : db 10    ; [$0610=$0B]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBB8C : db 10    ; [$0912=$02, $0910=$01, $0A12=$02, $0A10=$01, $0610=$0A]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBB9E : db 10    ; [$0910=$02, $0A10=$02, $0610=$0B]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBBAA : db 10    ; [$0910=$03, $0A10=$03, $0610=$0A]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBBB6 : db 10    ; [$0910=$04, $0A10=$04, $0610=$0B]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBBC2 : db 10    ; [$0910=$01, $0A10=$01, $0610=$0A]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBBCE : db 128   ; [$0912=$00, $0910=$35, $0A12=$00, $0A10=$35, $0610=$07]  ; @entry 25: "Whatdidyoudotomygrandpa?!Throwthison"
; org $DFBBE1 : db 176   ; [$0600=$01, $0602=$3F, $0605=$98, $060A=$36, $060B=$0E, $0630=$01, $0610=$05, $0700=$01, $0702=$98, $0705=$B0, $0706=$FF, $0708=$48, $0709=$00, $070A=$36, $070B=$0A, $0730=$01, $072A=$01, $0725=$32, $0710=$00, $1670=$01, $1672=$84, $1675=$18, $167A=$14, $167D=$26, $1680=$00, $1692=$01, $1694=$84, $1697=$18, $169C=$14, $169F=$26, $16A2=$00, $16B4=$01, $16B6=$84, $16B9=$18, $16BE=$14, $16C1=$26, $16C4=$00, $16D6=$01, $16D8=$84, $16DB=$18, $16E0=$14, $16E3=$26, $16E6=$00, $16F8=$01, $16FA=$84, $16FD=$18, $1702=$14, $1705=$26, $1708=$00, $171A=$01, $171C=$84, $171F=$18, $1724=$14, $1727=$26, $172A=$00, $173C=$01, $173E=$84, $1741=$18, $1746=$14, $1749=$26, $174C=$00]  ; @entry 26: "Sniff...sniff..."
; org $DFBC9C : db 16    ; [$1685=$01, $16A7=$01, $16C9=$01, $16EB=$01, $170D=$01, $172F=$01, $1751=$01]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCB4 : db 16    ; [$1685=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCBA : db 16    ; [$16A7=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCC0 : db 16    ; [$16C9=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCC6 : db 16    ; [$16EB=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCCC : db 16    ; [$170D=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCD2 : db 16    ; [$172F=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCD8 : db 16    ; [$1751=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCDF : db 80    ; [$0715=$02, $0710=$01]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCE8 : db 96    ; [$0702=$A0, $0715=$00, $0710=$00]  ; @entry 27: "SoundslikethiswretchtheycallKrummbac"
; org $DFBCF5 : db 16    ; [$0610=$06]  ; @entry 28: "Hm?!Mister-!Who'reyou?Anallyofjustic"
; org $DFBCFB : db 112   ; [$0610=$07]  ; @entry 28: "Hm?!Mister-!Who'reyou?Anallyofjustic"
; --- ending fade + epilogue (entries 29-51), added 2026-05-24 after widening
;     tools/gen_scen28_timing.py to SLOT_HI=$520 / CLUSTER_HI=$C2FF. NOTE: the
;     @entry label is the GENERATOR's index ($1C48-derived); the ROM actually
;     displays data-entry (label+1) under it (snippet off-by-one). ---
; org $DFBD02 : db 64    ; [$0612=$00, $062A=$01, $0610=$07]  ; @entry 28: "Hm?!Mister-!Who'reyou?Anallyofjustic"
; org $DFBD0F : db 0     ; [scene setup x29]  ; @entry 29: "Allrightthen,goodgirl.Let'sgo.Holdon"
; org $DFBD6A : db 0     ; [scene setup x14]  ; @entry 31: "?!"
; org $DFBD98 : db 14    ; [$0705=$C7, $0711=$80, $0710=$00]  ; @entry 32: "Bigbrother!"
; org $DFBDA4 : db 14    ; [$0705=$C8]  ; @entry 32: "Bigbrother!"
; org $DFBDAB : db 0     ; [$0711=$00]  ; @entry 32: "Bigbrother!"
; org $DFBDB2 : db 0     ; [scene setup]  ; @entry 32: "Bigbrother!"
; org $DFBDD7 : db 11    ; [$0712=$01, $0710=$01]  ; @entry 32: "Bigbrother!"
; org $DFBDE0 : db 11    ; [$0710=$02]  ; @entry 32: "Bigbrother!"
; org $DFBDE6 : db 11    ; [$0710=$03]  ; @entry 32: "Bigbrother!"
; org $DFBDEC : db 11    ; [$0710=$04]  ; @entry 32: "Bigbrother!"
; org $DFBDF3 : db 0     ; [$0712=$00, $0710=$00]  ; @entry 32: "Bigbrother!"
; org $DFBDFD : db 1     ; [scene setup]  ; @entry 33: ROM shows "Bart sent me packing." (data 34)
; org $DFBE15 : db 240   ; [$0610=$00, $0612=$01]  ; @entry 33: "Bart sent me packing." (hold)
; org $DFBE1E : db 176   ; [(no writes)]  ; @entry 33: "Bart sent me packing." (hold)
; org $DFBE21 : db 0     ; [$0600=$00, $0612=$00]  ; @entry 33
; org $DFBE2B : db 1     ; [scene setup]  ; @entry 33
; org $DFBE43 : db 240   ; [$0710=$00, $0712=$01]  ; @entry 33 (hold)
; org $DFBE4C : db 176   ; [(no writes)]  ; @entry 33 (hold)
; org $DFBE4F : db 0     ; [$0700=$00, $0712=$00]  ; @entry 33
; org $DFBE59 : db 1     ; [scene setup]  ; @entry 33
; org $DFBE92 : db 240   ; [$0810=$00, $0610=$00, $0812=$01, $0612=$01]  ; @entry 33 (hold)
; org $DFBEA1 : db 176   ; [(no writes)]  ; @entry 33 (hold)
; org $DFBEA4 : db 0     ; [$0800=$00, $0600=$00, $0812=$00, $0612=$00]  ; @entry 33
; org $DFBEB4 : db 1     ; [scene setup]  ; @entry 33
; org $DFBEF3 : db 240   ; [$0710=$00, $0610=$00, $0712=$01, $0612=$01]  ; @entry 33 (hold)
; org $DFBF02 : db 176   ; [(no writes)]  ; @entry 33 (hold)
; org $DFBF05 : db 0     ; [$0700=$00, $0712=$00, $0600=$00, $0612=$00]  ; @entry 33
; org $DFBF15 : db 1     ; [scene setup]  ; @entry 33
; org $DFBF33 : db 240   ; [$0710=$00, $0712=$01]  ; @entry 33 (hold)
; org $DFBF3C : db 176   ; [(no writes)]  ; @entry 33 (hold)
; org $DFBF3F : db 0     ; [$0700=$00, $0712=$00]  ; @entry 33
; org $DFBF49 : db 1     ; [scene setup]  ; @entry 33
; org $DFBF6D : db 240   ; [$0610=$00, $0612=$01]  ; @entry 33 (hold)
; org $DFBF76 : db 176   ; [(no writes)]  ; @entry 33 (hold)
; org $DFBF79 : db 0     ; [$0600=$00, $0612=$00]  ; @entry 33
; org $DFBF83 : db 1     ; [scene setup]  ; @entry 33
; org $DFBFA7 : db 240   ; [$0610=$00, $0612=$01]  ; @entry 33 (hold)
; org $DFBFB0 : db 176   ; [(no writes)]  ; @entry 33 (hold)
; org $DFBFB3 : db 0     ; [$0600=$00, $0612=$00]  ; @entry 33
; org $DFBFBD : db 241   ; [(no writes)]  ; @entry 33 (final hold before transition)
; org $DFBFC0 : db 176   ; [(no writes)]  ; @entry 33 (final hold before transition)
; org $DFBFC4 : db 0     ; [scene setup]  ; @entry 39: "No.ItcamefromDr.Barkley'svault.Wefou"
; org $DFC031 : db 14    ; [$0610=$09]  ; @entry 39
; org $DFC037 : db 14    ; [$0610=$0A]  ; @entry 39
; org $DFC03D : db 14    ; [$0610=$0B]  ; @entry 39
; org $DFC043 : db 14    ; [$0610=$0C]  ; @entry 39
; org $DFC049 : db 14    ; [$0610=$0D]  ; @entry 39
; org $DFC04F : db 14    ; [$0610=$0E]  ; @entry 39
; org $DFC056 : db 0     ; [scene setup]  ; @entry 44: "Isee...thankgoodness.I'mgladaboveall"
; org $DFC07E : db 0     ; [scene setup]  ; @entry 46: "CanIevergoback...Tobeinganordinaryhu"
; org $DFC094 : db 0     ; [scene setup]  ; @entry 48: "Thatcan'tbe!TheremustbeSOMEway,mustn"
; org $DFC0AA : db 0     ; [scene setup]  ; @entry 50: "Elfin,it'sallright...Truly.Thepromis"
; org $DFC0C0 : db 0     ; [scene setup]  ; @entry 50
; org $DFC0D6 : db 1     ; [scene setup]  ; @entry 50
; org $DFC0EB : db 0     ; [$0810=$00]  ; @entry 50
; org $DFC0F2 : db 0     ; [scene setup]  ; @entry 50
; org $DFC105 : db 128   ; [scene setup + $1902/$1269/$126B]  ; @entry 51: "IfIweretobecomelikeVelk...Theremight"
; org $DFC14B : db 10    ; [$0710=$01, $0712=$FF, $0713=$FF]  ; @entry 51
; org $DFC157 : db 10    ; [$0710=$02]  ; @entry 51
; org $DFC15D : db 10    ; [$0710=$03]  ; @entry 51
; org $DFC163 : db 10    ; [$0710=$04]  ; @entry 51
; org $DFC169 : db 10    ; [$0710=$05]  ; @entry 51
; org $DFC16F : db 10    ; [$0710=$06]  ; @entry 51
; org $DFC176 : db 128   ; [$0710=$07, $0712=$00, $0713=$00]  ; @entry 51 (hold)
; org $DFC182 : db 240   ; [$0610=$07]  ; @entry 51 (hold)
; org $DFC188 : db 240   ; [(no writes)]  ; @entry 51 (final hold before transition)
; org $DFC1F9 : db 10    ; [$0610=$01, $0710=$01 ...]  ; @entry 51 (post-transition walk)
; org $DFC20E : db 10    ; [$0610=$02, $0710=$02]  ; @entry 51
; org $DFC217 : db 10    ; [$0610=$03, $0710=$03]  ; @entry 51
; org $DFC220 : db 10    ; [$0610=$04, $0710=$04]  ; @entry 51
; org $DFC229 : db 10    ; [$0610=$05, $0710=$05]  ; @entry 51
; org $DFC232 : db 10    ; [$0610=$06, $0710=$06]  ; @entry 51
; org $DFC23C : db 0     ; [$0610=$07 ...]  ; @entry 51
; --- SHARED fade/hold fragments reused by the ending (see also entries 5-32) ---
; org $DFB49B : db 228   ; [(no writes)]  ; ** SHARED hold, also @entries 5-31 — bumping affects all
; org $DFB36C : db 254   ; [$00D5=$01, $00D4=$00, $05F0=$00, $05F1=$00]  ; ** SHARED FADE-OUT trigger (slots $308/$31A/$514) — already near max(255), also @entries 8-32

; ===== END generated reference — ACTIVE tweaks below (override the reference) =====
org $DFBADF : db 70    ; [$0710=$0B]  ; @entries 22-23: "Krummbach'sambition...Wemustcrushit!"
org $DFBB13 : db 22    ; [$0712=$00, $0713=$00, $0810=$45]  ; @entry 23: "TheseareLordKrummbach'sorders.Todefy"
org $DFBB46 : db 16  ; [$0612=$00, $0614=$00, $0615=$00, $0616=$00, $0610=$07]  ; @entry 24: "Grandpa?"
org $DFBCF5 : db 80    ; [$0610=$06]  ; @entry 28: "Hm?!Mister-!Who'reyou?Anallyofjustic"
org $DFBCFB : db 122 ;  [$0610=$07]  ; @entry 28: "Hm?!Mister-!Who'reyou?Anallyofjustic"
org $DFB49F : db 74   ; [$0610=$03]  ; @entry 5: "...Listenwell,Dick.P...promiseme...Y"
org $DFB79E : db 31    ; [$0910=$05]  ; @entry 13: "I'msorry,Kythring.Thingshavetakenate"
