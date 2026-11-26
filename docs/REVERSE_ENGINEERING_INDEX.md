# Reverse-engineering index

This is the index for all reverse-engineering records in this project.
Findings are kept in docs with exact addresses, file offsets, byte sequences,
confidence labels and proven-vs-inferred separation.

No firmware build, install or camera test has been performed for the current
Art Filter work.

## Core Art Filter records

| Document | Covers | Status |
|---|---|---|
| [ART_FILTERS.md](ART_FILTERS.md) | Original stage map, camera-test history, known unknowns | Active baseline |
| [ART_FILTERS_DATA.md](ART_FILTERS_DATA.md) | Generated per-filter table addresses/values | Generated from firmware |
| [ART_STYLE_EDITOR.md](ART_STYLE_EDITOR.md) | Data-table editor, byte maps, shared tables, colour probes | Current tool reference |
| [ART_FILTER_CHAIN.md](ART_FILTER_CHAIN.md) | Chain dispatch, slots, modules, writer of `job+0x2c2c` | Mostly decoded |
| [ART_FILTER_KERNELS.md](ART_FILTER_KERNELS.md) | Downstream kernels/ISP paths | Vignette decoded; grain/blur pending |
| [ART_FILTER_MENU.md](ART_FILTER_MENU.md) | Menu names, icons, validator, PM/SCP tables, resource patching | UI resources decoded |
| [FRAME_EFFECT_PICTURE_MODES.md](FRAME_EFFECT_PICTURE_MODES.md) | Frame/vignette for non-Art picture modes; failed tests and frame-only injection plan | Plan only, not camera-tested |
| [FINDINGS.md](FINDINGS.md) | Older broad firmware findings and camera tests | Historical |

## Related mod records

| Document | Covers |
|---|---|
| [MOD_IDEAS.md](MOD_IDEAS.md) | General mod ideas and feasibility notes |
| [FEATURE_LIST.md](FEATURE_LIST.md) | Known firmware features |
| [MONO_SLOTS.md](MONO_SLOTS.md) | Monochrome/picture-mode slot work |
| [PICTURE_MODE_PATCH.md](PICTURE_MODE_PATCH.md) | Picture Mode table work |
| [PER_MODE_TONE.md](PER_MODE_TONE.md) | Per-mode tone curves |
| [HSL_EDITOR_PLAN.md](HSL_EDITOR_PLAN.md) | HSL editor plan |
| [ASPECT_PATCH.md](ASPECT_PATCH.md) | Aspect-ratio patching |
| [BIRD_AF.md](BIRD_AF.md) | Bird AF notes |

## Tools used for verification

| Tool | Purpose |
|---|---|
| `tools/olyfw.py` | Firmware unpack/pack/checksum handling |
| `tools/modcore.py` | Decompressed runtime image construction |
| `tools/disasm.py` | MN103 disassembly with runtime base |
| `tools/art_filter_dump.py` | Verifies every table address against code; dumps values/curves |
| `tools/patch_art_styles.py` | Probe + data-only style patcher; checksum-safe |
| `tools/patch_hires_art.py` | Precedent for table relocation and immediate rewriting |
| `tools/patch_art_gradation.py` | Camera-tested curve/menu patch precedent |
| `tools/patch_keyline_mono.py` | Key Line grey-vector patch |
| `tools/patch_grainy_color.py` | Colour-grain experiment |

## Current confirmed facts

### Data tables

* Tone curve stage: switch `0x603df193` on `key-11`, 256×u16 tables.
* Colour params: switch `0x603dd128`, packer `0x603dd053`, A then B to request
  `+100..+122`; visual meaning unproven.
* Pop Art matrix: `0x6051affc`, shared by Pop Art I/II.
* Register records: two identical 50-byte rows of 16×24-bit words.
* Coefficient records: 13-pointer records; 12 six-byte windows proven consumed.

### Chain and dispatch

* Secondary hash `0x6052dbb0` is checked first and wins on hit.
* Primary hash `0x6052dab0` is checked second.
* Slots: `job+0x2ae8`, stride 12; consumer `0x60381146`.
* End-marker/cleanup slot: `0x603843b0` — not a proven no-op.
* Builder epilogue: `0x60385404..0x6038543a` — do not replace.
* Preferred injection wrapper: `0x60383247` (calls `0x60384438`).
* Writer of `job+0x2c2c`: constructor `0x603807d0`, store `0x60380926`.
* `job+0x2c2c` equals the picture-mode key `0x01VV00MM` byte-for-byte.
* Variant III keys are above the range checks and always get generic chain
  `0x60384ec7`.

### Kernel paths

* Vignette/frame is ISP register programming, not a CPU pixel loop.
* Frame request builder: `0x6038b70d`, pass `0x8000`.
* Downstream consumer: `0x603ce899`.
* Radius band table: `0x60530084`.
* Aspect normalization: `0x603e41c5`.
* Family-scoped frame disable: `0x6038b6a0`.

### Menu/UI

* Four true Art Filter name lists:
  `0x60fb73c8`, `0x60fb84a4`, `0x60fb8eec`, `0x611d799c`.
* Validator: `0x604da7bc`.
* Picture Mode main list: `0x604bc4f4`; alt list: `0x604ae834`.
* Three PM lists:
  `0x611aeddc`, `0x6120628c`, `0x61287a40`.
* SCP icon lists: `0x611ec718` and `0x611ec9a0`.
* SCP master: `0x611ef284`.
* Snapshot → job key path: `0x60411db9` → `0x60411ebf` → `0x6041da81`
  → `0x603763d3` → `0x603807d0` → `job+0x2c2c`.
* Picture-mode key bytes: `01 VV MM 00`; `VV` from snapshot `+26824`.
* Setting resolver: `0x6040af6d`; setting→SCP map: `0x611c22b8`, stride 16,
  37 records.
* Per-filter setting IDs recovered for all stock Art Filters.
* Help string sid: `0x18a`.
* Normal PM common-methods table: `0x6129f86c`, stride `0xc`, consumed by
  `0x60ec9bf4`.
* RAM callback arrays: `0x61ea0f30`, `0x61ea0f40`, `0x61ea0f74`; producers
  unresolved.
* Wizard id `0x7e` producer unresolved.
* Resource-only ceiling: 17 new named entries, for 48 total menu entries.
* Recommended GUI allocation base: `0x612dcd17` (blob offset `0x670d17`).

## Active probes

| Probe | Status | Feeds into |
|---|---|---|
| Grain pixel kernel and Y-only mask | Completed negative: no pixel kernel/mask proven; earlier patch sites unsafe | `ART_FILTER_KERNELS.md` |
| Blur kernels for Diorama / Soft Focus | In progress | `ART_FILTER_KERNELS.md` |
| Menu enumeration table/count | Completed | `ART_FILTER_MENU.md` |
| Selection → job key, per-filter settings slots | Completed: key path and setting IDs proven | `ART_FILTER_MENU.md`, toggle design |
| Global selector → Art selection bridge | Unresolved | `ART_FILTER_MENU.md` |
| Effect-enable mask hook | Planned at wrapper `0x60383247`, not epilogue | New toggles per Art Filter |
| Frame effect for picture modes | Planned as frame-only injection into `0x60395eb9` | `FRAME_EFFECT_PICTURE_MODES.md` |

## Recording rules

For every finding:

1. Label it **proven** or **inferred**.
2. Record runtime address and file offset.
3. Record original bytes before proposing a patch.
4. Verify byte immediates again immediately before patching.
5. Rebuild checksums with `tools/olyfw.py`.
6. Re-run `tools/art_filter_dump.py` on patched output.
7. Do not build/install/test on camera until a direction is confirmed.
