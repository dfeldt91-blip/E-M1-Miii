# Features to add

The owner's list of firmware features to build, in order. Each moves to the mod builder app once it
works on the camera.

| # | Feature | What it should do | Status |
|---|---|---|---|
| 1 | **Sharpness as a linear scale** | −2 off, −1 25 %, 0 50 %, +1 75 %, +2 100 % (= stock +2). Stock −2 still sharpens. | **Done**: worked on the camera (1.680); in the app as `sharp_scale` |
| 2 | **100 % JPEG quality** | A JPEG compression step better than Super Fine (as close to no compression as the encoder allows). | On hold: scaler found; needs sample JPEGs |
| 3 | **C1–C4 remember photo / video** | Each C slot remembers whether the camera was in photo or video mode when it was saved; turning the dial to it opens that mode with its settings. (Stock already saves the movie settings, but Assign to Custom Mode is unavailable in movie mode and C positions are always photo.) | **Done**: worked on the camera (1.681); in the app as `cmode_video` |
| 4 | **Startup text** | A text the owner sets in the app (e.g. "Hello NAME", or name and phone number), shown when the camera switches on. Baked into the firmware, so it marks the camera as the owner's. | Dropped by the owner (would delay startup). |
| 5 | **Looks in Custom (Caduceus-style)** | Custom shoots a look picked on the computer (hue/saturation/lightness per colour, tone, later grain/split tone); later loaded from the card on the first half-press. | Stage 1 test 1.682 (`tools/patch_looks.py --test1`): colour engine hook |
| 6 | **240 fps slow motion** | High Speed movie runs the sensor in its 240 fps mode (LSSC) instead of 120 fps (MSSC). | 1.697 and 1.698: no change (still 120 fps). Paused: the value that drives the sensor is not found yet |
| 7 | **'_' in Edit Filename** | The Edit Filename character picker also offers '_', so names can start with an underscore. | **Done**: worked on the camera (1.700); in the app as `filename_underscore` |

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
- **5:** the E-M1 III colour engine is the E-P7's: selector `0x603def13..` checks key 11, `add 0x718,a3`,
  COLOR table `0x60529b50`, builder call `0x603def9a` (`cd 8f fd f0 60`) -> `0x603ded29`; output 12 x 24 B
  records at +688 (hue +18, lightness +22), control +976. Port of fishcu's PEN-F `image_parameters`
  (Caduceus HSL). Custom (Picture Mode entry 6) -> pipeline 11 as in the 1.595 repurpose.
  Long list (all looks in Custom's base-mode list, `--all31`, 1.692-1.695): 31/19 entries shown with names,
  but choosing any entry past the sixth restarts the camera (new values 64+, 4/6/8..30; filter pairs
  16+, colour+filter, Monotone filters + other picture types all crash). Dropped; next: SD-card loader.
- **6:** sensor driver `cam.c` states (jump table `0x6160efbc`): 3 HSSC, 4 MSSC, 5 LSSC (240 fps), 6 CLIP,
  7 HSHR, ... Cam command modes (`0x6013cd3c`): 0 HSSC, 1 MSSC, 2 LSSC, 3 CLIP, 4 HSHR, 6 4K, 7 C4K, 11 HQ.
  The exposure movie set-up `0x60437545..` takes the mode from `0x62167f30` and lets the debug override
  `0x60445254` ("exp movie cap 5/6" = LSSC, byte `0x6216c4ac`) replace it. Live view already uses 240 fps
  AE tables (`0x604325b7..`: 0xbf00/01/0a/0b with 240), so LSSC is real on this sensor. 1.697 set mode 2
  where the override would apply and the mode is 1: camera still 120 fps (clip 23.98p, 5x). 1.698 hooks the
  mode builder `0x60436f1e` (end `0x60436f3b`): 1 MSSC -> 2 LSSC and 9 MSPD -> 10 LSPD, in every mode.
  Camera 1.698: still 120 fps (10 s -> about 48 s at 23.98p), so the exposure mode record does not drive the
  sensor in High Speed movie. Next leads: the cam request queue (`0x6013b028`, list type 3 = frame rate at +8
  compared with `0x6016e037`), and module `0x6016....` with its own mode copy `0x620c7860` (set at
  `0x60163e56` from request+4; enum printed at `0x6016ada1`: STILL_HS 0, MOVIE_HS 1, HSSC 2, MSSC 3, LSSC 4,
  CLIP 5, HSHR 6, MSHR 7, 4K 8, C4K 9, PD 10, MSPD 11, LSPD 12, HQ 13, FULL 14, STILL 16; table `0x601f2950`).
- **7:** settings 0x93..0x9a `MODE_FILENAME_CUSTOM_SRGB1..4` / `_ADOBE1..4` (one character each, 0x20 = Off);
  read by `0x602cca00`; name builder `0x6065268f` ('P', month, day, number, then the custom characters, no
  check). Picker list `0x6129554c` (37 records: Off, 0-9, A-Z), descriptors `0x61295740` / `0x61295754`.
  1.699: 38-entry list at `0x600d9000` with '_' (UTF-16 '_' at `0x600411fe`): no '_' on the camera. The
  settings layer has its own list: records `0x604dc29c` + 20 x k -> 37 bytes at `0x604d9178`. 1.700 adds '_'
  there too (38 bytes at `0x600d9200`).
