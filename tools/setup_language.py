#!/usr/bin/env python3
"""setup_language.py — stage a retrotool project for a NEW translation language.

Generic: works on any retrotool project laid out like this one (a project.toml
with `<lang>_data_dir` script roots, `data_dirs` DataDef folders, and
[[rom.build.sections]] asset entries). Stdlib only (Python >= 3.11 for tomllib).

What it does, given a SOURCE language (default: en) and a NEW language code:

  1. Copies the source script folder  data/<src>  ->  data/<new>
     (the new language starts as a copy of the source script and is
     translated in place, e.g. with the script editor).
  2. project.toml:
       * adds   `<new>_data_dir = "data/<new>"`
       * sets   `build_lang = "<new>"`   (retrotool >= 0.9.3 reads the script
         from the matching `<lang>_data_dir` without repurposing the others)
       * renames `[rom] name` (suffix `_<src>` -> `_<new>`, else appends)
  3. Forks every LANGUAGE-BEARING asset the tomls point at, next to the
     original, renamed with the language code, and repoints the tomls:
       * `[[rom.build.sections]]` with kind "bin" / "graphics"  (fonts, art)
       * `[encoding] table_file` in every DataDef toml under `data_dirs`
     Naming: a stem already suffixed with a declared language code is
     re-suffixed (rbshura_en.tbl -> rbshura_fr.tbl); anything else gets
     `_<new>` appended (logo.png -> logo_fr.png). The copied CONTENT comes
     from the `--from` language's variant when one exists on disk.
     NOT forked (shared between languages): kind="asar"/"python" engine
     patches, and the `[rom] file` source ROM. Use --fork-all to fork those
     file references too.

The script prints the full plan and asks for confirmation before touching
anything (--yes skips the prompt, --dry-run never writes).

toml files are edited TEXTUALLY (exact quoted-string replacement) so all
comments and formatting are preserved; tomllib is used only to discover what
to replace. Every replacement is verified to have matched.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tomllib
from pathlib import Path

ASSET_KINDS = {"bin", "graphics"}       # section kinds whose `file` is forked
SHARED_KINDS = {"asar", "python"}       # engine code — shared, never forked


# ---------------------------------------------------------------------------
# Dev-environment detection (required before ANY action)
# ---------------------------------------------------------------------------

def venv_python(root: Path) -> Path | None:
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe"):
        p = root / rel
        if p.exists():
            return p
    return None


def check_environment(root: Path) -> list[str]:
    """Return a list of problems (empty = environment OK)."""
    problems = []
    if not (root / "project.toml").exists():
        problems.append(f"no project.toml in {root} — not a retrotool project root")
    if venv_python(root) is None:
        problems.append("no .venv — run scripts/setup.sh (or scripts\\win\\setup.cmd) first")
    else:
        retro = [p for rel in (".venv/bin/retrotool", ".venv/Scripts/retrotool.exe")
                 if (p := root / rel).exists()]
        if not retro:
            problems.append("retrotool missing from .venv — re-run the setup script")
    return problems


# ---------------------------------------------------------------------------
# Plan model
# ---------------------------------------------------------------------------

class Edit:
    """One exact-string replacement inside a text file."""
    def __init__(self, path: Path, old: str, new: str, why: str):
        self.path, self.old, self.new, self.why = path, old, new, why


class Plan:
    def __init__(self):
        self.copies: list[tuple[Path, Path, str]] = []   # (src, dst, why)
        self.edits: list[Edit] = []
        self.notes: list[str] = []

    def copy(self, src: Path, dst: Path, why: str):
        self.copies.append((src, dst, why))

    def edit(self, path: Path, old: str, new: str, why: str):
        self.edits.append(Edit(path, old, new, why))


def split_lang_suffix(stem: str, known_langs: set[str]) -> tuple[str, str | None]:
    """'rbshura_en' -> ('rbshura', 'en'); 'ascii' -> ('ascii', None).
    Longest language code wins ('br_pt' before 'pt')."""
    for lang in sorted(known_langs, key=len, reverse=True):
        if stem.endswith(f"_{lang}"):
            return stem[: -len(lang) - 1], lang
    return stem, None


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------

def build_plan(root: Path, src_lang: str, new_lang: str, fork_all: bool) -> Plan:
    pt_path = root / "project.toml"
    pt_text = pt_path.read_text(encoding="utf-8")
    cfg = tomllib.loads(pt_text)
    plan = Plan()

    # --- 1. script folder copy ------------------------------------------
    src_key = f"{src_lang}_data_dir"
    if src_key not in cfg:
        sys.exit(f"error: project.toml has no `{src_key}` — available languages: "
                 + ", ".join(k[:-len('_data_dir')] for k in cfg if k.endswith("_data_dir")))
    src_dir = root / cfg[src_key]
    if not src_dir.is_dir():
        sys.exit(f"error: source script folder {src_dir} does not exist")
    # New folder is a sibling of the source folder (data/en -> data/fr).
    new_dir = src_dir.parent / new_lang
    new_key = f"{new_lang}_data_dir"
    if new_key in cfg:
        plan.notes.append(f"{new_key} already declared in project.toml — keeping it")
        new_dir = root / cfg[new_key]
    if new_dir.exists():
        plan.notes.append(f"{new_dir.relative_to(root)} already exists — script copy skipped")
    else:
        plan.copy(src_dir, new_dir, "script folder (translate these files)")

    # --- 2. project.toml language keys -----------------------------------
    new_dir_rel = new_dir.relative_to(root).as_posix()
    src_line_re = re.compile(rf"^({re.escape(src_key)}\s*=\s*.*)$", re.M)
    m = src_line_re.search(pt_text)
    if not m:
        sys.exit(f"error: could not find the `{src_key} = ...` line in project.toml")
    if new_key not in cfg:
        plan.edit(pt_path, m.group(1),
                  m.group(1) + f'\n{new_key} = "{new_dir_rel}"',
                  f"declare {new_key}")
    bl = re.search(r"^(build_lang\s*=\s*\"[^\"]*\")", pt_text, re.M)
    if bl:
        plan.edit(pt_path, bl.group(1), f'build_lang = "{new_lang}"',
                  f"build the {new_lang} ROM")
    else:
        anchor = (m.group(1) + f'\n{new_key} = "{new_dir_rel}"'
                  if new_key not in cfg else m.group(1))
        plan.edit(pt_path, anchor, anchor + f'\nbuild_lang = "{new_lang}"',
                  f"build the {new_lang} ROM")

    # --- 2b. [rom] name ---------------------------------------------------
    rom = cfg.get("rom", {})
    old_name = rom.get("name")
    if old_name:
        if old_name.endswith(f"_{src_lang}"):
            new_name = old_name[: -len(src_lang)] + new_lang
        else:
            new_name = f"{old_name}_{new_lang}"
        plan.edit(pt_path, f'name = "{old_name}"', f'name = "{new_name}"',
                  f"built ROM -> {new_name}.sfc")

    # --- 3. fork toml-pointed assets --------------------------------------
    rom_file = rom.get("file")

    planned_copies: set[str] = set()
    # Language codes we can recognize as a `_<lang>` filename suffix: every
    # declared `<lang>_data_dir` plus the language being created.
    known_langs = {k[: -len("_data_dir")] for k in cfg if k.endswith("_data_dir")}
    known_langs.add(new_lang)

    def fork_ref(toml_path: Path, ref: str, why: str):
        """Plan: copy `ref` (project-relative path) to its language-forked
        name and repoint every textual occurrence in `toml_path`. The copy is
        planned once even when many tomls reference the same asset.

        The CONTENT comes from the `--from` language's variant of the asset
        when one exists (so staging `de` from `en` on a checkout currently
        pointed at `_fr` assets copies the `_en` files, not the French ones);
        otherwise from whatever the toml currently points at."""
        asset = root / ref
        base, cur_lang = split_lang_suffix(asset.stem, known_langs)
        if cur_lang == new_lang:
            # Already forked (re-run repair) — nothing to copy or repoint.
            return
        forked = asset.with_name(f"{base}_{new_lang}{asset.suffix}")
        forked_ref = forked.relative_to(root).as_posix()
        src_variant = asset.with_name(f"{base}_{src_lang}{asset.suffix}")
        copy_src = (src_variant
                    if cur_lang != src_lang and src_variant.exists() else asset)
        if not copy_src.exists():
            plan.notes.append(f"SKIP {ref} (referenced by {toml_path.name} but missing on disk)")
            return
        if ref not in planned_copies:
            planned_copies.add(ref)
            if forked.exists():
                plan.notes.append(f"{forked_ref} already exists — copy skipped, still repointed")
            else:
                plan.copy(copy_src, forked, why)
        plan.edit(toml_path, f'"{ref}"', f'"{forked_ref}"', f"repoint {why}")

    seen: set[str] = set()
    for sec in rom.get("build", {}).get("sections", []):
        kind, ref = sec.get("kind"), sec.get("file")
        if not ref or ref in seen or ref == rom_file:
            continue
        if kind in ASSET_KINDS or (fork_all and kind in SHARED_KINDS):
            seen.add(ref)
            fork_ref(pt_path, ref, f"{kind} asset")
        elif kind in SHARED_KINDS:
            plan.notes.append(f"shared {kind} patch kept as-is: {ref} (--fork-all to fork)")

    # DataDef tomls under data_dirs: fork each encoding table_file.
    for d in cfg.get("data_dirs", []):
        for tml in sorted((root / d).glob("*.toml")):
            try:
                sub = tomllib.loads(tml.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as e:
                plan.notes.append(f"SKIP {tml.relative_to(root)} (toml parse error: {e})")
                continue
            ref = sub.get("encoding", {}).get("table_file")
            if ref:
                fork_ref(tml, ref, "encoding table")

    return plan


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------

def apply_plan(root: Path, plan: Plan, dry_run: bool) -> None:
    for src, dst, _ in plan.copies:
        if dry_run:
            continue
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Group edits per file; apply sequentially against the live text so
    # chained anchors (data_dir line -> build_lang insert) compose.
    by_file: dict[Path, list[Edit]] = {}
    for e in plan.edits:
        by_file.setdefault(e.path, []).append(e)
    for path, edits in by_file.items():
        text = path.read_text(encoding="utf-8")
        for e in edits:
            if e.old not in text:
                sys.exit(f"error: expected `{e.old}` in {path} but it is gone — "
                         f"file changed underneath the plan; nothing else written.")
            text = text.replace(e.old, e.new)
        if not dry_run:
            path.write_text(text, encoding="utf-8")


def show_plan(root: Path, plan: Plan) -> None:
    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()
    print("\n=== plan ===")
    for src, dst, why in plan.copies:
        print(f"  COPY  {rel(src)}  ->  {rel(dst)}   [{why}]")
    for e in plan.edits:
        first = e.new.splitlines()[0] if "\n" not in e.old else "(multi-line)"
        print(f"  EDIT  {rel(e.path)}: {e.old.splitlines()[0][:60]}  ->  {first[:60]}   [{e.why}]")
    for n in plan.notes:
        print(f"  NOTE  {n}")
    if not plan.copies and not plan.edits:
        print("  (nothing to do)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_root(start: Path) -> Path | None:
    for p in (start, *start.parents):
        if (p / "project.toml").exists():
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Stage a retrotool project for a new translation language.")
    ap.add_argument("--project", type=Path, default=None,
                    help="project root (default: walk up from cwd to project.toml)")
    ap.add_argument("--from", dest="src_lang", default=None,
                    help="language to stage assets FROM (default: prompt, en)")
    ap.add_argument("--to", dest="new_lang", default=None,
                    help="new language code, e.g. fr / de / br_pt (default: prompt)")
    ap.add_argument("--fork-all", action="store_true",
                    help="also fork shared asar/python patch files")
    ap.add_argument("--yes", action="store_true", help="apply without confirmation")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    ap.add_argument("--skip-env-check", action="store_true",
                    help="skip the dev-environment check (CI etc.)")
    args = ap.parse_args()

    root = args.project.resolve() if args.project else find_root(Path.cwd().resolve())
    if root is None or not (root / "project.toml").exists():
        sys.exit("error: no project.toml found — run from inside a retrotool "
                 "project or pass --project <dir>")

    if not args.skip_env_check:
        problems = check_environment(root)
        if problems:
            print("Dev environment is NOT set up correctly:", file=sys.stderr)
            for p in problems:
                print(f"  ✗ {p}", file=sys.stderr)
            sys.exit(1)

    cfg = tomllib.loads((root / "project.toml").read_text(encoding="utf-8"))
    langs = sorted(k[: -len("_data_dir")] for k in cfg if k.endswith("_data_dir"))
    print(f"project: {root}")
    print(f"available languages: {', '.join(langs)}"
          + (f"   (build_lang = {cfg['build_lang']})" if "build_lang" in cfg else ""))

    src = args.src_lang
    if not src:
        default = "en" if "en" in langs else (langs[0] if langs else "en")
        src = input(f"Stage assets FROM which language? [{default}]: ").strip() or default
    new = args.new_lang
    if not new:
        new = input("NEW language code (e.g. fr, de, br_pt): ").strip()
    if not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", new or ""):
        sys.exit("error: language code must be lowercase letters/digits/underscores, e.g. fr / br_pt")
    if new == src:
        sys.exit("error: the new language must differ from the source language")
    if new in langs:
        print(f"warning: `{new}` is already declared in project.toml — the plan "
              f"will only repair missing copies / repoints.")

    plan = build_plan(root, src, new, args.fork_all)
    show_plan(root, plan)

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return
    if not args.yes:
        ok = input("\nApply this plan? [y/N]: ").strip().lower()
        if ok not in ("y", "yes"):
            print("aborted — nothing written.")
            return
    apply_plan(root, plan, dry_run=False)
    print(f"\nOK — project staged for `{new}`.")
    print(f"  * translate the files in {plan.copies[0][1].relative_to(root) if plan.copies else f'data/{new}'}"
          f" (the script editor follows build_lang automatically)")
    print(f"  * edit the forked encoding table / font / art for any new glyphs `{new}` needs")
    print(f"  * build as usual; the ROM lands in out/ under the new [rom] name")


if __name__ == "__main__":
    main()
