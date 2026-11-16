# Features to add

The owner's list of firmware features to build, in order. Each moves to the mod builder app once it
works on the camera.

| # | Feature | What it should do | Status |
|---|---|---|---|
| 1 | **Sharpness as a linear scale** | −2 off, −1 25 %, 0 50 %, +1 75 %, +2 100 % (= stock +2). Stock −2 still sharpens. | **Done**: worked on the camera (1.680); in the app as `sharp_scale` |
| 2 | **100 % JPEG quality** | A JPEG compression step better than Super Fine (as close to no compression as the encoder allows). | Not started |
| 3 | **Video settings in C1–C4** | Saving a Custom Mode (C1–C4) also keeps the movie settings, so recalling it brings them back. | Not started |
| 4 | **Startup text** | A text the owner sets in the app (e.g. "Hello NAME", or name and phone number), shown when the camera switches on. Baked into the firmware, so it marks the camera as the owner's. | Not started |

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
- **3:** Custom Mode save/recall (Myset) copies a list of setting ids; the movie settings are
  probably left out of that list. Find the list and add them.
- **4:** stock has Copyright Settings (`MODE_COPYRIGHT_ONOFF`, artist/copyright names in EXIF).
  The startup text needs a string the app writes into the firmware and a place to draw it at power-on.
