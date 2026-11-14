# E-M1 Mark III firmware notes

File analysed: `E1399999_Focus_Stack.BIN` (sha256 `fec00684…47ff`, 109,838,336 bytes).
Unpack with `python3 tools/olyfw.py unpack E1399999_Focus_Stack.BIN <outdir>`.

## Container format

Same as the 2010-era Olympus format handled by `oly_fw_tools.zip`:
same XOR-0xFF + 16-byte shuffle scrambling, same checksum. Unpack + repack is
byte-identical.

| # | Load addr    | Size       | Flags  | Contents |
|---|--------------|------------|--------|----------|
| 0 | `0x40800000` | `0x19fffc0`| 0x0100 | Main CPU code (AM / MN103 family) |
| 1 | `0x42400000` | `0x1afffc0`| 0x0101 | Text / fonts |
| 2 | `0x43f00000` | `0x323ffc0`| 0x0106 | Unknown; contains `MODE_*` setting-name table |
| 3 | `0x00000000` | `0x003ffc0`| 0x010e | Unknown |
| 4 | `0x47140000` | `0x00fffc0`| 0x0102 | Images |
| 5 | `0x08000000` | `0x003ffc0`| 0x0107 | Unknown (small; I2C strings) |

Model id `0x1390`, main code version `0x1500`. Load address includes the
32-byte head, so code starts at `0x40800020`.

## CPUs

- Main CPU is a Panasonic/Socionext "AM" core (MN103 / AM33 family). Opcode
  bytes (`fc cc`, `fc dc`, `fa fe`…) look like MN103. Strings: `am2arm`, `arm2am`.
- An ARM Cortex-A9 coprocessor is booted by the AM core with Linux or ITRON
  (`ARM Cortex-A9 start`, `load arm linux`, `load arm itron`).
- The main code is plain MN1030-family code: `tools/disasm.py` (opcode table
  generated from the manual in this repo) decodes all of block 0 except ~30 KB.
- **Block 0 runs at `0x60021020`** (not the header's `0x40800000`), same as
  E-M1 II / PEN-F. Found by matching `MOV imm32` pointers against string offsets.
- `0x6002372a`: debug printf (4073 callers).
- `0x47001165` / `0x47001059`: memset / memcpy (boot ROM, outside the firmware;
  pattern `a0=buf, d0=0|src, d1=len`). Many `0x380` immediates are sizes passed
  to these, not the colour-tone-dial setting ID.
- `0x600ee604`: strcmp.
- Candidate setting accessors (called after `MOV <setting id>,d0` with many
  different IDs): `0x605f6378`, `0x60689723`, `0x6145225c`, `0x602eeec8`. Unverified.
- Mode-controller ("mcon") API jump table at `0x602ca8b3`: `+0` down(mode),
  `+9` up(mode), `+0x12` get(mode) (wrappers around `0x602cb5f9`, `0x602cb74c`,
  `0x602cb8f4`). Used by the mcon debug shell (`mcon_if_debug.c`, handler near
  `0x615d2f89`; e.g. `mcon dialp mu` = up(MODE_DIAL_MAIN_PROGRAM)).
- `0x614a4fd9` is a trace logger (`a1=0x12345678`, `a0`=source file name,
  `d1`=line number). Its `d1` values are line numbers, not setting IDs.

## Setting-name table (block 2, offset `0x20403f0`)

Entries are 52 (0x34) byte NUL-padded strings; **entry index = setting (mode)
ID**, confirmed from the mcon shell (`dialp`→70 `MODE_DIAL_MAIN_PROGRAM`,
`diala`→74 `MODE_DIAL_MAIN_APERTURE`, `cdial c3/c4`→0x40b/0x40c
`MODE_CUSTOM3/4_DIAL`). Some later entries are misaligned/truncated.

## Feature: 65:24 aspect

Not present. Aspects found: 4:3, 16:9, 3:2, 6:6 (1:1), 3:4, 17:9
(`MODE_ASPECT_RATIO_*`, `mdet_laf_convert_dz_to_asp_*`). Adding 65:24 means new
code: crop geometry, live-view frame, EXIF, menu entry and strings.

## Feature: Color Creator / Monochrome Creator on a button

The code is already in the firmware, driven by a "colour-tone dial" setting
(the PEN-F-style front creative dial):

- `MODE_COLORTONE_DIAL` with values `_NEUTRAL`, `_ART`, `_COLOR_CREATOR`,
  `_COLOR_CREATOR_2`, `_MONOCHROME_CREATOR`, `_MCON`, `_NON`
- Full parameter sets: `MODE_COLOR_CREATOR_2_*`, `MODE_MONOCHROME_CREATOR_*`
  (granular, shading, tone control, monotone filter/colour, SET1–3)
- `MODE_CURSOR_SELECT_CONTROLES_{COLOR_CREATOR,COLOR_CREATOR_2,MONOCHROME_CREATOR}`
- Block 0 strings `colorprofile`, `monochromeprofile`

Multi Function menu: `MODE_EVF_FN` plus on/off items
`MODE_EVF_FN_ONOFF_{TONE_CONTROL,LV_MAGNIFY,ASPECT_RATIO,COLOR_CREATOR,WB_ISO,ISO_WB,PEAKING,NATURAL_VIEW,ISO,WB}`
(IDs `0x27f`–`0x284`, `0x2ff`, `0x532`, `0x5b6`, `0x5b7`). Classic Color Creator
already appears to be a Multi Function item; the dial-only modes are
`COLOR_CREATOR_2` (Color Profile) and `MONOCHROME_CREATOR` (Monochrome Profile).

The user confirmed: Multi Function "Color Creator" is the classic one-hue
creator. Wanted: Color Profile (`COLOR_CREATOR_2`, 12 saturations
`VIVID_1..12`) and Monochrome Profile (`MONOCHROME_CREATOR`).

- Image processing supports both: `chColorCreator2Saturation[0..11]`,
  `ucMonochromeCreatorLevel/Granular/Shading` (imgpro param dump strings).
- Dial position list (u32) at `0x60265ad8`: 0x381 NEUTRAL, 0x382 ART,
  0x383 COLOR_CREATOR, 0x384 COLOR_CREATOR_2, 0x3c6 MONOCHROME_CREATOR,
  0x385 NON, then 0x6f MODE_COLORTONE. No direct pointer to it; probably one
  record of a larger table.
- `0x6145225c` is called 18x with 0x384 (COLOR_CREATOR_2): likely an
  "is dial position X" check.
- Few code immediates reference these IDs, so menus/panels are table-driven
  (IDs stored as u16/u32 in data).
- Wi-Fi: `colorprofile`/`monochromeprofile` are myset backup "kind" values
  (`request_getmysetdata.cgi` etc.), so the profile data model exists on this
  body. The `set_camprop` property list has no colour-tone or creator property,
  so no remote shortcut. OI.Share capability XML lists `<support func="firmup"/>`
  (Wi-Fi firmware update), worth studying as an install path.

Likely approach: find the code that reads the (absent) dial position into
`MODE_COLORTONE_DIAL` and the button-function assignment table, then add a
button function that cycles that setting.

## Color Profile / Mono Profile as picture modes (new lead)

The firmware contains the newer "profiles as picture modes" model (three
presets each), not only the PEN-F creative dial:

- Picture Mode list toggles: `MODE_COLORTONE_COLOR_CREATOR_2_SET1..3_ONOFF`
  (`0x40e`-`0x410`), `MODE_COLORTONE_MONOCHROME_CREATOR_SET1..3_ONOFF`
  (`0x411`-`0x413`), next to the usual `MODE_COLORTONE_*_ONOFF` toggles
  (`0x157`-`0x167`, `0x24a` Color Creator, ...).
- Preset selectors: `MODE_COLOR_CREATOR_2_SELECT` (`0x386`),
  `MODE_MONOCHROME_CREATOR_SELECT` (`0x3c7`); dial copies `0x433`/`0x434`;
  RAW-edit copies `0x402`/`0x403`/`0x406`/`0x407`.
- Picture Mode values (`MODE_COLORTONE`, value-name list at block 2
  `0x2073ffc`): I_FINISH, VIVID, NATURAL, FLAT, SOFT, MONOTONE, CUSTOM, BEAUTY,
  UNDERWATER, COLOR_CREATOR, POPART ... PLACAME. No separate profile value, so
  profiles are probably Color Creator variants chosen by the selectors.
- UI text exists (block 1, UTF-16LE): "Color Profile 1-3", "Mono Profile 1-3"
  (short labels after ART filter labels and C3/C4), "Monochrome Profile 1-3"
  with icon codes `@A0B2@`-`@A0B7@`. Language block = 72 sections of
  NUL-terminated UTF-16 strings; string-ID scheme not yet decoded.
- Debug-shell code at `0x615cfc00`-`0x615d2fff` references all six toggles
  (confirms the IDs).

Likely patch: un-hide these picture-mode entries (find the model capability
check / list builder) instead of adding a button function.

## Mode storage internals

- get(mode) `0x602cb8f4`: kind = `0x602dc310(id)`; custom descriptor via
  RAM hash `0x621171a8` (64 buckets, +20 = getter fn); else `0x602eeec8`
  (u16 array at `0xa262ac38 - 12000 + 2*id` for id 6000..) or `0x602cbb47`.
- Conf records: RAM hash `0x62119a40` (128 buckets) filled at boot from ROM
  records at `0x604da438`, 20 bytes each, 0x58e of them (extended IDs).
- `0x605f6378` / `0x605f663b` are mode-change trace/notify hooks, not getters.
- `0x6145225c` is a fixed-point conversion (`0x384` there = 900), not a mode check.

## Pitfall

Linear-sweep disassembly decodes data as code, and setting IDs are small
numbers that collide with line numbers, sizes and constants. Several
"immediate = setting ID" hits were false. A recursive (call/branch-following)
disassembly is needed before trusting xrefs.

## Outside resources (E-P7 / PEN-F projects)

- **cakelesscoder/caduceus-ep7** (Apache-2.0): E-P7 firmware patches on the same
  CPU family. Install path: SD card `DCOLYMP/E1xx9999.BIN` (E-M1 III:
  `E1399999.BIN`), hold OK while powering on; light steady while writing,
  blinking when done. Restore = flash stock the same way. Their notes on the
  E-M1 III: main block base `0x60021020` (matches ours); "firmware analysed on
  disk only"; GUI/OSD/updater code not found in plain form, suspected
  compressed (~8-10 MB, 13-14 MB). Their COLOR profile *editor screens* are
  said to be absent on E-M1 III; the settings and labels are present here.
- **fishcu/oly_fw_analysis** (Apache-2.0 + GPL-3.0 sim): PEN-F HSL mod,
  component decoder, MN103 emulator (patched GNU sim from binutils-gdb),
  firmware inventory. Stock E-M1 III 1.5 = sha256
  `0fbc7b82dff3e5cc7de2c6a0793fcee2b89941f89805df05c75796608214902a`,
  1.6 = `4f9ea315a2f2280dd5746abc39b5e4b038f183836eadfbe9d96b266e49a09aac`. Historical E-M1 III patch
  `e1399999.bin` (sha `4786323c...`) is v1.2. Our file (`fec00684...`, header
  version 1.5) is not in the inventory: probably stock 1.5 + a focus-stacking
  allowlist patch.

## Compression check (our measurements)

Per-MB: entropy ~7.36 and only 8-19 % reached by recursive disassembly at
8-10 MB and 12-14.5 MB (runtime ~`0x60821020-0x60a21020`,
`0x60c21020-0x60eb1020`), vs 45-80 % elsewhere. Standard formats (zlib/gzip/
xz/lzma/bz2) not found; raw-deflate hits are false positives. Section-table
search (E-P7 style, 9 x `{start, src, dst}`) not found yet.
