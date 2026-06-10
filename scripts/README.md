# Dev-environment scripts

Helper scripts for contributors (translators / builders) on every platform.
**Linux and macOS** use the `.sh` scripts in this folder; **Windows** uses the
`.ps1`/`.cmd` pair in [`scripts/win/`](win/README.md) (same scripts, same
behavior — the table below maps them).

| Task | Linux / macOS | Windows |
|---|---|---|
| One-shot environment setup (run **first**) | `scripts/setup.sh` | `scripts\win\setup.cmd` |
| Launch the translation script editor | `scripts/run-editor.sh` | `scripts\win\run-editor.cmd` |
| Build the ROM (+ write-provenance audit gate) | `scripts/build.sh` | `scripts\win\build.cmd` |
| Stage the project for a NEW translation language | `scripts/setup-language.sh` | `scripts\win\setup-language.cmd` |

Every script **checks the dev environment before doing anything** (venv
present, retrotool installed, ROM where needed) and tells you exactly what to
run if something is missing — so the worst case of running them in the wrong
order is a clear error message, never a half-finished action.

## Setting up the dev environment

1. **Clone the repo** and open a terminal at its root.
2. **Run the setup script once per machine:**

   ```sh
   scripts/setup.sh                  # Linux / macOS
   ```
   ```bat
   scripts\win\setup.cmd             :: Windows (double-click works too)
   ```

   It installs [`uv`](https://docs.astral.sh/uv/) if missing, creates the
   project `.venv` with a matching CPython (downloaded automatically), and
   installs everything from PyPI: `retrotool[all]` (build engine + bundled
   libsfx / asar / bass / xdelta binaries), Pillow, and pywebview (the script
   editor's window — Qt backend on Linux, native on macOS/Windows). Nothing is
   sourced from a local checkout.

   The script ends with a **verification checklist** — every line must be ✓:

   ```
   ==> Verifying the environment:
     ✓ .venv python
     ✓ retrotool CLI
     ✓ retrotool importable
     ✓ Pillow (PIL)
     ✓ pywebview (editor)
     ! source ROM MISSING — place your legally-obtained copy at: roms/rbshura.sfc
   ```

3. **Place the source ROM** at the path the checklist names (it is read from
   `project.toml`, `roms/rbshura.sfc` for this project). It is gitignored for
   copyright and never distributed; the build and the editor both need it.
   Re-run the setup script any time to re-print the checklist.
4. **Build once** (`scripts/build.sh` / `build.cmd`) — this also gives the
   script editor the built ROM it extracts the in-game text palettes from.
5. **Edit the script** with `scripts/run-editor.sh` / `run-editor.cmd`.

Linux note: the editor uses Qt via pywebview. If the window fails to open on a
minimal distro, install your distro's basic Qt6/xcb runtime libraries.

## Starting a new translation language

`setup-language` stages the whole project for a new language in one step (it
wraps the cross-platform engine `tools/setup_language.py`, which is generic —
it works on any retrotool project with `<lang>_data_dir` keys and
`[[rom.build.sections]]`):

```sh
scripts/setup-language.sh                       # interactive (prompts below)
scripts/setup-language.sh --from en --to fr     # non-interactive
scripts/setup-language.sh --to fr --dry-run     # print the plan only
```

It asks **which language to stage assets from** (default `en`) and the **new
language code** (e.g. `fr`, `de`, `br_pt`), prints the full plan, and asks for
confirmation before writing anything. The plan:

1. **Copies the script folder** `data/en` → `data/fr` — translate those files
   in place (the editor follows `build_lang` automatically).
2. **Updates `project.toml`**: adds `fr_data_dir = "data/fr"`, sets
   `build_lang = "fr"`, and renames `[rom] name` (`rbshura_en` → `rbshura_fr`,
   so the build lands at `out/rbshura_fr.sfc`).
3. **Forks every toml-pointed language asset** next to its original with the
   language code as postfix, and repoints the tomls at the copies:
   - encoding tables (`tables/rbshura_en.tbl` → `tables/rbshura_fr.tbl`)
   - `kind = "bin"` sections (fonts: `fonts/rbshura_en.bin` → `fonts/rbshura_fr.bin`)
   - `kind = "graphics"` sections (title/attack-name art:
     `…_logo_en.png` → `…_logo_fr.png`)

   A stem already ending in `_en` is re-suffixed; anything else gets `_fr`
   appended. Engine patches (`kind = "asar"`) and the source ROM are **shared
   between languages** and left alone (pass `--fork-all` to fork patches too).

After staging: translate `data/fr/`, add any accented glyphs the language
needs to the forked font + encoding table, and build as usual. The original
language's files are never modified, so languages coexist on one checkout —
switch between them by editing `build_lang` in `project.toml`.

## Maintainer notes

- `setup.sh` / `setup.ps1` install **published** packages via `uv pip install`
  and deliberately ignore `pyproject.toml`'s `[tool.uv.sources]` editable
  local-checkout pins (those are for the maintainer's machine, where `uv sync`
  is the right command instead).
- `scripts/build.sh` is the canonical build: retrotool build **plus** the
  write-provenance audit gate (`tools/audit_writes.py`). See the project
  readme's "Building from source" section for `--patcher` / `--update-audit`.
