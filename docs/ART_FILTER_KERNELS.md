# Art Filter downstream kernels and hardware paths

All addresses are runtime; file offset = address − `0x60021020`.

This document tracks what happens *after* the chain modules in
[ART_FILTER_CHAIN.md](ART_FILTER_CHAIN.md): the code that consumes layer
descriptors/request blocks and produces the visual effect.

Status: active reverse engineering. The vignette/frame path and the
`job+0x2c2c` writer are decoded. The Grainy builder path is partially traced,
but no downstream Y-only pixel kernel has been proven. A 3×3 blur/sharpness
coefficient generator is proven, but its named-filter mapping is not.

## Important architectural correction

For vignette/frame, there is **no CPU pixel loop** that reads source pixels and
writes destination pixels. The chain builds a request block, then a downstream
function programs an ISP hardware-register structure. “Kernel” here means a
configuration generator, not a software convolution.

The same may be true for other effects; do not assume a CPU loop without
finding one.

## Vignette / frame path — decoded

### Installer

`0x6038b69b` is reached from variant router `0x6038b4e4` when
`byte[job+0x1a]` is 3 or 4. Other values route to `0x60393a1d`, `0x6038d720`,
`0x60394d8f`, `0x60394da3`.

It installs three slots at `job+0x2ae8` and sets `u16[job+0x2c32]=3`:

| Slot | Callback | Role |
|---:|---|---|
| 0 | `0x6038b70d` | build frame request `R = job+0x2c64`, pass `0x8000` |
| 1 | `0x6038baff` | descriptor `0x14002` resource/lifecycle work |
| 2 | `0x6038bbb3` | pass `0x8f00`, descriptor `0x1000002` |

Install sites: `0x6038b6a0`, `0x6038b6a7`, `0x6038b6b0`.

### Request builder `0x6038b70d`

* `byte[job+0x15c0] == 2` → early return at `0x6038bafb` (no frame request).
* `R+16 = 8` (mode byte)
* `R+12 (u16) = 0x8000` — pass ID
* `R+500 = u16[J+264]` minus `u16[J+276]` if `byte[V]==1`, else `u16[J+264]`
* `R+502 = u16[J+274]`
* `R+504 = u16[J+276]`
* `R+530 = u16[J+278]`
* `R+532 = byte[J+281]`
* `R+533 = byte[V]` — frame-enable/style byte
* 26×u16 from `job+0x3750` → `R+0x1c0`
* descriptors `0x4000`, `0x4001`, `0x14002` installed at `0x6038b953`,
  `0x6038b9c9`, `0x6038ba08`

### Downstream ISP consumer `0x603ce899`

A full xref sweep found exactly one reader each of `R+500`, `R+530` and
`R+533`, all in this function.

* `0x603ce899`: `a1 = (4,a0) = R`; requires `u16[R+12] == 0x8000`.
* `0x603ce8bb–0x603ce8c7`: `byte[R+533]` must be 1 or 2, else return.
* `0x603ce8d5`: reads `u16[R+500]`.
* `0x60530084`: 12-entry u16 band table `0x500,0x600,…,0x1000`
  (file `0x50f064`). `0x603ce8e9–0x603ce920` brackets the value into two band
  indices 0..12, clamped 0..11. This is the **radius/size quantizer**.
* LUT pointers `0x605300e8/ec/f0/f4/f8/fc/100` point to byte tables
  `0x605300a9`, `+b5`, `+c1`, `+cd`, `+d9` with values `01`, `10`, `02`, `00`,
  `ff`. `0x603ce965–0x603cea96` interpolates between bands into `R+260/+264`.
* `0x603ceb3f`: `u16[R+530]` through float helpers `0x600ef26a`,
  `0x600ef1a6`, `0x600ebda5`, `0x600ef1b8`, `0x600ef13f` → clamped 16-bit
  values. Likely feather/strength.
* `0x603cebf3`: `u16[R+0x1f8]` → float math → `R+252/+256`;
  `0x603cec4b`: `0x300 − u16[R+0x1f8]` → `R+240`.
* Tail `0x603cecc0–0x603ced64` writes a hardware register struct based at
  `SP+0x1cc4`.

Call chain: `0x603626f6` → `0x60369768` → `0x603697ce` → `0x603ce899`.

### Geometry / aspect correction

`0x6038be6f` calls `0x603e41c5` at `0x6038bc2b` when
`byte[job+0x15c0] != 2` (the `==2` branch uses shorter `0x6038bf9a`).

`0x603e41c5(a0=R+0x618, a1=out0, a2=out1, d0=out2)`:

```text
d1 = min(u16[a0+4], u16[a0+6])
out0 = clamp((u16[a0]   << 7) / d1, 1, 0xffff)
out2 = clamp((u16[a0+2] << 7) / d1, 1, 0xffff)
```

This is proven **aspect normalisation** using the shorter image dimension.

`0x6038be6f` then applies:

* `R+0x628 = clamp((u16[R+0x628] << 7) / out0, 1, 0xffff)`
* `R+0x62a = clamp((u16[R+0x62a] << 7) / out2, 1, 0xffff)`
* `R+0x62c = R+0x62e = 0x80` at `0x6038bf0b` — centre, 128/128
* clears 4×u16 at `R+0x600`, `R+0x610`, `R+0x620`
* sets `R+0x618..+0x61e` to `0x80`
* `u16[job+0x140] → R+0x64a`

`0x603ce1a8` is a filter-family predicate on codes `0x1010068`,
`0x1020068`, `0x1020079`, `0x102007b`; it is not vignette math.

## Vignette patch points

All original bytes were verified against the unpacked main block.

| ID | Runtime | File offset | Original bytes | Candidate patch | Scope |
|---|---|---:|---|---|---|
| P1 | `0x603ce89f` | `0x3ad87f` | `fc c8 00 80 00 00` | `fc c8 01 9e 00 00` | Global: skips all pass-`0x8000` frame config |
| P2 | `0x603ce8bf` | `0x3ad89f` | `a0 02 c8 09 a0 01 c8 05` | `a0 00 c8 09 a0 00 c8 05` | Global: frame-enable guard never passes |
| P3 | `0x6038b6a0` | `0x36a680` | `fc cc 0d b7 38 60` | `fc cc b0 43 38 60` | Filter-family scoped: slot 0 → end-marker `0x603843b0` (not proven no-op) |
| P4 | `0x6038b70d` | `0x36a6ed` | `cf f0 fa fe 68 ff 43 0c f1` | `fc cc 01 9e 00 00 df 00 04 90` | Same family: skip request build with `0x9e01` |
| P5 | `0x60530084` | `0x50f064` | `00 05 00 06 … 00 10` | edit thresholds | Global band/radius quantizer |
| P6 | `0x6038bf0b` | `0x36aeeb` | `2f 80 00` | assemble carefully | Moves frame centre |

**Safest starting point:** P3 (filter-family scoped). P1/P2 are smaller byte
edits but global to all frame requests. P3 leaves slots 1/2 running; camera
test required.

## Grain path — partial trace, no Y-only kernel proven

### Proven builder path for `job+16 == 0x2000`

At `0x60384520–0x60384525`, `0x60388c36(job+16)` returns a function pointer
from `0x6052dc30[4]` and stores it as the last slot's word1:

```text
0x6052dc30[4] = 0x603887bb
```

`0x603887bb` is a parameter-copy routine:

```asm
603887c1  MOVBU (16,a3),d0       ; request+16 = mode
603887c5  CMP 0,d0
603887c7  BEQ 0x603887cf
603887c9  CMP 3,d0
603887cb  BEQ 0x603887ee

603887cf  MOV (14236,a2),d0      ; job+14236
603887d3  MOV 12,a1
603887d7  MOV 0x214,a0
603887dc  MOV -16,d1             ; 16 words / 64 bytes
...
603887e5  MOV 0x500,d0
603887e8  MOVHU d0,(1838,a3)     ; request+1838 = 0x500
```

For mode 0:

```text
request+0x214 = 16 words copied from job+14236
request+1838  = 0x500
```

The downstream selector is:

```asm
603e3f11  ADD 0xfefd,d0          ; 0x500 + 0xfefd = 0x3fd
```

Then `0x6053e98c[0x3fd]` → `0x603e3f70` → category 13.

The proven chain is therefore:

```text
Grainy key
  -> Add Effects 4
  -> job+16 = 0x2000
  -> 0x60388c36
  -> 0x6052dc30[4] = 0x603887bb
  -> request+0x214 = 16 words from job+14236
  -> request+1838 = 0x500
  -> 0x603e3ef7
  -> key 0x3fd
  -> category 13
  -> 0x603cf4a6
```

### The `0x2000` word0 handlers are not pixel kernels

The `0x2000` dispatch at `0x60385229` jumps to `0x6038543d`. Its slot tail
selects:

```text
0x60388169 / 0x60388295 / 0x60388384 / 0x603884e2
```

These are parameter setup / continuation / cleanup functions. For example:

```asm
6038822d  MOV 0x2c30,a3
60388232  MOVHU (a3),d1          ; active slot count
60388243  MOV (10992,a0),d0      ; last slot word0
60388279  CALL 0x60396713        ; common callback runner
```

`0x60396713` invokes the last slot's word1 callback through the standard
descriptor runner. It does not contain a grain pixel loop.

### Corrected negative findings

* The earlier claim that `0x6039c671` reads `request+656` from `0x603859f0`
  was based on misleading compressed disassembly. Clean disassembly shows a
  job-side allocation/write under `0x20000`:

  ```asm
  60385a4d  MOV (8,SP),a1
  60385a4f  CMP 0,a0
  60385a51  MOV a0,(14236,a1)     ; write job+14236
  60385a59  MOV (12,SP),a0
  60385a5a  MOV (a0),d0
  60385a5a  BTST 0x20000,d02
  ```

* `job+14224` is nearby group metadata. The proven copied range starts at
  `job+14236`; no Grainy-specific write to `14224` was found.

* A full image scan found **no writer** at displacement `0x15d4`. The only
  proven reader is in the non-Grainy `0x80000` path:

  ```asm
  60388819  MOVSBU (0x15d4,a2),d0 ; strength -5..+5
  ```

  Therefore the `0x80000` strength path cannot be assumed to control Grainy.

* The accessor `0x603e402b` is proven:

  ```asm
  603e402b  MOVBU (16,a0),d0
  603e4032  CMP 3,d0
  603e4035  BNE 0x603e4042
  603e4037  MOVHU (656,a0),d1
  603e4042  MOVHU (1838,a0),d1
  ```

### Conclusion

No downstream instruction has been proven to be a Grainy-only channel mask or
Y-only pixel kernel. The earlier candidates:

```text
0x603881dc  flags 0x1010 -> 0x1000
0x603882f8  flags 0x1010 -> 0x1000
0x60383e48  flags 0x1060 -> 0x1000
0x6038463d  module 0x60383c5b -> 0x60384434
```

remain **inference only** and should not be treated as safe patch sites.

## Blur / sharpness coefficient generator — generator proven, filter mapping pending

A concrete 3×3 ISP coefficient generator was found at:

```text
0x603dc04a  file 0x3bb02a
```

### Proven generator path

`0x603dc04a`:

* reads signed byte `job+0x296` (`MOVBU (662,a0)` at `0x603dc065`);
* clamps it to `−5..+5`, then adds `5`, giving index `0..10`;
* loads a pointer from table `0x6053c1dc` at `0x603dc087`;
* if dword `job+52 == 5`, applies transform `0x603dbe0d` selected by byte
  `job+0x297`;
* if byte `job+0x292` is nonzero, applies a second transform with table
  `0x6051b00e`;
* calls `0x603dbd9a` to normalize/pack the result;
* writes nine signed halfword taps as five packed dwords at
  `request+80..+99`, starting at `0x603dc0dd`.

Supporting routines:

| Purpose | Runtime | File offset |
|---|---:|---:|
| Tap generator entry | `0x603dc04a` | `0x3bb02a` |
| 3×3 multiply-accumulate transform | `0x603dbb3b` | `0x3bab1b` |
| Normalization/packing | `0x603dbd9a` | `0x3bad7a` |
| Preset selector | `0x603dbe0d` | `0x3baded` |
| 11-pointer table | `0x6053c1dc` | `0x51b1bc` |

`0x603dbb3b` is a real multiply-accumulate over signed 16-bit taps with
`>>8` output. This is not merely register configuration.

### Proven coefficient semantics

The 11 base tables pointed to by `0x6053c1dc` are at:

```text
0x6053c114..0x6053c1d0
file 0x51b0f4..0x51b1b0
```

Their 3×3 values form:

| Index | Meaning |
|---:|---|
| `0..4` | progressively weaker low-pass / blur-like kernels |
| `5` | identity: centre `128`, neighbours `0` |
| `6..10` | progressively stronger high-pass / sharpen kernels |

These are proven signed 16-bit 3×3 filter taps consumed by the generator.

`0x603dbe0d` also selects directional/edge-style presets from `0x6051ae16`
onward (file `0x4f9df6`). Their sums are mostly `768`, consistent with
fixed-gain spatial filters.

### How the generator is selected

`request+12` type `0xf001` is written by six small wrappers:

| Runtime | File offset | Writes |
|---:|---:|---|
| `0x60388f41` | `0x367f21` | `0xf001`, then helper `job+0x290 = 0xb00` |
| `0x60388f56` | `0x367f36` | `0xf001`, then `0xb01` |
| `0x60388f6b` | `0x367f4b` | `0xf001`, then `0xb02` |
| `0x60388f80` | `0x367f60` | `0xf001`, then `0xb03` |
| `0x60388f95` | `0x367f75` | `0xf001`, then `0xb04` |
| `0x60388faa` | `0x367f8a` | `0xf001`, then `0xb05` |

They are installed by builder `0x6038543d` (file `0x36441d`), reached through
wrapper `0x60383250` (file `0x362230`).

Dispatcher `0x603816c5` (file `0x3606a5`) selects that builder when:

```text
job+0x1a not in {0, 4}
job+0x1b != 0
```

### Patch status

No blur patch bytes are published.

The generator is proven, but this chain is not yet proven:

```text
named Art Filter + setting
  → job+0x296
  → low-pass tap index
  → visible blur
```

Patching low-pass tables blindly could affect sharpness, Soft Focus,
Watercolor, grain or another spatial effect. The likely future patch scope is
the family-scoped pointer array `0x6053c1dc` or the six `0xb00..0xb05` wrapper
callbacks, not a global helper.

`0x60369019` remains only an older candidate coefficient loop; `0x603dc04a`
is the concrete generator to pursue.

## Proven vs inferred

Proven:

* request fields, pass IDs, slot pointers, band table, aspect math, guards and
  patch bytes
* the Grainy `0x2000` builder path up to category 13
* the `0x603dc04a` 3×3 coefficient generator, tap tables and tap semantics

Inferred:

* which request field is “darkness” versus “radius” versus “feather”
* which `job+0x1a` value is Pop Art II versus Pin Hole
* visual outcome of each patch
* any colour-grain / Y-only interpretation of the Grainy flags
* that indices `0..4` are specifically Diorama/Soft Focus blur rather than a
  generic low-pass family

## Pending

* Grain consumer and semantics of `request+0x214`
* Whether Grainy reaches `0x603976bf` and overwrites `request+1838` to `0xfe00`
* Complete scratch-to-MMIO pointer chain from category 13
* Whether `0x603845c1` variant descriptors match runtime Grainy values
* Whether `0x60383ff7` is invoked on the Grainy-specific builder tail
* Writer of `job+0x1b` and which filter key reaches wrapper `0x60383250`
* Which setting writes `job+0x296` for the `0xb00..0xb05` family
* Camera confirmation that a low-pass tap index changes the intended visual blur
* Effect-enable mask hook at wrapper `0x60383247`, not the epilogue
  `0x60385404..0x6038543a`

The `job+0x2c2c` writer is resolved in
[ART_FILTER_CHAIN.md](ART_FILTER_CHAIN.md): constructor `0x603807d0`, store
`0x60380926`, value = picture-mode key copied from source `+8..11`.
