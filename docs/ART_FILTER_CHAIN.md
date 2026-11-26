# Art Filter processing chain (stage F)

This document records the decoded dispatch and slot mechanics for the extra
processing modules that give each Art Filter its characteristic effect. All
addresses are runtime; file offset = address − `0x60021020`.

What happens downstream of these modules is tracked separately in
[ART_FILTER_KERNELS.md](ART_FILTER_KERNELS.md); for vignette/frame that path is
ISP register programming, not a CPU pixel loop.

Status: the **machine-level dispatch, slot layout, consumer, individual module
roles and the `job+0x2c2c` writer are proven**. The dispatch field is the
picture-mode key byte-for-byte. Both tables store residuals of that key. The
low Art Filter codes `0x64-0x67` still need reconciliation with the legacy
module notes; they miss both documented hash tables and likely use another
builder path.

## Builder and dispatch

Builder: `0x60384438` … `0x6038543a`.

* `a0` = job; `a3 = job+0x2ae8` (chain slot array).
* `field = *(job+0x2c2c)` at `0x60384465..0x6038446f`.
  Proven writer: job constructor `0x603807d0`, store at `0x60380926`.
  The value is copied from the constructor source record `src+8..11` and is
  exactly the picture-mode key `0x01VV00MM`; it is not derived arithmetically
  from the key.
* **Secondary table first** (`0x60384573`):
  * accepts `0x01010068 <= field <= 0x0102007b`
  * residual `r2 = field - 0x01010067` (`ADD 0xfefeff99,d1`)
  * index `r2 & 15`, table `0x6052dbb0`, **16 entries** (`0x6052dc30` bound)
  * a hit sets `(20,SP)=1`; the later primary-table check is skipped
* **Primary table** (`0x60384931` …):
  * accepts `12 <= field <= 0x0102007b`
  * residual `r1 = field - 11`, index `(r1 & 31)*8`
  * table `0x6052dab0`, 32 entries; miss handler `0x60384ec7`

Both tables store **residuals**, not absolute fields:

```text
r1 = field - 11
r2 = field - 0x01010067
```

Because `field == 0x01VV00MM`, for normal v1 art codes:

```text
r1 = 0x010100(code - 0x0b)
r2 = code - 0x67          (only when code >= 0x68)
```

For v2, the high halfword of `r2` becomes `0x0001`; for v3 the field is above
the range checks entirely.

The earlier assumption that the primary table alone selects Art Filters is
wrong for fields that hit the secondary table. Secondary hits win.

### Writer of `job+0x2c2c` — proven

Job constructor `0x603807d0` copies source `+0..31` into `job+4..35`, then
recomposes the key from the copied bytes:

```text
603808fb  f1 eb         MOV d2,a3        ; a3 = job+4
603808fd  53            INC4 a3
60380908  9a 08         MOV 8,a2
6038090a  f1 7e         ADD a3,a2        ; a2 = job+12
6038090c  f0 46         MOVBU (a2),d1    ; key byte 0
6038090e  f8 42 01      MOVBU (1,a2),d0  ; key byte 1
60380911  f8 6e 02      MOVHU (2,a2),d3  ; key halfword 2
60380914  f8 c1 18      ASL 24,d1
60380917  f8 c0 10      ASL 16,d0
6038091a  f2 11         OR d0,d1
6038091c  84            MOV d1,d0
6038091d  f2 1c         OR d3,d0
6038091f  24 2c 2c      MOV 0x2c2c,a0
60380922  f1 68         ADD d2,a0        ; a0 = job + 0x2c2c
60380924  43 0c         MOV a0,(12,SP)
60380926  60            MOV d0,(a0)      ; store field
```

So `field = (src[8]<<24) | (src[9]<<16) | (src[10]<<8) | src[11]`,
i.e. the picture-mode key itself. The key is produced by `0x6041da81` via
`0x603763d3` and written into the constructor source by `0x60418b7f`.

The variant byte at source `+21` is a sibling value, not an input to the field
formula. It lands at allocated `job+25`; the chain builder's `job+21` is
relative to its `job+4` base.

### Consequence for variants

* Any field with high halfword `0x0103` is above `0x0102007b`, so **variant 3
  always takes the generic chain** (`0x60384ec7`). This is proven from the
  range checks, independent of the field formula.
* Variant 2 can only hit the secondary table through residuals `1`, `0x10001`,
  `6`, `0x10006`, `0x10`, `0x10010`, `0x14`, `0x10014`; all others fall through
  to the primary table or generic.
* Fields whose residual is `0x01010014` / `0x01020014` are outside both tables
  and go generic.

### Tables

Secondary `0x6052dbb0` (16 entries). First column is the residual `r2`:

| residual r2 | handler |
|---|---|
| `1`, `0x00010001` | `0x603845c1` |
| `5` | `0x603847bc` |
| `6`, `0x00010006` | `0x6038468e` |
| `8`, `0x0000000e` | `0x60384858` |
| `0x0000000f` | `0x6038472e` |
| `0x10`, `0x00010010` | `0x603847f4` |
| `0x14` | `0x603848a2` |
| `0x00010014` | `0x603848dd` |
| zero slots | `0x60384927` (miss) |

Primary `0x6052dab0` non-miss entries. First column is the stored residual
`r1 = field − 11`; for v1 art codes this is `code − 0x0b`:

| residual r1 | handler |
|---|---|
| `0x0101005d`, `0x0102005d` | `0x6038497a` |
| `0x0101005f`, `0x0102005f` | `0x60384a38` |
| `1` | `0x60384cee` |
| `0x01010061` | `0x60384b6d` |
| `0x01010062`, `0x01020062` | `0x60384abc` |
| `0x01010064`, `0x0101006a` | `0x60384cc4` |
| `0x0101006b` | `0x60384b1c` |
| `0x0101006c`, `0x0102006c` | `0x60384ba2` |
| `0x0101006d`, `0x0102006d` | `0x60384c53` |
| `0x0101006e`, `0x0102006e` | `0x60384d63` |
| `0x01010070` | `0x60384d71` |
| `0x01020070` | `0x60384d7f` |
| `0x01010071` | `0x60384e05` |

All other slots use `0x60384ec7`.

## Chain slots and consumer — proven

* Slot array base: `job+0x2ae8` (`0x60384440`, `0x60381169`).
* Stride: 12 bytes (`UDFU01 12,d0` at `0x6038445b`, `0x603811ae`).
* Slot word 0 = module entry point.
* Slot word 1 = pointer returned by `0x60388c36(flags)`.
* Count fields: `job+0x2c30` / `job+0x2c32`; written in the epilogue at
  `0x6038541a` and read by the consumer at `0x6038114d`.
* Append helper: `0x603830c6`.
* Consumer: `0x60381146`; word 0 is null-checked at `0x603811b1` and modules
  are called with `CALLS (a1)` at `0x603811c0`. Called from `0x6038137e`
  (`d1=-1`) and nearby loops.
* Epilogue `0x60385404..0x6038543a`: if no slots, returns `0x9ec1`; if the last
  slot word 0 is `0x60384353`, appends `0x603843b0`.
  `0x603843b0` is an **end-marker/cleanup module**, not a harmless no-op: it
  reads `job+0x2c30`, clears slot state, calls `0x603836bc` and writes slot data.
  Do not replace this epilogue with a custom hook.

Flag helper `0x60388c36` maps `job+0x10` bits to slot word 1:

| mask | returned pointer |
|---|---|
| `0x400` | `0x603886e9` |
| `0x8000` | `0x6038873b` |
| `0x2000` | `0x603887bb` |
| `0x10000` | `0x603888d9` |
| `0x20000` | `0x603889b5` |
| `0x40000` | `0x60388a86` |
| `0x1800` | `0x60388afa` |
| `0x80000` | `0x60388813` |
| else | `0` |

## Job fields that alter insertion — proven

* `job+16`: `&0xf00 == 0x100` or `&-16 == 0x40` selects the grain-like short
  paths in many handlers.
* `job+21`: variant byte; `== 2` inserts extra modules in `0x603845c1`,
  `0x6038468e`, `0x60384abc`, etc.
* `job+0x2c45`: values `0..3`, `4..8`, `8` gate modules in `0x60384a38`,
  `0x603845c1`, `0x60384fb4`, `0x6038579b`.
* `job+0x2c38`: nonzero selects special branches in several handlers and sets
  `job+0x2c39 = 1`.
* `job+0x2c20/+0x2c24/+0x2c28`: cleared for keys `0x1010068`, `0x1020068`,
  `12`; otherwise set to `0x60382e6e`, `0x60382ec9`, `0x6038326a`.
* `job+0x2c4c`: read by thunk `0x6038441d`; `0x603889b5` stores `0x9e01` at
  `job+0x2c46`.

Common tail `0x60384f0e..0x60385404` adds flag-driven modules:
`0x20000` → `0x60388db8/0x60388dca`, `0x40000` → `0x60388ddc/0x60388dee`,
`0x40` with `job+0x2c45 in {0,1,2,3,8}` → `0x6038abd9`, `0x1800` →
`0x60388afa`.

## Handler module summaries — proven handler contents

These are the module writes inside each handler. Conditional branches are
listed; they are not a single fixed chain.

### Secondary

* `0x603845c1` (`1`, `0x10001`): `0x60383c69` for grain-like flags; otherwise
  `0x603839fd`/`0x60383a1f`, then `job+21==2` → `0x60388169`, `0x60383c5b`,
  `0x60388295`; else `0x60388169`/`0x603880f0`; then `0x603884e2`.
* `0x6038468e` (`6`, `0x10006`): optional `0x6038621c`; `job+21==2` →
  `0x60386283`, `0x60383c5b`, `0x603843b0`; else `0x6038639c`.
* `0x603847bc` (`5`): `0x60386442`, optional `0x60383c5b`, then `0x603866da`.
* `0x6038472e` (`0xf`): grain-like → `0x60383c69`; else `0x603839fd`,
  `0x60387e4e`, `0x60387f68`, `0x60388076`.
* `0x603847f4` (`0x10`, `0x10010`): `0x603867f7`, `0x60386a81`, `0x60386e97`.
* `0x60384858` (`8`, `0xe`): `0x60386fc2`, optional `0x60383c5b`, then
  `0x60387254`.
* `0x603848a2` (`0x14`): `0x60385dbe`.
* `0x603848dd` (`0x10014`): only if `job+0x2c38 == 0` → `0x60385e18`,
  `0x60385f31`, `0x60387254`.
* `0x60384927`: secondary miss.

### Primary

* `0x6038497a` (`0x0101005d`, `0x0102005d`): `0x60383d99` or grain-like chain
  `0x603839fd`/`0x60383a1f`, `0x60388169`, `0x60383c5b`, `0x60388295`,
  `0x603884e2`, `0x60388384`.
* `0x60384a38` (`0x0101005f`, `0x0102005f`): `job+0x2c45 in 0..3` →
  `0x6038619b`, `0x60383c5b`, `0x60384353`, `0x6038605d`, `0x60383d99`;
  else `0x60383d99`.
* `0x60384abc` (`0x01010062`, `0x01020062`): `0x6038621c`, then `0x60386283`
  (plus `0x60383c5b`, `0x60384353` when `job+21==2`).
* `0x60384b1c` (`0x0101006b`): grain-like → `0x603839fd`, `0x60387e4e`,
  `0x60387f68`.
* `0x60384b6d` (`0x01010061`): `0x60386442`, optional `0x60383c5b`, then
  `0x6038655b`.
* `0x60384ba2` (`0x0101006c`, `0x0102006c`): short grain-like `0x603867f7`,
  `0x60386a81`, `0x60386d77`; otherwise Key Line chain `0x603867f7`,
  `0x6038685b`, `0x60386a81`, `0x6038696b`, `0x60386bab`, `0x60386d06`.
* `0x60384c53` (`0x0101006d`, `0x0102006d`): `0x60387606`, `0x60387716`,
  `0x6038781d`, `0x60387978`.
* `0x60384cc4` (`0x01010064`, `0x0101006a`): `0x60386fc2`, optional
  `0x60383c5b`.
* `0x60384cee` (`1`): `0x60383d99`/`0x60383c69`/`0x603875f5` or
  `0x6038735f`, `0x6038746f`.
* `0x60384d63` (`0x0101006e`, `0x0102006e`): `0x60388596`.
* `0x60384d71` (`0x01010070`): `0x60385b6b`.
* `0x60384d7f` (`0x01020070`): `0x60383c69`, `0x60385f5b`, … or `0x60385e18`,
  `0x60385f31`, `0x603870db`.
* `0x60384e05` (`0x01010071`): `0x60387a4c`, then grain-like
  `0x60383d99`, `0x60383c69`, `0x60387d61` or the `0x60387c2a`/
  `0x60387dfb`/`0x60387afa`/`0x60387da2` path, ending `0x60387c2a`,
  `0x60387daf`, `0x603870db`, `0x60387254`, `0x60387e0f`.
* `0x60384ec7`: generic — conditional `0x60384345`/`0x60383c5b`/
  `0x60384353` plus the common tail.

## Module semantics — decoded

The worker descriptors use common helpers `0x6037d71e` (17-word coefficient
copy), `0x6037d7f7` (56-byte descriptor mode), `0x6037db33` (resource lookup)
and `0x60396713` / `0x603836e4` (callback installation). Pass IDs are written by
small callback functions; they are the clearest identifier for each effect.

| Module | Operation / pass | Worker / resource | Proven handler xref(s) |
|---|---|---|---|
| `0x603867f7` | staging slot patcher; callback `0x60386f08` sets pass `0x500` when byte `job+0x10==6` | gate `job+0x2c4b`, ID `0x1050` | `0x6038481d`, `0x60384bc9`, `0x60384bf6` |
| `0x6038685b` | line/threshold pass `0x501` | `0x1051`, mode `0x304`, align `0x40` | `0x60384c04` |
| `0x6038696b` | follow-up pass `0x502`, 17-word coefficient copy | `0x1051`, mode `0x304` | `0x60384c1f` |
| `0x60386a81` | fill/setup pass `0x503`, writes `0x1000002` at record `+0x1a0c` | `0x1052`, mode `0x302` | `0x6038482c`, `0x60384bd8`, `0x60384c12` |
| `0x60386bab` | combine pass `0x504` | `0x1000`, resources `0x1051`+`0x1052` | `0x60384c37`, `0x60384c40` |
| `0x60386d06` | alternate combine pass `0x504` | `0x1000`, resource `0x1052` | `0x60384c4b` |
| `0x60386d77` | short-path final pass `0x505` | `0x1000`, resource `0x1052` | `0x60384be7` |
| `0x60386e97` | slot patcher for short-path pass `0x505` | resource `0x1052` | `0x6038483b` |
| `0x60387606` | first spatial/wash pass `0x600` | `0x1040`, mode `0x304`, align `0x40` | `0x60384c80` |
| `0x60387716` | second spatial/wash pass `0x601` | `0x1041`, mode `0x302` | `0x60384c8d` |
| `0x6038781d` | combine pass `0x602` | `0x1000`, resources `0x1040`+`0x1041` | `0x60384ca5`, `0x60384cae` |
| `0x60387978` | texture/spatial pass using pointer tables `0x604fb2f4`, `0x604fb2e4`, `0x604fb304` | `0x10b0`, mode `0x304` | `0x60384cb9` |
| `0x6038621c` | staging slot patcher; callback `0x603863f6` sets pass `0x400` when byte `job+0x10==6` | ID `0x1000002` | `0x6038469f`, `0x60384acd` |
| `0x60386283` | main local-contrast pass `0x401` | `0x1000`, mode `0x302` | `0x603846b7`, `0x60384ae5`, `0x60384b0f` |
| `0x6038639c` | callback installer for pass `0x401` | callback `0x6038640a` | `0x603846fa` |
| `0x60386442` | first sepia/toning pass `0x200`/`0x201` | `0x1030`, mode `0x302` | `0x603847c1`, `0x60384b72` |
| `0x6038655b` | final sepia/toning pass `0x201` | `0x1000`, resource `0x1030` | `0x60384b99` |
| `0x603866da` | slot finisher for pass `0x201`; gate `job+0x19` | callback `0x603867b4` | `0x603847eb` |
| `0x60385dbe` | bleach pass installer, passes `0xa00`, `0xa01`, `0xa02` via `0x60385fc4` / `0x60385f31` | `0x1000`, mode `0x302` | `0x603848aa` |
| `0x603870db` | extra bleach/instant pass; alt descriptor when `job+0x19==2` | `0x1000`, mode `0x302` | `0x60384dfc`, `0x60384ea6` |
| `0x60387a4c` | instant-film texture pass, same worker family as `0x60387978` | `0x10b0`, mode `0x304` | `0x60384e0a` |
| `0x60387c2a` | instant-film multi-pass finalizer, passes `0xb00`–`0xb04` | `0x1000`, resource `0x10b0`, mode `0x305` | `0x60384e5d`, `0x60384e8b` |
| `0x60388596` | vintage final pass, 17-word copy gated by `job+0x2c4d` and `job+0x19` | `0x1000`, mode `0x302` | `0x60384d68` |

### Grain, blur and frame modules

These modules are decoded from the layer setup and callback paths. Layer flags
`0x302`/`0x304`/`0x305` select the descriptor shape; the 16-word block is copied
by `0x6037d71e` into `0x19c0 + idx*88`.

| Module | Operation / pass | Parameters / flags | Proven handler xref(s) |
|---|---|---|---|
| `0x603839fd` | grain init A, keeps PRNG state | `job+0x2af0`, `job+0x2c30` | `0x6038460a` (`job+0x2c4d` 4..8) |
| `0x60383a1f` | grain init B, clears PRNG | `job+0x3788` xorshift `(x<<13)^x`, `(x>>17)`, `(x<<5)` | `0x60384617` |
| `0x60383c5b` | grain dispatcher wrapper | forwards to `0x603985de`; **not** `0x6038385b` | `0x6038463d`, plus Pop Art/Dramatic sites |
| `0x60383c69` | chain-tail updater A | rewrites last slot word1 | `0x603845da`, `0x60384517` |
| `0x60383ccb` | variant-II slot 0 updater | continuation `0x60383d46` | `0x603844ea` |
| `0x60383cd9` | variant-II slot 2 updater | continuation `0x60383d46` | `0x603844fc` |
| `0x60383d99` | type `0x305` grain wrapper | layer `0x305`, flags `0x1060`, then `0x302`/`0x1000` | `0x60384a02`, `0x60384a1b` |
| `0x60388169` | grain layer setup, variant I/II | type `0x302`, **flags `0x1010`** | `0x6038462f`, `0x6038465e` |
| `0x60388295` | grain continuation setup, variant II | type `0x302`, flags `0x1010`, allocator `0x101` | `0x6038464c` |
| `0x603880f0` | variant-I word1 partner | chain word1 only | `0x60384665` |
| `0x603884e2` | grain finalizer | allocator `0x1010`, layer `0x302`/`0x1000` | `0x60384678` |
| `0x6038619b` | Diorama setup | type `0x302`, `0x1000`, `0x1000002` | `0x60384a78` |
| `0x6038605d` | Diorama companion | flags `0x1070`, type `0x1000` | `0x60384aa2` |
| `0x60386fc2` | Pop Art / Diorama setup | type `0x302`, `0x1000` | `0x6038485d`, `0x60384cc9` |
| `0x60387254` | Pop Art / Cross / other setup | type `0x304`, flags `0x10a0` | `0x60384887`, `0x60384906`, `0x60384eb4` |
| `0x60384353` | secondary grain/key dispatcher | builds four slots; reads `job+0x2c2c` | chain builder path |

`0x603884e8`/`0x6038838b` also contain `0x1010`, but there it is an allocator
count passed to `0x6037db33`, not a layer flag. Do not patch those for colour.

### Grain strength — proven path

`0x60388813` is the grain-style word1 handler selected by flag `0x80000` in
`0x60388c36`:

* reads signed byte `job+0x15d4`, clamps to **−5..+5**;
* sign table `0x6052dc30` picks a callback family;
* divisor table `0x604fb35e` starts `928, 952, 976, 1000, 1024, 246, 258, …`;
* computes `d2 = 0x100000 / divisor`, `d3 = 0xc00` for active strengths;
* writes request `+1838/+1842/+1829` (mode 0) or `+656/+680/+661` (mode 3).

Strength `0` uses `0x60388856`, which sets `d3=0`, `d2=0x400`: effectively no
grain. The flag and divisor tables are shared, so do **not** patch them to tune
one filter; force `job+0x15d4` to zero at its source if a clean strength patch
is needed. No direct writer of that byte was found in the main block.

### Luminance-only grain — unproven; colour patches not safe

Camera tests already showed toning is not the source of mono photos. The grain
layers are the only layers using flags `0x1010` (`0x603881dc`, `0x603882f8`)
and `0x1060` (`0x60383e48`); comparable colour layers use `0x1000`. However, the
grain probe did **not** find a downstream pixel loop or channel mask. The
`0x2000` builder path leads to parameter copies and category-13 register setup,
not to a proven Y-only kernel. The colour-grain patches below remain
**unproven inference** and should not be treated as safe patch sites.
See [ART_FILTER_KERNELS.md](ART_FILTER_KERNELS.md) for the full trace.

Special tone-curve passes that pair with these modules:

* Key Line pass `0x501` uses the flat curve at `0x6053d3b4`, selected at
  `0x603df2dc`.
* Watercolor pass `0x601` / sub-mode `0x100`/`0x40` uses the identity curve at
  `0x603df2f5` / `0x603df319`.
* Instant Film pass `0xb00` uses the clipped curve at `0x6050e9a2`, selected at
  `0x603df37a`.

**Do not patch globally:** `0x6037d71e`, `0x6037d7f7`, `0x6037db33`,
`0x60396713`, worker IDs `0x1000`/`0x10b0`, or pointer tables
`0x604fb2f4`/`0x604fb2e4`/`0x604fb304` are shared across many filters. Patch the
single module immediate inside the relevant handler instead.

## Residual-to-filter mapping

The table below uses the stored primary residual `r1 = field − 11`. Since the
field is now proven to be the picture-mode key, `r1` is `code − 0x0b` for v1
filters. Secondary hits are listed where they shadow the primary entry.

The low codes `0x64-0x67` are not explained by these two tables; they miss both
hashes and need reconciliation with the legacy module notes.

| residual | v1 | v2 | v3 |
|---|---|---|---|
| `0x5d` | sec 1 → `0x603845c1` | sec `0x10001` → `0x603845c1` | generic |
| `0x5e` | generic | generic | generic |
| `0x5f` | pri `0x0101005f` → `0x60384a38` | pri `0x0102005f` → `0x60384a38` | generic |
| `0x60` | generic | generic | generic |
| `0x61` | sec 5 → `0x603847bc` | generic | generic |
| `0x62` | sec 6 → `0x6038468e` | sec `0x10006` → `0x6038468e` | generic |
| `0x63` | generic | generic | generic |
| `0x64` | sec 8 → `0x60384858` | generic | generic |
| `0x65`–`0x69` | generic | generic | generic |
| `0x6a` | sec `0xe` → `0x60384858` | generic | generic |
| `0x6b` | sec `0xf` → `0x6038472e` | generic | generic |
| `0x6c` | sec `0x10` → `0x603847f4` | sec `0x10010` → `0x603847f4` | generic |
| `0x6d` | pri `0x0101006d` → `0x60384c53` | pri `0x0102006d` → `0x60384c53` | generic |
| `0x6e` | pri `0x0101006e` → `0x60384d63` | pri `0x0102006e` → `0x60384d63` | generic |
| `0x6f` | generic | generic | generic |
| `0x70` | sec `0x14` → `0x603848a2` | sec `0x10014` → `0x603848dd` | generic |
| `0x71` | pri `0x01010071` → `0x60384e05` | generic | generic |
| `0x72`–`0x76` | generic | generic | generic |

The existing `F` strings in `tools/art_filter_dump.py` are coarse legacy hints,
not definitive module lists. `--probe` in `tools/patch_art_styles.py` prints the
raw handler tables instead.

## Validator tables (supportive, role not fully traced)

* `0x6052d930` (16 entries): most keys → `0x60383bce`; `0x0101005d`/
  `0x0102005d` → `0x60383bd0`; `0x01010064` → `0x60383be8`; `0x0101006d` →
  `0x60383be3`.
* `0x6052da30`: `0x01010070` → `0x60383b88`; `0x01010061`,
  `0x01010062`, `0x01020062`, `0x0101006c`, `0x0102006c` → `0x60383b84`;
  `0x01010064`, `0x0101006a` → `0x60383b86`; `0x01010071` → `0x60383b8a`;
  `1` → `0x60383b8c`; rest → `0x60383b8e`.

## Safest patch points

* **Remove a whole filter-specific effect:** re-point the relevant key in
  `0x6052dbb0` or `0x6052dab0` to `0x60384927` / `0x60384ec7` (miss). Do not
  edit the handler code itself.
* **Disable one module inside a handler:** patch its 4-byte immediate in the
  handler to the end-marker `0x603843b0`, but only after checking the target
  handler and conditional branch. `0x603843b0` performs slot cleanup and is
  **not** a guaranteed no-op; camera validation is still required. Several
  modules are shared by multiple filters.
* **Change the last-slot fixup:** `0x6038541d` appends `0x603843b0` when the
  last module is `0x60384353`; patching that compare changes only the fixup.
* **Do not rely on variant-3 custom chains:** the range check makes them
  generic regardless of the table contents.

### Preferred injection wrapper for custom module masks

Use the thin wrapper at `0x60383247` (file `0x362227`), not the builder epilogue:

```text
60383247  CALL 0x60384438
6038324b  EXTHU d0
6038324d  RET
```

It has exactly one direct caller, `0x6038170f` (file `0x3606ef`), and does
nothing except call the Art builder. A custom function should:

1. preserve `a0 = job` and the `d2,d3,a2,a3` register contract;
2. call original `0x60384438`;
3. if successful and the key matches a target filter, append/remove modules in
   `job+0x2ae8` using `0x603830c6`;
4. update count at `job+0x2c30`;
5. return the original/updated `d0`.

Do **not** replace `0x60385404..0x6038543a`: it performs required slot-count
and last-slot fixup work and can append `0x603843b0`.

### Camera-test patch sites

All addresses are runtime; file offset = address − `0x60021020`. Verify the
existing 4-byte immediate before patching. `0x603843b0` is an end-marker/cleanup
module, not a proven harmless no-op; treating it as disabled output is still an
inference. Secondary-table handlers win over primary ones where both exist, so
patch the secondary site first.

| Goal | Patch site (file offset) | Change |
|---|---|---|
| Disable Grainy grain — **inference only, not safe** | `0x6038463d` (`0x36361d`) | module `0x60383c5b` → `0x60384434` |
| Test colour grain — **inference only, not safe** | `0x603881dc` (`0x3671bc`), `0x603882f8` (`0x3672d8`) | layer flag `0x1010` → `0x1000` |
| Test colour grain — **inference only, not safe** | `0x60383e48` (`0x362e28`) | layer flag `0x1060` → `0x1000` |
| Disable Key Line (secondary path) | `0x6038482c` (`0x36380c`), `0x6038483b` (`0x36381b`) | module → `0x603843b0` |
| Disable Key Line (primary path) | `0x60384c04`, `0x60384c1f`, `0x60384c37`, `0x60384c4b` | module → `0x603843b0` |
| Disable Watercolor | `0x60384c80`, `0x60384c8d`, `0x60384ca5`, `0x60384cb9` | module → `0x603843b0` |
| Disable Dramatic Tone (secondary wins) | `0x6038469f`, `0x603846b7`, `0x603846fa` | module → `0x603843b0` |
| Disable Vintage | `0x60384d68` (`0x363d48`) | module → `0x603843b0` |
| Disable Bleach Bypass I | `0x603848aa` (`0x36388a`) | module → `0x603843b0` |
| Disable Bleach Bypass II | `0x603848dd` handler: `0x60385e18`/`0x60385f31`/`0x60387254`; primary `0x60384d7f` is shadowed | patch handler immediates |
| Disable Instant Film texture | `0x60384e0a`, `0x60384e5d`, `0x60384e8b`, `0x60384ea6` | module → `0x603843b0` |
| Disable Diorama blur | `0x60384a78`, `0x60384aa2` | module → `0x603843b0` |
| Disable Pop Art effect pass | `0x6038485d`/`0x60384887` and `0x60384cc9` | module → `0x603843b0` |
| Disable frame/vignette (family scoped) | `0x6038b6a0` (`0x36a680`) | slot 0 pointer `0x6038b70d` → `0x603843b0` |

See [ART_FILTER_KERNELS.md](ART_FILTER_KERNELS.md) for the downstream ISP path
and additional global/tuning patch points.

Do **not** patch globally: `0x6037d71e`, `0x6037d7f7`, `0x6037db33`,
`0x60388c36`, `0x60388813`, worker IDs `0x1000`/`0x10b0`, or pointer tables
`0x604fb2f4`/`0x604fb2e4`/`0x604fb304`.

## Remaining unknowns

* Low art codes `0x64-0x67` miss both documented hash tables. The legacy module
  notes for Pop Art / Soft Focus / Pale & Light / Light Tone need to be
  reconciled with another builder path (`0x603857de` / `0x60385a81`) or with
  the generic chain.
* The downstream grain and blur kernels are still being traced. The
  vignette/frame path is decoded in [ART_FILTER_KERNELS.md](ART_FILTER_KERNELS.md).
* Art Filter menu enumeration is not decoded yet; see
  [ART_FILTER_MENU.md](ART_FILTER_MENU.md).
