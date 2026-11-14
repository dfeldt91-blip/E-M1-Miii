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
- Disassembly needs an MN10300/AM33 disassembler: GNU binutils built with
  `--target=mn10300-elf` (`objdump -m am33-2`), or Ghidra/IDA with an MN103 module.

## Setting-name table (block 2, offset `0x20403f0`)

6163 entries of 52 (0x34) byte NUL-padded strings; entry index is presumably
the setting ID (`MODE_DRIVE` = 0, `MODE_AE` = 1, …).

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

Likely approach: find the code that reads the (absent) dial position into
`MODE_COLORTONE_DIAL` and the button-function assignment table, then add a
button function that cycles that setting.
