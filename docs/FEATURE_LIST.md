# Features to add

The owner's list of firmware features to build, in order. Each moves to the mod builder app once it
works on the camera.

| # | Feature | What it should do | Status |
|---|---|---|---|
| 1 | **Sharpness as a linear scale** | −2 off, −1 25 %, 0 50 %, +1 75 %, +2 100 % (= stock +2). Stock −2 still sharpens. | **Done**: worked on the camera (1.680); in the app as `sharp_scale` |
| 2 | **100 % JPEG quality** | A JPEG compression step better than Super Fine (as close to no compression as the encoder allows). | On hold: scaler found; needs sample JPEGs |
| 3 | **C1–C4 remember photo / video** | Each C slot remembers whether the camera was in photo or video mode when it was saved; turning the dial to it opens that mode with its settings. (Stock already saves the movie settings, but Assign to Custom Mode is unavailable in movie mode and C positions are always photo.) | **Done**: worked on the camera (1.681); in the app as `cmode_video` |
| 4 | **Startup text** | A text the owner sets in the app (e.g. "Hello NAME", or name and phone number), shown when the camera switches on. Baked into the firmware, so it marks the camera as the owner's. | Dropped by the owner (would delay startup). |

## Leads

- **1:** settings `MODE_SHARP` and the per-mode `MODE_SHARP_VIVID/NATURAL/FLAT/MONOCHROME/SOFT/I_FINISH`
  (block 2 names). The image parameter builder (`0x60418d51..`, docs/FINDINGS.md) turns them into
  the sharpening strength; −2 needs to map to zero there. Caduceus E-P7 docs/SHARPENING_OFF.md did
  the same on the E-P7.
- **2:** quantisation scaler `0x603e4cb8..0x603e4d1d` (same as the E-P7's `0x603b6120`, caduceus
  docs/JPEG_QUALITY.md): `Sf` = job +20 (u16, `usJpegSf`; 0 -> caller default in d2), cached at
  `0xa26e00ec`; for luma and chroma, entry = min(255, (base x Sf + 128) >> 8), no lower clamp, into
  a stack table that then goes to the JPEG engine (`0x99901200..`) and the DQT header
  (`0x60328eb4`, template `ff db 00 c5` at `0x604e94d0`). Base tables (pointers at `0x6053eb3c`):
  luma `0x6053eb4c`, chroma `0x6053eb8c` = the JPEG Annex K Q50 tables, transposed. All-1 tables
  (true 100 %) need a min-1 clamp (base 10..121: no single Sf gives all 1s). The job also has
  `ulJpegTargetSize` / `ulJpegCodeSize` (+12/+16), so a rate control probably raises Sf for detailed
  scenes; the E-P7 measured Super Fine at Sf 0-3 (all 1s) for most files, 5-11 for detailed ones.
  Settings: compression per quality slot `MODE_SHQ_Q/HQ_Q/SQ1_Q/SQ2_Q` (0xb-0xe, values 0..2); UI
  strings SF/F/N/B. Open: where Sf is chosen per compression, and the rate control.
- **3:** solved by `tools/patch_cmode_video.py`: the menu's changeable check `0x608d522f` greyed
  out Reset / Custom Modes (0xd1d), Assign (0x13df) and Recall (0x13e0) in movie mode; with it
  answering yes, the stock save/recall keeps the movie exposure mode (camera 1.681).
- **4 (dropped):** stock has Copyright Settings (`MODE_COPYRIGHT_ONOFF`, artist/copyright names in EXIF).
  The startup text needs a string the app writes into the firmware and a place to draw it at power-on.
  Lead: an API module `LogoScreen` (`drawImage`, `existImage`, `regist`, `unregist`; name table
  `0x602633cc`, API source `OlyApiLogoScreen.cpp`, getter `0x608a16b0`, vtable `0x60b69df8`,
  wrappers around `0x608a1646` calling `0x608c3d30` / `0x608c3d3c`) and callback names
  `CBC_DRAW_OPENING_IMAGE` / `CBS_END_LOGO_IMAGE`: a power-on opening image may exist. If it does,
  the app can render the owner's text into that image (Pillow). Fallback: a text message posted
  once at power-on, with a replaced message string. Findings: the OpnScr functions are only
  reached from the debug command shell (`sdk api ... drawImage`), not at power-on; timed GUI
  messages go through `0x60ed18cd` (e.g. 0xb37 at `0x60eb11fc`).
