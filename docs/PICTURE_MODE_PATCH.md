# Picture Mode patch: Color Profile + Monochrome Profile (EXPERIMENTAL)

Status: built and statically verified. **Not run on a camera, not run in an
emulator.** Use at your own risk; modified firmware can crash or brick the
camera.

## What it does

Adds two entries to the E-M1 Mark III Picture Mode list:

| Entry | Pipeline mode | GUI value | Copied from |
|---|---|---|---|
| Color Profile | 11 | 54 (`0x36`) | stock dial-less list `MODE_COLORTONE_DIAL_NON` (0x385) |
| Monochrome Profile | 12 | 57 (`0x39`) | same |

The stock list (setting `0x6f`, 26 entries) has no 11/12; the dial-less list and
the PEN-F-style dial lists do. The image pipeline handles types 11/12 on this
body (imgpro builder `0x60418d51`, see FINDINGS.md).

Expected on camera: the two modes selectable like other Picture Modes; photos
rendered with Color/Mono Profile using the currently stored preset values
(probably defaults). **No on-camera editor**: none was found in this firmware,
and the SCP INFO handler (`0x60e7e4e1`) has no branch for 54/57.

Unknowns: menu/SCP labels may be blank or odd; the "Picture Mode Settings"
hide toggles may filter the new entries; which preset (1-3) is used is not
confirmed (probably `MODE_COLOR_CREATOR_2_SELECT` 0x386 /
`MODE_MONOCHROME_CREATOR_SELECT` 0x3c7); GUI code that assumes 26 entries was
not ruled out; OM Workspace RAW development may not reproduce the look.

## Exact change (main block, component 0x100)

| Address | Size | Stock | Patched |
|---|---|---|---|
| `0x604da7bc` (record of 0x6f) | 20 | `6f00 8000 f4c44b60 34e84a60 8006 4000 00060000` | list `0x600d7000`, alt `0x600d7700`, bytes `0x0700` |
| `0x600d7000` | 1792 | 0xff padding | 26 stock entries + entries for 11 and 12 |
| `0x600d7700` | 112 | 0xff padding | 26 stock GUI values + 0x36, 0x39 |

Plus the block checksum. 1916 file bytes change in total.

Free space: `0x600d24f0-0x600d8000` is 0xff padding after a string table, inside
the base section the boot code copies from flash (`0x4080f000` ->
`0x60030000`..`0x600e0800`). No code immediate or branch points into it; the
few aligned words that look like pointers into the run are instruction bytes.
The stock lists are referenced only by the record (no code references).

## Build

```bash
python3 tools/patch_picture_modes.py E1399999_Focus_Stack.BIN out/E1399999.BIN --report
python3 tools/olyfw.py info out/E1399999.BIN
```

The script checks the record, both stock lists, the dial-less 11/12 entries and
the free area byte-for-byte, and refuses to write if anything differs.

## Install path (from the firmware; E-P7 procedure)

The card updater (`api_firmup.c`, strings at `0x604e4bf9`, `0x60f1c0d8`) looks
for folder `DCOLYMP` and `E139????.BIN`. On the E-P7 the update is started by
holding OK while switching on (caduceus INSTALL.md); this is unconfirmed on the
E-M1 III.

## Before any flash

1. Keep a restore file: the exact firmware the camera runs now (if that is
   `E1399999_Focus_Stack.BIN`, keep it; otherwise get stock 1.5 from OM).
2. Full battery, card formatted in the camera.
3. Test order (caduceus BODIES.md): first re-flash the camera's *current*
   firmware through the card updater and confirm it boots; then the patched
   file; then restore once to prove the way back.

## Test plan after flashing

- Picture Mode menu and SCP: are Color Profile and Mono Profile listed, with
  what labels/icons?
- Select each, take JPEGs of a colourful scene; compare with Natural/Monotone.
- INFO on the entries: what happens?
- Power cycle: does the selection persist? Any error?
- Restore the original file and confirm the camera is back to normal.

## Camera results (2026-11)

| Build | Change | Result |
|---|---|---|
| 1.590-1.593 | new list entries 11/12, menu option lists, 0x6f rule maps, toggle table 0x611cfbc0 | nothing visible |
| 1.594 diag | Muted out of validator, Portrait out of menu lists, Custom on ONOFF 0x40e | all three still shown: none of these lists drive the menu/SCP |
| 1.595 `--repurpose` | Custom entry pipeline 6 -> 11, e-Portrait 8 -> 12 (2 bytes at 0x604bc674 / 0x604bc6b4) | e-Portrait shoots black and white (Monochrome Profile); Custom looks like Natural (Color Profile defaults are flat); minor graphic glitch; EXIF shows the menu name |

So the validator list's pipeline type drives the image pipeline, while the menus use GUI-side lists
behind a filter not found yet. No editor for the profile parameters (12 saturations etc.).
