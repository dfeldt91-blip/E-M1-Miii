# Three monochrome Picture Mode slots (EXPERIMENTAL, UNTESTED ON A CAMERA)

`tools/patch_mono_slots.py` turns **Underwater** into **Monochrome Profile 2**
and **e-Portrait** into **Monochrome Profile 3**, and moves them next to
Monotone in the Picture Mode list so the order reads Monochrome 1, 2, 3.

## What it changes

| Mode | Stock | Patched | Stored settings |
|---|---|---|---|
| Monotone (GUI 3) | pipeline 5, filter 1 | unchanged, relabelled "Monochrome Profile 1" | stock Monotone |
| Underwater (GUI 0x1c) | pipeline 10 (colour) | pipeline 12, slot 2 | `MODE_MONOCHROME_CREATOR_*_SET2` |
| e-Portrait (GUI 0x14) | pipeline 8 | pipeline 12, slot 3 | `MODE_MONOCHROME_CREATOR_*_SET3` |
| Custom (GUI 6) | between Monotone and e-Portrait | moved after the three mono slots | unchanged |

**Validator list** (block 0, `0x604bc4f4`, 64-byte entries): the entries at
index 7 (e-Portrait) and 8 (Underwater) are replaced with the stock
`MODE_COLORTONE_DIAL_MONOCHROME_CREATOR` (0x3c6) entries for preset slots 3
and 2 respectively — bytes copied verbatim from `0x604c3cf4 + 64*k`.

**GUI menu lists** (blob B, three copies at descriptors `0x611af718`,
`0x61206bc8`, `0x6128837c`): entries 5-8 are reordered to Monotone, Underwater,
e-Portrait, Custom and their labels change from icons to language strings
`0xac5`/`0xac6`/`0xac7` ("Monochrome Profile 1/2/3"). The GUI **values**
(3, 0x1c, 0x14, 6) and conditions are untouched, so the settings core, the
0x6f restriction rules, the SCP and Live Control keep working with the same
values — only the menu text/order changes.

Blob B is unpacked, edited, LZ4-repacked and verified to round-trip; its
compressed size changes by a few bytes. All other data relied on is checked
byte-for-byte against stock before anything is written.

## Slot vs preset note

The +4 field of a 0x6f validator entry is the value of component setting
`0x6af` (the mono **filter**), not the profile preset selector. By giving
Underwater and e-Portrait filter values 2 and 3 the camera distinguishes them
as separate picture modes and each gets its own filter. The underlying
Monochrome Profile preset (level / grain / shading, SET1..3) is selected by
the global setting `MODE_MONOCHROME_CREATOR_SELECT` (0x3c7), so both new slots
initially use the same preset. Different filter values already produce
different looks; to give each slot its own full preset needs a follow-up code
patch (add 0x3c7 as a component of 0x6f, or have the image builder derive the
preset from the filter field).

## Build

```bash
python3 tools/patch_mono_slots.py E1399999_Focus_Stack.BIN out/E1399999.BIN \
    --version 0x1750 --report
python3 tools/olyfw.py info out/E1399999.BIN
```

The script refuses to run on firmware whose 0x6f record, stock list, DIAL_MONO
list or GUI menu lists differ from stock (e.g. an output of
`patch_picture_modes.py --repurpose` or `patch_looks.py --all31`).

## Camera test plan

- Picture Mode menu: do Monochrome Profile 1/2/3 appear together, in that
  order, with Custom after them?
- Shoot a colourful scene in each: are all three black and white?
- Does changing Contrast / Sharpness / Filter / Mono colour in the Picture
  Mode submenu still work for each slot?
- INFO on each entry: what editor opens, if any?
- EXIF picture-mode name for each slot.
- Power cycle: does the order and the selection persist?
