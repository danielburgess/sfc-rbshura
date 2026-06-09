# Windows helper scripts

PowerShell scripts for Windows contributors (translators / builders). They mirror
the Linux workflow (`uv sync` + `scripts/build.sh`).

| Script | Purpose                                                                                                                                  |
|---|------------------------------------------------------------------------------------------------------------------------------------------|
| `setup.ps1` | One-shot environment setup: installs `uv`, downloads a matching CPython, creates `.venv`, installs all dependencies. Run this **first**. |
| `run-editor.ps1` | Launches the translation script editor (`script_editor.py`).                                                                             |
| `build.ps1` | Builds `out\rbshura_br_pt.sfc` (+ `.ips`/`.xdelta`) and runs the write-provenance audit gate. Supports `-Patcher` and `-UpdateAudit`.    |

## Running them

**Easiest — double-click the `.cmd` wrapper** (`setup.cmd`, `run-editor.cmd`,
`build.cmd`). Each wrapper runs its matching `.ps1` with the execution policy
relaxed **for that single invocation only** (it does not change your machine's
global policy).

Or run the `.ps1` directly with the policy relaxed per-invocation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\run-editor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1
```

`build.ps1` accepts the same options as `build.sh`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1 -Patcher
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1 -UpdateAudit
```

## Prerequisites / caveats

- **Source ROM.** `build.ps1` needs the pristine Japanese ROM at `roms\rbshura.sfc`
  (gitignored for copyright). The editor and build will not run without it.
- **retrotool dependency.** `pyproject.toml` pins the `retrotool` build engine to a
  local editable checkout (an absolute path that only exists on the original
  author's machine). On a fresh Windows machine `uv sync` cannot resolve it until
  you point it at your own retrotool checkout:

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\setup.ps1 -RetrotoolPath C:\path\to\retrotool
  ```

  That rewrites `[tool.uv.sources]` in `pyproject.toml` to your checkout (a backup
  is saved to `pyproject.toml.bak`).
