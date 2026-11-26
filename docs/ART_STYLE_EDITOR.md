# Art-filter style editor: probe and current edit points

`tools/patch_art_styles.py` is a read-only probe plus a small patcher for the
built-in Art Filters. It works on the stock 1.6-family firmware used by this
project (`E1399999_Focus_Stack.BIN`, runtime base `0x60021020`).

```sh
# List every mapped table and every shared-table group:
python3 tools/patch_art_styles.py FIRMWARE.BIN --probe

# Apply a style config (checksums are rebuilt automatically):
python3 tools/patch_art_styles.py FIRMWARE.BIN OUT.BIN STYLES.json [--version 0x1622]
```

The patcher verifies the input block checksums, writes only the selected tables,
and verifies the output checksums. Re-run `tools/art_filter_dump.py OUT.BIN out.md`
to confirm the edited values. `--probe` also dumps both processing-chain hash
tables (`0x6052dab0` and `0x6052dbb0`) so the dispatch handlers can be checked
before attempting a code-level module patch.

## What the reverse engineering established

Each art filter is a picture-mode code in the 64-byte Picture Mode list at
`0x604bc4f4`: `0x64` Pop Art, `0x65` Soft Focus, `0x66` Pale & Light Color,
`0x67` Light Tone, `0x68` Grainy Film, `0x69` Pin Hole, `0x6a` Diorama,
`0x6b` Cross Process, `0x6c` Gentle Sepia, `0x6d` Dramatic Tone, `0x77` Key Line,
`0x78` Watercolor, `0x79` Vintage, `0x7a` Partial Color, `0x7b` Bleach Bypass,
`0x7c` Instant Film. Image-processing jobs tag themselves with
`0x01VV00MM` at job +52 (`MM` = code, `VV` = variant 1/2/3).

The image pipeline selects per-filter behaviour with compiler hash switches on
that key (or key-8/11). The mapped stages are:

| Stage | Selector | Per-filter data | Editable here |
|---|---|---|---|
| Tone curve | `0x603df05c`, switch `0x603df193` (key-11) | 256 x u16, output 0..1023 | yes |
| Colour params | `0x603dd0c3`, switch `0x603dd128` | 2 x 6 s16, A then B -> request +100..+122 | yes (raw values) |
| Colour matrix | `0x603dbf28` | 3 x 3 s16, 256 = 1.0 (Pop Art only) | yes |
| Coefficient record | `0x603de54d`, switch `0x603de57d` | 13-pointer record -> coefficient block | no |
| Register record | switch `0x603d88b1` (key-8) | 100-byte packed record | no |
| Processing chain | switch `0x60384953` (key-11) | extra module entry points | no |

Details and per-filter addresses: [ART_FILTERS.md](ART_FILTERS.md) and
[ART_FILTERS_DATA.md](ART_FILTERS_DATA.md).

### Proven edit points

* **Tone curve** — replaces a 512-byte table. The art-filter curve is fixed, so
  the camera's Contrast setting has no effect on art filters. Camera tests of
  the related `patch_art_gradation.py` confirmed that these curve tables drive
  both live view and the saved photo.
* **Colour parameters** — two 6-word s16 tables. Packer `0x603dd053` writes
  `A[0..5]` to request `+100..+110` and then `B[0..5]` to `+112..+122`; the 12
  words are A-first, **not** interleaved. Dramatic Tone I/II clear all 12 via
  `0x603dd0aa`. No CPU reader of `+100..+123` was found: the values are proven
  written but their visual meaning, scale and units remain unproven (possibly
  consumed by hardware/DMA or an opaque request-block path). Stock Pop Art I
  (`[53,76,100,56,-1,48]` / `[1,8,10,0,22,-10]`) and Diorama
  (`[48,44,64,32,28,48]` / `[-1,7,-2,-2,-8,-7]`) have the largest values, which
  suggests a saturation/hue-sector control, but this is only a hypothesis.
  Camera probe: change one word at a time (e.g. Pop Art I `A[0]` at runtime
  `0x6051b0f2` / file `0x4fa0d2` from `53` to `0`) and compare live view and a
  saved photo; repeat for `B[0]` at `0x6051b0fe` / `0x4fa0de`.
* **Colour matrix** — only Pop Art I/II have their own matrix; it is a mild
  saturation boost (~+6%).

### Colour-parameter byte map

Each A/B table is 12 bytes: six little-endian s16 values in memory order.
File offset = runtime address − `0x60021020`.

| Filter(s) | A address / file offset / bytes | B address / file offset / bytes |
|---|---|---|
| Pop Art I | `0x6051b0f2` / `0x4fa0d2` / `35 00 4c 00 64 00 38 00 ff ff 30 00` | `0x6051b0fe` / `0x4fa0de` / `01 00 08 00 0a 00 00 00 16 00 f6 ff` |
| Pop Art II | `0x6051b1b2` / `0x4fa192` / `00 00 f9 ff 00 00 00 00 00 00 00 00` | `0x6051b1be` / `0x4fa19e` / `00 00 0d 00 fa ff 04 00 fd ff ff ff` |
| Soft Focus | `0x6051b0da` / `0x4fa0ba` / `07 00 26 00 19 00 0a 00 0f 00 0f 00` | `0x6051b0e6` / `0x4fa0c6` / `fe ff 08 00 00 00 04 00 fa ff f0 ff` |
| Pale & Light I | `0x6051b13a` / `0x4fa11a` / `00 00 0d 00 00 00 0f 00 fb ff 05 00` | `0x6051b146` / `0x4fa126` / `ff ff 0a 00 00 00 00 00 02 00 fe ff` |
| Pale & Light II | `0x6051b19a` / `0x4fa17a` / `00 00 0d 00 00 00 05 00 07 00 00 00` | `0x6051b1a6` / `0x4fa186` / `ff ff 06 00 06 00 ff ff 02 00 f9 ff` |
| Light Tone | `0x6051b152` / `0x4fa132` / `00 00 08 00 00 00 00 00 00 00 03 00` | `0x6051b15e` / `0x4fa13e` / `fd ff 08 00 00 00 00 00 00 00 fb ff` |
| Pin Hole I/II/III | `0x6051b16a` / `0x4fa14a` / `07 00 12 00 13 00 ff ff 0c 00 0c 00` | `0x6051b176` / `0x4fa156` / `00 00 05 00 ff ff fd ff f6 ff fa ff` |
| Diorama I/II | `0x6051b182` / `0x4fa162` / `30 00 2c 00 40 00 20 00 1c 00 30 00` | `0x6051b18e` / `0x4fa16e` / `ff ff 07 00 fe ff fe ff f8 ff f9 ff` |
| Watercolor I/II | `0x6051b23a` / `0x4fa21a` / `00 00 00 00 3c 00 00 00 d8 ff 00 00` | `0x6051b246` / `0x4fa226` / `ff ff 08 00 00 00 00 00 ec ff 00 00` |
| Vintage II | `0x6051b252` / `0x4fa232` / `00 00 c4 ff 00 00 f1 ff 00 00 00 00` | `0x6051b25e` / `0x4fa23e` / `ff ff 08 00 00 00 00 00 23 00 00 00` |
| Default (many filters) | `0x6051b032` / `0x4fa012` / all zero | `0x6051b03e` / `0x4fa01e` / `ff ff 08 00 00 00 00 00 00 00 00 00` |

Dramatic Tone I/II have no table; the writer clears the request words instead.
A secondary interpolation path around `0x603cb4ac` uses additional tables
(`0x6051b1ca`, `0x6051b1ce`, `0x6051b1e6`, `0x6051b310`, `0x6051b314`,
`0x6051a4ae`, `0x6051a4c6`, `0x6051a4d2`, `0x6051a4d6`) and still calls the
same packer at `0x603cb62a`.

### Stage E register records (layout decoded, meaning unproven)

The 100-byte record at `0x604f8e..0x604f92xx` is two identical 50-byte rows:

```text
A[16] | B[16] | S | C[16] | pad       (row size 50, S and pad are 0 in stock)
W[i] = (C[i] << 16) | (B[i] << 8) | A[i]   for i = 0..15
```

Selector `0x603d8873` (switch `0x6053b738` on key-8) picks the record; `0x603d8a4e`
unpacks it into `job+0x130` (scalar `S<<16`) and `job+0x134+4*i` (`W[i]`), and
`0x603ca2a1` copies the record verbatim into request +29..+128. Downstream
14-dword reads from `+0x130`-based tables at `0x60396ead`, `0x60396ec8`,
`0x60396f8b` and `0x60396fb8` link it into image processing.

Distinct records: Pop Art I `0x604f8f96`, Pop Art II `0x604f9252`, Pale & Light
I `0x604f91ee`; shared common `0x604f8f32`; shared late `0x604f8ece`.
`--probe` prints the 16 words per record. The config field `register_words`
(16 integers 0..`0xffffff`) rewrites both rows; the scalar byte is preserved.
This is structurally proven but visually unproven: treat it as an experiment.

### Stage D coefficient records (layout decoded, meaning partial)

Each record is 13 pointers (52 bytes). `pointer[0]` is a coefficient block;
`pointer[1..12]` all point to the shared luminance row table `0x6051a7a8`.
`0x603de84b` returns `pointer[0]` and the batch builder stores it at request +16.
Consumer `0x603c59cf` uses a breakpoint table at `0x6051b334`
(`1280,1536,…,4096`) and, for each of 12 groups `n`, interpolates one u16 from
the row table and writes 3 signed u16 to the destination:

```text
group n starts at block + 0x0c + 0x1c*n
dest_u16[3*n + k] = (interp * i16(block + 0x0c + 0x1c*n + 2*k)) >> 8   (k=0..2)
```

So the only bytes proven to be read from the coefficient block are the 6-byte
windows at `+0x00c, +0x028, +0x044, +0x060, +0x07c, +0x098, +0x0b4, +0x0d0,
+0x0ec, +0x108, +0x124, +0x140` (and the 12-byte header `+0..+0xb` is unused by
this consumer). `--probe` prints these 12 triples for every filter.

Important: for Partial Color, Bleach Bypass II and most of Instant Film the
consumed triples are `(0,-768,0)` — the distinctive look is in the *unproven*
header and per-group tail bytes (`group+0x06..+0x19`), which contain structured
hue/strength values (e.g. `2c72/2000`, `41c7/2000`, …). Editing only the proven
coefficient windows would mostly change a constant scaling term for those
filters. This stage is therefore probe-only in the editor.

### Shared tables

Several filters deliberately share one physical table because they share one
switch handler. Changing it changes all of them:

* `0x6050bfa2` Diorama I + II; `0x6050cba2` Pin Hole II + III;
  `0x6050cfa2` Dramatic Tone I + II (tone curves).
* `0x6051b16a/b176` Pin Hole I + II + III; `0x6051b182/b18e` Diorama I + II;
  `0x6051b23a/b246` Watercolor I + II (colour params).
* `0x6051b032/b03e` is the *default* colour table used by Grainy Film,
  Cross Process, Gentle Sepia, Dramatic Tone, Key Line, Vintage I/III,
  Partial Color, Bleach Bypass and Instant Film. Editing it changes all of them,
  including normal picture modes.
* `0x6051affc` matrix: Pop Art I + II.

The patcher refuses a config that assigns different values to one shared table.
Per-variant differences would require copying the table to free RAM and
re-pointing the immediate in the shared handler — possible for some stages, but
not for the default path, and not attempted here.

### Not editable yet

Conditional tone curves (Key Line, Watercolor, Bleach Bypass II, the special
passes of Grainy Film and Instant Film) are handled by code paths rather than a
single fixed table; the patcher rejects them. Dramatic Tone clears all 12 colour
parameters in code (`0x603dd0aa`) rather than loading a table.

The characteristic *effects* (Soft Focus blur, Grainy Film grain, Diorama blur,
Key Line extraction, Watercolor passes, Vintage/Bleach short chains, frame and
vignette) come from extra processing modules added by the chain builder
`0x60384438`. The dispatch, slot layout and consumer are now decoded in
[ART_FILTER_CHAIN.md](ART_FILTER_CHAIN.md): a 16-entry secondary hash at
`0x6052dbb0` is checked first and wins, then the 32-entry primary hash at
`0x6052dab0`; the 12-byte slots live at `job+0x2ae8` and are called by
`0x60381146`. Individual module roles, pass IDs and single-site patch points are
now decoded in the same document; this editor still exposes only data tables, so
module edits remain separate code patches. `tools/patch_hires_art.py` shows one practical
consequence: in High Res Shot the colour and tone are applied but these extra
effect steps are skipped.

Two existing tools already change a separable part of the look and can be
combined with this editor:

* `tools/patch_keyline_mono.py` re-points Key Line II's entry in the toning hash
  at `0x6053e67c` to force a grey vector.
* `tools/patch_grainy_color.py` re-points Grainy Film's toning entry and skips a
  photo-pass compare so grain is rendered in colour.

Both patch code/hash slots rather than the data tables this editor writes, so
apply them *after* the style config (or verify the expected slots are still
stock before applying).

## Config format

Keys are lowercase filter names with `_1`/`_2`/`_3` (or `_i`/`_ii`/`_iii`) for
variants; `art_0x64_1` also works. Fields:

* `curve`: either `"in:out ..."` points with `in` 0..255 and `out` 0..255
  (monotone cubic interpolation, scaled to 0..1023), or a list of exactly 256
  integers 0..1023.
* `colour_a`, `colour_b`: lists of 6 signed 16-bit integers.
* `matrix`: list of 9 signed 16-bit integers (only for Pop Art).
* `register_words`: list of 16 integers 0..`0xffffff` (decimal!) for a filter's
  100-byte register record. Experimental; see above.

```json
{
  "pop_art_i": {
    "curve": "0:0 64:40 128:80 192:140 255:255",
    "colour_a": [53, 76, 100, 56, -1, 48],
    "colour_b": [1, 8, 10, 0, 22, -10],
    "matrix": [273, -14, -3, -7, 266, -3, -7, -14, 277]
  },
  "vintage_3": {"curve": "0:20 64:55 128:105 192:165 255:255"}
}
```

Changes are deliberately conservative: no code is patched, no tables are
moved, and every modified table is one whose address is checked against the
handler that loads it. This makes the result safe to build on top of other mods
as long as they do not use the same table addresses.
