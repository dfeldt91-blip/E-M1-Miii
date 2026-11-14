# 65:24 (XPan "Panorama") aspect on the E-M1 Mark III (EXPERIMENTAL)

Built with `tools/patch_aspect.py` from the 1.5-based `E1399999_Focus_Stack.BIN`.
Approach ported from the E-P7 notes (cakelesscoder/caduceus-ep7 `docs/ASPECT.md`): the hidden
aspect id 6 (stock 7:6) is repurposed as 65:24 and labelled "Panorama" (string 0xf1).

```bash
MN10300_BIN=/path/to/mn10300-elf/bin RT_LST=/path/to/rt.lst \
  python3 tools/patch_aspect.py E1399999_Focus_Stack.BIN out/E1399999.BIN --stage9 --version 0x1581
```

Each stage includes the previous ones. All addresses are runtime addresses
(main block offset + 0x60021020); blob A/B are the LZ4 "olycompress" GUI/code blobs, edited
unpacked and recompressed (LZ4 HC 12 reproduces stock byte for byte).

## Camera results (latest: stage 9, 1.581)

| Area | Result |
|---|---|
| Menu + SCP selectable, label "Panorama" | OK |
| JPEG/ORF 5184x1920 (High Res 10368x3824 / 8160x3008), no squash | OK |
| Live view framing | OK |
| SCP size readout | OK |
| Kept across power cycle | OK |
| AF target selection (S-AF), touch AF | OK |
| C-AF, C-AF+TR | OK |
| AF point on shooting screen | C-AF small OK; C-AF larger sizes show a small and a large frame; S-AF none |
| Metering / AEL spot mark | missing |
| Grid | not handled (16:9 bitmaps would be wrong) |

## Stages

| Stage | What | Where |
|---|---|---|
| 1 | diagnostic: validator byte count (3:4 removed) | validator record 0x604dc954 |
| 2a | allowed values [1,3,2,4,9,6] | new u8 list 0x600d7000 |
| 2b-2d | menu option lists, menu label list 0x612941d4, SCP rows 0x611fe0e4 and row 17 0x611eeedc | blob B |
| 2e | restriction rule 12 (stills) map + {6,6} | rule record 0x60492f00 (engine 0x602d4bb5; step skips 0x100) |
| 3 | W/H size-class rows 0x60549864/0x60549a14, ORF frame jump 0x60549770, ratio pair 0x6025ab44 -> 65:24 | |
| 4 | 49 per-aspect (w,h) tables (E-P7 scanner), 8 LV/playback box switches -> 640x240, AF target lists 0x611950e8 | |
| 5 | SCP readout table (0x60ee1756, 6 columns), AF target position tables (16 load sites 0x60ed1474..) | |
| 6 | AF cursor range switches 0x60ecff4d / 0x60ed065b (switch tails -> stubs) | |
| 7 | AF actuator ranges 0x60de0d9e, layout index 0x60d430b8, widgets 0x60dbc161 (`--ratio16` variant 1.597 did not install; probably low battery, unproven) | |
| 8 | local 6->3 remaps after GetValue(0x10d): metering 0x60e32995, overlay obj+300 0x60e0f215, SCP viewers 0x60e2189d/24e07/251c3/26e5c | |
| 9 | AF/tracking ratio-pair globals 0xa27212e1/e2: 65:24 -> 16:9 after the 3 writers 0x60609a92 / 0x60616f31 / 0x6061c23b | fixed C-AF/TR |

Free space used: 0x600d3000-0x600d6100 and 0x600d7000-0x600d7800 (0xff padding in the boot-copied
base section; no aligned references).

## Install notes (observed)

- Card: `DCOLYMP/E1399999.BIN`. The updater skips a file whose main-block version equals the
  installed one; downgrades (1.596 -> 1.5) are accepted.
- A successful install may end with the light simply going out (no blinking). Check the result
  (e.g. Panorama present / absent) instead of the light.
- Firmware screen always shows 1.5 (it reads a stored property, not the file header).
- Restore: the original file, or the original with only the version changed (e.g. 1.599).

## Open

- Rec_Info_Viewer (shooting info) reads the aspect via getter 0x60d00909 at ~13 sites
  (0x60e54bc2 .. 0x60e5c451) with per-aspect lists 0x6122xxxx; likely source of the missing
  metering mark / S-AF point and the double C-AF frame.
- 17:9 movie label slot in list 0x612941d4 is now Panorama (10 is never offered for stills).
