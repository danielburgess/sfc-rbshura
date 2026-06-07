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

**1.1 release.** The translation is complete and the build is verified.

### Changelog

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

| | |
|---|---|
| File size | `2,097,152` bytes (2 MB) |
| SHA-256 | `b1c9b743ebab25d9c00153f77f78b494f610227eecaa49f9771f4e76ed6e7815` |

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
