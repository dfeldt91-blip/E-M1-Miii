# Monochrome II in the i-Finish slot

`tools/patch_mono_slots.py` turns **i-Enhance / i-Finish** into **Monochrome II**:
a monochrome picture profile that uses the stock Monotone engine and has its
own picture-profile settings. It is placed immediately after Monotone in the
Picture Mode menus.

## What it changes

| Item | Stock | Patched |
|---|---|---|
| Validator slot 0 (i-Finish, GUI value 7) | pipeline 7, filter 0 | copy of stock Monotone: pipeline 5, filter 1 |
| String `0x091` | `i-Enhance` | `Monochrome II` |
| String `0xca9` | `@A089@i-Enhance` | `@A089@Monochrome II` |
| Picture Mode menus | i-Finish at index 0, Monotone at index 5 | Monotone then i-Finish/Monochrome II, relabelled |

The two renamed strings are written into the even-aligned UTF-16 padding after
the language pointer table (block 1, English section). Allocation is idempotent
and tracks reserved ranges, so it also works when this mod is chained with
other language mods in the builder.

Blob B's three Picture Mode menu lists (descriptors `0x611af718`,
`0x61206bc8`, `0x6128837c`) are edited in place: i-Finish gets string `0x091`,
Monotone `0xac5`, Underwater `0xac6`, e-Portrait `0xac7`, and the first ten
entries are reordered so i-Finish sits after Monotone. The script still also
copies the Monotone entry into the Underwater and e-Portrait validator slots
from the earlier experiment; those slots are labelled Monochrome 2 and 3.

Blob B is unpacked, edited, LZ4-repacked and verified to round-trip. Every
stock byte relied on is checked before writing.

The two renamed strings use 68 of the 74 bytes in the gap after the language
pointer table. The **Owner title** mod can still be selected: when that gap is
full it writes longer owner text into the unused zero area after the English
trailer instead of failing.

## Effect-strength cell

The i-Enhance effect-strength cell (`Low / Standard / High`) still appears.
An attempted Blob A data patch changed the `0x19c4` comparison to `0x7f`, but
that removed the Monochrome II cell itself, so it was reverted. Removing only
the effect-strength cell needs a proper Blob A code patch and is not solved
here.

## Build and check

```bash
python3 tools/patch_mono_slots.py E1399999_Focus_Stack.BIN out/E1399999.BIN \
    --version 0x1780 --report
python3 tools/olyfw.py info out/E1399999.BIN
python3 tools/olyfw.py verify out/E1399999.BIN
```

The script refuses to run on firmware whose 0x6f validator record, stock GUI
value list, validator entries or Picture Mode menu lists differ from stock.

## Camera status

Confirmed on camera (test 1.7.7.8): the Monochrome II profile is monochrome,
and both the menu/submenu label and the SCP cell label read `Monochrome II`.
The effect-strength cell is still visible but has no effect on the monochrome
profile.
