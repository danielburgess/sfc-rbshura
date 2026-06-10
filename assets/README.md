# assets/ — title encoder inputs

Build-time inputs for the title-screen graphics encoders
(`tools/encode_title_logo.py`, `tools/encode_title_kanji_meta.py`). These are
**committed sources** — the build never regenerates them.

| file | size | sha256 (first 16) | provenance |
|------|------|-------------------|------------|
| `title_cgram.bin` | 512 B | `d5a40ae60252906c` | **Extracted directly from ROM** by `tools/extract_title_cgram.py`: LZSS palette block `$D8:3D30` holds the title's four encoder-relevant palette groups (title CGRAM group 4 = block group 8, 5 = 9, 6 = 7, 12 = 13). Groups the encoders never read are zero — the rest of the title CGRAM is composed at runtime and not stored in title layout anywhere in ROM. Regenerable any time from `roms/rbshura.sfc`. |
| `title_flame.bin` | 384 B | `55f34c6499e88b24` | The 12 BG2 flame tiles (slots `$7A/$7E/$AC/$AD/$AE/$DC/$EB/$FB-$FF`) that the expanded EN BG1 char must preserve. **Not stored in ROM** — the flame is generated at runtime by an effect routine (the tiles appear nowhere in ROM data, even across all decompressed screen-manifest blocks). This is a capture of one composed frame, as shipped in EN v1.1. |
| `title_tilemap_orig.bin` | 12 KiB | `3a2229296130a9c2` | The combined BG1\|BG2\|BG3 title tilemap blob (VRAM `$A000-$D000`; staged at `$7F:8800`, pushed by `updateContinueMenu`). **Not stored in ROM** — the game composes it at runtime (BG3 text rows are rendered from ASCII strings at `$C0:E684`, e.g. "PUSH START"; the BG2 flame map is generated). This is a capture of the composed output. The encoder splices a new BG1 map over the first 4 KiB and applies the subtitle transform to BG3; BG2 and the remaining BG3 rows are preserved verbatim. |

Recovery note (2026-06-09): the original captures were lost before being
committed. `title_flame.bin` / `title_tilemap_orig.bin` were recovered from the
shipped v1.1 patch (flame verbatim from the built char slots; the blob by
inverting `encode_title_logo._set_subtitle`) and verified by re-running both EN
encoders and comparing all four outputs byte-identical against that patch.
`title_cgram.bin` was then re-sourced directly from ROM data (same verification
passed). The recovery/verification scripts were one-shot and intentionally not
kept — the patch is a regenerated build artifact, not a data source.
