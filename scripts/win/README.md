# Windows helper scripts

PowerShell scripts for Windows contributors (translators / builders). `setup.ps1`
creates a `.venv` and installs **`retrotool[all]` + Pillow + pywebview from PyPI**
(no local checkout needed); `build.ps1` is the Windows equivalent of
`scripts/build.sh`. The Linux/macOS equivalents live one level up in `scripts/`
— see [`scripts/README.md`](../README.md) for the full dev-environment guide.

Every script **checks the dev environment before doing anything** and tells
you what to run if something is missing.

| Script | Purpose |
|---|---|
| `setup.ps1` | One-shot environment setup: installs `uv`, downloads a matching CPython, creates `.venv`, installs all dependencies, then prints a verification checklist. Run this **first**. |
| `run-editor.ps1` | Launches the translation script editor (`script_editor.py`). Needs a built ROM in `out\` (run `build.cmd` once). |
| `build.ps1` | Builds the ROM named by `project.toml` into `out\` (+ `.ips`/`.xdelta`) and runs the write-provenance audit gate. Supports `-Patcher` and `-UpdateAudit`. |
| `setup-language.ps1` | Stages the project for a NEW translation language (wraps `tools\setup_language.py`). See [`scripts/README.md`](../README.md#starting-a-new-translation-language). |

## Running them

**Easiest — double-click the `.cmd` wrapper** (`setup.cmd`, `run-editor.cmd`,
`build.cmd`, `setup-language.cmd`). Each wrapper runs its matching `.ps1` with
the execution policy relaxed **for that single invocation only** (it does not
change your machine's global policy).

Or run the `.ps1` directly with the policy relaxed per-invocation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\run-editor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\setup-language.ps1 --from en --to fr
```

`build.ps1` accepts the same options as `build.sh`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1 -Patcher
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1 -UpdateAudit
```

## Prerequisites / caveats

- **Source ROM.** `build.ps1` needs the pristine Japanese ROM at `roms\rbshura.sfc`
  (gitignored for copyright). The editor and build will not run without it.
- **retrotool comes from PyPI.** `setup.ps1` installs `retrotool[all]` (>=0.9.3, which
  bundles the libsfx / asar / bass / xdelta binaries) plus Pillow and pywebview via `uv pip install`.
  It does **not** use `uv sync`, so the editable local-checkout pin in the project's
  `pyproject.toml` (`[tool.uv.sources]`, for the maintainer's machine only) is ignored —
  nothing local is required.
