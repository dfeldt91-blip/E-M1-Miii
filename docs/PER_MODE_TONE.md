# Per-picture-mode Highlight & Shadow control — research

Status: **research + experimental, not camera-tested.** Rated **Idea / Plausible-hard**
(MOD_IDEAS.md C16).

## Goal

Make the "Highlight & Shadow Control" tone-curve adjustment
(`MODE_TONE_CONTROL_HIGH/MIDDLE/LOW`, ids `0x17f`/`0x2b2`/`0x17e`) save and
restore **per picture mode**, instead of one global setting applied on top of
every picture mode.

## What already exists (per-mode tone)

- `MODE_TONE_VIVID` (0x137), `MODE_TONE_NATURAL` (0x138), … and
  `MODE_CUSTOM_TONE_VIVID` (0xbb), … store the **base** tone (Gradation) per
  picture mode.
- `MODE_TONE_CONTROL_HIGH/MIDDLE/LOW` (0x17f/0x2b2/0x17e) is the separate
  H&S adjustment and is **global** today.

So the precedent for per-mode tone storage exists; H&S just isn't wired into it.

## Picture-mode component table

Runtime `0x60469774`, 144 entries × 34 B:
`{u16 sid, u16 comp[16]}` where `0xc80` (= 3200) is the end sentinel.

| sid | components |
|---|---|
| 0x6f (Picture Mode) | 0x6f, 0x6af (FILTER), 0xc80 |
| 0x381 (Dial NEUTRAL) | 0x381, 0xc80 |
| 0x382 (Dial ART) | 0x382, 0x432, 0xc80 |
| 0x384 (Dial COLOR_CREATOR_2) | 0x384, 0x433, 0xc80 |
| 0x3c6 (Dial MONOCHROME_CREATOR) | 0x3c6, 0x434, 0xc80 |
| 0x385 (Dial NON) | 0x385, 0xc80 |

The compound getter (FINDINGS: `0x602cc395`/`0x602cc3b4` reference the table)
fills a struct with the u32 values of each component setting for the active mode.

Tone control (`0x17f`/`0x2b2`/`0x17e`) is **not** a component of any mode
today — that is why it behaves globally.

## Candidate approach (experimental, untested)

Add `0x17f`, `0x2b2`, `0x17e` to the Picture Mode (0x6f) component list:

  {0x6f, 0x6af, 0x17f, 0x2b2, 0x17e, 0xc80}

so the mode bundle includes them. Whether the settings core actually
save/restores them per mode (and whether the menus expose per-mode editing)
is **not yet verified** — the read path (compound get) will include them, but
the write/save path and the UI are separate and unexamined.

## What still needs work

1. Confirm the settings core saves/restores component settings per mode (find
   the mode-switch save path; check whether `0x17e/0x17f/0x2b2` are handled).
2. Per-mode default values (need `MODE_TONE_CONTROL_*` defaults per mode, or
   reuse the global default for all).
3. Menu / SCP UI: editing H&S per mode (the menu currently edits the global).
4. Camera testing (flash + verify H&S differs between picture modes).

## Key addresses (stock 1.6)

| Item | Runtime address |
|---|---|
| Component table (144 × 34 B) | `0x60469774` |
| Picture Mode (0x6f) entry | `0x60469ca2` (components 0x6f, 0x6af, 0xc80) |
| TONE_CONTROL_LOW | id `0x17e` |
| TONE_CONTROL_HIGH | id `0x17f` |
| TONE_CONTROL_MIDDLE | id `0x2b2` |
| TONE (base, per-mode) | ids `0x137`..`0x13b` |
| CUSTOM_TONE (per-mode) | ids `0xbb`..`0xcc` |
| Compound-get refs to table | `0x602cc395`, `0x602cc3b4` |
