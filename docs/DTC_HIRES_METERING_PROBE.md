# Static probe: Digital Teleconverter + High Res, and full-sensor H/S metering

Findings came from static analysis; the DTC restriction bypass was then built,
flashed and camera-tested. Metering work remains static only. All addresses are
runtime addresses in the expanded stock 1.6 image (`B = 0x60021020`).

## 1. Can we get more real resolution by "stacking like High Res, then cropping in"?

### Short answer
- **DTC alone: no.** It is a centre crop + upscale of one normal-resolution frame.
- **High Res alone: yes** (pixel-shift stacking produces a larger real image).
- **High Res + DTC: works on the camera.** The firmware explicitly forbids DTC
  in a set of special drive modes that include the High Res variants. With the
  restriction bypassed, selecting High Res normally and enabling Digital Tele
  produces an image and plays it back with no observed issues. Whether the 2x
  crop runs on the stacked buffer (≈12 MP effective instead of ≈5 MP) still
  needs the output dimensions/EXIF to confirm.

### DTC mechanics (confirmed)
- `0x22` = `MODE_DIGITAL_ZOOM_ONOFF` (validator `0x604dd9f8`, values {0,1}).
- `0x21` = `MODE_DIGITAL_ZOOM` (ratio). `0x602d7822` reads `0x22` and calls
  `setdefault(0x21, 200)` when on / `100` when off. Stock ceiling is 2x.
- Two essentially identical crop builders:
  - `0x603131b4` — full-still path (callers `0x602d720f`, `0x602d72cb`,
    `0x602d7817`, `0x602d7d43`, `0x602d7ef9`, `0x602d8125`, `0x602d8cxx`,
    `0x602d908b`, `0x60922230`, `0x60930894`, ...).
  - `0x60314e6f` — display/thumbnail path; caller `0x60921d99` scales its
    output to 320x240 (`0x140`, `0xf0`).
- Both gate the crop on `rawget(0x22) == 1` (at `0x60313314` / `0x60314efd`)
  **and** `rawget(0x21) > 100` (at `0x603133bf` / `0x60314fb1`).
- Both read `0x22` and `0x21` via `rawget` (`0x602eeec8`), divide the source
  width/height by `0x21/100`, then call `0x6030dc3f` for aspect handling
  (jump table `0x604e8384`, crop table `0x604e80dc`), producing a centred crop
  rectangle.
- Therefore DTC invents no detail: it throws away sensor pixels and enlarges
  the remaining ones.

### Restriction rules that disable DTC (confirmed)
Record `0x60492e24` (sid `0x22`), 10 rules at `0x60488dd0`, all using the
shared force-0 map `0x60470fc0` (`{0->0, 1->0}`):

| rule | condition |
|------|-----------|
| 0 | `0x70f` (`MODE_MULTI_EXPOSURE`) == 1 |
| 1 | `0x3bac` == 1 |
| 2 | `0x18` (`MODE_EXPOSE`) == `0xb9` |
| 3 | `0x18` == `0xba` |
| 4 | `0x18` == `0xbb` |
| 5 | `0x18` == `0xbc` |
| 6 | `0x18` == `0xbd` |
| 7 | `0x2a9` (`MODE_DIGITAL_SHIFT_MENU`) == 1 |
| 8 | `0x597` (`MODE_FISH_EYE_CORRECTION`) == 1 |
| 9 | `0xbc0` == 2 |

The `0x18` values `0xb9..0xbd` occupy indices 119-121 and 123-124 of the
`0x18` validator list at `0x604d8e63`. These are special drive modes; the GUI
option labels live in compressed blob B and were not recovered statically, but
the cluster is exactly the set of modes where DTC is switched off.

### High Res mechanics (partial)
- IDs: `0x2f2` `MODE_PIXSHIFT_SR`, `0x302` `MODE_PIXSHIFT_SR_MENU`,
  `0x68f` `MODE_PIXSHIFT_SR_HANDHELD`, `0x35d` `MODE_QUALITY_PIXSHIFT_SR`,
  `0x35f` `MODE_RAW_PIXSHIFT_SR`.
- Earlier camera test: setting `0x2f2 = 1` directly showed the High Res icon
  but **froze on shot**. `0x2f2` alone is not a usable trigger; the drive-mode
  state machine (including `0x302` and `0x68f`) must be driven coherently.
- `0xcc1` value 18 is a display value only (maps to Single). `0x302` toggles
  High Res visibility in the Drive list.
- High Res flash restriction conditions use the term pair
  `(0x2f2, 1, 0)` and `(0x68f, 1, 0)`, i.e. those two flags together identify
  the High Res drive state.

### Implemented patch point (camera-tested)
1. **Permit DTC in the special drive modes:** in rule record `0x60492e24`,
   the map pointer of rule entries `0x60488dd0 + k*16` for `k = 2..6` is changed
   from `0x60470fc0` (force 0) to the existing identity map `0x60480ee4`
   (`{0->0, 1->1}`). This is the same technique used by
   `tools/patch_hhrs_flash.py` for `MODE_STB_GENERAL` rule 3. The condition
   records and maps are shared, so only the rule-entry pointers change.
   Implemented as `tools/patch_dtc_highres.py IN.BIN OUT.BIN [--version 0x1621]`,
   registered as `dtc_highres` in `builder/mods.json` and `tools/make_modpack.py`.
   Validated against stock 1.6: exactly 15 bytes differ, all in those five
   pointer fields; block checksums and size are preserved.
2. **Raise the crop ratio:** `0x21` is clamped by its validator; the setter at
   `0x602d7822` writes 200. Any higher value would also need validator and
   crop-builder work, and is not required for the 2x High Res idea.
3. **Remaining question:** does `0x603131b4` read the pre-stack single frame or
   the post-stack pixel-shift buffer? The camera test proves the mode
   combination works; only the crop's real resolution is still unmeasured.
   Check the output dimensions:
   - normal 2x DTC on a 20 MP frame: roughly 2592x1944 (5 MP);
   - High Res with a 2x crop after stacking: roughly 4080x3060 (12 MP);
   - High Res frame size with a pre-stack crop/upscale: roughly 8160x6120, but
     with no extra detail from stacking.
4. **Camera test result (build `1.F`):** user confirmed DTC is allowed in High
   Res, an image is created and plays back, and no issues were observed. Output
   dimensions/EXIF have not been reported yet.

### Test build handed to the user
`E1399999_DTCHighRes_v1.BIN` — DTC-only test build, firmware version `0x1f00`
(camera should display `1.F`), SHA-256
`34e64660047f9869d442904bde1cb50f5d617002c37836d0ddd00ac504dbc70e`.
Built from stock 1.6 with:

```
python3 tools/patch_dtc_highres.py OLY_E_139_1600_0000_0000.BIN \
  E1399999_DTCHighRes_v1.BIN --version 0x1f00
```

This build contains only the `dtc_highres` change, not the other mods.

## 2. Full-sensor highlight/shadow metering

### Short answer
The camera's "Highlight" and "Shadow" metering modes are **spot** modes
(`SPOT_HIGHLIGHT` / `SPOT_SHADOW`), not full-frame variants. The firmware does
contain a `force_full_area_metering` control flag and internal `full_expand
spot2/spot3` geometry, so a full-area H/S mode is conceptually reachable, but
the exact write site was not isolated in this pass.

### Confirmed findings
- API `meteringMode` enum (debug dumps at `0x6086bf78` and `0x60876a40`):
  - 0 = `METERING_MODE_SPOT`        (`0x60b4cbc1`)
  - 1 = `METERING_MODE_CENTER`      (`0x60b4cbd6`)
  - 2 = `METERING_MODE_ESP`         (`0x60b4cbed`)
  - 3 = `METERING_MODE_SPOT_HIGHLIGHT` (`0x60b4cc01`)
  - 4 = `METERING_MODE_SPOT_SHADOW`    (`0x60b4cc20`)
- These two dumps only *print* the enum; they are not the source of the value.
- Debug struct dump at `0x615e3e92`:
  - `control + 0x6c` = `lv_info`, `+0x70` = `frame_type`,
    `+0x74` = `metering_type` (label string `0x6162a5c7`).
  - `control_cam + 0x98` = `lens_sync_set_state`,
    `+0x9c` = **`force_full_area_metering`** (label `0x6162a7b3`),
    `+0xa0` = `flk_frame_anti_flicker`.
  - The dump is gated by bits of `0x6216c6cc` (bit 8 = control block,
    bit 32 = control_cam block).
- Related setting IDs: `MODE_AE` `0x1`, `MODE_AE_BASE_ADJUST_ESP/CENTER/SPOT`
  `0x110/0x111/0x112`, `MODE_AE_SPOT` `0x1047`, `MODE_AE_ESP` `0x1048`,
  `EXPOSE_BV*` `0x7bc..0x7bf`, `MODE_EXPOSE_CONTROL_HIGHLIGHT` `0xfdc`,
  `MODE_EXPOSE_CONTROL_SHADOW` `0xfdd`.
- Debug traces `[exp]:full_expand spot2 hs|vs:` / `hw|vw:` (strings
  `0x6054ba08`, `0x6054ba27`, `0x6054ba46`, `0x6054ba65`; code `0x6042cb86`
  etc.) show the exposure engine already expands spot2/spot3 areas into
  full-frame horizontal/vertical geometry. This is the strongest lead that a
  full-area H/S path exists internally.
- Metering calculation traces: `stb_calc_metering_expose_*` at
  `0x601f6a65..0x601f6d00`; `mode_ae_base_adjust_spot(8.8)` at `0x601fa2e8`.

### What remains to find
1. The writer of `control_cam + 0x9c` (`force_full_area_metering`). A raw scan
   for `MOV ..,(156,aN)` finds many generic struct writes; the metering-specific
   one must be isolated by recursive disassembly from the `stb_calc_metering_expose_*`
   and `full_expand` functions, following the struct pointer rather than the
   raw offset.
2. The source of `meteringMode` values 3/4. The API dump reads a parameter
   struct field; the producer is in the SCP/property layer, not yet traced.
   Candidate lever: force the API enum to 3/4 while the base adjust is ESP
   (`0x110`) and hold `force_full_area_metering` on.
3. The menu/validator records for selecting such a mode. Validator-list edits
   alone are known *not* to drive menus/SCP on this body (see `patch_looks.py`
   notes); the GUI and runtime paths must be traced separately.

### Feasibility assessment
Metering remains unproven: if `force_full_area_metering` can be set while the
highlight/shadow spot type is active, the desired behaviour follows directly
from the existing metering engine. Risk: the flag may be recomputed every frame
from the metering mode, in which case the writer (not the mode value) must be
patched. No metering patch has been implemented.

## 3. Recommended next steps
1. Report the dimensions/EXIF from the `1.F` High Res + DTC image. That resolves
   whether the crop ran on the stacked buffer; the mode combination itself is
   already confirmed working on the camera.
2. Recursively disassemble from `0x6042caf0` and the
   `stb_calc_metering_expose_*` entry points, tracking the control/control_cam
   struct pointers to the exact `+0x74` / `+0x9c` writers.
3. Building, flashing, committing and releasing still require an explicit
   request.
