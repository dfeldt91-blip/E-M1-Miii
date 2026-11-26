# Frame effect for non-Art picture modes

Goal: enable the Art Filter frame/vignette effect while shooting ordinary
picture modes, preserving the picture mode's own tone/colour look.

Status: **plan only**. No firmware has been built or camera-tested for this
approach. Older camera tests 1.722–1.727 are recorded in `ART_FILTERS.md`.

## Why the simple routes failed

| Test | Attempt | Result | Cause |
|---|---|---|---|
| 1.722 | SCP Color Space → Frame switch + chain flag for non-Art jobs | No frame | SCP item still behaved as Color Space |
| 1.723 | Set Art Effect property `0xf5d1` → Frame `3` | No frame | Picture-mode normalization at `0x6147d3e8` cleared Art Effect |
| 1.724 | Write Frame back after normalization | No frame | Chain still lacked frame modules |
| 1.725 | Check switch from image code via property read | No response | `0x6005fa9c(0x8bf1)` did not see the switch in image code |
| 1.726 | Use settings getter `0x602ca6a5(0x3c)` | Switch reached image code, still no frame | Dispatch `0x603816c5` sends picture modes to `0x60395eb9`, which has no Art effects |
| 1.727 | Route picture-mode photo jobs to Art builder `0x60384438` | Crash/reboot | Art builder needs Art-only job setup absent from picture-mode jobs |

The missing piece is therefore specific:

```text
picture-mode builder 0x60395eb9 has no frame chain modules
```

Do **not** route whole picture-mode jobs into `0x60384438`.

## Frame path facts

From `ART_FILTER_KERNELS.md`:

```text
frame installer:       0x6038b69b
slots installed at:    job+0x2ae8
callbacks:             0x6038b70d, 0x6038baff, 0x6038bbb3
request:               R = job+0x2c64
pass ID:               R+12 = 0x8000
enable byte:           R+533 = byte[job+0x15c0]
downstream consumer:   0x603ce899
wrapper:               0x603626f6 -> 0x60369768 -> 0x603697ce -> 0x603ce899
```

The frame is ISP register programming, not a CPU pixel filter.

Effective conditions:

1. chain contains the three frame callbacks;
2. `byte[job+0x15c0] == 1`;
   - `2` is accepted by the consumer guard, but `0x6038b70d` early-outs on `2`;
3. geometry fields are populated:
   - `R+500`, `R+502`, `R+504`, `R+530`, `R+532`
   - aspect fields `R+0x618..+0x64a`.

The frame slot writes to copy are:

```text
0x6038b6a0 -> slot 0 word0 = 0x6038b70d
0x6038b6a7 -> slot 1 word0 = 0x6038baff
0x6038b6b0 -> slot 2 word0 = 0x6038bbb3
```

Descriptors used by those slots are `0x4000`, `0x4001`, `0x14002`.
Reuse the existing word1 callbacks; do not invent new descriptors.

## Recommended approach: frame-only injection

1. Keep the picture-mode dispatch:

   ```text
   0x603816c5 -> picture-mode builder 0x60395eb9
   ```

2. Add a settings-gated branch inside/after `0x60395eb9`, using the proven
   settings getter `0x602ca6a5(0x3c)` from test 1.726.

3. When Frame is on, append only the three frame callbacks to the chain slots.
   First verify that `0x60395eb9` uses the same layout as the Art builder:

   ```text
   job+0x2ae8, stride 12
   count fields: job+0x2c30 / job+0x2c32
   append helper: 0x603830c6
   ```

   If the picture-mode builder has a different slot array, find its equivalent
   before patching.

4. Force:

   ```text
   byte[job+0x15c0] = 1
   ```

   so `R+533 = 1`, passing the guard at `0x603ce8bf`. Use `1`, not `2`.

5. Copy geometry setup from `0x6038b70d`:

   ```text
   R+500 = u16[J+264] minus u16[J+276] if byte[V] == 1
   R+502 = u16[J+274]
   R+504 = u16[J+276]
   R+530 = u16[J+278]
   R+532 = byte[J+281]
   ```

   If picture-mode jobs do not carry those values, initialize them from image
   dimensions. Do not hardcode constants before camera testing.

6. Verify the shared wrapper `0x603626f6 -> ... -> 0x603ce899` runs for
   picture-mode jobs. If it does, no downstream patch is needed.

Expected result:

```text
Picture Mode + Frame On  -> framed image, picture-mode tone preserved
Picture Mode + Frame Off -> stock
```

Risk: **Medium** if `0x60395eb9` uses the same slot layout; **High** if
frame-only setup depends on Art-only job fields.

## Alternatives

### Neutral Art Filter carrier

Make the job appear as a minimal Art Filter that natively supports frame, then
neutralize the carrier's tone/colour so the picture-mode look survives.

Pros: native frame path; less chain rebuilding.

Cons: must suppress the carrier's effects; must avoid the Art-only setup that
crashed 1.727; needs a job-field comparison to pick a truly neutral carrier.

Risk: Medium–High.

### Direct ISP request synthesis

Build `R = job+0x2c64` directly, set `R+12 = 0x8000`, fill geometry/enable
fields and call `0x603626f6` without the chain.

Pros: avoids the Art builder crash.

Cons: a valid request must be synthesized; hardware register path is
sensitive; no camera validation.

Risk: High.

### Fix the Art Effect property path

Patch normalization at `0x6147d3e8` so it preserves `0xf5d1 = Frame`.

Pros: uses the existing Art Effect mechanism.

Cons: 1.724 proved this alone does not create frame; chain modules are still
missing. Not recommended as the first path.

## Proven vs inferred

Proven:

* failed camera tests 1.722–1.727 and their recorded causes
* picture-mode dispatch `0x603816c5` → builder `0x60395eb9`
* frame installer, callbacks, request layout and downstream consumer
* settings getter `0x602ca6a5(0x3c)` reaches image code

Inferred / unverified:

* `0x60395eb9` uses the same chain slot layout as the Art builder
* picture-mode jobs contain the geometry fields read by `0x6038b70d`
* the shared downstream wrapper runs unchanged for picture-mode jobs
* any visible outcome or safe BIOS-level implementation

## Next probe

Before any patch, disassemble `0x60395eb9` far enough to answer:

1. does it write `job+0x2ae8` / `job+0x2c30`?
2. where is its append/epilogue point?
3. does it populate `job+0x15c0`, `job+264`, `job+274`, `job+276`,
   `job+278`, `job+281` and `job+0x140`?
4. is `0x603626f6` reachable from its request path?

No build, install or camera test until these are answered and a direction is
chosen.
