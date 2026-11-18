# On-camera 12-sector HSL editor: implementation plan (E-M1 Mark III 1.6)

Goal: edit hue, saturation and lightness for the 12 colour sectors on the camera, applied to the
Custom picture mode (photos and live view). This is the PEN-F "Color Profile Control" editor that
fishcu and Caduceus (E-P7) extended. Credit: Caduceus and fishcu, whose E-P7/PEN-F work this follows.

## What already exists

| Part | State | Where |
|---|---|---|
| Colour engine: per-sector hue / lightness (builder records) and saturation (request +0x718) | Works (1.682-1.690) | tools/patch_looks.py |
| Custom (Picture Mode entry 6) routed to pipeline 11 (Color Profile) | Works (1.595) | tools/patch_picture_modes.py --repurpose |
| Storage for 36 values | Present, unused | hidden settings, see below |
| Live-view preview request for Color Profile (kind 5) | Present, unused | 0x609ec110 / 0x603085c6 |
| Editor screen for Color Profile | **Missing** | none found (FINDINGS.md "Editor search"); state 69 is not it (1.712) |

## Findings (this round)

- 0x609ec110 is not a wheel GUI. It is slot 1044 of a live-view class whose vtable has 12 copies
  (0x60bdad8c...). The class's message switch 0x609b2055 (hash table 0x60bc91b8, key = id - 0x119)
  calls it for message 0x264 (handler 0x609b39cc, payload at message +32). The message object is
  built by 0x6081b291 (12 x u16 payload). Senders: 0x60842ef4, 0x609b09d3.
- The packed payload goes to 0x603085c6(kind, payload), which handles kinds 1..11 through the table
  0x604e7db8 and posts message 0x1b7c to the image pipeline: kind 1 Color Creator (0x60302de5),
  2-4 Partial Color (0x60302eb4), **5 Color Profile (0x60302f74, 13 bytes: cursor + 12 values)**,
  6.. Monochrome Profile. So the preview path for a 12-sector edit still exists in the firmware.
- The classic Color Creator screen (GUI state 53) is the only working two-dial colour editor. Its
  class (methods 0x60e02280, 0x60e022b6, 0x60e02302, 0x60e02453, handler table 0x6027e4a0) has two
  item objects at +28 (hue, 0x267, 30 positions on the colour ring) and +32 (saturation, 0x268,
  8 steps). The method 0x60e02302 reads both settings through the facade (vtable +152) and compares
  them with the items (vtable +4 index, +16 value) to detect a change. The screen is opened by
  PostEventToCA(33, 48) (SCP INFO on Picture Mode 21 at 0x60e7e640, Multi Function, ...).
  Hue-item binding: 0x60e6f81a / 0x60e6f932 call 0x60e7062d(8, 0x267).

## Storage: the hidden Color Profile settings

Three sets of 12 sector values already exist, are saved with the other settings and are not used
by any menu (the PEN-F had 3 Color Profile slots):

| Axis | Settings | Range used |
|---|---|---|
| Saturation | 0x399..0x3a4 (SET1_1..12) | -5..+5 (stock range) |
| Hue | 0x3a5..0x3b0 (SET2) | -7..+7 (x1000 in the builder) |
| Lightness | 0x3b1..0x3bc (SET3) | -7..+7 (fishcu's lightness table) |
| Cursor (selected sector) | 0x43c | 0..11 |

Getter 0x602ca6a5 / 0x602ca8c5, setter 0x602ca855(sid d0, value d1). Range checks for these ids
are not mapped yet (step 1 tests them).

## Plan

1. **Engine reads the settings (build 1.713).** The patch_looks stub reads the 36 settings instead
   of a fixed look table when Custom is in "HSL" mode. A temporary seed (one sector set to an
   obvious value on first boot) shows that writes stick, that the range allows +-7, and that the
   values survive a power cycle. Camera test: Custom shows the seeded shift; it is still there after
   the battery is pulled.
2. **Editor entry.** SCP INFO on Custom (Picture Mode 6) posts (33, 48) and sets a RAM flag
   "HSL mode" (new branch in the SCP INFO handler 0x60e7e4e1, next to the 1.712 probe site). Other
   entries to the Color Creator screen clear the flag, so Color Creator itself is unchanged.
3. **Editor (Color Creator screen in HSL mode).**
   - Front dial (hue ring, 30 positions) picks the sector: position p -> sector round(p * 12 / 30)
     in the engine's order (yellow, orange, ..., yellow-green). The ring shows the colour being
     edited, which is the natural cue.
   - Rear dial (saturation bar) sets the value of the current axis. The stock bar has 8 steps
     (-4..+3); first version uses that range, a later one rescales the label table
     (0x611d2da0 / 0x611d2de0, drawn by 0x60e08ee0) to -7..+7.
   - INFO (or the button Caduceus uses, Delete) cycles S -> H -> L; the screen title shows the axis.
   - When the sector changes, the bar is reloaded from the stored value of that sector/axis.
   - OK writes the edited values to 0x399..0x3bc instead of 0x267/0x268 (hook the commit in
     0x60e02302's caller); Back discards.
   - Hooks: redirect the two items' setting ids (0x267 -> current sector, 0x268 -> current value)
     while the flag is set, at the binding call 0x60e7062d and the facade reads in 0x60e02302.
4. **Live preview.** After each change, send a kind-5 preview request (message 0x264 path) or
   re-run the builder; the engine stub already runs on live view, so the preview may be free once
   the stub reads the settings. Kind 1 (stock Color Creator preview) must be suppressed in HSL mode.
5. **Desktop app.** A "HSL editor" mod in tools/make_modpack.py; the SD-card LOOKS.BIN path and the
   on-camera values coexist (the card look seeds the 36 settings).

Open questions for the camera: setting ranges (step 1); whether the Color Creator screen can be
opened while Picture Mode is Custom (the screen may switch Picture Mode to Color Creator on OK; the
commit hook covers that).

## Status

- 1.713 (step 1, tools/patch_hsl.py --seed, on 1.709): engine reads the 36 settings; SCP INFO on
  Color Creator writes red hue +7, blue lightness +7, green saturation -5. Awaiting camera test.

## Risks

- Every step needs a camera round; the screen hijack needs 3-5 rounds.
- If the item objects clamp to their own ranges (30 / 8 positions), the -7..+7 range needs the
  label/limit tables changed, not just the setting ids.
- Multiple exposure work is dropped; HSL builds start from 1.709 (before the 1.710/1.711 hooks).
