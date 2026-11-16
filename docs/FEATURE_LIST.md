# Features to add

The owner's list of firmware features to build, in order. Each moves to the mod builder app once it
works on the camera.

| # | Feature | What it should do | Status |
|---|---|---|---|
| 1 | **Sharpness as a linear scale** | −2 off, −1 25 %, 0 50 %, +1 75 %, +2 100 % (= stock +2). Stock −2 still sharpens. | Test 1.680 built (`tools/patch_sharp_off.py`), not camera-tested |
| 2 | **100 % JPEG quality** | A JPEG compression step better than Super Fine (as close to no compression as the encoder allows). | Not started |
| 3 | **Video settings in C1–C4** | Saving a Custom Mode (C1–C4) also keeps the movie settings, so recalling it brings them back. | Not started |
| 4 | **Startup text** | A text the owner sets in the app (e.g. "Hello NAME", or name and phone number), shown when the camera switches on. Baked into the firmware, so it marks the camera as the owner's. | Not started |

## Leads

- **1:** settings `MODE_SHARP` and the per-mode `MODE_SHARP_VIVID/NATURAL/FLAT/MONOCHROME/SOFT/I_FINISH`
  (block 2 names). The image parameter builder (`0x60418d51..`, docs/FINDINGS.md) turns them into
  the sharpening strength; −2 needs to map to zero there. Caduceus E-P7 docs/SHARPENING_OFF.md did
  the same on the E-P7.
- **2:** `MODE_QUALITY`, `MODE_QUALITY_SET1..4_P` (the four quality presets: size + compression).
  Find the compression table (SF/F/N/B → quantisation scale) and add or change a step.
- **3:** Custom Mode save/recall (Myset) copies a list of setting ids; the movie settings are
  probably left out of that list. Find the list and add them.
- **4:** stock has Copyright Settings (`MODE_COPYRIGHT_ONOFF`, artist/copyright names in EXIF).
  The startup text needs a string the app writes into the firmware and a place to draw it at power-on.
