#!/usr/bin/env python3
"""Apply English translations to a scenario_NN.txt file.

Reads the existing file, replaces JP runs with EN translations per a
hand-written mapping below, preserves every control code exactly, writes
the file back atomically as UTF-16.

Run as: python scripts/translate_scen.py <scenario_NN>
"""
from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
EN_DIR = ROOT / "data" / "en"

ENTRY_HDR_RE = re.compile(r"<<\$\d+:\d+\[\$\d+\]>>")


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------
# Format: scen_id → {entry_idx → new_body}
# new_body must include all control codes (verbatim from source structure).
# All literal text is Latin-only per tables/rbshura_en.tbl.

TRANSLATIONS: dict[int, dict[int, str]] = {
    # =====================================================================
    # SCEN 06 — "Unseen Bond" (Dick/Amy storyline)
    # Dick infiltrates Krummbach's facility, finds his sister Amy
    # transformed by the Jecaxin drug. McCoy explains Krummbach's plan.
    # =====================================================================
    6: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][CE][FC][01][04][FC][00][2D]Unseen [FC][00][2D]Bond[FB][15]',
        17: ('[F9][04][F8][01][FC][01][01][FC][02][52][08]'
             'Krummbach, with his[FD]Jecaxin research,[F7][FF][FB][10][FE][F7][08]'
             'has bred humans of[FD]immense destructive power.[F7][FF][FB][10][FE][F7][08]'
             'For now, they remain[FD]hard to control[F7][FF][FB][10][FE][F7][08]'
             'and have been sealed away.[F7][FF][FB][10][FE][F7][08]'
             'But should they be unleashed,[F7][FF][FB][10][FE][F7][08]'
             'the lives lost would be[FD]beyond imagining.[F7][FF][FB][10][FE][F7][08]'
             'For humanity itself,[F7][FF][FB][10][FE][F7][08]'
             "please stop[FD]Krummbach's plan.[F7][FF][FB][15]"),
        20: ('[F9][04][FC][01][01][FC][02][52][08]'
             'My comrades should be[FD]waiting at the ruins.[F7][FF][FB][10][FE][F7][08]'
             'Please meet with them.[F7][FF][FB][15]'),
        21: "Sorry I'm late.[F7][FF][FB][15]",
        22: ('[F9][04][FC][01][01][FC][02][44][08]'
             "No... it's all right...[FD]You came for me...[F7][FF][FB][10][FE][F7][08]"
             'That ribbon...[FD]looks good on you...[F7][FF][FB][15]'),
        23: "What are you saying?[FD]This was yours...[F7][FF][FB][15]",
        24: ('[F9][04][FC][01][01][FC][02][44][08]'
             "...It's all right.[F7][FF][FB][10][FE][F7][08]"
             "I... won't be able...[FD]to wear it any longer.[F7][FF][FB][15]"),
        25: "Wh-what?[F7][FF][FB][15]",
        26: ('[F9][02][F8][01][FC][01][01][FC][02][54][08]'
             'M-my lord, what shall we do?[FD]They have come.[F7][FF][FB][10][FE][F7][08]'
             '[FC][02][56][08]Do not panic.[F7][FF][FB][10][FE][F7][08]'
             'Is this not a chance[FD]to see the research bear fruit?[F7][FF][FB][10][FE][F7][08]'
             'Lord Krummbach,[F7][FF][FB][10][FE][F7][08]'
             'we shall give you[FD]quite the show.[F7][FF][FB][10][FE][F7][08]'
             '[F9][02][FC][02][2C][08]Hm —[FD]I shall expect great things.[F7][FF][FB][10][FE][F7][08]'
             '[F9][02][FC][02][56][08]Yes, sir![F7][FF][FB][10][FE][F7][08]'
             'Amy![F7][FF][FB][10][FE][F7][08]'
             'Crush[FD]every last one of them![F7][FF][FB][15]'),
        27: "Amy?![F7][FF][FB][15]",
        28: "Is this...[F7][FF][FB][10][FE][F7][08]really Amy?[F7][FF][FB][15]",
        29: "It can't be![F7][FF][FB][15]",
        30: "Sh-she's huge![F7][FF][FB][15]",
        31: ('[F9][02][FC][01][01][F8][01][FC][02][54][08]'
             'My lord Krummbach,[FD]please escape![F7][FF][FB][10][FE][F7][08]'
             '[FC][02][2C][08]Grr... ngh...[F7][FF][FB][15]'),
        32: "[F8][01][FC][01][01]Amy![F7][FF][FB][15]",
        33: ('[F9][04][FC][01][01][FC][02][44][08]'
             'Brother... I[FD]waited for so long.[F7][FF][FB][10][FE][F7][08]'
             'I waited for you[FD]to come for me.[F7][FF][FB][15]'),
        34: "[F8][01][FC][01][01]Amy!![F7][FF][FB][15]",
        35: "[FC][01][01][F8][01]To use Jecaxin[FD]even on a little girl...[F7][FF][FB][15]",
        36: "Krummbach...[FD]I will never forgive you.[F7][FF][FB][15]",
        37: "Krummbach...[FD]I will never forgive you.[F7][FF][FB][15]",
        38: "Uoooohhh![F7][FF][FB][15]",
        39: "[FC][01][01][F8][01]Dick!![F7][FF][FB][15]",
        40: ('[F9][02][FC][01][01][FC][02][54][08]'
             'The prototype...[FD]why is it here?[F7][FF][FB][10][FE][F7][08]'
             '[FC][02][56][08]Lord Krummbach[FD]must be told of this.[F7][FF][FB][15]'),
        41: ('[FC][02][2E][08][F9][02]'
             'Have we still not[FD]reached the airport?[F7][FF][FB][10][FE]'
             '[FC][02][14][08][F9][04]It will take[FD]a little while longer.[F7][FF][FB][15]'),
        42: ('[FC][02][58][08][F9][00]'
             'H-hey,[FD]let go of me!![F7][FF][FB][10][FE]'
             '[FC][02][14][08][F9][04]Silence.[F7][FF][FB][15]'),
        43: ('[FC][02][2E][08][F9][02]'
             'To be beaten this badly[FD]by mere rats...[F7][FF][FB][15]'),
        44: ('[F9][04][FC][01][01][FC][02][44][08]'
             '...Take care of[FD]the ribbon...[F7][FF][FB][15]'),
        45: "............[F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 08 — "Pirate's Dock"
    # Burnett's Three Devils block the path; Norton joins after introducing
    # himself as wanting to destroy the Jecaxin Factory.
    # =====================================================================
    8: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][FC][01][04][FC][00][2D]Pirate\'s [CE][FC][00][2D]Dock[FB][15]',
        17: ('[F9][02][F8][01][FC][01][01][FC][02][32][08]'
             "You won't pass[FD]beyond here, ya hear?[F7][FF][FB][15]"),
        18: ('[F9][02][F8][01][FC][01][01][FC][02][32][08]'
             "As long as we,[FD]Burnett's Three Devils, stand[F7][FF][FB][10][FE][F7][08]"
             "you'll never board[FD]the ship.[F7][FF][FB][10][FE][F7][08]"
             "You meet your end[FD]right here.[F7][FF][FB][15]"),
        20: ('[F9][02][F8][01][FC][01][01][FC][02][32][08]'
             "You're a touch late.[F7][FF][FB][10][FE][F7][08]"
             "Lord Burnett[FD]has already set sail.[F7][FF][FB][10][FE][F7][08]"
             "He left dealing with you[FD]to us Three Devils.[F7][FF][FB][10][FE][F7][08]"
             "You die[FD]right here.[FB][15]"),
        21: ('[F9][04][F8][01][FC][01][01][FC][02][28][08]'
             "Are you all right?[F7][FF][FB][15]"),
        22: "And you are...?[F7][FF][FB][15]",
        23: "And who are you?[F7][FF][FB][15]",
        24: ('[F9][04][FC][01][01][FC][02][28][08]'
             "I'm Norton.[F7][FF][FB][10][FE][F7][08]"
             "I'm here to destroy[FD]the Jecaxin factory.[F7][FF][FB][15]"),
        25: "The Jecaxin factory?[F7][FF][FB][15]",
        26: ('[F9][04][FC][01][01][FC][02][28][08]'
             "Jecaxin carries[FD]too many bitter memories.[F7][FF][FB][10][FE][F7][08]"
             "Until it's all destroyed,[FD]my fight isn't over.[F7][FF][FB][10][FE][F7][08]"
             "Will you lend me[FD]your strength?[F7][FF][FB][15]"),
        27: "Of course.[FB][15]",
        28: "Let's join forces.[FB][15]",
        29: ('[F9][04][FC][01][01][FC][02][28][08]'
             "The factory is up[FD]the ladder ahead.[F7][FF][FB][10][FE][F7][08]"
             "Come on, let's go.[F7][FF][FB][15]"),
        30: "[FC][01][01][F8][01]Let's head out[FD]the way we came.[F7][FF][FB][15]",
        31: "[FC][01][01][F8][01]Let's go back up[FD]that ladder.[F7][FF][FB][15]",
        32: ".....[F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 10 — "Pursuit"
    # Confrontation with Krummbach on a transport plane he's set to crash.
    # =====================================================================
    10: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][CE][CE][FC][01][04][FC][00][2D]Pur[FC][00][2D]suit[FB][15]',
        17: "[FC][01][01][F8][01]Where is Krummbach?[F7][FF][FB][15]",
        18: "[FC][01][01][F8][01]Where's Krummbach?[F7][FF][FB][15]",
        19: ('[FC][01][01][F8][01][FC][02][2C][08][F9][02]'
             "Th-that you have[FD]cornered me this far...[F7][FF][FB][10][FE][F7][08]"
             "It seems I have[FD]misjudged your strength.[F7][FF][FB][15]"),
        20: "So you're Krummbach?![FD]My father — for that —![F7][FF][FB][15]",
        21: ('[FC][02][2C][08][F9][02]'
             "I'm afraid you[F7][FF][FB][10][FE][F7][08]"
             "are sorely mistaken[FD]about something.[F7][FF][FB][15]"),
        22: ('[FC][02][2C][08][F9][02]'
             "No matter — here is[FB][10][FE][F7][08]"
             "where we part ways.[F7][FF][FB][10][FE][F7][08]"
             "For eternity...[FB][15]"),
        23: "What?[F7][FF][FB][15]",
        24: "What did you say?[F7][FF][FB][15]",
        25: ('[FC][02][2C][08][F9][02]'
             "This transport is[FB][10][FE]"
             "rigged to crash.[F7][FF][F7][08][FB][10][FE]"
             "There is no way left[FD]for you to be saved.[F7][FF][FB][10][FE][F7][08]"
             "Not unless you[FD]destroy the system.[F7][FF][FB][10][FE][F7][08]"
             "Struggle all you like,[FD]for what little it gains.[F7][FF][FB][15]"),
        26: "[FC][02][58][08][F9][04]Kyaaaah![F7][FF][FB][15]",
        27: ('[FC][01][01][F8][01]This transport —[F7][FF][FB][10][FE][F7][08]'
             'where on earth[FD]is it taking us?[F7][FF][FB][15]'),
        28: ('[FC][01][01][F8][01]This transport...[FD]'
             "where is it taking us?[F7][FF][FB][15]"),
        29: ('[FC][01][01][F8][01][F9][02]EXPLOSION IN[FD]15 SECONDS.[F7][FF][FB][10][FE][F7][08]'
             "PLEASE[FD]EVACUATE.[F7][FF][FB][15]"),
        30: "Maria!![F7][FF][FB][15]",
        31: "[F7][FF].....[FB][15]",
    },
    # =====================================================================
    # SCEN 12 — "Storm of Steel"
    # Sea-bound combat; Burnett's pirates try to drag the heroes down with
    # the ship. Metal Frames appear at the climax.
    # =====================================================================
    12: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][CE][FC][01][04][FC][00][2D]Storm of[FC][00][2D]Steel[FB][15]',
        17: ('[FC][02][30][08][F8][01][F9][02][FC][01][01]'
             "We can't have you[F7][FF][FB][10][FE][F7][08]"
             "tagging along to Japan.[F7][FF][FB][10][FE][F7][08]"
             "A shame, but[FD]you die here.[F7][FF][FB][10][FE][F7][08]"
             "Boys —[FD]send them under!![F7][FF][FB][15]"),
        18: '[FC][01][01][F8][01]At this rate, the ship[FD]will sink with us![F7][FF][FB][15]',
        19: ('[FC][02][30][08][FC][01][01][F8][01][F9][02]'
             "So this is the end...[F7][FF][FB][10][FE][F7][08]"
             "But don't think[FD]you've won.[F7][FF][FB][10][FE][F7][08]"
             "You'll die alongside[FD]my beloved pirate ship.[F7][FF][FB][10][FE][F7][08]"
             "Sink, and be gone.[F7][FF][FB][15]"),
        20: "[FC][01][01][F8][01]Did he get away...?[F7][FF][FB][15]",
        21: "[FC][01][01][F8][01]He escaped...[F7][FF][FB][15]",
        22: "Damn it!![FD]It's going to blow![F7][FF][FB][15]",
        23: "!![FD]It's going to blow![F7][FF][FB][15]",
        24: "[FC][01][01][F8][01]Why are[FD]Metal Frames here?[F7][FF][FB][15]",
        25: "[FC][01][01][F8][01]How can[FD]Metal Frames be here?[F7][FF][FB][15]",
        26: "Port![[FD]We're saved![F7][FF][FB][15]",
        27: "Port![[FD]We're saved![F7][FF][FB][15]",
        28: "[FC][01][01][F8][01]You mean to sink us[FD]along with the ship?[F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 14 — "Another Revenge"
    # Heroes wash up in a town with a fighting tournament; chasing
    # leads on DM Corp through the underground arena.
    # =====================================================================
    14: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][FC][01][04][FC][00][2D]Another [FC][00][2D]Revenge[FB][15]',
        17: ('[FC][01][01][F8][01]Somehow I survived...[F7][FF][FB][10][FE][F7][08]'
             "But...[FD]where am I?[F7][FF][FB][15]"),
        18: ('[FC][01][01][F8][01]Somehow I survived...[F7][FF][FB][10][FE][F7][08]'
             "But...[FD]where could I be?[F7][FF][FB][15]"),
        19: ('World Martial Arts Tourney?[F7][FF][FB][10][FE][F7][08]'
             "Sounds interesting...[F7][FF][FB][15]"),
        20: ('World Martial Arts Tourney?[F7][FF][FB][10][FE][F7][08]'
             "Maybe a clue[FD]is waiting there.[F7][FF][FB][15]"),
        21: "[FC][01][01][F8][01].....[F7][FF][FB][15]",
        22: ('[FC][01][01][F8][01][FC][02][5E][08][F9][04]'
             "Waaah...[F7][FF][FB][10][FE][F7][08]"
             "Papa... Papa...[F7][FF][FB][15]"),
        23: ('[F9][04]A tournament is being held[FD]in this town today.[F7][FF][FB][10][FE][F7][08]'
             "Word may be there[FD]about DM Corp...[F7][FF][FB][10][FE][F7][08]"
             "Care to join me?[F7][FF][FB][15]"),
        24: "Sure.[F7][FF][FB][15]",
        25: "Yes.[F7][FF][FB][15]",
        26: ('[FC][02][38][08][FC][01][01][F8][01][F9][02]'
             "Gwahahaha![FD]Any challengers out there?[F7][FF][FB][15]"),
        27: "Has the world really[FD]rotted this far?[F7][FF][FB][15]",
        28: ('Unforgivable.[F7][FF][FB][10][FE][F7][08]'
             "You all —[FD]I will never forgive![F7][FF][FB][15]"),
        29: "Why must you do[FD]such terrible things?[F7][FF][FB][15]",
        30: ('[FC][02][3C][08][F9][02]'
             "If you have the guts,[FD]step into the ring!![F7][FF][FB][15]"),
        31: ('[FC][01][01][F8][01][FC][02][38][08][F9][02]'
             "Next ones for hell[FD]would be you, eh?[F7][FF][FB][15]"),
        32: "If you wish to fight that much,[FD]do it in hell.[F7][FF][FB][15]",
        33: ('You lot are[F7][FF][FB][10][FE][F7][08]'
             "well-suited to[FD]a tournament in hell.[F7][FF][FB][15]"),
        34: ('[FC][02][3C][08][F9][02]'
             "Cheeky![FD]I'll knock you flat![F7][FF][FB][15]"),
        35: ('[FC][02][38][08][FC][01][01][F8][01][F9][02]'
             "We held this tournament[FD]to find a champion[F7][FF][FB][10][FE][F7][08]"
             "capable of[FD]defeating Krummbach.[F7][FF][FB][10][FE][F7][08]"
             "[FC][02][3C][08][F9][02]"
             "To avenge[FD]our master...[F7][FF][FB][15]"),
        36: "Krummbach...?[F7][FF][FB][15]",
        37: ('[FC][02][3C][08][F9][02]'
             "But most of those who[FD]came were no more[F7][FF][FB][10][FE][F7][08]"
             "than thugs chasing[FD]the prize money.[F7][FF][FB][10][FE][F7][08]"
             "By the time I knew it,[FD]things had come to this....[F7][FF][FB][15]"),
        38: "We're searching[FD]for Krummbach.[F7][FF][FB][15]",
        39: "We're searching[FD]for Krummbach.[F7][FF][FB][15]",
        40: ('[FC][02][38][08][F9][02]'
             "What?! Truly?![F7][FF][FB][10][FE][F7][08]"
             "Krummbach is on the[FD]artificial island ahead.[F7][FF][FB][10][FE][F7][08]"
             "The island lies just[FD]past the bridge.[F7][FF][FB][10][FE][F7][08]"
             "Please —[FD]avenge our master...[F7][FF][FB][15]"),
        41: "[FC][01][01][F8][01]Norton?![F7][FF][FB][15]",
        42: ("[F9][04]So you're the ones[FD]who destroyed the[F7][FF][FB][10][FE][F7][08]"
             "Jecaxin factory.[F7][FF][FB][15]"),
        43: "Yeah, but why[FD]are you here of all places?[F7][FF][FB][15]",
        44: "Yes, but how[FD]did you end up here?[F7][FF][FB][15]",
        45: "[F9][04]Come on, let's go.[F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 16 — "Uncharted Island"
    # Long scenario; back half repeats the Amy/Dick climax from scen_06.
    # =====================================================================
    16: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][FC][01][04][FC][00][2D]Uncharted [FC][00][2D]Island[FB][15]',
        17: ('[FC][01][01][F8][01][F9][02][FC][02][56][08]'
             "Kekeke, you fell[FD]right into the trap.[F7][FF][FB][15]"),
        19: ('[FC][01][01][FC][02][16][08][F8][01][F9][02]'
             "What're you doing here?[FD]Where is Lord Krummbach?[F7][FF][FB][15]"),
        20: "That's what we'd like[FD]to know ourselves.[F7][FF][FB][15]",
        21: "That's what we'd like[FD]to know![F7][FF][FB][15]",
        22: ('[FC][02][16][08][F9][02][FC][01][01]'
             "Heh — I see now.[FD]It's you lot,[F7][FF][FB][10][FE][F7][08]"
             "the fools defying[FD]Lord Krummbach.[F7][FF][FB][15]"),
        23: "And what if we are?[F7][FF][FB][15]",
        24: "And what if we are?[F7][FF][FB][15]",
        25: ('[FC][02][16][08][F9][02]'
             "Then I'll teach[FD]you a painful lesson!![F7][FF][FB][15]"),
        26: "Ngh... run, now![F7][FF][FB][15]",
        27: "Jim!![F7][FF][FB][15]",
        28: ('[FC][02][16][08][F8][01][F9][02][FC][01][01]'
             "Tch! So you survived[FD]after all.[F7][FF][FB][10][FE][F7][08]"
             "No matter —[FD]I'll finish you myself![F7][FF][FB][15]"),
        29: ('[FC][02][16][08][F8][01][F9][02][FC][01][01]'
             "That I should fall[FD]to the likes of you...[F7][FF][FB][10][FE][F7][08]"
             "But know this —[FD]from the very start,[F7][FF][FB][10][FE][F7][08]"
             "Lord Krummbach's[FD]victory was assured.[F7][FF][FB][10][FE][F7][08]"
             "No one[FD]can stop him.[F7][FF][FB][10][FE][F7][08]"
             "Not while those[FD]Enhanced Ones live...[F7][FF][FB][15]"),
        30: "What do you mean?![F7][FF][FB][15]",
        31: "What do you mean?![F7][FF][FB][15]",
        32: ('[FC][02][16][08][F9][02][FC][01][01]'
             "Heh heh heh, you'll[FD]find out soon enough...[F7][FF][FB][15]"),
        33: ('[FC][02][16][08][FC][01][01][F8][01][F9][02]'
             "I'll spare you[FD]for today!![F7][FF][FB][10][FE][F7][08]"
             "But next we meet[FD]will be your last!![F7][FF][FB][15]"),
        34: "Go — quickly![FD]And Krummbach...[F7][FF][FB][15]",
        35: "[FC][01][01][F8][01]Jim...[F7][FF][FB][15]",
        36: "[FC][01][01][F8][01]Don't worry —[FD]I won't die yet.[F7][FF][FB][15]",
        37: ('[FC][01][01][F8][01]Sorry,[FD]Amy.[F7][FF][FB][10][FE][F7][08]'
             "I won't be able[FD]to avenge you...[F7][FF][FB][10][FE][F7][08]"
             "But they will —[FD]I'm sure of them.[F7][FF][FB][10][FE][F7][08]"
             "Without a doubt...[F7][FF][FB][15]"),
        39: ('[F9][02][FC][01][01][FC][02][54][08][F8][01]'
             "You will not reach[FD]the artificial island.[F7][FF][FB][10][FE][F7][08]"
             "I'll take you with me[FD]when this factory blows.[F7][FF][FB][10][FE][F7][08]"
             "My lord Krummbach,[FD]rule this world![F7][FF][FB][15]"),
        40: ('[F9][04][F8][01][FC][01][01][FC][02][50][08]'
             "Thank goodness...[F7][FF][FB][10][FE][F7][08]"
             "That you would come[FD]all the way out here...[F7][FF][FB][10][FE][F7][08]"
             "Please — take this with you![F7][FF][FB][15]"),
        41: "This is —![FD]A Metal Frame?![F7][FF][FB][15]",
        42: "It's not a Metal Frame.[F7][FF][FB][15]",
        43: ('[F9][04][FC][01][01][FC][02][50][08]'
             "......[FD]Krummbach[F7][FF][FB][10][FE][F7][08]"
             "intends to scatter[FD]Metal Frames worldwide[F7][FF][FB][10][FE][F7][08]"
             "and start a war.[F7][FF][FB][10][FE][F7][08]"
             "This is a test unit,[FD]a Metal Frame,[F7][FF][FB][10][FE][F7][08]"
             "modified by my hand.[F7][FF][FB][10][FE][F7][08]"
             "I hoped it might[FD]be of use...[F7][FF][FB][10][FE][F7][08]"
             "This is all[FD]I am able to[F7][FF][FB][10][FE][F7][08]"
             "do for you[FD]as I am now...[F7][FF][FB][15]"),
        44: "Thank you.[F7][FF][FB][15]",
        45: "Thank you.[F7][FF][FB][15]",
        46: ('[FC][02][16][08][FC][01][01][F8][01][F9][02]'
             "You lot again?[F7][FF][FB][10][FE][F7][08]"
             "Seems you're truly[FD]eager for the afterlife.[F7][FF][FB][15]"),
        47: ('[F9][02][F8][01][FC][01][01][FC][02][54][08]'
             "Gegh![FD]Why are they here?![F7][FF][FB][15]"),
        48: "A Jecaxin factory[FD]way out here too?![F7][FF][FB][15]",
        49: "A Jecaxin factory[FD]way out here too?![F7][FF][FB][15]",
        50: ('[F9][02][F8][01][FC][01][01][FC][02][56][08]'
             "Bah —[CE]no helping it.[F7][FF][FB][10][FE][F7][08]"
             "Helheim![CE]Devour[FD]them whole!![F7][FF][FB][15]"),
        # Entries 51-72 mirror the scen_06 Amy/Dick climax — reuse those translations
        51: ('[F9][02][F8][01][FC][01][01][FC][02][54][08]'
             "M-my lord, what shall we do?[FD]They have come.[F7][FF][FB][10][FE][F7][08]"
             "[FC][02][56][08]Do not panic.[F7][FF][FB][10][FE][F7][08]"
             "Is this not a chance[FD]to see the research bear fruit?[F7][FF][FB][10][FE][F7][08]"
             "Amy![F7][FF][FB][10][FE][F7][08]"
             "Crush[FD]every last one of them![F7][FF][FB][15]"),
        52: "Amy?![F7][FF][FB][15]",
        53: "[FC][01][01][F8][01]Is this...[F7][FF][FB][10][FE][F7][08]really Amy?[F7][FF][FB][15]",
        54: "[FC][01][01][F8][01]Sh-she's huge![F7][FF][FB][15]",
        55: "[FC][01][01][F8][01]Amy...[F7][FF][FB][15]",
        56: ('[F9][04][FC][01][01][FC][02][44][08]'
             "Brother... I[FD]waited for so long.[F7][FF][FB][10][FE][F7][08]"
             "I waited for you[FD]to come for me.[F7][FF][FB][15]"),
        57: "Sorry I'm late.[F7][FF][FB][15]",
        58: ('[F9][04][FC][01][01][FC][02][44][08]'
             "No... it's all right...[FD]You came for me...[F7][FF][FB][10][FE][F7][08]"
             "That ribbon...[FD]looks good on you...[F7][FF][FB][15]"),
        59: "What are you saying?[FD]This was yours...[F7][FF][FB][15]",
        60: ('[F9][04][FC][01][01][FC][02][44][08]'
             "...It's all right.[F7][FF][FB][10][FE][F7][08]"
             "I... won't be able...[FD]to wear it any longer.[F7][FF][FB][15]"),
        61: "It can't be![F7][FF][FB][15]",
        62: ('[F9][04][FC][01][01][FC][02][44][08]'
             "...Take care of[FD]the ribbon...[FB][15]"),
        63: "[FC][01][01][F8][01]Amy...?![F7][FF]",
        64: "Amy!![F7][FF][FB][10]",
        65: "[FC][01][01][F8][01]To use Jecaxin[FD]even on a little girl...[F7][FF][FB][15]",
        66: "Krummbach...[FD]I will never forgive you.[F7][FF][FB][15]",
        67: "Krummbach...[FD]I will never forgive you.[F7][FF][FB][15]",
        68: "Uoooohhh![F7][FF][FB][15]",
        69: "[FC][01][01][F8][01]Dick!![F7][FF][FB][15]",
        70: ('[F9][02][FC][01][01][FC][02][54][08]'
             "Hm?![F7][FF][FB][10][FE][F7][08]"
             "The prototype...[FD]why is it here?[F7][FF][FB][10][FE][F7][08]"
             "[FC][02][56][08]Lord Krummbach[FD]must be told of this.[F7][FF][FB][15]"),
        71: ".....[F7][FF][FB][15]",
        72: "Wh-what?![F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 18 — "Wicked Capital"
    # Anti-Jecaxin vaccine subplot; back half reprises the Amy climax.
    # =====================================================================
    18: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][CE][FC][01][04][FC][00][2D]Wicked [FC][00][2D]Capital[FB][15]',
        17: ('[F9][04][F8][01][FC][01][01][FC][02][52][08]'
             "Beyond this point lies[FD]the Jecaxin research lab.[F7][FF][FB][10][FE][F7][08]"
             "Destroy it and you[FD]halt Jecaxin production.[F7][FF][FB][10][FE][F7][08]"
             ".....Jecaxin...[F7][FF][FB][10][FE][F7][08]"
             "If only Dr. Barclay[FD]were still alive,[F7][FF][FB][10][FE][F7][08]"
             "it would never have[FD]come to be used like this.[F7][FF][FB][15]"),
        18: "Rest easy.[FD]I'll erase Jecaxin myself.[F7][FF][FB][15]",
        19: "Rest easy.[FD]I'll erase Jecaxin.[F7][FF][FB][15]",
        20: ('[F9][04][FC][01][01][FC][02][52][08]'
             "Thank you.[F7][FF][FB][10][FE][F7][08]"
             "We have been[FD]developing a vaccine[F7][FF][FB][10][FE][F7][08]"
             "against Jecaxin.[F7][FF][FB][10][FE][F7][08]"
             "Once completed, it[FD]should save many lives.[F7][FF][FB][15]"),
        21: "An anti-Jecaxin vaccine?![F7][FF][FB][15]",
        22: ('[F9][04][FC][01][01][FC][02][52][08]'
             "Find a man named Yamaoka.[FD]He will lend his strength.[F7][FF][FB][10][FE][F7][08]"
             "Also, please take[FD]this ID card.[F7][FF][FB][10][FE][F7][08]"
             "It will surely help.[F7][FF][FB][15]"),
        23: "[FC][01][01][F8][01]Wh-what?[F7][FF][FB][15]",
        24: ('[F9][02][F8][01][FC][01][01][FC][02][54][08]'
             "M-my lord, what shall we do?[FD]They have come.[F7][FF][FB][10][FE][F7][08]"
             "[FC][02][56][08]Do not panic.[F7][FF][FB][10][FE][F7][08]"
             "Is this not a chance[FD]to see the research bear fruit?[F7][FF][FB][10][FE][F7][08]"
             "Amy![FB][10][FE]Crush[FD]every last one of them![F7][FF][FB][15]"),
        25: "Amy?![F7][FF][FB][15]",
        26: "[FC][01][01][F8][01]Is this...[F7][FF][FB][10][FE][F7][08]really Amy?[F7][FF][FB][15]",
        27: "[FC][01][01][F8][01]Sh-she's huge![F7][FF][FB][15]",
        28: "[FC][01][01][F8][01]Amy...[F7][FF][FB][15]",
        29: ('[F9][04][FC][01][01][FC][02][44][08]'
             "Brother... I[FD]waited for so long.[F7][FF][FB][10][FE][F7][08]"
             "I waited for you[FD]to come for me.[F7][FF][FB][15]"),
        30: "Amy...?!",
        31: "[FC][01][01][F8][01]To use Jecaxin[FD]even on a little girl...[F7][FF][FB][15]",
        32: "Krummbach...[FD]I will never forgive you.[F7][FF][FB][15]",
        33: "Krummbach...[FD]I will never forgive you.[F7][FF][FB][15]",
        34: "[FC][01][01][F8][01]Uoooohhh![F7][FF][FB][15]",
        35: "[FC][01][01][F8][01]Dick!![F7][FF][FB][15]",
        36: ('[F9][02][FC][01][01][FC][02][54][08]'
             "Hm?![F7][FF][FB][10][FE][F7][08]"
             "The prototype...[FD]why is it here?[F7][FF][FB][10][FE][F7][08]"
             "[FC][02][56][08]Lord Krummbach[FD]must be told of this.[F7][FF][FB][15]"),
        37: "Sorry I'm late.[F7][FF][FB][15]",
        38: ('[F9][04][FC][01][01][FC][02][44][08]'
             "No... it's all right...[FD]You came for me...[F7][FF][FB][10][FE][F7][08]"
             "That ribbon...[FD]looks good on you...[F7][FF][FB][15]"),
        39: "What are you saying?[FD]This was yours...[F7][FF][FB][15]",
        40: ('[F9][04][FC][01][01][FC][02][44][08]'
             "...It's all right.[F7][FF][FB][10][FE][F7][08]"
             "I... won't be able...[FD]to wear it any longer.[F7][FF][FB][15]"),
        41: "It can't be![F7][FF][FB][15]",
        42: ('[F9][04][FC][01][01][FC][02][44][08]'
             "...Take care of[FD]the ribbon...[FB][15]"),
        43: "[FC][01][01][F8][01]Amy!![F7][FF][FB][10]",
        44: "[FC][01][01][F8][01].....[F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 20 — "Riot"
    # Bart-tier pirate confronts heroes, then meta-frame production reveal.
    # =====================================================================
    20: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][CE][CE][CE][FC][01][04][FC][00][2D]Riot[FB][10][FB][15]',
        17: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "Wait![FD]Spare me![F7][FF][FB][10][FE][F7][08]"
             "I've had[FD]a change of heart.[F7][FF][FB][10][FE][F7][08]"
             "Let's bring down[FD]Krummbach together.[F7][FF][FB][10][FE][F7][08]"
             "Up ahead there's a[FD]powerful weapon stashed.[F7][FF][FB][10][FE][F7][08]"
             "If you forgive me,[F7][FF][FB][10][FE][F7][08]"
             "I'll let you[FD]have it for yourselves.[FB][15]"),
        18: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "I'll have the weapon[FD]ready and waiting.[F7][FF][FB][15]"),
        19: "We won't fall for[FD]talk like that.[F7][FF][FB][15]",
        20: "I won't be fooled.[F7][FF][FB][15]",
        21: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "Tch.[F7][FF][FB][10][FE][F7][08]"
             "If you saw through it,[FD]no helping it then.[F7][FF][FB][15]"),
        22: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "...Heh heh heh.[FD]A shame, but —[F7][FF][FB][10][FE][F7][08]"
             "Metal Frame production[FD]has already begun.[F7][FF][FB][10][FE][F7][08]"
             "Even if you destroy[FD]the factory now,[F7][FF][FB][10][FE][F7][08]"
             "this plan won't stop.[F7][FF][FB][15]"),
        23: "Whatever it takes,[FD]I will stop it.[F7][FF][FB][15]",
        24: "I will stop it.[FD]Without fail.[F7][FF][FB][15]",
        25: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "Had you let me deceive you,[FB][10][FE][F7][08]"
             "you'd have lived[FD]a touch longer!![F7][FF][FB][15]"),
        26: ('[F9][04][F8][01][FC][01][01][FC][02][52][08]'
             "So you've made it[FD]this far at last...[F7][FF][FB][10][FE][F7][08]"
             "The Metal Frame factory[FD]is just ahead.[F7][FF][FB][10][FE][F7][08]"
             "Please hurry.[F7][FF][FB][10][FE][F7][08]"
             "Vaccine development is[FD]progressing well.[F7][FF][FB][10][FE][F7][08]"
             "Once it is finished,[F7][FF][FB][10][FE][F7][08]"
             "it should save[FD]countless lives.[F7][FF][FB][10][FE][F7][08]"
             "As a scientist,[F7][FF][FB][10][FE][F7][08]"
             "I will do[FD]all I can.[F7][FF][FB][15]"),
        27: "Understood.[F7][FF][FB][10][FE][F7][08]Krummbach is mine[FD]to deal with.[F7][FF][FB][15]",
        28: "Understood.[F7][FF][FB][10][FE][F7][08]Krummbach is mine[FD]to deal with.[F7][FF][FB][15]",
        29: ('[F9][04][F8][01][FC][01][01][FC][02][52][08]'
             "Thank you.[F7][FF][FB][10][FE][F7][08]"
             "I, too, shall surely[FD]complete the vaccine.[F7][FF][FB][15]"),
        # scen_20 entries 30+
        30: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "I had the nuisance[FD]disposed of in advance.[F7][FF][FB][15][FE][F7][08]"
             "I have a gift[FD]prepared for you, too —[F7][FF][FB][10][FE][F7][08]"
             "explosives[FD]right beneath your feet!![F7][FF][FB][10][FE][F7][08]"
             "Gwahaha![FD]Vanish with the bridge!![F7][FF][FB][15]"),
        31: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "Damn it.[F7][FF][FB][10][FE][F7][08]"
             "Not enough[FD]explosives, was it...[F7][FF][FB][10][FE][F7][08]"
             "Then I'll have to[FD]finish you myself![F7][FF][FB][15]"),
        32: "[F8][01][FC][01][01]Only the Metal Frame[FD]factory remains.[F7][FF][FB][15]",
        33: "[F8][01][FC][01][01]Only the Metal Frame[FD]factory left.[F7][FF][FB][15]",
        34: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "Hm?![F7][FF][F7][08][FB][10][FE]"
             "You —[FD]Barclay's granddaughter.[F7][FF][F7][08][FB][10][FE]"
             "I remember you.[F7][FF][FB][15]"),
        35: "Huh?[F7][FF][FB][15]",
        36: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "Heh heh.[F7][FF][FB][10][FE][F7][08]"
             "What is the granddaughter[FD]of Dr. Barclay,[F7][FF][FB][10][FE][F7][08]"
             "Jecaxin's creator,[FD]doing in a place like this?[F7][FF][FB][10][FE][F7][08]"
             "Barclay, too, might[FD]have lived a little longer[F7][FF][FB][10][FE][F7][08]"
             "had he been wiser.[F7][FF][FB][10][FE][F7][08]"
             "He sealed his fate[FD]by defying Lord Krummbach.[F7][FF][FB][15]"),
        37: "Stop it!![F7][FF][FB][15]",
        38: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "Very well —[FD]you will die anyway.[F7][FF][FB][10][FE][F7][08]"
             "Alongside every fool[FD]in the world.[F7][FF][FB][10][FE][F7][08]"
             "Gugh.[F7][FF][FB][15]"),
        39: "Let's go, Elfin.[F7][FF][FB][15]",
        40: "[F8][01][FC][01][01].....[F7][FF][FB][15]",
        41: ('[F9][02][F8][01][FC][01][01][FC][02][30][08]'
             "A pile of scrap iron[FD]playing hero?[F7][FF][FB][10][FE][F7][08]"
             "Hmph.[FD]Foolish machine.[F7][FF][FB][10][FE][F7][08]"
             "Felling me changes[FD]nothing at all![F7][FF][FB][10][FE][F7][08]"
             "This plan[FD]will not be stopped!![F7][FF][FB][15]"),
        42: ('[F9][04][F8][01][FC][01][01][FC][02][52][08]'
             "You're doing well.[F7][FF][FB][10][FE][F7][08]"
             "Please —[FD]keep helping them.[F7][FF][FB][15]"),
    },
    # =====================================================================
    # SCEN 22 — "End of the Legend"
    # Yamaoka subplot; encounter with Lord J / Norton's history reveal.
    # =====================================================================
    22: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][CE][CE][FC][01][04][FC][00][2D]End of [FC][00][2D]the [FC][00][2D]Legend[FB][15]',
        17: ('[F9][04][F8][01][FC][01][01][FC][02][44][08]'
             "What are you doing,[FD]bursting in unannounced?[F7][FF][FB][15]"),
        18: ('We have business[FA]with Yamaoka.[F7][FF][FB][10][FE][F7][08]'
             "We must stop[FD]Krummbach's plan.[F7][FF][FB][15]"),
        19: ('Forgive us...[F7][FF][FB][10][FE][F7][08]'
             "We have no choice —[FD]this plan must be[F7][FF][FB][10][FE][F7][08]"
             "stopped, no matter what.[F7][FF][FB][15]"),
        20: ('[F9][04][FC][01][01][FC][02][44][08]'
             "Wait, please!![F7][FF][FB][10][FE][F7][08]"
             "Lord Yamaoka[FD]is not a bad man.[F7][FF][FB][10][FE][F7][08]"
             "It's just that he...[F7][FF][FB][15]"),
        21: "Sorry —[FD]we have no time.[F7][FF][FB][15]",
        22: "Forgive me —[FD]we have no time.[F7][FF][FB][15]",
        23: ('[F9][02][F8][01][FC][01][01][FC][02][40][08]'
             "Smashing[FD]my precious vase![F7][FF][FB][10][FE][F7][08]"
             "I won't forgive you.[F7][FF][FB][15]"),
        24: ('[FC][01][01][F8][01]Why does[FD]a man of your strength[F7][FF][FB][10][FE][F7][08]'
             "lend his hand[FD]to Krummbach?[F7][FF][FB][15]"),
        25: "[FC][01][01][F8][01]Why does[FD]one such as you...?[F7][FF][FB][15]",
        26: "If you used that strength[FD]for justice...[F7][FF][FB][15]",
        27: ('[F9][02][FC][01][01][FC][02][40][08]'
             "Hmph.[FD]Justice, you say?[F7][FF][FB][10][FE][F7][08]"
             "Such a nostalgic word.[F7][FF][FB][15]"),
        28: ('[F9][02][FC][01][01][FC][02][40][08]'
             "It is not that I[FD]fear Krummbach.[F7][FF][FB][10][FE][F7][08]"
             "Krummbach holds[FD]a trump card —[F7][FF][FB][10][FE][F7][08]"
             "and that I have[FD]come to dread.[F7][FF][FB][15]"),
        29: "You mean the Metal Frames?[F7][FF][FB][15]",
        30: "The Metal Frames?[F7][FF][FB][15]",
        31: ('[F9][02][FC][01][01][FC][02][40][08]'
             "The Metal Frames[F7][FF][FB][10][FE][F7][08]"
             "are toys[FD]compared to it.[F7][FF][FB][10][FE][F7][08]"
             "But you...[F7][FF][FB][10][FE][F7][08]"
             "you might be able[FD]to defeat it...[F7][FF][FB][10][FE][F7][08][F7][FF].....[FB][15]"),
        32: "!?[F7][FF][FB][10][FE][F7][08]Yamaoka!![F7][FF][FB][15]",
        33: ('[F9][02][F8][01][FC][01][01][FC][02][40][08]'
             "So you're the fools[F7][FF][FB][10][FE][F7][08]"
             "defying[FD]Lord Krummbach.[F7][FF][FB][15]"),
        34: ('Do not get in our way.[FD]Krummbach\'s plan must be[F7][FF][FB][10][FE][F7][08]'
             "stopped, or so many[FD]more will die...[F7][FF][FB][15]"),
        35: ('Don\'t get in our way.[FD]Krummbach\'s plan must be[F7][FF][FB][10][FE][F7][08]'
             "stopped, or so many[FD]more will die...[F7][FF][FB][15]"),
        36: ('[F9][02][FC][01][01][FC][02][40][08]'
             "Stop the plan, you say?[FD]Don\'t make me laugh.[F7][FF][FB][10][FE][F7][08]"
             "That strength —[FD]I shall test it myself.[F7][FF][FB][10][FE][F7][08]"
             "Come on!![F7][FF][FB][15]"),
        37: "Who are you...?[F7][FF][FB][15]",
        38: "Who could you be...?[F7][FF][FB][15]",
        39: ('[F9][02][FC][01][01][FC][02][40][08]'
             "...I am a beaten cur.[FD]But you are not.[F7][FF][FB][10][FE][F7][08]"
             "Listen well — you must win![F7][FF][FB][10][FE][F7][08]"
             "And then[FD]you must stop this plan.[F7][FF][FB][15]"),
        40: ('[F9][02][FC][01][01][FC][02][40][08][F7][FF].....[FB][10][FE][F7][08]'
             "Watching you,[FD]I feel that I, too,[F7][FF][FB][10][FE][F7][08]"
             "must do[FD]something.[F7][FF][FB][15][FE][F7][08]"
             "I shall go to[FD]Dr. Barclay's lab.[F7][FF][FB][10][FE][F7][08]"
             "The vaccine[FD]may yet be there...[F7][FF][FB][15]"),
        41: ('[F9][02][F8][01][FC][01][01][FC][02][40][08]'
             "Your skills have grown,[FD]Norton.[F7][FF][FB][15]"),
        42: ('Why do you know my name?[FD]Could it be...[F7][FF][FB][10][FE][F7][08]'
             "Lord J...?[F7][FF][FB][15]"),
        43: ('[F9][02][FC][01][01][FC][02][40][08]'
             "Do not call me[FD]by that name.[F7][FF][FB][10][FE][F7][08]"
             "I am not[FD]the man I once was.[F7][FF][FB][10][FE][F7][08]"
             "Only a beaten cur...[F7][FF][FB][15]"),
        44: "Lord J...[F7][FF][FB][15]",
        45: ('[F9][02][FC][01][01][FC][02][40][08]'
             "I wished to be strong —[FD]stronger than anyone.[F7][FF][FB][10][FE][F7][08]"
             "But when I saw[FD]the Enhanced Ones[F7][FF][FB][10][FE][F7][08]"
             "Krummbach had made,[FD]I changed.[F7][FF][FB][10][FE][F7][08]"
             "A single human had[FD]planted dread in me.[F7][FF][FB][10][FE][F7][08]"
             "Norton —[FD]say nothing, just flee.[F7][FF][FB][10][FE][F7][08]"
             "No one alive[FD]can beat that one.[F7][FF][FB][15]"),
        46: ('...I cannot[FD]run from this.[F7][FF][FB][10][FE][F7][08]'
             "Too many lives[FD]hang in the balance.[F7][FF][FB][15]"),
        47: ('[F9][02][FC][01][01][FC][02][40][08]'
             "...I see.[FD]That is just like you.[F7][FF][FB][10][FE][F7][08]"
             "Without fail —[FD]come back alive.[F7][FF][FB][15]"),
        48: "Yeah![F7][FF][FB][15]",
        49: ".....[F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 24 — "Broken Gears" (Krummbach POV)
    # Long sequence of Krummbach reacting to the heroes' progress. Lots of
    # short villain quips + status reports.
    # =====================================================================
    24: {
        16: 'They have broken out of[FD]the factory.[F7][FF][FB][15]',
        17: ('Oho — not bad at all.[FD]Summon Captain Burnett.[F7][FF][FB][15]'),
        18: 'Yes, my lord![F7][FF][FB][15]',
        19: 'Burnett —[FD]their fate is in your hands.[F7][FF][FB][15]',
        20: ('Leave it to me.[FD]I\'ll reduce them to[F7][FF][FB][10][FE][F7][08]'
             "missile-dust.[F7][FF][FB][15]"),
        21: 'The plan succeeded.[F7][FF][FB][15]',
        22: ('I see —[FD]so it blew up.[F7][FF][FB][10][FE][F7][08]'
             "Their lives are worth no[FD]more than one shoddy factory.[F7][FF][FB][15]"),
        23: ('Splendid, Paliko.[FD]All according to plan.[F7][FF][FB][10][FE][F7][08]'
             "Do you understand[FD]this joy of mine?[F7][FF][FB][15]"),
        24: ('Nyaaan — oho, you do.[FD]Hahahaha![F7][FF][FB][15]'),
        25: ('What — both[FD]of those brothers, beaten?![F7][FF][FB][10][FE][F7][08]'
             "Useless wretches.[F7][FF][FB][10][FE][F7][08]"
             "They will be making[FD]for the research lab.[F7][FF][FB][10][FE][F7][08]"
             "Do not let them in.[F7][FF][FB][15]"),
        26: ('We have captured a woman[FD]snooping about Jecaxin.[F7][FF][FB][10][FE][F7][08]'
             "This is her dossier:[F7][FF][FB][10][FE][F7][08]"
             "Maria Norton.[F7][FF][FB][10][FE][F7][08]"
             "Neo-Cisco Times[FD]journalist.[F7][FF][FB][10][FE][F7][08]"
             "Scooped the Cyber-Clone[FD]project.[F7][FF][FB][15]"),
        27: ('Hmm — I shall meet her[FD]without delay.[F7][FF][FB][10][FE][F7][08]'
             "Hm? Is there more?[F7][FF][FB][10][FE][F7][08]"
             "Hah! The researcher,[FD]she escaped...[F7][FF][FB][10][FE][F7][08][F7][FF].....[FB][10][FE][F7][08]"
             "I understand.[FD]Find her at once.[F7][FF][FB][15]"),
        28: "Truly,[FD]what has become of things?[F7][FF][FB][15]",
        29: "Lord Krummbach!![F7][FF][FB][15]",
        30: "Why are you so panicked?[F7][FF][FB][15]",
        31: ('Yes —[FD]a report has come[F7][FF][FB][10][FE][F7][08]'
             "that they are heading[FD]for the Metal Frame ship.[F7][FF][FB][15]"),
        32: "What?! Do not let them[FD]anywhere near the ship![F7][FF][FB][15]",
        33: ('Lord Burnett is there,[FD]so we need not worry.[F7][FF][FB][15]'),
        34: "Hmmm...[F7][FF][FB][15]",
        35: "Burnett, hm...[FD]I must make my next move.[F7][FF][FB][15]",
        36: "Lord Krummbach![F7][FF][FB][15]",
        37: "Lord Krummbach![F7][FF][FB][15]",
        38: ('Terrible news![FD]Word has come that the[F7][FF][FB][10][FE][F7][08]'
             "Japan factory[FD]has been destroyed.[F7][FF][FB][15]"),
        39: "What?![FD]Summon Yamaoka.[F7][FF][FB][15]",
        40: "I hear the factory[FD]has been destroyed.[F7][FF][FB][15]",
        41: "I let them[FD]board the ship.[F7][FF][FB][15]",
        42: "Tch — what was[FD]Burnett doing?[F7][FF][FB][15]",
        43: "W-well, you see...[F7][FF][FB][15]",
        44: ('Enough![FD]If the ship cannot be saved,[F7][FF][FB][10][FE][F7][08]'
             "activate the Metal Frames.[F7][FF][FB][15]"),
        45: "But, my lord —[FD]that is...[F7][FF][FB][15]",
        46: "Silence.[FD]Just do as I say.[F7][FF][FB][15]",
        47: "They appear to be[FD]heading for the lab.[F7][FF][FB][15]",
        48: "Tighten the guard.[FD]Do not let them near it.[F7][FF][FB][15]",
        49: "My deepest apologies.[F7][FF][FB][15]",
        50: "The Metal Frames[FD]have been destroyed.[F7][FF][FB][15]",
        51: "Impossible![FD]And they have crossed[F7][FF][FB][10][FE][F7][08]into Japan, it seems.[F7][FF][FB][15]",
        52: "Halt production.[FD]Enhance the Metal Frames.[F7][FF][FB][15]",
        53: "(Damn it...)[F7][FF][FB][10][FE][F7][08].....[FD]I must buy a new vase.[F7][FF][FB][15]",
        54: ('To dare to take my life —[F7][FF][FB][10][FE][F7][08]'
             "rats should know[FD]their place as rats.[F7][FF][FB][15]"),
        55: "Summon Calsonic.[F7][FF][FB][15]",
        56: "Lord Krummbach has[FD]departed for the airport.[F7][FF][FB][15]",
        57: ('Even if they manage[FD]to reach the airport,[F7][FF][FB][10][FE][F7][08]'
             "Calsonic will deal with them.[F7][FF][FB][15]"),
        58: "Just so, my lord.[F7][FF][FB][15]",
        59: "A toast — shall I buy[FD]yet another new vase?[F7][FF][FB][15]",
        60: "The transport's[FD]destruction is confirmed.[F7][FF][FB][15]",
        61: ('Hm — so it crashed.[FD]But knowing them,[F7][FF][FB][10][FE][F7][08]'
             "they may yet live.[F7][FF][FB][15]"),
        62: ('Rest easy.[FD]Even if they survived,[F7][FF][FB][10][FE][F7][08]'
             "no outsider ever leaves[FD]the Black Area alive.[F7][FF][FB][15]"),
        63: "Hahahaha — I see.[F7][FF][FB][15]",
        64: ("The ship's destruction[FD]is confirmed.[F7][FF][FB][10][FE][F7][08]"
             "Currently recovering[FD]the Metal Frames.[F7][FF][FB][15]"),
        65: "Hm. Summon Calsonic.[F7][FF][FB][15]",
        66: "Dispose of them[FD]without fail.[F7][FF][FB][15]",
        67: "You called?[F7][FF][FB][15]",
        68: "Indeed —[FD]I have a task for you.[F7][FF][FB][15]",
        69: "Whatever you wish.[F7][FF][FB][15]",
        70: "Confirm[FD]their corpses.[F7][FF][FB][15]",
        71: "As you command.[F7][FF][FB][15]",
        72: "They have begun[FD]crossing the bridge.[F7][FF][FB][15]",
        73: "Launch the helicopters[FD]at once.[F7][FF][FB][15]",
        74: "..........[FD]Yes, my lord.[F7][FF][FB][15]",
        75: "Shall we sortie as well?[F7][FF][FB][15]",
        76: "Your strength[FD]will not be needed.[FB][10][FE][F7][08]Step back.[F7][FF][FB][15]",
        77: "As you wish.[F7][FF][FB][15]",
        78: '[F9][00][FC][01][01][FB][10][FD][CE][FC][01][04][FC][00][2D]Broken [FC][00][2D]Gears[FB][15]',
        80: "So you have come[FD]this far at last.[F7][FF][FB][15]",
        81: "Th-they have entered[FD]the factory.[F7][FF][FB][15]",
        82: "Fool!![FD]I know that already![F7][FF][FB][15]",
        83: "..........[FD]Shall we continue[F7][FF][FB][10][FE][F7][08]Metal Frame production?[F7][FF][FB][15]",
        84: "Of course.[F7][FF][FB][15]",
        85: "I am sorry.[F7][FF][FB][15]",
        86: "Every last one of them[FD]is useless.[F7][FF][FB][15]",
        87: ('All shall be ruled —[F7][FF][FB][10][FE][F7][08]'
             "You... and the world.[F7][FF][FB][15]"),
        88: ".....[F7][FF][FB][15]",
        89: ('Th-that I... should fall[FD]to mere robots...[F7][FF][FB][10][FE][F7][08]'
             "How infuriating...[F7][FF][FB][15]"),
        90: ('W-well, color me surprised.[FD]To have come this far...[F7][FF][FB][15]'),
        91: "This ends now![FD]Krummbach!![F7][FF][FB][15]",
        92: "This ends now![FD]Krummbach!![F7][FF][FB][15]",
        96: ('.....[FD]Such a tiresome lot.[F7][FF][FB][10][FE][F7][08]'
             "Mean to defeat me, do you?[FD]Defeat me —[F7][FF][FB][10][FE][F7][08]"
             "when the world is about[FD]to become mine?[F7][FF][FB][10][FE][F7][08]"
             "I will not be hindered now!![F7][FF][FB][15]"),
        97: "Kira! Kidou![FD]The rest is yours![F7][FF][FB][15]",
        98: ('Ha![FD]You will come no nearer[F7][FF][FB][10][FE][F7][08]'
             "to Lord Krummbach.[F7][FF][FB][10][FE][F7][08]"
             "Become prey to our[FD]Togakure-style killing arts![F7][FF][FB][10][FE][F7][08]"
             "Come!![F7][FF][FB][15]"),
        99: ('...I see...[FD]more than the rumors said...[F7][FF][FB][10][FE][F7][08]'
             "But...[FD]you will not best Lord Berg![F7][FF][FB][15]"),
        100: "Yes![F7][FF][FB][15]",
    },
    # =====================================================================
    # SCEN 26 — "Shura" (Final showdown — Berg the Enhanced One)
    # Robotic katakana speech rendered as stilted/ALL-CAPS English.
    # =====================================================================
    26: {
        16: '[F9][00][FC][01][01][FB][10][FD][CE][CE][CE][CE][FC][01][04][FC][00][2D]Shu[FC][00][2D]ra[FB][15]',
        17: "Hahaha![FD]Looking troubled, are we?[F7][FF][FB][15]",
        18: "Krummbach!![F7][FF][FB][15]",
        19: ('Whether you make it out[FD]of there or not,[F7][FF][FB][10][FE][F7][08]'
             "is up to your own strength.[FD]Hahahaha![F7][FF][FB][15]"),
        20: ".....[F7][FF][FB][15]",
        21: "No more running, Krummbach![F7][FF][FB][15]",
        22: "No more running, Krummbach![F7][FF][FB][15]",
        24: ('Don\'t get carried away[FD]just because you[F7][FF][FB][10][FE][F7][08]'
             "beat a Metal Frame.[F7][FF][FB][15]"),
        25: ('Oho — for scrap to come[FD]this far is impressive.[F7][FF][FB][10][FE][F7][08]'
             "But I do not accept[FD]anything incomplete.[F7][FF][FB][10][FE][F7][08]"
             "Be gone.[F7][FF][FB][15]"),
        26: "This time —[FD]Jecaxin ends here!![F7][FF][FB][15]",
        27: ('You hate Jecaxin that much?[F7][FF][FB][10][FE][F7][08]'
             "I merely gave your father[FD]what he yearned for.[F7][FF][FB][10][FE][F7][08]"
             "Kintaak was impatient.[F7][FF][FB][10][FE][F7][08]"
             "He happily used the[FD]incomplete Jecaxin.[F7][FF][FB][15]"),
        28: ('Is that all you have to say?[F7][FF][FB][10][FE][F7][08]'
             "Vanish from this world[FD]along with Jecaxin!![F7][FF][FB][15]"),
        29: "Father's killer —[FD]I'll have my revenge!![F7][FF][FB][15]",
        30: ('Gwahahaha![FD]That mercenary, Harry —[F7][FF][FB][10][FE][F7][08]'
             "you truly thought[FD]he was your father?[F7][FF][FB][10][FE][F7][08]"
             "It was I who made you!![F7][FF][FB][10][FE][F7][08]"
             "A failed prototype![F7][FF][FB][15]"),
        31: "SILENCE!!!![F7][FF][FB][15]",
        32: ('So — a little of[FD]your power awakens.[F7][FF][FB][10][FE][F7][08]'
             "But that is[FD]nothing worth speaking of![F7][FF][FB][15]"),
        33: "There's nowhere left, Krummbach![F7][FF][FB][15]",
        34: ('You think so?[FD]Sadly for you,[F7][FF][FB][10][FE][F7][08]'
             "I have a trump card.[F7][FF][FB][10][FE][F7][08]"
             "Has it not been said —[FD]none can stop me?[F7][FF][FB][15]"),
        35: ('For Amy...[FD]and the ribbon I wore —[F7][FF][FB][10][FE][F7][08]'
             "I swear to defeat you!![F7][FF][FB][15]"),
        36: ('...This is my final plan.[FD]I shall end it now!![F7][FF][FB][15]'),
        37: "NOW. ALL NUISANCES.[FD]ARE GONE.[F7][FF][FB][15]",
        38: "So this is the trump card![F7][FF][FB][15]",
        39: "This is the trump card?![F7][FF][FB][15]",
        40: ('For all those who lost[FD]someone irreplaceable —[F7][FF][FB][10][FE][F7][08]'
             "you shall be made to pay![F7][FF][FB][15]"),
        41: ("You — Barclay's[FD]granddaughter, no?[F7][FF][FB][10][FE][F7][08]"
             "Had he not insisted on[FD]a Jecaxin vaccine,[F7][FF][FB][10][FE][F7][08]"
             "he might still have been[FD]of use to me.[F7][FF][FB][10][FE][F7][08]"
             "Such a waste.[F7][FF][FB][15]"),
        42: ("You still don't see it[FD]at all, do you?[F7][FF][FB][10][FE][F7][08]"
             "A person's grief!![F7][FF][FB][15]"),
        43: ('McCoy. Bart. Harry.[FD]Can you hear me?[F7][FF][FB][10][FE][F7][08]'
             "If you can —[FD]lend me your strength...[F7][FF][FB][15]"),
        44: ('What are you mumbling?[FD]You think you[F7][FF][FB][10][FE][F7][08]'
             "can defeat me?[F7][FF][FB][15]"),
        45: ('(What is Berg doing?)[F7][FF][FB][10][FE][F7][08]'
             "(Will he never wake?!)[F7][FF][FB][10][FE][F7][08]"
             ".....[FD]Damn it![F7][FF][FB][10][FE][F7][08]"
             "Then I shall fight[FD]you myself!![F7][FF][FB][15]"),
        46: ('To enter this chamber...[F7][FF][FB][10][FE][F7][08]'
             "So Yamaoka did betray me.[F7][FF][FB][10][FE][F7][08]"
             "I knew his intent[FD]all along,[F7][FF][FB][10][FE][F7][08]"
             "but to come to this[FD]is a touch disappointing.[F7][FF][FB][15]"),
        47: ('Impossible — how...[FD]could this be?[F7][FF][FB][10][FE][F7][08]'
             "Beaten by mere Metal Frames...[F7][FF][FB][15]"),
        48: ('I-impossible.[F7][FF][FB][10][FE][F7][08]'
             "There is no way I could lose![F7][FF][FB][10][FE][F7][08]"
             "Why, why is Berg[FD]not waking?[F7][FF][FB][10][FE][F7][08]"
             "That cursed Berg —[FD]could it be...?[F7][FF][FB][10][FE][F7][08]"
             "Geuwabh![F7][FF][FB][15]"),
        49: "!!![F7][FF][FB][15]",
        50: ('I AM. BERG.[F7][FF][FB][10][FE][F7][08]'
             "ALL. SHALL BE. DESTROYED.[F7][FF][FB][10][FE][F7][08]"
             "I FIGHT BY[FD]MY OWN WILL NOW.[F7][FF][FB][10][FE][F7][08]"
             "NO COMMAND[FD]SHALL I OBEY![F7][FF][FB][10][FE][F7][08]"
             "I SHALL[FD]SHATTER YOU ALL![F7][FF][FB][15]"),
        51: "I'll defeat you and[FD]end this fight![F7][FF][FB][15]",
        52: "I'll defeat you and[FD]end this fight![F7][FF][FB][15]",
        53: "I. WILL. CRUSH. YOU.[F7][FF][FB][15]",
        54: ('.....SO YOU MEAN TO[FD]BEAT ME WITH THAT?[F7][FF][FB][10][FE][F7][08]'
             "AMUSING.[F7][FF][FB][10][FE][F7][08]"
             "DO NOT[FD]UNDERESTIMATE ME!![F7][FF][FB][15]"),
        55: ('YOU... SEEM TO BE[FD]AN ENHANCED ONE LIKE ME.[F7][FF][FB][10][FE][F7][08]'
             "BUT YOU ARE[FD]ONLY A PROTOTYPE.[F7][FF][FB][10][FE][F7][08]"
             "YOU CANNOT[FD]DEFEAT ME![F7][FF][FB][15]"),
        57: "Silence!![FD]Do not call me a prototype![F7][FF][FB][15]",
        58: ('YOU DARE COMMAND ME?[F7][FF][FB][10][FE][F7][08]'
             "INSOLENT.[FD]I SHALL ERASE YOU NOW!![F7][FF][FB][15]"),
        59: ('I HAVE LOST...[FD]I — defeated...[F7][FF][FB][10][FE][F7][08]'
             "ALL I WAS TAUGHT[FD]WAS TO FIGHT,[F7][FF][FB][10][FE][F7][08]"
             "TO DESTROY EVERYTHING...[F7][FF][FB][10][FE][F7][08]"
             "BUT YOU ARE DIFFERENT...[F7][FF][FB][10][FE][F7][08]"
             "HOW... CAN YOU FIGHT[FD]LIKE THIS...?[F7][FF][FB][15]"),
        60: ('IN ME LIES[FD]MANY HOPES.[F7][FF][FB][10][FE][F7][08]'
             "GUARD THE FUTURE.[FD]GUARD THE PEACE...[F7][FF][FB][15]"),
        61: ('.....IS THAT[FD]YOUR STRENGTH?[F7][FF][FB][10][FE][F7][08]'
             "I HAD NOTHING[FD]TO GUARD AT ALL.[F7][FF][FB][15]"),
        62: ('.....BEAUTIFUL.[F7][FF][FB][10][FE][F7][08]'
             "IS THIS WHAT YOU[FD]TRIED TO PROTECT...?[F7][FF][FB][15]"),
        63: ('I have comrades who[FD]always stand by me...[F7][FF][FB][10][FE][F7][08]'
             "So no matter what,[FD]I did not want to lose[F7][FF][FB][10][FE][F7][08]"
             "my comrades —[FD]or the future[F7][FF][FB][10][FE][F7][08]"
             "we all tried to guard.[F7][FF][FB][15]"),
        64: ('I had comrades who[FD]always stood by me...[F7][FF][FB][10][FE][F7][08]'
             "So no matter what,[FD]I did not want to lose[F7][FF][FB][10][FE][F7][08]"
             "my comrades —[FD]or the future[F7][FF][FB][10][FE][F7][08]"
             "we all tried to guard.[F7][FF][FB][15]"),
        65: ('I UNDERSTAND, NOW.[FD]GOOD.[F7][FF][FB][10][FE][F7][08]'
             "WITH THIS[FD]I, TOO, MAY REST[F7][FF][FB][10][FE][F7][08]"
             "AT LAST... AT... LAST.[F7][FF][FB][15]"),
        66: ('WHY?[FD]BY ALL CALCULATIONS[F7][FF][FB][10][FE][F7][08]'
             "I COULD NOT LOSE.[F7][FF][FB][15]"),
        67: ('THE WISH FOR PEACE...[FD]I SEE NOW.[F7][FF][FB][10][FE][F7][08]'
             "OF COURSE I COULD NOT[FD]DEFEAT YOU.[F7][FF][FB][15]"),
        68: "Heh-heh-heh-heh.[F7][FF][FB][15]",
        69: ('METAL FRAME[FD]LOCKOFF RELEASE[F7][FF][FB][10][FE][F7][08]'
             "IN 15 MINUTES.[F7][FF][FB][15]"),
        70: ('Not quite to plan —[FD]but my project[F7][FF][FB][10][FE][F7][08]'
             "is about to be complete.[F7][FF][FB][15]"),
    },
}


# ---------------------------------------------------------------------------
# File rewriter
# ---------------------------------------------------------------------------

def apply_translations(scen_id: int) -> tuple[int, int]:
    """Apply TRANSLATIONS[scen_id] to data/en/scenario_NN.txt. Returns
    (replaced, total) count."""
    if scen_id not in TRANSLATIONS:
        raise SystemExit(f"no translations defined for scenario {scen_id:02d}")
    repl = TRANSLATIONS[scen_id]
    src = EN_DIR / f"scenario_{scen_id:02d}.txt"
    text = src.read_text(encoding="utf-16")

    # Parse into (header, body) pairs and rebuild
    parts = re.split(r"(<<\$\d+:\d+\[\$\d+\]>>)\n", text)
    out_lines = []
    replaced = 0
    total = 0
    for i in range(1, len(parts), 2):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        body = body.rstrip("\n")
        m = re.match(r"<<\$\d+:(\d+)\[\$\d+\]>>", header)
        idx = int(m.group(1)) if m else -1
        total += 1
        if idx in repl:
            body = repl[idx]
            replaced += 1
        out_lines.append(f"{header}\n{body}\n")
    content = "".join(out_lines)

    # Atomic write as UTF-16 LE WITH BOM (matches input format)
    fd, tmp = tempfile.mkstemp(
        dir=str(src.parent),
        prefix=f".{src.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(content)
        os.replace(tmp, src)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return replaced, total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scen", help="Scenario id (06, 08, 10, ..., 26)")
    args = ap.parse_args()
    scen_id = int(args.scen, 10)
    rep, tot = apply_translations(scen_id)
    print(f"scen_{scen_id:02d}: {rep}/{tot} entries translated")


if __name__ == "__main__":
    main()
