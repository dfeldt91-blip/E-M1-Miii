# Art Filter menu enumeration and UI resources

Goal: determine how the camera builds the selectable Art Filter list and what
must be patched to add cloned monochrome filters as real menu entries.

Status: **UI resource and row decoding largely complete**. The exact name
lists, language strings, normal Picture Mode menu list, its 3-entry descriptor
table and 3-entry handler table, Picture Mode selection map, SCP icon records,
validator mapping, 12-byte record decoder output layout, handler/cleanup object
offsets, handler callback dispatch and free space are known. The dispatcher
entry for wizard id `0x7e` and the wizard construction code are proven; no
static call site or known dynamic lookup table actually passes `0x7e`, so the
trigger that opens the wizard is still unresolved. The final UI-selection →
job-key call chain also remains inferred at one step. Follow-up probes are
checking per-filter setting slots for effect toggles.

All runtime addresses are from the authoritative decompressed image
`runtime_full.bin` built by `tools/modcore.py`. Block 0 file offset = runtime −
`0x60021020`. GUI blob B bytes live at `blobB[A − 0x60c6c000]`, which equals
`runtime_full[A − 0x60021020]` for the expanded GUI.

`probe_ui.MAIN` is the raw compressed block. Raw-stream pointer hits in it
(e.g. `M:0x60e30ebe` for `0x60fb84a8`) are not expanded-code xrefs and are
discarded. A temporary `runtime_expanded.bin` made from `probe_ui.MAIN` was a
false lead and is also discarded.

---

## Containers

### Blocks

| Block | File offset | Load address | Size | Flags |
|---:|---:|---:|---:|---:|
| 0 / MAIN | `0x00000000` | `0x40800000` | `0x01a00000` | `0x0100` |
| 1 | `0x01a00040` | `0x42400000` | `0x01b00000` | `0x0101` |

### Compressed GUI blobs

| Blob | Header file offset | Payload file offset | Runtime base |
|---|---:|---:|---:|
| A | `0x0007e1fe0` | `0x00000800` | `0xa303d000` |
| B | `0x00c4afe0` | `0x00c4b000` | `0x60c6c000` |

Blob B stock compressed length: `0x28959c`, payload end `0xed459c`.
`olycompress.unpack` → `pack` is byte-identical for stock blob B.

Blob B free tail: `0x612d47b8–0x612f1000`, length `0x1c848`, all `0xff`.

A full aligned-u32 scan finds 36 numeric values in this range, including 13
references to 12 unique aligned target addresses; every target still contains
`0xff`. Nearby source text suggests stale debug/assert metadata, not Art Filter
resources. The tail is therefore free as bytes but not completely free of
inbound references.

**Recommended allocation base:** `0x612dcd17`, blob offset `0x670d17`.
This lies in the reference-free run `0x612dcd17–0x612e0edc` (`0x41c5` bytes),
which is far more than needed for 17 new entries.

Completed scan confirmation: exactly **12 unique aligned u32 targets** were
found in the free tail, all still `0xff`; the recommended allocation base is
unchanged.

### English language section

Block 1 section 8:

| Item | Value |
|---|---:|
| Flash address | `0x42623c00` |
| Block1 offset | `0x223c00` |
| Section size | `0x36c00` |
| Pointer table offset | `0x32c9c` |
| Count | `3929` (`0xf59`) |
| String RAM base | `0xa402b560` |
| Trailer offset | `0x36a4a` |

Free padding: section offsets `0x36a00–0x36a4a`, 74 bytes = 37 UTF-16 code
units including terminators. Verified empty/unreferenced sids:
`0x4a0`, `0x640`, `0xf1e`, `0xf1f`, `0xf20`, `0xf21`, `0xf2c`, `0xf2d`,
`0xf2e`, `0xf2f`.

---

## Core record format

Most GUI option and SCP icon records are 12 bytes:

```c
struct {
    uint32_t value;
    uint16_t type;   // 3 = icon/SCP/PM-style, 4 = text/name/help-style
    uint16_t field;  // language sid for type 4; icon/resource id for type 3
    uint32_t cond;   // owning list/base condition
};
```

Example, first Art Filter name record at `0x60fb73cc`:

```text
11 86 05 00 04 00 75 0a c8 73 fb 60
value=0x00058611 type=4 sid=0x0a75 cond=0x60fb73c8
```

Descriptors are commonly:

```c
struct { uint16_t sid; uint16_t count; uint32_t list; };
```

---

## True Art Filter name lists

Six aligned bases carry the identical first 32 `(value,sid)` name groups. Five
of them continue with 20 more 12-byte type-4 records (effect/monochrome
settings); one is a composite with 8-byte sublists.

| Runtime base | block0 file offset | blob B offset | Contiguous 12-byte type-4 records |
|---:|---:|---:|---:|
| `0x60fb73c8` | `0x00f963a8` | `0x34b3c8` | 52 |
| `0x60fb84a4` | `0x00f97484` | `0x34c4a4` | 32 |
| `0x60fb8eec` | `0x00f97ecc` | `0x34ceec` | 52 |
| `0x611d799c` | `0x11b697c` | `0x56b99c` | 52 |
| `0x61238578` | `0x1217558` | `0x5cc578` | 52 |
| `0x612470f4` | `0x12260d4` | `0x5db0f4` | 52 |

Records begin at `base + 4 + 12*k`. The 52-record lists are 32 Art Filter names
followed by 20 setting rows: `Art Effect Off`, `Soft Focus Effect`,
`Pin Hole Effect`, `White Edge Effect`, `Frame Effect`, `Star Light Effect`,
top/bottom and left/right blur and shade, 5 colour filters, and 5 monochrome
tones. First-record bytes:

```text
0x60fb73cc  11 86 05 00 04 00 75 0a c8 73 fb 60
0x60fb84a8  11 86 05 00 04 00 75 0a a4 84 fb 60
0x60fb8ef0  11 86 05 00 04 00 75 0a ec 8e fb 60
0x611d79a0  11 86 05 00 04 00 75 0a 9c 79 1d 61
0x6123857c  11 86 05 00 04 00 75 0a 78 85 61 61
0x612470f8  11 86 05 00 04 00 75 0a f4 70 24 61
```

Only the final `cond` pointer changes. The first 32 `(value,sid)` groups are
identical in all six lists.

### Composite layout of `0x60fb84a4`

`0x60fb84a4` stops after 32 name records. At `0x60fb8628` it contains:

```text
0x60fb8628  0x60fb84a8 0x00000020 0x00000000   // list, count=32, zero
```

The remaining 20 setting rows are 8-byte records
`{u16 type=4, u16 sid, u32 cond, u32 value}` in two sublists:

* descriptor `0x60fb86a8`: list `0x60fb8630`, count `10`
* descriptor `0x60fb86ec`: list `0x60fb86b0`, count `5`

The other five lists have 52 contiguous 12-byte type-4 records but then also
carry embedded descriptors/sublists. This is why **relocation is safer than
in-place append**.

### Settings-screen wiring for the two additional lists

A 19-entry pointer table at `0x61185140` (file `0x1164120`, blob B `0x519140`)
is passed with count `0x13` by the code at `0x60ddc8bb`:

```text
60ddc8bb  MOV 2,d0
60ddc8bd  MOV d0,(4,SP)
60ddc8bf  MOV 0x19,d0
60ddc8c1  MOV 0x61185140,a1
60ddc8c7  MOV 1,d1
60ddc8c9  CALL 0x60cf9b25
```

Two entries point at descriptors for the additional Art Filter lists:

```text
0x61185140  0x61238558  ->  0x0064000e 0x0064004b 0x61237f70 ... 0x00058611 0x0a750004 0x61238578
0x61185180  0x612470d4  ->  0x00600003 0x00600009 0x61246f9c ... 0x00058611 0x0a750004 0x612470f4
```

This proves `0x61238578` and `0x612470f4` are live Art Filter name lists, not
unreferenced copies.

### Exact 32-entry name table

`SCP val` is the Picture Mode picker value:

```text
SCP val = (variant << 16) | gui_byte
job key = 0x01VV00MM
```

| k | setting value | sid | English name | SCP val | code | Var | job key |
|---:|---:|---:|---|---:|---:|---:|---:|
| 0 | `0x00058611` | `0xa75` | `Pop Art@A050@` | `0x00010008` | `0x64` | 1 | `0x01010064` |
| 1 | `0x00058612` | `0xa76` | `Pop Art@A051@` | `0x00020008` | `0x64` | 2 | `0x01020064` |
| 2 | `0x00000045` | `0x044` | `Soft Focus` | `0x00000009` | `0x65` | 1 | `0x01010065` |
| 3 | `0x000591c9` | `0xa77` | `Pale&Light Color@A050@` | `0x0001000a` | `0x66` | 1 | `0x01010066` |
| 4 | `0x000591ca` | `0xa78` | `Pale&Light Color@A051@` | `0x0002000a` | `0x66` | 2 | `0x01020066` |
| 5 | `0x00000048` | `0x041` | `Light Tone` | `0x0000000b` | `0x67` | 1 | `0x01010067` |
| 6 | `0x000589f9` | `0xa79` | `Grainy Film@A050@` | `0x0001000c` | `0x68` | 1 | `0x01010068` |
| 7 | `0x000589fa` | `0xa7a` | `Grainy Film@A051@` | `0x0002000c` | `0x68` | 2 | `0x01020068` |
| 8 | `0x00058de1` | `0xa7b` | `Pin Hole@A050@` | `0x0001000d` | `0x69` | 1 | `0x01010069` |
| 9 | `0x00058de2` | `0xa7c` | `Pin Hole@A051@` | `0x0002000d` | `0x69` | 2 | `0x01020069` |
| 10 | `0x00058de3` | `0xa7d` | `Pin Hole@A052@` | `0x0003000d` | `0x69` | 3 | `0x01030069` |
| 11 | `0x00090c69` | `0xa7e` | `Diorama@A050@` | `0x0001000e` | `0x6a` | 1 | `0x0101006a` |
| 12 | `0x00090c6a` | `0xa7f` | `Diorama@A051@` | `0x0002000e` | `0x6a` | 2 | `0x0102006a` |
| 13 | `0x000595b1` | `0xa80` | `Cross Process@A050@` | `0x0001000f` | `0x6b` | 1 | `0x0101006b` |
| 14 | `0x000595b2` | `0xa81` | `Cross Process@A051@` | `0x0002000f` | `0x6b` | 2 | `0x0102006b` |
| 15 | `0x0000005b` | `0x03f` | `Gentle Sepia` | `0x00000010` | `0x6c` | 1 | `0x0101006c` |
| 16 | `0x00059999` | `0xa82` | `Dramatic Tone@A050@` | `0x00010011` | `0x6d` | 1 | `0x0101006d` |
| 17 | `0x0005999a` | `0xa83` | `Dramatic Tone@A051@` | `0x00020011` | `0x6d` | 2 | `0x0102006d` |
| 18 | `0x00059d81` | `0xa84` | `Key Line@A050@` | `0x00010012` | `0x77` | 1 | `0x01010077` |
| 19 | `0x00059d82` | `0xa85` | `Key Line@A051@` | `0x00020012` | `0x77` | 2 | `0x01020077` |
| 20 | `0x00072039` | `0xa86` | `Watercolor@A050@` | `0x00010013` | `0x78` | 1 | `0x01010078` |
| 21 | `0x0007203a` | `0xa87` | `Watercolor@A051@` | `0x00020013` | `0x78` | 2 | `0x01020078` |
| 22 | `0x000a0669` | `0xa88` | `Vintage@A050@` | `0x0001001a` | `0x79` | 1 | `0x01010079` |
| 23 | `0x000a066a` | `0xa89` | `Vintage@A051@` | `0x0002001a` | `0x79` | 2 | `0x01020079` |
| 24 | `0x000a066b` | `0xa8a` | `Vintage@A052@` | `0x0003001a` | `0x79` | 3 | `0x01030079` |
| 25 | `0x000a0e39` | `0xa8b` | `Partial Color@A050@` | `0x0001001b` | `0x7a` | 1 | `0x0101007a` |
| 26 | `0x000a0e3a` | `0xa8c` | `Partial Color@A051@` | `0x0002001b` | `0x7a` | 2 | `0x0102007a` |
| 27 | `0x000a0e3b` | `0xa8d` | `Partial Color@A052@` | `0x0003001b` | `0x7a` | 3 | `0x0103007a` |
| 28 | `0x00000003` | `0x6f6` | `ART BKT` | — | `0x05` | — | `0x01010005` |
| 29 | `0x0015b699` | `0xcde` | `Bleach Bypass@A050@` | `0x0001003c` | `0x7b` | 1 | `0x0101007b` |
| 30 | `0x0015b69a` | `0xcdf` | `Bleach Bypass@A051@` | `0x0002003c` | `0x7b` | 2 | `0x0102007b` |
| 31 | `0x000000db` | `0xd11` | `Instant Film` | `0x0000003f` | `0x7c` | 1 | `0x0101007c` |

There are no duplicate/spare name slots among the first 32.

---

## Help text and adjacent descriptors

`0x611ac538` is a GUI descriptor base with 2875 type-4 references.

Exact help record:

```text
0x611ac630  04 00 8a 01 38 c5 1a 61
type=4 sid=0x18a cond=0x611ac538
```

`ss[0x18a]`:

```text
To select the art filter or
finish according to the shooting purpose.
```

Title record at `0x611ac628` resolves to `"Picture Mode"`.

Earlier `probe_ui.py labels` output using `sid = i + 2` was off by two; the
`sid` values in the table above are direct language indices.

---

## Normal main Picture Mode menu

The camera's normal Picture Mode menu is **not** driven by the SCP lists alone.
Its name list is `0x6129f4a0` (file `0x127e480`, blob B `0x6334a0`).

### Mixed record structure at `0x6129f4a0`

```text
0x6129f4a0  00 00 00 00 04 00 cb 00 a0 f4 29 61
            value=0, type=4, sid=0x0cb, cond=base        "Picture Mode"

0x6129f4ac  04 00 14 0c a0 f4 29 61                    "Existing Folder"
0x6129f4b4  04 00 31 0b a0 f4 29 61                    "Copy"
0x6129f4bc  04 00 32 0b a0 f4 29 61                    "Copy Select"
```

Those three rows are 8-byte records `{type=4, sid, cond}`. The 64 visible
Picture Mode rows then start at `0x6129f4c4` with normal 12-byte records:

```text
0x6129f4c4  1d 00 00 00 04 00 98 0a a0 f4 29 61
            value=0x1d, type=4, sid=0xa98, cond=base
            "@A056@Pop Art@A050@"
```

`0x6129f4c4 + 12*k`, `k=0..63`, ends at `0x6129f7b8`. A further 8-byte
`Set@A019@`/`Yes`/`No` sublist begins at `0x6129f7c4`.

### Proven count source and live descriptor table

Prefix/descriptor pair at `0x6129f838` (file `0x127e818`, blob B `0x633838`):

```text
0x6129f838  0x6129f4a0   // base list pointer
0x6129f83c  0x00400000   // mode=0, visible count=0x40 (64)
```

The 3-entry 16-byte descriptor table starts at `0x6129f83c`; it is selected by
the u16 `viewKind` at `object+0x484`:

```text
0x6129f83c  {0x00400000, 0x6129f4a4, 0x6129f4c4, 0x6129f7c4}  // mode 0, count 0x40
0x6129f84c  {0x00000001, 0x6129f4ac, 0,         0x6129f7f4}    // mode 1
0x6129f85c  {0x00020002, 0x6129f4b4, 0x6129f824, 0x6129f7f4}  // mode 2
```

Selection is proven by `0x60ec9a3c`:

```text
60ec9a3c  MOVHU (a2),d2                 // object + 0x484 = viewKind
60ec9a41  MOV 0x6129f83c,a2
60ec9a48  MOVHU (a2),d0                 // low u16 of first word = mode key
60ec9a4a  CMP d0,d2
60ec9a4d  MOV a2,(20,SP)
60ec9a51  MOV a2,(a0)                   // chosen descriptor -> object + 0x488
60ec9a56  ADD 16,a2
60ec9a58  CMP 3,d1
```

The 64 entries consist of:

* 30 collapsed art values `0x1d..0x3e` (Pop Art through Bleach Bypass II);
* three `@A082@Vintage` rows with values `0x39/0x3a/0x3b`;
* three colour-profile rows with values `0x36/0x37/0x38`;
* 28 PM-style values `(gui<<8)|variant`, from `0x0801` to `0x0000003f`
  (Instant Film).

### Selection → background-id map

A 42-entry 8-byte table at `0x6129f8b4` (file `0x127e894`, blob B `0x6338b4`)
holds `{key, background_id}` pairs:

```text
0x6129f8b4  0x00000801 0x00000148   Pop Art I    -> id 0x148
0x6129f8bc  0x00000802 0x00000149   Pop Art II   -> id 0x149
0x6129f8c4  0x00000009 0x0000014a   Soft Focus   -> id 0x14a
...
0x6129fa14  0x00001102 0x00000374   Dramatic II  -> id 0x374
```

A 3-entry exception table at `0x6129fa04` maps
`0x0c01→0x01ce`, `0x0c02→0x0373`, `0x1102→0x0374`.

`0x6129f888` is **not** a standalone 8-byte prefix. It is the second and third
words of entry 2 in the 3-entry common-methods table at `0x6129f86c`
(described below). The 3-entry handler table itself starts at `0x6129f890`
(file `0x127e890`, blob B `0x633890`), stride 12, format
`{u32 key, u32 enter, u32 cleanup}`:

```text
0x6129f890  {2, 0x60ec9f6f, 0x60eca343}
0x6129f89c  {1, 0x60ec9c58, 0x60ec9eea}
0x6129f8a8  {0, 0x60eca40c, 0x60ec9eea}
```

This table is selected by the same u16 `viewKind` at `object+0x484`. Proven by
`0x60ec9b13`:

```text
60ec9b1b  ADD 0x484,a2                 // viewKind
60ec9b27  MOVHU (a2),d0
60ec9b59  UDFU01 12,d1                 // index * 12
60ec9b5e  ADD 0x6129f890,a0
60ec9b64  MOV (a0),d0                  // key
60ec9b65  CMP d0,d3
60ec9b68  MOV (4,a0),d0                // enter -> 0x61ea0f34
60ec9b71  MOV (8,a0),a0                // cleanup -> 0x61ea0f38
```

`0x60eca357` (file `0xea9337`, blob B `0x25e357`) contains:

```text
60eca364  MOV (a2),d0 / CALLS (vtable+4)     // object + 0x95c
60eca36f  MOV (a2),d1 / CALLS (vtable+16)
60eca3bf  MOV (28,SP),d0
60eca3c1  MOV a3,d1
60eca3c3  ASL 16,d0
60eca3c6  OR d0,d1                         // key = (v4 << 16) | v16
60eca3d8  ADD 0x6129f8b4,a0
60eca3de  MOV (a0),d0
60eca3df  CMP d0,a3
60eca403  CMP 42,d3                         // 42-entry loop bound
```

Its debug strings are decisive:

```text
0x6129fd06  "inside  methods Wizard_Multirow_SampleImage_Viewer::get_background_id_picture_mode mode:%d"
0x6129fd61  " mode:%d background_id :%d"
0x6129fd7c  "Wizard_Multirow_SampleImage_Viewer::parts_cursor cursor = %d total_num:%d"
```

So the normal Picture Mode selection path is proven through
`0x6129f4a0` → `0x6129f83c` (3-entry descriptor table, count `0x40`) →
`0x6129f890` (3-entry handler table) → `0x6129f8b4` (map) →
`0x60eca357` (background id). Camera tests showing that SCP/LABEL edits do not
change the main Picture Mode menu are consistent with this separation.

### Common methods table and callback arrays

`0x6129f86c` is a 3-entry table with stride `0xc`, not a prefix. Its entries are
`{u32 viewKind, u32 delta, u32 callback_or_zero}`:

```text
0x6129f86c  {1, 0xffe8, 0}
0x6129f878  {2, 0xffe7, 0}
0x6129f884  {0, 1, 0x60eca357}
```

It is consumed by `0x60ec9bf4`, which debug-identifies itself with
`0x6129fafa = "inside Methods  Wizard_Multirow_SampleImage_Viewer::common"`:

```text
60ec9c17  UDFU01 12,d0              // stride 0xc
60ec9c1c  ADD 0x6129f86c,a0
60ec9c22  MOV (a0),d0 / CMP d3,d0   // key = viewKind from object +0x484
60ec9c2a  MOV (8,a0),d0 / CMP 0,d0  // callback slot
60ec9c2f  MOV (4,a0),d0             // else use delta
60ec9c37  CALLS (a1)                // viewKind 0: call 0x60eca357
60ec9c39  MOVHU d0,(a3)             // store result/delta at object +0x10
```

For `viewKind=0` it calls `0x60eca357` and stores the resulting background id at
object `+0x10`; for `viewKind=1/2` it stores the negative `u32` delta. This is
what resolves the earlier apparent `0x6129f888` prefix: those bytes are the
`delta=1` and `callback=0x60eca357` words at offsets `+0x1c` and `+0x20` of the
table, i.e. entry 2 at `0x6129f884`.

The static image contains null-terminated callback groups immediately before
the Art tables:

```text
0x60280c40  {0x60ec8135, 0x60ec81e4, 0}
0x60280c4c  {1, 0x60ec85ad, 0x60ec8734, 0x60ec892e, 0x60ec8661, 0}
0x60280c60  {0, 0x60ec96f2, 0x60ec96ff, 0}
0x60280c70  {0x60ec9bf4, 0x60ec9c58, 0x60ec9eea, 0}
0x60280c80  {0x60ecaa87, 0x60eca739, 0x60eca924, 0x60eca9ab, 0}
0x60280c94  {0x60ecadca, 0x60ecaf59, 0x60ecb2d1, 0}
... groups continue through 0x60280d44
```

Group `0x60280c70` exactly matches the three RAM slots programmed by
`0x60ec9b13` and dispatched by `0x60ec9b82`: `0x61ea0f30/34/38` receive
`common`, `enter` and `cleanup`. A byte-wise search of every runtime byte
(including both expanded GUI blobs) finds **no** immediate or aligned `u32`
reference to any group base, so the copy/registration mechanism remains
inferred; the RAM slots are zero in the static image.

Two further RAM callback arrays are proven by their consumers:

* `0x61ea0f40` is dispatched at `0x60eca6c0`. Slot 0 must be nonzero; each
  4-byte-strided slot is called with the wizard object until a null slot is
  reached. There are no direct xrefs to `0x60eca6c0` itself.
* `0x61ea0f74` is scanned at `0x60ecab90`: a `u16` value is compared against
  three 4-byte slots; a match sets byte flags at object `+0x50/+0x51` and then
  writes a flag with row stride `0x74` to three 15-entry row arrays at
  `object+0x258`, `+0x45e` and `+0x52`. It has one direct xref only.

Both arrays have no static initializer in the image; their producers remain
unresolved. Their effect is rendering/flag state, not the job key.

### 12-byte record decoder layout

`0x60e08efa` (multi-record) and `0x60e08fa0` (single record) decode a 12-byte
GUI record `{u32 value, u16 type, u16 field, u32 cond}` into a 74-byte (`0x4a`)
row:

```text
+0   u16 type
+2   u16 field              for types 3, 8, 7
+4   u16 field              for types 4, 1, 2, 0xa, 0xb, 9  (0xefa only:
                             4,1,2,0xa,0xb,9; 0xfa0 only: 4,1,2)
+6   u16 enabled flag       written later by the enter handlers
+8   66-byte UTF-16 string  (memset 0x42 at 0x60e08f78)
```

In `0x60e08efa`, types `{1,2,7,8,5,6,0xa,0xb,9}` take the string branch; in
`0x60e08fa0` types `{1,2,5,6}` do. The string source is the `u32` at record
`+8`, resolved through `0x600ee63b` and copied by `0x60e08fff`.

### Factory dispatch and wizard construction

The dispatcher is `0x60e08e8b`. It scans the 8-byte table at `0x611d7c10`
(`count=0x87`, stride 8) and calls the function pointer at `+4` when D0 matches
the id at `+0`:

```text
60e08e8b  MOV a0,a2
60e08e8f  MOV 0x611d7c10,a1
60e08e96  MOV (a1),d1           // factory id
60e08e97  CMP d0,d1
60e08e9a  MOV (4,a1),a1         // constructor
60e08e9e  CALLS (a1)
60e08ea5  CMP 0x87,d2           // 135 entries
```

The Art Filter/Picture Mode wizard entry is proven at
`0x611d7fe0 = {0x7e, 0x60ec995e}`. This is not the id `0x62` entry at
`0x611d7f08 = {0x62, 0x60ec2570}`; that other constructor only maps view kinds
through `0x61293b44` to descriptors `0x61293b60`/`0x61293b68`.

`0x60ec995e` allocates a `0x964`-byte object and initializes the wizard state:

```text
60ec9988  MOV 0x6129fdc8,d0 / MOV d0,(a0)       // vtable
60ec9991  MOV 0x4c6,d1 / ADD 0x490,d0 / CALL 0x47001165  // clear +0x490, size 0x4c6
60ec99a7  ADD 0x960,a0 / MOV 2,d1 / CALL 0x47001165     // clear +0x960, size 2
60ec99d9  ADD 0x958,a3 / MOV d0,(a3)            // caller arg -> +0x958
60ec99e3  ADD 0x484,d3 / MOVHU d0,(a0)          // viewKind -> +0x484
60ec9a41  MOV 0x6129f83c,a2                     // descriptor table
60ec9a51  MOV a2,(a0)                           // chosen descriptor -> +0x488
60ec99f2  MOV (32,a1),a1 / CALLS (a1)
60ec9ffd  MOV a0,(a2)                           // row-buffer object -> +0x95c
```

`0x6129fdc8` itself is `{0x60ec9b13, 0x60ec9ad8, 0x60e09028, 0}`. Descriptor
selection by `viewKind` is proven at `0x60ec9a3c`; handler selection by the same
`viewKind` is proven at `0x60ec9b13`. It writes the selected enter function to
`0x61ea0f34` and cleanup function to `0x61ea0f38`:

```text
60ec9b64  MOV (a0),d0                // handler key
60ec9b65  CMP d0,d3                  // viewKind
60ec9b68  MOV (4,a0),d0 / MOV d0,(0x61ea0f34)   // enter
60ec9b71  MOV (8,a0),a0 / MOV a0,(0x61ea0f38)   // cleanup
```

`0x60ec9b82` then treats `0x61ea0f30` as the base of a 4-byte-strided callback
array. It loads the first slot, and if nonzero calls each slot in order with the
wizard object and an incrementing index until it reaches a null slot. Thus the
two selected handlers are not merely stored; they are placed into an array that
is dispatched by this loop. The only direct xrefs to `0x61ea0f30` are the load
and address-take at `0x60ec9b84`/`0x60ec9b8a`, so the producer of slot 0 is
unresolved. Only pointer xrefs to `0x6129fdc8` are `0x60ec998a` and
`0x60ec9ae0`.

Static dispatcher call ids are `0x62` (`0x60e0cfa9`), `0x13`
(`0x60e50131`), `0x14` (`0x60eaa566`), `0x46` (`0x60eaec39`) and `0x34`
(`0x60eb91ee`). The seven dynamic call sites are `0x60e70284`,
`0x60e7039c`, `0x60e70494`, `0x60e7058e`, `0x60e71b70`, `0x60e71cb5` and
`0x60e0d0a9`.

Four of the dynamic sites are branches inside one generic resource loader,
`0x60e700cc`. It indexes a runtime callback table at `0x61ea0340` (stride 8,
initialized by `0x60e6fd52`), invokes the selected callback, then scans the
48-record table at `0x6123b450`:

```text
60e70128  ASL 3,d0
60e7012d  ADD 0x61ea0340,a1       // callback table entry {key, fn}
60e70207  UDFU01 12,d0            // index * 12 (0x0c, not decimal 12)
60e7020a  ADD 0x6123b450,a0
60e70212  MOV (a0),d0             // record key
60e70218  MOV (4,a0),d0           // kind; special-cased as 0x55
60e7021c  MOV (8,a0),d0           // factory id; special-cased as 0x91
```

`0x6123b450` records are `{u32 key, u32 kind, u32 factory_id}`. The first 35
records are populated; records 35..47 are zero. No populated record has
`factory_id=0x7e`. The observed ids are `0x00,0x02..0x0f,0x11,0x12,0x46,
0x51,0x52,0x53,0x5e,0x67,0x89,0x90`. The loader passes that `+8` value to
`0x60e08e8b` at `0x60e70284`, and the three later branches at `0x60e7039c`,
`0x60e70494`, `0x60e7058e` pass the same value after resource-specific
post-processing. `0x60e71b70`/`0x60e71cb5` likewise pass the `+12` slot
initialized from that table.

`0x60e7062d`, `0x60e706a6` and `0x60e70785` are callers of the loader that
look up resource pools through the 14-entry `0x61243ed8` metadata table. They
pass their incoming u16 argument as the factory id. A byte-level scan of every
call site found **no** `MOV 0x7e,d1` immediate (`85 7e`, `2d 7e 00` or
`fc cd 7e 00 00 00`) within 256 bytes before any of the 73 callers of
`0x60e7062d`, its single caller at `0x60ea6dad`, or its single caller at
`0x60e9da1e`. The same scan of all 12 direct call sites of `0x60e08e8b` also
found no such immediate. Because the dispatcher takes its id in **D0**, the same
512-byte window was also scanned for `80 7e` (`MOV 0x7e,d0`), `fc cd 7e 00 00 00`
and an aligned `u32 0x7e`; all 12 call sites are negative. D0/D1 can still arrive
through a register or memory slot, so this proves only that no direct immediate
producer exists at those sites.
The metadata table itself has 14 real 12-byte entries followed by ASCII debug
strings (`[GUI]_PARTS_...`). Some nested pool rows contain `0x7e` in other
fields, but those fields are not the factory-id slot.

`0x60e0d0a9` instead scans the 8-byte wrapper table `0x611dd8e0`, format
`{u16 lookup_key, u16 variant, u32 factory_id}`. The lookup keys are
`0x46,0x45,0x47,0x48,0x4a,0x49,0x56,0x55,0x5b,0x60,0xa3,0xb5,0xc2,0xc4`;
the factory id actually passed to the dispatcher is `0x3f` for the first 14
rows and `0x4d` for the final row. Neither is `0x7e`.

A tempting false positive is `0x611ca0a8`, whose `+8` word is `0x7e`. Its base
`0x611ca080` is a `0xa2`-entry resource table used at `0x60df46d9` and
`0x60df55b8`; code there reads `+8` as an allocation count, not a factory id:

```text
60df46d2  UDFU01 12,d1
60df46d7  ADD 0x611ca080,a2
60df46e2  MOVHU (8,a2),d0       // count used for two array allocations
60df4709  MOV (4,a2),a1 / CALL 0x47001059
```

Therefore the dispatcher entry and constructor are proven, but the actual call
that passes id `0x7e` is not.

Factory id `0x37` is a separate path proven at
`0x611d7d9c = {0x37, 0x60eca581}`. `0x60eca581` calls `0x60eca5a1`, which
allocates a `0x7cc` object, stores the source value at `+0x7bc`, the source u16
at `+0x4e8`, clears `+0x7c4/+0x7c8/+0x4ec`, calls vtable `+32`, and scans a
2-entry table at `0x6129fe3c`:

```text
60eca5f6  UDFU01 20,d0          // stride 0x20, two entries
60eca5fb  ADD 0x6129fe3c,a2
60eca601  MOVHU (a2),d0         // key 0, then key 0x25
60eca628  MOV (12,a2),a0        // descriptor pointer -> object +0x10
```

This is not the id `0x7e` wizard path and must remain separate in the report.

### Handler row buffers and cleanup

The three handler-table enter functions build display rows, not the final job
key:

* `0x60ec9c58` (viewKind 1) reads the count from `object+0x1160`, zeroes u16
  arrays at `object+0x490+2` (`0xe` bytes), `object+0x490+0x10` (`0x206`),
  `object+0x21c+0x10` (`0x206`) and `object+0x490+0x22a` (`0x206`), plus two
  stack buffers of 9 and 4 bytes. It uses vtable slots `+4`, `+8` and `+16`,
  calls the 12-byte decoder `0x60e08efa`, sets selected flags in the
  `+0x490`/`+0x21c` arrays, and debug-counts with `0x6129fb35`.
* `0x60ec9f6f` (viewKind 2) zeroes arrays at `object+0x490+2` (`0xe`),
  `object+0x490+0x10` (`0x206`), `object+0x21c+0x10` (`0x206`),
  `object+0x430+0x10` (`0x94`) and two stack buffers (9 and 4 bytes). It sets
  `object+0x490+0x4c4 = 1`, scans with a `0x384` loop bound and stride `0x10`,
  pages 7 rows with stride `0x4a`, and uses debug strings `0x6129fb8e`,
  `0x6129fbea`, `0x6129fc0a`, `0x6129fc22`, `0x6129fc3f`, `0x6129fc58`,
  `0x6129fc60`, `0x6129fcb0` and `0x6129fcb3`. The `0x384` bound is proven as a
  numeric loop bound; its semantic source is not yet proven.
* `0x60eca40c` (viewKind 0) uses `object+0x1160` as the cursor/count source,
  `0x6129fd7c` as the cursor/total debug string, and calls the 12-byte decoder
  `0x60e08efa`.

Key evidence from `0x60eca40c`:

```text
60eca413  MOV (1160,a0),d0      // count/cursor source
60eca45a  MOV d0,(28,SP)        // decoder output pointer = object + 0x95c
60eca535  UDFU01 74,d2          // row stride 0x74
60eca53e  CALL 0x60e08efa       // decode one 12-byte source record
60eca550  CALLS (a1)            // vtable +12 enables/disables row
60eca55c  MOVHU d0,(6,a2)       // decoded row +6 = enabled flag
60eca56c  MOVHU d0,(d3,a0)      // selected flag at +0x490 + 2*i
60eca570  MOVHU d0,(d3,a0)      // selected flag at +0x21c + 2*i
```

Neither this function nor the other two enter handlers calls the proven job-key
writer `0x603807d0`. Cleanup is also limited to cursor/flag state:
`0x60eca343` clears u16 flags at `object+0x490+0x216/+0x218/+0x21a`;
`0x60ec9eea` clears the same three flags, calls vtable `+4/+8` on `+0x95c`,
and conditionally restores them from the current page/cursor. This explains
why main-menu edits affect row rendering and cursor state but do not by
themselves prove the final selection-to-job-key step.

---

## Validator → Picture Mode → SCP → job path

### Validator

Validator record at `0x604da7bc`:

```text
6f 00 80 00 f4 c4 4b 60 34 e8 4a 60 80 06 40 00 00 06 00 00
```

```text
sid       = 0x6f
flag      = 0x80
main list = 0x604bc4f4   // 26 x 64-byte entries
alt list  = 0x604ae834   // 26 x u32
main size = 0x680 bytes
element   = 0x40 bytes
```

Art portion of raw index → GUI alt → code:

| raw | alt | code |
|---:|---:|---:|
| 5 | `0x03` | `0x05` (ART BKT) |
| 10 | `0x08` | `0x64` |
| 11 | `0x09` | `0x65` |
| 12 | `0x0a` | `0x66` |
| 13 | `0x0b` | `0x67` |
| 14 | `0x0c` | `0x68` |
| 15 | `0x0d` | `0x69` |
| 16 | `0x0e` | `0x6a` |
| 17 | `0x0f` | `0x6b` |
| 18 | `0x10` | `0x6c` |
| 19 | `0x11` | `0x6d` |
| 20 | `0x12` | `0x77` |
| 21 | `0x13` | `0x78` |
| 22 | `0x1a` | `0x79` |
| 23 | `0x1b` | `0x7a` |
| 24 | `0x3c` | `0x7b` |
| 25 | `0x3f` | `0x7c` |

### Job-key writer source struct

The job-key writer `0x603807d0` is proven. It copies 32 bytes from its A0
source struct into a new job record at `+4`, then reads the copied bytes that
came from source `+8/+9/+10` and writes the combined value to `job+0x2c2c`:

```text
60380902  MOV (a2),d0          // copy 8 x u32 from A0 source
6038090c  MOVBU (a2),d1        // source +8  = 0x01
6038090e  MOVBU (1,a2),d0      // source +9  = variant
60380911  MOVHU (2,a2),d3      // source +10 = gui byte
60380914  ASL 24,d1 / ASL 16,d0 / OR d0,d1 / OR d3,d0
60380926  MOV d0,(a0)          // job +0x2c2c
```

For the picture-mode byte triple `01 VV 00 MM` this produces
`0x01VV00MM`, matching the table in the unused-variant section.

The source struct is built by the generic camera-state helpers
`0x60418b7f`, `0x6041bb8f`, `0x6041be44`, `0x6041de1e` and `0x604268b9`.
A representative call chain is `0x6041997c` → `0x60418b7f` → `0x603807d0`:

```text
6041997c  MOV d1,d0 / CALL 0x47001165     // zero 32-byte struct at SP+16
60419987  MOV a3,a0 / MOV a2,a1 / CALL 0x60418b7f
60418ba4  MOV 0x6041a802,d0 / MOV d0,(a2) // struct +0
60418baf  MOV 8,a1 / ADD a2,a1
60418bb3  CALL 0x6041da81                 // struct +8..+11 = mode bytes
60418bbd  CALL 0x6041dbd1                 // struct +12..+15 = flags
60419993  MOV a2,a0 / CLR d0 / CALL 0x603807d0
```

`0x6041da81` derives its output bytes from camera-object fields
(`object+0x65e7`, `object+0x65ca`, `object+0x68c8`, globals near `0x61ea00c2`),
not directly from a GUI row. Therefore key production from camera state is
proven, but the link from the selected Art Filter row to that camera state is
still inferred.

### Picture Mode lists

Three parallel descriptors:

```text
0x611af718  6f 00 36 00 dc ed 1a 61   list=0x611aeddc count=0x36
0x61206bc8  6f 00 36 00 8c 62 20 61   list=0x6120628c count=0x36
0x6128837c  6f 00 36 00 40 7a 28 61   list=0x61287a40 count=0x36
```

Each list has 54 type-3 records with the same values but different `cond`
bases. Example Pop Art I at `0x611aee54`:

```text
01 08 00 00 03 00 bb 11 38 c5 1a 61
```

Reconciliation:

```text
PM bytes[0:2] = {variant=1, gui=0x08}
SCP u32       = (variant << 16) | gui = 0x00010008
```

PM `u32 0x0801` and SCP `u32 0x00010008` encode the same `{variant,gui}` pair.

PM type-3 `field` values above `LANG_COUNT=3929` (`0xf59`) are icon/resource
IDs, not language IDs.

### SCP Picture Mode icons

Master record:

```text
0x611ef284
id=0x22 list1=0x611ec718 list2=0x611ec9a0 count=54
```

Cell addresses:

```text
small = 0x611ec718 + 12*k
large = 0x611ec9a0 + 12*k
```

Record:

```c
{ ((variant<<16)|gui), 3, icon_id, 0x611e78f4 }
```

Icon descriptor format at format 14:

```c
struct {
    uint16_t fmt = 14;
    uint16_t w;
    uint16_t h;
    uint16_t depth = 8;
    uint32_t zero;
    uint32_t data_size;
    uint32_t data_ptr;
    uint32_t zero;
};
```

Decoded icon blob bases:

| Blob | Runtime base | File payload |
|---|---:|---:|
| small 50×38 | `0xa303d000` | `0x00000800` |
| large 64×48 | `0xa373d000` | `0x009f1200` |

For any `bloboff`:

```text
runtime = icon_base + bloboff
file    = payload_base + bloboff
```

Compact Art icon IDs by SCP value:

| SCP val | Name | small icon | large icon |
|---:|---|---:|---:|
| `0x000003` | ART BKT | `0x0324` | `0x0224` |
| `0x010008` | Pop Art I | `0x1156` | `0x1130` |
| `0x020008` | Pop Art II | `0x1157` | `0x1131` |
| `0x000009` | Soft Focus | `0x1158` | `0x1132` |
| `0x01000a` | Pale & Light I | `0x1159` | `0x1133` |
| `0x02000a` | Pale & Light II | `0x115a` | `0x1134` |
| `0x00000b` | Light Tone | `0x115b` | `0x1135` |
| `0x01000c` | Grainy I | `0x115c` | `0x1136` |
| `0x02000c` | Grainy II | `0x115d` | `0x1137` |
| `0x01000d` | Pin Hole I | `0x115e` | `0x1138` |
| `0x02000d` | Pin Hole II | `0x115f` | `0x1139` |
| `0x03000d` | Pin Hole III | `0x1160` | `0x113a` |
| `0x01000e` | Diorama I | `0x1161` | `0x113b` |
| `0x02000e` | Diorama II | `0x1162` | `0x113c` |
| `0x01000f` | Cross Process I | `0x117a` | `0x113d` |
| `0x02000f` | Cross Process II | `0x1164` | `0x113e` |
| `0x000010` | Gentle Sepia | `0x1165` | `0x113f` |
| `0x010011` | Dramatic Tone I | `0x1166` | `0x1140` |
| `0x020011` | Dramatic Tone II | `0x1167` | `0x1141` |
| `0x010012` | Key Line I | `0x1168` | `0x1142` |
| `0x020012` | Key Line II | `0x1169` | `0x1143` |
| `0x010013` | Watercolor I | `0x116a` | `0x1144` |
| `0x020013` | Watercolor II | `0x116b` | `0x1145` |
| `0x01001a` | Vintage I | `0x116c` | `0x1146` |
| `0x02001a` | Vintage II | `0x116d` | `0x1147` |
| `0x03001a` | Vintage III | `0x116e` | `0x1148` |
| `0x01001b` | Partial Color I | `0x116f` | `0x1149` |
| `0x02001b` | Partial Color II | `0x1170` | `0x114a` |
| `0x03001b` | Partial Color III | `0x1171` | `0x114b` |
| `0x01003c` | Bleach Bypass I | `0x1bd8` | `0x1bd2` |
| `0x02003c` | Bleach Bypass II | `0x1bda` | `0x1bd4` |
| `0x00003f` | Instant Film | `0x1e84` | `0x2167` |

For new monochrome entries, reuse a mono-looking icon such as Gentle Sepia
`0x1165/0x113f` or Instant Film `0x1e84/0x2167`.

The temporary contact sheet `art_icons.png` decodes 28 of the 32 small icon IDs
listed above. Missing from that sheet are `0x0324` (ART BKT), `0x1158`
(Soft Focus), `0x115b` (Light Tone) and `0x117a` (Cross Process I); the large
64×48 icons are not decoded there. Icon reuse is therefore only partially
cross-checked visually, and the exact best mono icon remains inferred.

### SCP panel text

`0x611ef038` points to `0x611eb26c`, count 4. Camera-tested
`tools/patch_art_gradation.py` extends this list when SCP panel labels are
required. Name-list edits alone did not draw all SCP labels.

---

## Resource-role separation

The firmware contains several similar-looking lists with different roles.

| Resource | Runtime address | Role |
|---|---|---|
| first SCP table base | `0x611eeb9c` | stride `0x34`, id at `+0`; rows for SCP icon/text grids |
| first-table row | `0x611ef118` | id `0x1b`, icons `0x611eb5b4`/`0x611ebbe4`, count `0x39` |
| first-table row | `0x611ef180` | id `0x1d`, icons `0x611eb878`/`0x611ebea8`, count `0x47` |
| first-table row | `0x611ef284` | id `0x22`, icons `0x611ec718`/`0x611ec9a0`, count `0x36` |
| second SCP table base | `0x611efba0` | stride `0x34`, id at `+8` |
| second-table row | `0x611efc08` | id `0x22`, icons `0x611ecf28`/`0x611ed1a4`, count `0x35` |
| SCP text list | `0x611ecc28` | 64 rows, descriptor `0x611ef2a8` |
| SCP text list | `0x611ec244` | 68 rows, descriptors `0x611ef13c`/`0x611ef1a4` |
| SCP text list | `0x611ed420` | 42 rows, descriptor `0x611efc34` |
| art text run | `0x611e7a78` | 16 art names, descriptor `0x611eebc0`, cond `0x611e78f4` |
| Live Control descriptor | `0x611fe03c` | sid `0x6f`, count `0x4b`, lists `0x611fb39c`/`0x611fb738` |
| Live Control copies | `0x611af718`, `0x61206bc8`, `0x6128837c` | 54 type-3 icon rows each |
| normal Picture Mode list | `0x6129f4a0` | 64 rows, descriptor table `0x6129f83c`, handler table `0x6129f890`, map `0x6129f8b4` |
| Art Filter name lists | `0x60fb73c8`, `0x60fb84a4`, `0x60fb8eec`, `0x611d799c`, `0x61238578`, `0x612470f4` | 32 name rows + setting rows |

The first-table icon user at `0x60e15bd1` is an 8-byte-stride lookup helper:

```text
a2 = key >> 8; table = 0x611efc44
compare u16 key; return MOVHU (2,a2), MOVHU (4,a2)
```

Context at `0x611efc44` is
`0x00510000, 0x611eeb9c, 0x00010001, 0x611efc10, 0x60e15bcc`. This explains
why editing SCP rows changes SCP icon grids but not the normal main menu.

---

## Unused picture-mode variants

There are 17 unused `(code,variant)` slots. All are II/III variants.

| code | GUI alt | variant | SCP value | PM bytes | job key |
|---:|---:|---:|---|---|---:|
| `0x64` | `0x08` | 3 | `0x00030008` | `03 08 00 00` | `0x01030064` |
| `0x65` | `0x09` | 2 | `0x00020009` | `02 09 00 00` | `0x01020065` |
| `0x65` | `0x09` | 3 | `0x00030009` | `03 09 00 00` | `0x01030065` |
| `0x66` | `0x0a` | 3 | `0x0003000a` | `03 0a 00 00` | `0x01030066` |
| `0x67` | `0x0b` | 2 | `0x0002000b` | `02 0b 00 00` | `0x01020067` |
| `0x67` | `0x0b` | 3 | `0x0003000b` | `03 0b 00 00` | `0x01030067` |
| `0x68` | `0x0c` | 3 | `0x0003000c` | `03 0c 00 00` | `0x01030068` |
| `0x6a` | `0x0e` | 3 | `0x0003000e` | `03 0e 00 00` | `0x0103006a` |
| `0x6b` | `0x0f` | 3 | `0x0003000f` | `03 0f 00 00` | `0x0103006b` |
| `0x6c` | `0x10` | 2 | `0x00020010` | `02 10 00 00` | `0x0102006c` |
| `0x6c` | `0x10` | 3 | `0x00030010` | `03 10 00 00` | `0x0103006c` |
| `0x6d` | `0x11` | 3 | `0x00030011` | `03 11 00 00` | `0x0103006d` |
| `0x77` | `0x12` | 3 | `0x00030012` | `03 12 00 00` | `0x01030077` |
| `0x78` | `0x13` | 3 | `0x00030013` | `03 13 00 00` | `0x01030078` |
| `0x7b` | `0x3c` | 3 | `0x0003003c` | `03 3c 00 00` | `0x0103007b` |
| `0x7c` | `0x3f` | 2 | `0x0002003f` | `02 3f 00 00` | `0x0102007c` |
| `0x7c` | `0x3f` | 3 | `0x0003003f` | `03 3f 00 00` | `0x0103007c` |

None of these PM type-3 records currently exist in the three PM lists.

Resource-only ceiling: **17 new named entries** by reusing these variants,
for **48 total Art Filter menu entries**. Beyond that requires new picture-mode
codes and processing-chain work.

Variant III always takes the generic chain because `0x0103xxxx` is above the
secondary/primary range checks. Custom effects for III need the dispatch range
patch discussed in `ART_FILTER_CHAIN.md`.

---

## Free space and collisions

| Area | Status |
|---|---|
| `0x612d47b8–0x612f1000` | blob B unpacked tail, all `0xff`; use `0x612dcd17+` to avoid stale refs |
| `0x600dc000–0x600df000` | free, used by `patch_art_gradation.py` |
| `0x600d9600`, `0x600dec00` | curve areas used by `patch_art_gradation.py` |
| `0x600d3000–0x600d77d1` | panorama mod area, occupied |
| `0x600d2b00` | XPAN area, occupied |
| boot pools `0x602859a0`, `0x6028f0c4`, `0x60292804`, `0x6029952c`, `0x600e0800` | not free |

---

## Patch strategy for N new named entries

Recommended strategy: **relocate, do not append in place**. In-place append is
unsafe because `0x60fb84a4` has embedded sublists and the other name lists have
at most six usable 12-byte slots.

For each new filter:

1. Choose an unused `(code,variant)` from the table above.
2. Relocate the six true name lists to blob B tail starting at
   `0x612dcd17` (blob offset `0x670d17`); rebase all `cond` references; append
   `N` type-4 records:

   ```c
   { unique_setting_value, 4, new_sid, new_list_base }
   ```

   Suggested unique values: `0x005a000 + i`.

3. Add UTF-16LE names in language-section padding and repoint
   `LANG_TAB + 4*new_sid`. Budget: 74 bytes total / 37 UTF-16 code units.

4. Relocate/extend the three Live Control PM type-3 lists and update
   descriptors `0x611af718`, `0x61206bc8`, `0x6128837c`:

   ```text
   count = 0x36 + N
   list pointer = relocated list
   ```

5. **Also relocate/extend the normal main Picture Mode list** at
   `0x6129f4a0`. The 64 visible rows start at `0x6129f4c4`; append the same
   `N` PM-style type-3 rows there and update descriptor `0x6129f83c`:

   ```text
   first word = ((0x40 + N) << 16) | 0x0000   // was 0x00400000
   row pointer = relocated row base
   ```

   Extend the 42-entry selection map at `0x6129f8b4` with one
   `{PM-style value, background_id}` pair per new row, and update the prefix
   `0x6129f838` if the whole list is moved. Camera tests proving that SCP/LABEL
   edits alone do not change the main menu make this step mandatory, not
   optional.

6. Relocate/extend SCP icon lists `0x611ec718` and `0x611ec9a0`; update
   `0x611ef284` count `54 → 54+N`.

7. Extend SCP panel text list `0x611eb26c` and update `0x611ef038`
   count `4 → 4+N`.

8. Optional: extend the 8-byte setting→SCP map at `0x611c2314`. Not proven
   necessary.

9. Recompress blob B; set header size at file offset `0xc4afe0+16`; pad with
   `0xff` if shorter; verify `unpack(new) == edited GUI`.

10. Recompute block checksums with `olyfw.build_block`. Both block 0 and block 1
    change.

Updated relocation/append simulation from `0x612dcd17`, now including the
normal main Picture Mode list, both SCP icon lists and the selection-map
extension. The packer reproduces stock blob B byte-for-byte; the per-entry
records use unique values/SIDs so the result is not artificially compressed:

| N | Raw bytes added | Allocation end | Compressed size | Δ from stock `0x28959c` |
|---:|---:|---:|---:|---:|
| 0 | `0x1f2c` | `0x612dec43` | `0x28a57c` | `+4064` |
| 12 | `0x26dc` | `0x612df3f3` | `0x28a82d` | `+4753` |
| 17 | `0x2a10` | `0x612df727` | `0x28a945` | `+5033` |

The static copy budget is six name lists (`6 × 628`), three Live Control PM
lists (`3 × 652`), the SCP text list (`48`), the normal PM list (`0x384`) and
two SCP icon lists (`2 × 648`), plus `0xc` alignment padding. Each new entry
adds 13 twelve-byte records (6 name + 3 PM + 1 SCP text + 1 normal PM +
2 SCP icon) and 8 bytes of selection-map data, i.e. `164` bytes.

All three end addresses remain inside the reference-free run
`0x612dcd17–0x612e0edc` (`0x41c5` bytes). Compressed size is content-dependent,
so treat these figures as a representative estimate rather than a guarantee;
even so, blob-B space is not the limiting factor. The practical limits remain
the 17 unused variants and the 37 UTF-16 code units.

---

## Selection → job key and per-filter settings

Status: the Art-selection → job-key path is now instruction-traced. The exact
bridge from global picture-mode selectors into the wizard/dispatcher that feeds
it is still unresolved.

### Proven snapshot → key path

| Purpose | Runtime | File offset |
|---|---:|---:|
| Normal Picture Mode list | `0x6129f4a0` | `0x127e480` |
| PM list descriptor/count | `0x6129f83c` | `0x127e81c` |
| PM handler table | `0x6129f890` | `0x127e870` |
| Selection→background map | `0x6129f8b4` | `0x127e894` |
| SCP icon list 1 | `0x611ec718` | `0x11cb6f8` |
| SCP icon list 2 | `0x611ec9a0` | `0x11cb980` |
| SCP master count | `0x611ef284` | `0x11ce264` |
| SCP panel text list | `0x611eb26c` | `0x11ca24c` |
| SCP panel count | `0x611ef038` | `0x11ce018` |

`0x6126553c` / `0x61265bb0` are not direct Art SCP variant lists. Art SCP
values do occur at `0x6129f674` and `0x611ec2e0`.

Loader `0x60411db9` (file `0x3f0d99`) reads Art records at
snapshot `+26850 + index*44` and writes:

* `+26087` at `0x60411e22` — picture-mode/code byte used by the key builder;
* `+26058` at `0x60411e2e` — secondary u16 control;
* `+26824` at `0x60411e55` — variant override/control byte;
* `+26825` at `0x60411e63` — additional control byte.

Hash dispatch `0x60411ebf` (file `0x3f0e9f`) reads snapshot `+26087`,
validates `1..124`, indexes `(code & 31)*8` into
`0x60546d90..0x60546e90` (file `0x525d70`), and maps every Art code
`0x64..0x7c` to `0x60411f5e`, which writes `2`.

Key builder `0x6041da81` (file `0x3fca61`) reads object `+26087`, `+26058`
and `+26824` into a local source, then calls `0x603763d3` with destination
`constructor_source+8`. For Art codes `>=100`, `0x603763d3` emits:

```text
source[0] = 0x01
source[1] = variant_byte        // source +4, from snapshot +26824
source[2..3] = u16 picture_code // source +0, from snapshot +26087
```

So the four bytes are `01 VV MM 00`. `0x60418b7f` builds the full 32-byte
constructor source and calls `0x6041da81` at `0x60418bb3`. The constructor
`0x603807d0` copies source `+0..31` to `job+4..35` and writes the recomposed
key to `job+0x2c2c` at `0x60380926`.

Known callers of `0x60418b7f`:

```text
0x60419989, 0x6041f232, 0x60425193, 0x604253c3,
0x604254ce, 0x60426dac
```

Known callers of `0x6041da81`:

```text
0x60418bb3, 0x6041bbbd, 0x6041be48, 0x6041de22, 0x604268e8
```

Variant byte: the chain reads `(21,a0)` where `a0 = job+4`, so absolute
`job+25`. Proven Art source builders write only `0` or `1` at source `+21`;
the chain's `==2` branches are reachable from generic builders but their Art
producer is unresolved. Treat `VV` as a real variant, not a free toggle.

### Global picture-mode selector paths (proven, bridge unresolved)

* `0x61e88ba8` — selected picture-mode value, read by `0x60a1f28f`.
* `0x61e88bac` — secondary/variant value, read by `0x60a1f298`.
* `0x60a1f2b6` (blobA file `0x21c2b6`) writes both.
* `0x60a1f2cf` (blobA file `0x21c2cf`) writes only `0x61e88bac`.
* `0x60a1f2a1` compares the two globals.

Key/log paths at `0x609e04ad`/`0x609e04bb` and `0x60a39bf0`/`0x60a39bfa`
read these globals, build `0x01VV00MM`-style values and call `0x609fb732`.

`0x609fcc19` (blobA file `0x1f9c19`) is a proven variant/control dispatcher:

```text
call 0x609e65af
compare input to 0x61e88b20
1 -> 0x609fcc45
2 -> 0x609fceaa
6 -> 0x609fcf81
otherwise -> 0x609fd107
```

It has 29 callers with `d0` values `0,1,2,3,6,7` plus one register-derived
value. Direct global writer examples include `0x6093357c` → `0x61e88b20 = 2`
and `0x60a3067a`/`0x60a30684` → `0x61e88ba8 = 102`, `0x61e88bac = 101`.

The bridge from `0x61e88ba8`, `0x61e88b20` or `0x61e88b70` into Art
selection is still unresolved. The trigger passing wizard id `0x7e` is also
unresolved; no static caller or known dynamic table was found.

### Per-filter setting IDs and read path

Setting resolver:

```text
0x6040af6d (file 0x3e9f4d)
helpers: 0x60409aca (0x3e8aaa), 0x60409bc3 (0x3e8ba3)
group table: 0x60545cdc (0x524cbc), stride 8
```

Setting→SCP map:

```text
base   = 0x611c22b8 (main file 0x11a1298, blobB 0x5562b8)
bound  = 0x611c2508 (blobB 0x556508)
stride = 16
count  = 37
```

Record format:

```c
struct {
    uint32_t key;           // (gui << 16) | setting_id
    uint32_t sid_pair;      // SCP pair
    uint32_t index;
    uint32_t setting_value;
};
```

The first Art record is `0x611c2318` (blobB `0x556318`). Recovered Art
setting IDs:

| Filter | Setting IDs |
|---|---|
| Soft Focus | `0x15f` |
| Light Tone | `0x161` |
| Gentle Sepia | `0x166` |
| Pop Art | `0x414`, `0x415` |
| Pale & Light | `0x416`, `0x417` |
| Grainy Film | `0x418`, `0x419` |
| Pin Hole | `0x41a`, `0x41b`, `0x41c` |
| Diorama | `0x41d`, `0x41e` |
| Cross Process | `0x41f`, `0x420` |
| Dramatic Tone | `0x421`, `0x422` |
| Key Line | `0x423`, `0x424` |
| Watercolor | `0x425`, `0x426` |
| Vintage | `0x427`, `0x428`, `0x429` |
| Partial Color | `0x42a`, `0x42b`, `0x42c` |
| Bleach Bypass | `0x595`, `0x596` |
| Instant Film | `0x5a0` |

Example setting-name table rows:

| SID | Name |
|---:|---|
| `0x15f` | `MODE_COLORTONE_FANTASIC_FOCUS_ONOFF` |
| `0x161` | `MODE_COLORTONE_LIGHT_TONE_ONOFF` |
| `0x166` | `MODE_COLORTONE_SEPIA_ONOFF` |
| `0x414` | `MODE_COLORTONE_POPART_TYPE1_ONOFF` |
| `0x415` | `MODE_COLORTONE_POPART_TYPE2_ONOFF` |
| `0x595` | `MODE_COLORTONE_BLEACH_BYPASS_TYPE1_ONOFF` |
| `0x5a0` | `MODE_COLORTONE_PLACAME_ONOFF` |

Older names map to current ones: Fantasic Focus=Soft Focus, Daydream=Pale &
Light, Rough Monochro=Grainy Film, Toy Photo=Pin Hole, Miniature=Diorama,
Pastel=Watercolor, Ligne Clair=Key Line, Placame=Instant Film.

Setting read path:

```text
0x602c4d16 (file 0x2a3cf6) reads Art record field +6 as u16 setting_id
  -> 0x6040af6d resolves it
  -> 0x602c4ea1 (file 0x2a3e81) writes result to source +148
  -> 0x6037f866 / 0x6037f8eb
  -> 0x6037f8eb (file 0x35e8cb) copies source +148 to destination +52
```

This proves per-filter values are resolved and copied into descriptor/
request structures. It does **not** prove `0x60384438` consults them
automatically.

Consequences for toggles:

* Existing `*_TYPE1_ONOFF` / `TYPE2_ONOFF` setting IDs can be reused as
  explicit read-only gates if custom code resolves them and branches on them.
* They are global camera settings keyed by filter/type, not session-local
  switches.
* Reusing one for a clone aliases the clone with the original filter. A
  distinct toggle needs a new SID, name-table row, SCP/map record and menu
  resource entry.
* Hidden Film Grain `0x3e` does not reach image code; `0x6005fa9c(0x8bf1)`
  also does not reach image code. Neither is usable as an image-code toggle.

### Preferred module-mask injection point

Use the thin wrapper at `0x60383247` (file `0x362227`), not the builder
epilogue:

```text
60383247  CALL 0x60384438
6038324b  EXTHU d0
6038324d  RET
```

It has one direct caller, `0x6038170f` (file `0x3606ef`), and does nothing
except call the Art builder. A custom function should preserve `a0 = job` and
the `d2,d3,a2,a3` register contract, call the original builder, then append
or remove modules at `job+0x2ae8` keyed by `job+0x2c2c`, updating
`job+0x2c30`.

Do not replace `0x60385404..0x6038543a`: it performs slot-count and
last-slot fixup work and can append `0x603843b0`. `0x603843b0` is an
end-marker/cleanup module, not a harmless no-op.

---

## Proven vs inferred

Proven:

* six name-list bases and all 32 names/values/sids
* validator, alt list and Picture Mode list addresses
* normal Picture Mode 3-entry descriptor table at `0x6129f83c` and its
  selection code at `0x60ec9a3c`
* normal Picture Mode 3-entry handler table at `0x6129f890` and its
  selection code at `0x60ec9b13`, including writes to `0x61ea0f34`/`0x38`
  and the 4-byte-strided callback dispatch loop rooted at `0x61ea0f30`
* 3-entry common-methods table `0x6129f86c` consumed by `0x60ec9bf4`
  (`Wizard_Multirow_SampleImage_Viewer::common`), including the
  `viewKind=0` call to `0x60eca357`
* static callback groups at `0x60280c40..0x60280d44`, including the
  `0x60280c70` group that exactly matches RAM slots `0x61ea0f30/34/38`
* callback-array consumers `0x60eca6c0` (`0x61ea0f40`) and `0x60ecab90`
  (`0x61ea0f74`), plus the 74-byte decoded-row layout of `0x60e08efa`
  and `0x60e08fa0`
* three PM lists and SCP icon list formats
* language help string `sid=0x18a`
* 17 unused variants
* free blob B tail and language padding
* relocation requirement for name lists
* normal main Picture Mode list `0x6129f4a0` is a separate live source and
  must be extended in addition to SCP/Live Control lists
* blob recompression and checksum procedure
* dispatcher `0x60e08e8b`, its 135-entry table and the id `0x7e` →
  `0x60ec995e` wizard constructor entry
* wizard object initialization at `0x60ec997e` and row-buffer object at
  `+0x95c`
* absence of an immediate id `0x7e` at all 12 direct dispatcher call sites and
  at all 75 callers of the three resource-loader entry points
  (`0x60e7062d`, `0x60e706a6`, `0x60e70785`)
* generic resource loader `0x60e700cc`, runtime callback table `0x61ea0340`
  and the true `{key,kind,factory_id}` format of `0x6123b450`
* `0x60ec9c58`/`0x60ec9f6f`/`0x60eca40c` row-buffer construction, decoder
  stride `0x74`, decoded-row `+6` enable flag and selected-row flags
* cleanup at `0x60eca343`/`0x60ec9eea` clearing cursor flags at
  `+0x490+0x216/+0x218/+0x21a`
* factory id `0x37` path `0x611d7d9c` → `0x60eca581` → `0x60eca5a1` and
  table `0x6129fe3c`
* job-key writer `0x603807d0` source-byte layout and its 32-byte struct
  construction via `0x60418b7f`/`0x6041da81`/`0x6041dbd1`
* snapshot → key path: `0x60411db9` → `0x60411ebf` → `0x6041da81` →
  `0x603763d3` → `0x603807d0` → `job+0x2c2c`
* picture-mode key bytes are `01 VV MM 00` and `VV` comes from snapshot
  `+26824`, not from an effect toggle
* setting resolver `0x6040af6d`, setting→SCP map `0x611c22b8`, and the
  recovered per-filter setting IDs
* setting read path `0x602c4d16` → source `+148` → destination `+52`
* wrapper `0x60383247` is the structural injection point; `0x603843b0` is
  an end-marker/cleanup module, not a harmless no-op
* no expanded-image immediate/call xrefs to SCP descriptors
  `0x611ef284`/`0x611efc08`/`0x611fe03c` or the name-list bases

Inferred:

* what actually triggers the dispatcher with id `0x7e`
* producer/initial value of callback slot `0x61ea0f30`; only its dispatch loop
  is proven
* copy/registration path from static callback group `0x60280c70` into RAM slots
  `0x61ea0f30/34/38`; no immediate or aligned `u32` reference to any group base
  exists in the expanded runtime image
* producers of callback arrays `0x61ea0f40` and `0x61ea0f74`; only their
  consumers are proven
* semantic source of the `0x384` bound in `0x60ec9f6f`; only its numeric value
  is proven
* bridge from global picture-mode selectors (`0x61e88ba8`, `0x61e88b20`,
  `0x61e88b70`) into the Art wizard/dispatcher that feeds `0x6041da81`
* trigger that passes wizard id `0x7e`
* Art producer of source/chain `+21 == 2`
* whether cloned filters need new setting IDs or may alias stock SIDs
* runtime safety of a custom wrapper at `0x60383247` (not camera-tested)
* which reused icon best suits a new monochrome filter
* whether the optional map at `0x611c2314` must be updated
* visual behavior of variant III entries without the dispatch range patch

---

## Remaining probes

* trace beyond the 12 known dispatcher call sites to find a producer of id
  `0x7e`; none of the static immediates, the `0x6123b450`/`0x611dd8e0`
  factory-id slots, or the 75 callers of the three loader entry points contains
  it
* find the producer of callback slot `0x61ea0f30` to close the handler-dispatch
  loop, including a byte-wise search for indirect references into the static
  callback groups at `0x60280c40..0x60280d44` (no direct immediate or aligned
  `u32` reference exists)
* selection-to-job-key path and per-filter setting IDs — completed and recorded
  above
* bridge from global picture-mode selectors into the Art selection dispatcher —
  still unresolved
* SCP descriptor/name-list consumer resolution; only direct-xref absence is
  proven so far
* grain kernel/Y-only mask — completed negative; no safe patch site proven
* blur kernels for Diorama / Soft Focus — in progress
* effect-enable mask hook at wrapper `0x60383247`, not the builder epilogue —
  planned; camera validation required
