# E-M1 Mark III firmware mod ideas (firmware 1.6)

The complete list of mods: what's done, what's been tried, and what could still be built.
Each idea is rated by how likely it is to work and how much work it is.
The ratings are estimates from what we know of the firmware so far. A rating only becomes a fact once the camera has been tested.

**Ratings**
- **Likely**: a single limit, value or table we can change; few test flashes.
- **Plausible**: the firmware has the parts; needs a hook or new code and several test rounds.
- **Idea**: worth looking at, but the mechanism isn't found yet.
- **Unlikely**: probably a hardware limit (sensor, encoder, memory, heat). A test would most likely crash or give bad files.
- **No**: not possible, or not worth it.

## Done: in the app, camera-tested
| Mod | App id |
|---|---|
| Panorama aspect 65:24 | `panorama` |
| Multiple Exposure with 3 and 4 frames | `multiexp` |
| Focus stacking with any lens | `stack_any_lens` |
| Key Line II in black and white | `keyline_mono` |
| More arrow-key functions | `arrow_keys` |
| Flash in handheld High Res | `hhrs_flash` |
| Art filters in High Res | `hires_art` |
| SCP button cell opens the main menu | `scp_menu` |
| Sharpness as a linear scale (−2 = off … +2 = stock +2) | `sharp_scale` |
| Custom Modes C1–C4 save and open video | `cmode_video` |
| Underscore `_` in Edit Filename | `filename_underscore` |
| Frame art effect: plain white border, also in Panorama | `white_frame`, `white_frame_panorama` |
| XPAN icon for Panorama on the SCP | `xpan_icon` |
| Underwater picture mode in black and white | `underwater_mono` |
| Six film looks in Custom, picked in the app (Caduceus recipes) | `custom_looks` |

## Built, not yet camera-tested
- **Looks loaded from the SD card** (`custom_looks` → "Load looks from SD card"; test firmware 1.696). On the first half-press, the camera reads `EM1MOD\LOOKS.BIN`, so you can change the six looks without reflashing.

## Tried and dropped
- **All 31 looks in Custom's list.** Every entry past the sixth restarts the camera.
- **Startup text.** Dropped by you, because it would slow startup.
- **MENU as an assignable button.** It didn't work.

## Video
| # | Idea | Rating | Notes |
|---|---|---|---|
| V1 | **240 fps slow motion** (lower resolution, e.g. 720p or smaller) | **Plausible** | The firmware lists a sensor mode `MOVIE_LSSC (240fps)` next to `MSSC (120fps)`. It also has image buffers named `MJPEG_240_CHUNK` / `MJPEG_240_YC` and a 240 fps lens-sync state. That points to an unused 240 fps high-speed movie path, probably shared code from Olympus's Tough cameras. 720p at 240 fps is about the same pixel rate as stock 1080p at 120 fps, so it's within the encoder's known limit. First test: point the High Speed movie setting at the 240 fps sensor mode. |
| V2 | **1080p slow motion above 120 fps** (e.g. 1080p 180 or 240) | **Unlikely** | Above what the encoder is known to handle (stock 1080p 120 already matches 4K 30 in pixel rate). |
| V3 | **Slow motion with sound / longer clips** | **Idea** | Look for the high-speed clip length limit and audio flag. |
| V4 | **C4K at 25p and 30p** (stock: 24p only) | **Plausible** | Same 30 fps sensor mode as 4K 30p, with about 7 % more pixels. |
| V5 | **4K 60p** | **Unlikely** | The full-resolution sensor mode is defined as 30 fps; 4K 60 needs about twice the sensor read-out and encoder throughput. |
| V6 | **Higher 4K / 1080p bitrate**, or 4K bitrate choices (SF/F/N) | **Plausible** | The movie writer has bitrate fields (`ulBitRate`, `ulMaxBitRate`, `BITRATE_OVER`). Limited by card speed and encoder. |
| V7 | **Recording limit raised** (29 min / per-clip cap) to many hours | **Likely** | Caduceus did this on the E-P7. The `1740` s (29 min) constant appears several times here. |
| V8 | **Vertical video rotation flag** (portrait clips play upright) | **Plausible** | Camera-tested on the E-P7. |
| V9 | **Film looks / Custom look in video** | **Plausible–hard** | Movie uses a separate colour path. |
| V10 | **Picture modes other than Flat with OM-Log** / different log curve | **Idea** | |
| V11 | **10-bit internal recording** | **No** | The internal encoder is 8-bit. |
| V12 | **RAW video, 6K, open gate** | **No** | Hardware. |
| V13 | **Zebras at more levels, false colour** | **Idea** | Zebra levels may be a table; false colour would be new drawing code. |
| V14 | **Peaking: more colours or a stronger level** | **Plausible** | Peaking colours are a small table (none, black, white, red, yellow). |
| V15 | **Timecode presets / frame rate options for timecode** | **Idea** | |
| V16 | **Audio: higher level range, limiter options** | **Idea** | |
| V17 | **Movie digital stabilisation with less crop** | **Idea** | |
| V18 | **Movie tally / red frame while recording** | **Plausible** | Drawing code in the GUI blob. |

## Stills and shooting
| # | Idea | Rating | Notes |
|---|---|---|---|
| S1 | **100 % JPEG quality** (beyond Super Fine) | **Plausible** | Quantisation scaler found (`0x603e4cb8`). On hold until you send sample JPEGs. |
| S2 | **Real 21:9 and 65:24 crops with framing** (not just the aspect) | **Plausible** | 65:24 done; 21:9 via the hidden 6:5 aspect slot. |
| S3 | **Framing lines / thirds grid for 65:24 and 21:9** | **Plausible** | |
| S4 | **Bulb / Live Time beyond 30 min; longer Live Composite** | **Likely** | `bulbtimelimit` and `LiveCompLimitMinute` are named settings; probably one limit each. |
| S5 | **Live ND above ND32** | **Plausible** | Averaging more frames; check the limit and memory. |
| S6 | **Pro Capture: more pre-shot frames** | **Plausible–hard** | Memory-limited. |
| S7 | **More bracketing frames / finer steps** (AE, WB, FL, ART, focus) | **Likely** | Mostly limit tables. |
| S8 | **Interval timer: more frames, shorter or longer intervals** | **Likely** | |
| S9 | **Minimum shutter speed in P/A** (ISO-Auto lowest S/S, finer) | **Plausible** | |
| S10 | **ISO-Auto upper limit above 6400 / extended ISO in ISO-Auto** | **Plausible** | |
| S11 | **ISO 64 / Low with Auto** | **Idea** | |
| S12 | **Higher-frame High Res modes** (e.g. handheld High Res faster) | **Idea** | |
| S13 | **High Res with more lenses / settings unlocked** | **Plausible** | We already unlocked flash and art filters. |
| S14 | **Starry Sky AF with more lenses / modes** | **Idea** | |
| S15 | **Focus bracketing finer step sizes** | **Plausible** | |
| S16 | **Silent shutter at faster speeds, sequential high in silent** | **Idea** | Limited by sensor read-out. |
| S17 | **Faster sequential shooting** | **Unlikely** | Mechanical shutter and buffer limits. |
| S18 | **Electronic shutter sound** | **Plausible–hard** | Speaker playback exists for other sounds. |
| S19 | **Anti-shock delays below 1/8 s** | **Likely** | |
| S20 | **Self-timer: custom delays, more repeats** | **Likely** | |
| S21 | **Keystone / fisheye correction options** | **Idea** | |
| S22 | **Multiple Exposure with more than 4 frames** | **Plausible** | 3 and 4 already done. |
| S23 | **Digital teleconverter at other factors (1.4×, 3×)** | **Idea** | |
| S24 | **Subject detection: more subjects** (e.g. bird, animal) | **Unlikely** | The E-M1 III has no trained subject detection models. |
| S25 | **Face/eye AF in more modes** | **Idea** | |
| S26 | **C-AF tracking sensitivity −5..+5** | **Plausible** | |

## Picture and colour
| # | Idea | Rating | Notes |
|---|---|---|---|
| C1 | **Looks from the SD card** | **Built** | Awaiting your test (see above). |
| C2 | **More picture modes repurposed as fixed looks** (e.g. e-Portrait as a second look slot) | **Likely** | Same method as Underwater and Custom. |
| C3 | **Mono film presets** (Tri-X, HP5, Acros, sepia, selenium) | **Plausible** | Fixed Monochrome Profile settings. |
| C4 | **Grain on colour looks** | **Plausible** | Port the mono grain job to the colour path. |
| C5 | **Split toning** | **Plausible** | Bends the tone tables. |
| C6 | **Blacks / Whites** (tone curve ends) | **Plausible** | |
| C7 | **Colour mix / channel matrix per look** (the "Kodachrome" factor) | **Plausible–hard** | |
| C8 | **Halation, bloom, clarity** | **Hard** | Extra image-engine passes. |
| C9 | **Noise reduction per picture mode, or NR fully off** | **Plausible** | |
| C10 | **Lens shading correction off per mode** | **Plausible** | |
| C11 | **Look name written into EXIF** | **Plausible** | |
| C12 | **Wider Contrast / Saturation / Gradation ranges** | **Plausible** | Same approach as the sharpness scale. |
| C13 | **More white-balance presets / finer Kelvin** | **Plausible** | |
| C14 | **Art filters: new variations** (e.g. more frame/effect options) | **Plausible** | White frame is an example. |
| C15 | **On-camera look editor** (HSL screens like the E-P7 / PEN-F) | **No / very hard** | The editor screens don't exist in this firmware; it would mean writing a new GUI. |

## Buttons, menus and display
| # | Idea | Rating | Notes |
|---|---|---|---|
| B1 | **More button functions** (S-AF/C-AF toggle, Sequential H/L toggle, Picture Mode list, Level, HDR) | **Plausible** | Each is its own trial. |
| B2 | **Picture Mode list on one button** | **Plausible** | |
| B3 | **Fn lever positions remember drive and AF modes** | **Idea** | |
| B4 | **Re-label or re-order SCP cells** | **Plausible** | Done once for the Menu cell. |
| B5 | **Larger My Menu / custom menu tab** | **Plausible** | |
| B6 | **Hide menu items you never use** | **Plausible** | |
| B7 | **Lens L-Fn button functions** | **Idea** | |
| B8 | **Panasonic/Leica lens aperture ring support** | **Idea** | No aperture-ring code found in this firmware. |
| B9 | **LCD colour fix** (rear screen pink cast) | **Plausible** | Display only; photos and video unchanged. |
| B10 | **EVF/LCD brightness range or colour temperature** | **Idea** | |
| B11 | **Mod version on the firmware screen** | **Plausible** | |
| B12 | **Owner name in the camera** (e.g. on the info screen, not at startup) | **Plausible** | Your copyright name already goes into EXIF; this would show it on a menu or info screen, so startup isn't slowed. |
| B13 | **Histogram options** (RGB histogram, larger) | **Idea** | |
| B14 | **Level gauge on more displays** | **Idea** | |
| B15 | **Faster power-on** | **Unlikely** | |

## Connectivity and files
| # | Idea | Rating | Notes |
|---|---|---|---|
| F1 | **Custom file naming / folder names** | **Plausible** | |
| F2 | **Settings backup to the card** (stock has My Set backup over Wi-Fi) | **Idea** | The Wi-Fi My Set backup code exists. |
| F3 | **More Wi-Fi remote features** (bulb from the phone, etc.) | **Idea** | |
| F4 | **USB webcam at higher resolution** | **Idea** | |

## Next candidates
If you want quick wins, I'd start with:
1. **240 fps slow motion (V1)**. The firmware already has a 240 fps sensor mode.
2. **Recording limit (V7)**, **Bulb / Live Composite limits (S4)** and **interval / bracketing limits (S7, S8)**. These are mostly single values.
3. **C4K 25/30p (V4)**.
4. **Another picture mode as a second look slot (C2)**, plus **mono film presets (C3)**.
