# Rushing Beat Shura: The Eternal Conflict

**A complete English fan-translation of ラッシング・ビート修羅 (*Rushing Beat Shura*) for the Super Famicom.**

> You must supply your own legally-obtained Japanese ROM. This project distributes
> only a **patch** (the differences between the Japanese and English ROMs) — not
> the game itself.

---

## About the game

*Rushing Beat Shura* (1994, Jaleco) is the third entry in the *Rushing Beat*
beat-'em-up series — known in North America as **Rival Turf!**, **Brawl Brothers**,
and **The Peace Keepers**. The third game was released **only in Japan**; the
North American release, *The Peace Keepers*, was substantially altered (renamed
characters, reworked story and dialogue, and content changes).

This patch translates the **original Japanese release** into English, keeping its
own story, characters, and tone rather than reverting to the altered Peace Keepers
localization.

## Translation & localization notes

- The full in-game script is translated: story cutscenes, the multi-path scenario
  dialogue (all 15 scenario branches), the opening crawl, the per-character ending
  narration screens, on-screen character/HUD names, and the special-move name plates.
- Character and place names follow the **Japanese** version's intent (transliterated
  from katakana), not the PeaceKeepers renames. There are a couple localization choices
  some may see as controversial, but are minimal.
- The original font had no Latin alphabet suited to English text, so the translation
  ships the same font that was used in PeaceKeepers -- a 8×16 Latin font and a tightened 
  text renderer that fits ~32 characters per line, plus a 24-bit text-pointer engine so
  English lines aren't limited to the cramped Japanese string budget.
- The patched ROM is expanded from 2 MB to 4 MB to hold the larger English script and
  re-rendered word-art (I didn't try very hard to cram anything into available space).

## Status

**English: 1.2 release.** The English translation is complete and the build is verified.

**Brazilian Portuguese (`pt-BR`): in progress — unreleased.** A Brazilian-Portuguese
translation is being prepared on the **`br-pt`** branch. On this branch the build is
wired to produce the pt-BR ROM **out of the box** — `project.toml` sets
`build_lang = "br_pt"`, so `scripts/build.sh` reads the script from **`data/br_pt/`**
(the 15 `scenario_*.txt`, `char_names.txt`, `intro.txt`, `narration_screens.txt`) and the
`tables/rbshura_br_pt.tbl` encoding, and writes `out/rbshura_br_pt.sfc`. (`en_data_dir`
still points only at the untouched English reference in `data/en/`.)

It is **not released**: `data/br_pt/` currently holds a copy of the English text as a
translation starting point, so no actual Portuguese text exists yet. The engine
groundwork is in place — the `pt-BR` encoding table, the accented-glyph set
(`Éáéíóúâêôàãõç`), and a relocated/extended font at `$E2` with the renderers' font base
repointed so the extra glyphs fit (the original `$100000` font is full). The font
relocation is built and audit-clean but **still needs in-emulator verification** that
all text paths render correctly. No `pt-BR` patch is available yet.

### Changelog

**Unreleased (`br-pt` branch)**
- Brazilian-Portuguese build, wired to build out of the box via `build_lang = "br_pt"`
  in `project.toml`: `data/br_pt/` script tree, `tables/rbshura_br_pt.tbl` referenced by
  all scenario/intro/narration tables, the Portuguese accented-character glyph set, and a
  relocated/extended font at `$E2`. `en_data_dir` keeps pointing only at the English
  reference (`data/en/`).
- Windows helper scripts for contributors (`scripts/win/`): one-shot environment
  setup, a script-editor launcher, a build wrapper, and a Portuguese `README.pt-BR.md`.

**1.2**
- Script/dialogue pass: fixed lines that ran past the dialog-box width
  (text running off-screen), including a few malformed line-break codes —
  found with a new width-overflow checker added to the script editor.
- Translation corrections and refinements across several scenarios, including
  issues from a user report and lines re-evaluated after seeing them in-game.

**1.1**
- Fixed a background-graphics corruption on the Metal Frame Factory stage. The
  fix that converts the per-character ending/intro narration screens to the
  English font was hooking a *shared* screen-rendering routine, so it also ran
  during normal gameplay and garbled the stage backdrop. It is now gated to run
  only for the narration screens.
- Minor script/dialogue corrections.

**1.0**
- Initial complete English release.

---

## How to apply the patch

You need an **unheadered** Japanese *Rushing Beat Shura* ROM:

|           | |
|-----------|---|
| File size | `2,097,152` bytes (2 MB) |
| CRC-32    | `0A2E4C2F` |
| MD5       | `325A9D637C9F6E7211B2D413EE1FEF3D` |
| SHA-1     | `0381086AD61745FB7AAA0B3950434EEF586D3989` |
| SHA-256 | `00e78318926e5cae79bce0535fddd3dccaa732f5c70e43acefc2769a9899eaed` |

The patcher verifies this automatically (and auto-strips a 512-byte copier header if
present). The result is a 4 MB English ROM named **`Rushing Beat Shura (English).sfc`**,
written next to your input ROM.

### Easiest: the bundled patcher

**Windows** — download **`apply_patch.exe`** from the release, then either:
- **Double-click it** → a dialog asks you to pick your Japanese ROM, or
- **Drag your ROM file onto `apply_patch.exe`**.

**macOS / Linux** — download **`apply_patch.py`** (needs Python 3.9+; it uses only the
standard library). Then either:
- Run `python3 apply_patch.py` → a file dialog opens, or
- Run `python3 apply_patch.py "/path/to/your_rom.sfc"`, or
- Drag your ROM onto the script if your file manager runs `.py` with Python.

  > The file dialog needs Tk. If you get a Tk error, install it:
  > - Debian/Ubuntu: `sudo apt install python3-tk`
  > - Fedora: `sudo dnf install python3-tkinter`
  > - Arch: `sudo pacman -S tk`
  > - macOS (Homebrew Python): `brew install python-tk`
  >
  > Or skip the dialog entirely by passing the ROM path on the command line.

### Alternative: use your own patch tool

The release also includes the raw patches if you prefer your own tools:

- **`rbshura_en.ips`** — IPS patch. Apply with [Floating IPS / Flips](https://www.smwcentral.net/?p=section&s=tools),
  Lunar IPS, `beat`, or any IPS patcher.
- **`rbshura_en.xdelta`** — xdelta3 patch (smaller). Apply with `xdelta3 -d -s your_rom.sfc rbshura_en.xdelta out.sfc`,
  or a GUI such as Delta Patcher / MultiPatch.

After patching, the English ROM runs on any accurate SNES/SFC emulator (Mesen, Snes9x,
bsnes/higan) or flash cart.

---

## Building from source (developers)

The English ROM is produced by a single retrotool `build_project()` call. The Japanese
source ROM is **not** included (copyright); place it at `roms/rbshura.sfc`.

```sh
uv sync
scripts/build.sh                 # canonical build: ROM + ips/xdelta, then the write-audit gate
scripts/build.sh --patcher       # also regenerate dist/apply_patch.py + dist/ patches
```

`scripts/build.sh` is the canonical build step. It runs the retrotool build and
then **`tools/audit_writes.py`**, a write-provenance gate that fails the build if
any byte changed vs the pristine ROM is not attributable to an intentional
insertion — collisions, stray writes, a "freespace" pool that isn't actually
free, or a section's footprint growing into adjacent game data. The approved
footprint lives in `tools/build_write_manifest.json`; after an intentional
change to what gets written, re-bless it with `scripts/build.sh --update-audit`.

Under the hood it is just:

```sh
./.venv/bin/retrotool build project.toml -j 1 --no-cache --diff both  # → out/rbshura_en.sfc (+ .ips/.xdelta)
./.venv/bin/python tools/audit_writes.py                              # provenance gate
./.venv/bin/python tools/make_patcher.py                              # (--patcher) regenerate dist/
```

Everything — font, engine patches, char_names, 14 scenarios, **and the EN title
graphics** — is declared in `project.toml` and built in one `retrotool build`.
The title logo + kanji are custom `kind="graphics"` encoders
(`tools/encode_title_logo.py`, `tools/encode_title_kanji_meta.py`) that run
during the build: edit the source PNG and rebuild — no pre-steps. The asar
engine patches carry `cache = "1"` so the build reports each patch's precise
write footprint (used by the audit).

`project.toml` is the build manifest (font, engine patches, scenario tables). See
`PROJECT_INDEX.md` for a map of the repo.

### Releasing

`dist/` holds the committed, distributable artifacts (patches + `apply_patch.py` — diffs
only, no ROM data). Pushing a `vX.Y` tag triggers `.github/workflows/release.yml`, which
PyInstaller-builds `apply_patch.exe` on a Windows runner and attaches all four assets to
the GitHub Release. (CI never builds the ROM — the source ROM is gitignored.)

---

## Legal

This is an unofficial, non-commercial fan translation. *Rushing Beat Shura* and all
related characters are property of their respective rights holders. No copyrighted ROM
data is distributed here — only disassembled source code, and a patch of differences that you apply to a ROM you own.
