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
