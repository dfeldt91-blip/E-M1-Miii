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

## Toolchain (this session)

- GNU binutils 2.45 `mn10300-elf` built from the signature-verified ftp.gnu.org
  tarball (`objdump -D -b binary -m am33-2 --adjust-vma=0x60021020`), and the
  GNU MN10300 simulator from GDB 18.1 (`sim/mn10300/run`, built with sim
  hardware enabled; `--disable-sim-hardware` fails to link).
- `tools/disasm.py` / `tools/mn103/mn103.py` agree with GNU objdump on
  99,573 of 99,574 instructions over 0x602c0000-0x60300000.
- `tools/mn103/recursive.py`: control-flow disassembly from the entry;
  3.67 M instructions, 48,028 functions, 27.6 % of block 0 reached.

## String IDs (language block)

Block 1 = 72 sections (languages), same string order in each; string ID =
index of the NUL-terminated UTF-16LE string. English is section 8.
`0x4f4` "Color Creator", `0xabb-0xabd` "Color Profile 1-3",
`0xabe-0xac0` "@A0B2@..@A0B4@Color Profile 1-3", `0xac3-0xac5`
"Monochrome Profile 1-3", `0xac6-0xac8` iconed, `0xb29-0xb2e` short
"Color/Mono Profile 1-3". `0x606f5c40..` draws 0xabb / 0xac8 via
`0x606e93c1(d0=0xf812000, d1=21, a1=string id)`.

## Boot

Reset `0x60021020` -> boot copies via flash reader `0x60022454(a0=flash,
a1=dst, d0=len)` (plain page copies, no decompression):
flash `0x4080f000` -> `0x60030000` (to `0x600e0800`, linear), initialised data
flash `0x40a31800/0x40a69800/0x40a71800/0x40a75800` -> `0x61e72ac0/
0x61eaaac0/0x61eb2ac0/0x61eb6ac0`, flash `0x41e28000` -> `0x61649000`
(0x1800). Then main `0x6003009c`. Remaining sections load later
(`USRSTART2..5`, `USRSTART_LOAD[_1/_2]` names present, as on the E-P7);
the loader and its table are not found yet. `0x6005c2ac..` and
`0x60022675..` are settings-bank (28 slots at flash `0x4eb20000`) readers/
writers, not code loaders.

## Suspect regions: what they are not

Two blobs, roughly block-0 offsets `0x7f5000-0x9eb000` (runtime
`0x60816020-0x60a0c020`) and `0xc78000-0xddf000` (`0x60c99020-0x60e00020`),
4 KB-window entropy 7.0-7.45 throughout (code 6.4-7.0, deflate/LZMA ~7.95).

- Not plain code: decoding as MN103 gives calls whose targets hit known
  functions 3-7 % of the time and the top-300 called functions 0 % (normal code:
  86 % / 51 %).
- Not relocated code: no constant delta maps their call targets onto known
  functions.
- No clean code calls or jumps into them; no clean code loads their RAM or
  flash addresses.
- No zlib/gzip/xz/lzma/bz2 stream; classic Okumura LZSS constants
  (`|0xff00`, `&0xfff`, `0xfee`) not found together in clean code.
- Raw bytes show MN103 fragments (`dd ..` calls, `df ..` returns), so an LZ-type
  compression of code (no entropy coder) remains the best guess, possibly
  unpacked by another CPU or by code not reached here. LZSS literal-scoring
  (flag=1 literal, 2-byte refs, LSB-first) is suggestive for the first blob
  but not conclusive.

## ARM (Cortex-A9) side: not the unpacker

Block 2 sub-image `0x46000000` (block-2 offset `0x2100000`, 14 MB) has its own
directory: kernel (gzip at +`0x17e78`, Linux 4.4.127), initramfs (gzip cpio at
+`0x1d1fe0`), squashfs (LZO, +`0x4887e0`). Contents: Wi-Fi/BT (Broadcom
bcmdhd, CYW43455 firmware, BLE bridge), lighttpd + OI.Share fcgi (`isc_*`),
`sd_reader`, `remocon`, `hhhr` (matrix math for High Res Shot, uses /dev/mem).
No decompression of main-CPU data anywhere on the ARM side.

The blobs also show no internally repeated call targets when decoded as MN103
(max 3 callers vs 399 in normal code), so they are not plain code for any core
or base: compressed/encrypted data, possibly not code at all.

Next lead: recursive disassembly reached only 27.6 % of block 0; much plain C++
UI code is reachable only via vtables/handler tables. Extend seeding before
assuming the Picture Mode list is inside the blobs.

## Validator records (format from caduceus RE_SETTINGS.md)

ROM `0x604da438`: 1375 x 20-byte records `{u16 sid, u16 attr, u32 list, u32 list2,
u16 bytes, u16 elem, u8 ?, u8 type, u16 ?}`; type 1 u8 list, 2 s8, 3/4 s16,
5 u16, 6 blob. Confirmed by `MODE_ASPECT_RATIO` = [1,3,2,4,9] (same as E-P7).
On the E-P7, editing a setting's validator list changes what menus enumerate
(caduceus ASPECT.md v4).

- `MODE_COLORTONE_DIAL` 0x380 (u16): [0x381 NEUTRAL, 0x382 ART, 0x383 COLOR_CREATOR,
  0x384 COLOR_CREATOR_2, 0x3c6 MONOCHROME_CREATOR]: profiles are valid values.
- `MODE_COLOR_CREATOR_2_SELECT` 0x386, `MODE_MONOCHROME_CREATOR_SELECT` 0x3c7: [0,1,2,3].
- Profile picture-mode toggles 0x40e-0x413: [0,1] (same as all `*_ONOFF`).
- `MODE_EVF_FN` 0x1b4 (Multi Function, u16): [1,6,11,12,2,3,9,10] (8 items).
  Debug value names (`MODE_EVF_FN_NONE .. _WB`, 12 names) are not in value order.
- `MODE_COLORTONE` 0x6f: type 6, 26 x 64-byte blobs at `0x604c5ef4` (not decoded).

## Menu option lists not in plain form

E-P7 menu lists are 12-byte `{u32 value, u16 type, u16 string, u32 cond}`
entries under `{u16 sid, u16 count, u32 list}` descriptors. No such lists exist
in E-M1 III block 0, and no table holds the Color/Mono Profile string-ID trios
(0xabb.., 0xac3.., 0xb29..) at any stride in blocks 0/1/2/4. Consistent with
caduceus: the E-M1 III GUI tables/code sit in the compressed blobs. The E-P7
section table shape `(start, flash src, dst)` is absent too.

## Image processing supports Color/Mono Profile on this body

Imgpro parameter builder `0x60418d51..` (dump strings at `0x61623bd6..`, dump code
`0x615e0548..`). Parameter block fields: +5536 CC hue, +5537 CC sat,
+5538..5549 Color Profile saturations x12, +5550 mono level, +5551 grain,
+5552 shading. The builder reads the effective picture-mode type at settings
snapshot +26087: if 11, copies 12 u16 saturations from snapshot +26092; if 12,
copies mono level/grain/shading from snapshot +26118..26120. Snapshot fields
come from property keys via `0x6005fa9c(key)` in `0x602c2d5e..` (e.g. key
0xe8f1 -> +26090 CC hue, 0xe909 -> +26091 CC sat). +26087 is written directly
only by the picture-bracket path `0x60411e22` (44-byte bracket entries); the
normal-path writer is not identified yet (many `add 0x65e7` pointer sites).

## SOLVED: the compressed regions ("olycompress" = LZ4)

Header (32 bytes): `"olycompress"` + spaces (16 B), u32 compressed size,
u32 uncompressed size, 8 zero bytes; then a **raw LZ4 block**. Verified:
both main-block blobs consume exactly the compressed size and produce exactly
the uncompressed size. `tools/olycompress.py list|unpack|runtime`.

| Block | Offset | Runtime | Compressed | Unpacked | Load address |
|---|---|---|---|---|---|
| 0 main | `0x7e1fe0` | `0x60803000` | `0x220c23` | `0x469000` | in place, `0x60803000` (89 distinct known call targets match; next best 12) |
| 0 main | `0xc4afe0` | `0x60c6c000` | `0x28959c` | `0x685000` | in place, `0x60c6c000` (105 vs 9) |
| 1 OSD | `0x7e0` | | `0xc9cec` | `0x5a549e` | (OSD data) |
| 1 OSD | `0x9f11e0` | | `0x13dd81` | `0x692cd4` | (OSD data) |

`0x60803000 + 0x469000 = 0x60c6c000` and `0x60c6c000 + 0x685000 = 0x612f1000`
(the reserved 0xff space). The runtime main image = block 0 with both blobs
unpacked in place. Nothing in main code checks the magic (unpacked by boot
ROM / another core / hardware).

The runtime image contains the GUI that caduceus could not find on this body:
`SsMenuLv_*`, `IGui_Controler`, `GPIInitPlatform`,
`Cursor_Move_Set_Mode_Actuator`, `Lv_Control_Mode_Viewer`,
`OlyApiSettingControllerController`, `ColorCreator_Entry/_HandleEvent/
_EvtStChgJogDial/_EvtStChgCtrlRing`, `ColorCreatorScpEvent`,
`MonochromeCreator`, `MONOCHROME_CREATOR_SET1..3`. E-P7-style menu option
lists `{u32 value, u16 type, u16 string, u32 cond}` now appear (678 runs),
including entries for "Color Profile 1/2" (string 0xb29/0xb2a).

To patch GUI code: edit the unpacked image, LZ4-compress again (must fit the
space before the next blob / padding), rewrite the header sizes.

## Picture Mode lists: why Color/Mono Profile are missing (runtime image)

String IDs: real ID = my English-section index + 2 (checked on the aspect menu:
0x124 "4:3", 0x123 "16:9", 0x125 "3:2", 0x6fa "1:1", 0x127 "3:4", 0xcbd
"17:9"). Corrected: Color Creator 0x4f6, Color Profile 1-3 0xabd-0xabf
(iconed 0xac0-0xac2), Monochrome Profile 1-3 0xac5-0xac7 (iconed
0xac8-0xaca), short "Color/Mono Profile 1-3" 0xb2b-0xb30.

Menu/LV descriptors `{u16 sid, u16 count, u32 list}` (e.g. table `0x611af710`:
AE, COLORTONE 54 icons, ASPECT 6, QUALITY 31 ...; three copies at 0x611af...,
0x61206..., 0x61287...). Live Control select array (24-B rows `{sid, n, listA,
listB, ...}`): COLORTONE row `0x611fe03c`, 75 icon entries incl. GUI values
54-59 (= Color Profile 1-3, Mono Profile 1-3 per the E-P7 GUI enum) and
`mode | variant<<16` art types. (Correction: 26 = Vintage, 27 = Partial Color,
from the picture-bracket list builder `0x60a09d51`.)

Validator lists for picture modes are 64-byte entries `{+0 pipeline mode,
+4 profile slot}`:

| sid | list | entries |
|---|---|---|
| 0x6f MODE_COLORTONE (used on this body) | `0x604bc4f4`, 26 | 7,1,2,3,4,5(+4=1),6,8,10,9,100-109,119-124 |
| 0x385 DIAL_NON | `0x604c3df4`, 26 | 7,1-6,8,9,11,12 (slot 0),100-109,119-123 |
| 0x381 DIAL_NEUTRAL | 8 | 7,1..6,8 |
| 0x383 DIAL_COLOR_CREATOR | 2 | 2, 9 |
| 0x384 DIAL_COLOR_CREATOR_2 | 4 | 2, 11/1, 11/2, 11/3 |
| 0x3c6 DIAL_MONOCHROME_CREATOR | 4 | 2, 12/1, 12/2, 12/3 |

Pipeline types 11/12 = Color/Mono Profile (the imgpro builder handles both).
Record for 0x6f: `0x604da7bc` `{0x6f, 0x80, list 0x604bc4f4, alt 0x604ae834,
1664 B, elem 64, type 6}`. Alt lists: CC2 `0x604aefa4` = {1,0x36}, {0x15,0x36};
MONO `0x604aefb4` = {1,0x39}, {9,0xa} (0x36 = GUI 54 Color Profile 1, 0x39 =
GUI 57 Mono Profile 1).

Candidate patch (E-P7 aspect method): give the 0x6f record a new list = the
26 stock entries + {11,1},{11,2},{11,3},{12,1},{12,2},{12,3} (2048 B) placed in
verified free space, and raise its byte count 1664 -> 2048. Open: how the GUI
maps pipeline values to GUI 54-59 labels/icons, the alt-list meaning, and
whether INFO opens the profile editor.

## How the menus enumerate Picture Mode, and what INFO does (runtime image)

- Settings core: count `0x602dbf80` = bytes(+12)/elem(+14) of the validator
  record; value-by-index `0x602dc2c4` (type 6 -> pointer to the idx-th elem-byte
  entry); compound get `0x602cbb47` fills a 64-byte struct with u32 values of the
  component settings from table `0x60469774` (144 x 34 B `{u16 sid, u16 comp[], 3200}`).
- Components: `0x6f` = {111 COLORTONE, 1711 FILTER}; DIAL_COLOR_CREATOR_2 =
  {900, 1075 SELECT}; DIAL_MONOCHROME_CREATOR = {966, 1076 SELECT}; DIAL_NON = {901}.
  So in the 0x6f list +4 is the mono FILTER, not a profile slot.
- Alt lists = GUI value per entry (u32): 0x6f: 7,0,1,2,5,3,6,20,28,21,8..19,26,27,60,63
  (Vivid 0, Natural 1, Muted 2, Monotone 3, Portrait 5, Custom 6, i-Finish 7,
  e-Portrait 20, Color Creator 21, Underwater 28, Art 8..19/26 Vintage/27 Partial
  Color/60/63). DIAL_NON adds {11}->54 Color Profile, {12}->57 Mono Profile;
  dial CC2 -> 54,55,56; dial MONO -> 57,58,59.
- Live Control Picture Mode row (`0x611fe03c`, 75 icons) already has GUI 54-59.

**Patch design (data only):** new 0x6f list = 26 stock entries + {11,0} + {12,0};
new alt list = stock 26 + 0x36 + 0x39; record `0x604da7bc`: list/alt pointers
to the new copies, bytes 1664 -> 1792. Mirrors the stock DIAL_NON list. The
preset used is then presumably MODE_COLOR_CREATOR_2_SELECT (0x386) /
MODE_MONOCHROME_CREATOR_SELECT (0x3c7) (not yet confirmed).

**INFO:** the SCP/Live Control INFO handler `0x60e7e4e1` opens editors only for
row 111 values 27/51/52/53 (Partial Color -> setting 661) and 21 (Color Creator,
`0x60ed7ee1(2)`); no branch for 54-59. No named GUI state for a Color/Mono
Profile editor (152 named states; only RAW-edit Color Creator).
`0x609ec110` packs per-kind picture-mode parameters (kind 5 = Color Profile:
selector 902 then that preset's 12 saturations 933..) - display/metadata, not an
editor. Whether a profile editor screen exists at all is still open.
