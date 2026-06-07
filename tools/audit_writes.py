#!/usr/bin/env python3
"""Audit exactly what the build writes, and what original data it overwrites.

Goal: a verifiable guarantee that every byte the build changes is attributable
to an intentional insertion, with no silent collisions, no stray writes, and no
"freespace" pool that turns out to hold real game data.

It builds the ROM via retrotool's ``build_project()`` and uses the AUTHORITATIVE
per-section ``WriteRange`` provenance it returns (``BuildResult.sections`` — this
includes asar patches, captured in diff mode), cross-checked against a byte-diff
of the built ROM vs the pristine ROM.

Checks (any failure → non-zero exit):

  1. COLLISION   — two sections write the same byte. asar ``org`` overlaps are
                   otherwise silent (later patch wins). See the project's
                   "Asar silent org collisions" note.
  2. UNCLAIMED   — a byte differs from pristine but no section claims it
                   (stray/unintentional overwrite), excluding the SNES header
                   checksum/size bytes the build legitimately rewrites.
  3. FREESPACE   — a write that lands in a declared [rom.build].freespace pool
                   overwrites NON-free pristine bytes (the pool wasn't actually
                   free → it was clobbering real data, the BG1-glitch class).
  4. ENVELOPE    — a section's LIVE-data overwrite (replacing real original
                   bytes, e.g. scenario text / font) falls outside the region
                   previously approved for that section in the manifest. Catches
                   a [data].end set too wide spilling into adjacent game data.

Usage:
    python tools/audit_writes.py                 # build + audit; exit 1 on violations
    python tools/audit_writes.py --update        # accept current footprint as the
                                                 #   approved manifest (after an
                                                 #   intentional change)
    python tools/audit_writes.py --json out.json # machine-readable report

The approved manifest is tools/build_write_manifest.json (checked in).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "tools", "build_write_manifest.json")

# SNES internal header (HiROM, file $FFB0-$FFFF): the build recomputes the
# checksum/complement and may bump the ROM-size byte. Those writes are made by
# retrotool post-pass, not by a section, so allow-list them as build metadata.
HEADER_LO, HEADER_HI = 0xFFB0, 0x10000

# Per-owner LIVE-overwrite ranges within this gap get merged into one envelope.
ENVELOPE_MERGE_GAP = 0x1000


def hx(s: str) -> int:
    return int(str(s).replace("$", ""), 16)


def hirom_snes(off: int) -> str:
    """File offset → a readable HiROM bank:addr (banks $C0+ region)."""
    return f"${0xC0 + (off >> 16):02X}:{off & 0xFFFF:04X}"


def is_free(b: bytes) -> bool:
    """A region is 'free' only if it is uniform $00 or uniform $FF fill."""
    if not b:
        return True
    s = set(b)
    return s <= {0x00} or s <= {0xFF}


def merge(ranges: list[tuple[int, int]], gap: int = 0) -> list[tuple[int, int]]:
    """Merge [start,end) ranges that overlap or sit within `gap` of each other."""
    if not ranges:
        return []
    ranges = sorted(ranges)
    out = [list(ranges[0])]
    for s, e in ranges[1:]:
        if s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def load_project():
    doc = tomllib.load(open(os.path.join(ROOT, "project.toml"), "rb"))
    rom = doc.get("rom", {})
    build = rom.get("build", {})
    pristine = os.path.join(ROOT, rom["file"])
    out = os.path.join(ROOT, build.get("output_dir", "."), f"{rom['name']}.sfc")
    freespace = [(hx(a), hx(b)) for a, b in build.get("freespace", [])]
    return pristine, out, freespace


def collect_writes():
    """Build and return (built_rom_path, [(start, end, owner) ...])."""
    from retrotool.build import build_project
    res = build_project("project.toml", no_cache=True, jobs=1,
                        print_summary=False, no_progress=True)
    writes = []
    for sr in res.sections:
        owner = _owner_of(sr.section)
        for w in sr.write:
            if w.length > 0:
                writes.append((w.offset, w.offset + w.length, owner))
    return str(res.rom_path), writes


def _owner_of(section) -> str:
    """A stable, human-readable owner key (robust to section reordering).

    datadefs keep their ``datadef:<name>`` source; everything else (asar
    patches, graphics, bin) is keyed by its input filename. Falls back to the
    section source only if neither is available.
    """
    src = getattr(section, "source", "") or ""
    if src.startswith("datadef:"):
        return src
    files = getattr(section, "files", None)
    if files:
        return os.path.basename(str(files[0]))
    return src or getattr(section, "name", "?")


def in_any(off: int, ranges: list[tuple[int, int]]) -> bool:
    for s, e in ranges:
        if s <= off < e:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="rewrite the approved manifest from the current build")
    ap.add_argument("--json", help="write the full report as JSON to this path")
    args = ap.parse_args()

    pristine_path, out_path, freespace = load_project()
    pristine = open(pristine_path, "rb").read()
    built_path, writes = collect_writes()
    built = open(built_path, "rb").read()
    plen = len(pristine)

    violations: list[str] = []

    # ---- 1. COLLISION: overlapping writes from different owners ----------
    sw = sorted(writes)
    collisions = []
    for i in range(1, len(sw)):
        ps, pe, po = sw[i - 1]
        cs, ce, co = sw[i]
        if cs < pe and po != co:
            ov_s, ov_e = cs, min(pe, ce)
            # asar re-fixes the SNES checksum on every patch; the final
            # retrotool pass does too. Those header writes legitimately overlap
            # across patches — not a real collision. Skip overlaps fully inside
            # the header range.
            if HEADER_LO <= ov_s and ov_e <= HEADER_HI:
                continue
            collisions.append((ov_s, ov_e, po, co))
    for s, e, a, b in collisions:
        violations.append(
            f"COLLISION {hirom_snes(s)}..{hirom_snes(e)} written by both "
            f"{a!r} and {b!r}")

    # ---- coverage + per-owner classification ----------------------------
    # Mark every claimed byte; classify each write's pristine content.
    claimed = bytearray(len(built))           # 1 where some section wrote
    owner_live: dict[str, list[tuple[int, int]]] = {}   # owner -> live-overwrite ranges
    freespace_live = []                       # writes into freespace hitting real data
    for s, e, owner in writes:
        for i in range(s, min(e, len(claimed))):
            claimed[i] = 1
        # Classify only the part that overlaps the original ROM (an in-place
        # overwrite). Bytes beyond pristine length are new expansion space.
        ov_e = min(e, plen)
        # Exclude the SNES header (checksum/size) — every asar patch rewrites it
        # as build metadata; it is not an intentional content overwrite.
        if ov_e > s and not (HEADER_LO <= s and ov_e <= HEADER_HI):
            pri = pristine[s:ov_e]
            changed = built[s:ov_e] != pri      # did we actually change it?
            if changed and not is_free(pri):
                owner_live.setdefault(owner, []).append((s, ov_e))
                if in_any(s, freespace):
                    freespace_live.append((s, ov_e, owner))

    # ---- 3. FREESPACE pool integrity ------------------------------------
    for s, e, owner in freespace_live:
        violations.append(
            f"FREESPACE-CLOBBER {owner!r} wrote {hirom_snes(s)}..{hirom_snes(e)} "
            f"which is in a freespace pool but holds NON-free pristine data")
    # Also flag any freespace pool that is not actually free in pristine
    # (latent danger even if unused this build).
    for s, e in freespace:
        seg = pristine[s:min(e, plen)]
        if seg and not is_free(seg):
            # how much is non-free
            nf = sum(1 for b in seg if b not in (0x00, 0xFF))
            violations.append(
                f"FREESPACE-NOT-FREE pool {hirom_snes(s)}..{hirom_snes(e)} "
                f"has {nf} non-fill bytes in pristine ROM (declared free, isn't)")

    # ---- 2. UNCLAIMED diffs ---------------------------------------------
    unclaimed = []
    for i in range(plen):
        if built[i] != pristine[i] and not claimed[i]:
            if HEADER_LO <= i < HEADER_HI:
                continue  # checksum / size — build metadata
            unclaimed.append(i)
    for s, e in merge([(u, u + 1) for u in unclaimed]):
        violations.append(
            f"UNCLAIMED diff {hirom_snes(s)}..{hirom_snes(e)} "
            f"({e - s} B changed vs pristine, no section claims it)")

    # ---- per-owner envelopes (the approved LIVE footprint) --------------
    envelopes = {o: merge(rs, ENVELOPE_MERGE_GAP) for o, rs in owner_live.items()}

    if args.update:
        man = {o: [[s, e] for s, e in env] for o, env in sorted(envelopes.items())}
        json.dump({"live_overwrite_envelopes": man}, open(MANIFEST, "w"), indent=2)
        print(f"updated approved manifest: {MANIFEST}")
        print(f"  {len(man)} owners make intentional live-data overwrites")
    else:
        # ---- 4. ENVELOPE drift vs approved manifest ---------------------
        if os.path.exists(MANIFEST):
            approved = json.load(open(MANIFEST)).get("live_overwrite_envelopes", {})
            approved = {o: [(s, e) for s, e in v] for o, v in approved.items()}
            for owner, rs in owner_live.items():
                appr = approved.get(owner)
                if appr is None:
                    tot = sum(e - s for s, e in rs)
                    violations.append(
                        f"NEW-LIVE-OVERWRITE {owner!r} now overwrites {tot} B of real "
                        f"data (no approved envelope). If intended: --update")
                    continue
                for s, e in rs:
                    for i in range(s, e):
                        if not in_any(i, appr):
                            violations.append(
                                f"ENVELOPE-DRIFT {owner!r} overwrote {hirom_snes(i)} "
                                f"outside its approved envelope (footprint grew "
                                f"into adjacent data). If intended: --update")
                            break
        else:
            print("note: no approved manifest yet — run --update to create the "
                  "baseline once the current footprint is verified intentional.")

    # ---- report ---------------------------------------------------------
    print("\n=== build write provenance ===")
    print(f"pristine: {os.path.relpath(pristine_path, ROOT)} ({plen:,} B)")
    print(f"built:    {os.path.relpath(built_path, ROOT)} ({len(built):,} B)")
    rows = []
    for owner in sorted(set(o for _, _, o in writes)):
        ows = [(s, e) for s, e, o in writes if o == owner]
        total = sum(e - s for s, e in ows)
        inplace = sum(min(e, plen) - s for s, e in ows if s < plen)
        live = sum(e - s for s, e in owner_live.get(owner, []))
        rows.append((owner, len(ows), total, inplace, live))
    w = max(len(r[0]) for r in rows)
    print(f"\n{'owner':<{w}}  ranges   total    in-place   live-overwrite")
    for owner, n, total, inplace, live in rows:
        print(f"{owner:<{w}}  {n:>6}  {total:>7}  {inplace:>9}  {live:>9}"
              + ("  <-- replaces real game data" if live else ""))

    print("\n=== verdict ===")
    if violations:
        print(f"FAIL — {len(violations)} violation(s):")
        for v in violations:
            print("  ✗ " + v)
    else:
        print("PASS — every changed byte is claimed by exactly one section; "
              "no collisions; freespace pools are genuinely free; live overwrites "
              "match the approved manifest.")

    if args.json:
        report = {
            "pristine": pristine_path, "built": built_path,
            "owners": {o: {"ranges": [[s, e] for s, e, ow in writes if ow == o],
                           "live_envelopes": envelopes.get(o, [])}
                       for o in set(ow for _, _, ow in writes)},
            "violations": violations,
        }
        json.dump(report, open(args.json, "w"), indent=2, default=list)
        print(f"\nwrote JSON report: {args.json}")

    return 1 if violations and not args.update else 0


if __name__ == "__main__":
    sys.exit(main())
