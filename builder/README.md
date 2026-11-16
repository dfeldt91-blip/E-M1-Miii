# E-M1 Mark III mod builder

A small window app that:

1. downloads the official E-M1 Mark III firmware **1.6** from OM Digital Solutions' update server
   (the same request OM's updater makes) and checks its SHA-256,
2. lets you tick the mods you want,
3. writes `E1399999.BIN` for the camera's card updater.

No OM firmware is stored in this repository. The mods are edit lists (`mods.json`) that are applied to
your own download.

**Unofficial. Flashing modified firmware is at your own risk.**

## Mac app

GitHub builds a ready-to-run Mac app (workflow `.github/workflows/mac-app.yml`), with
Python, tkinter and lz4 inside, so nothing else needs installing:

1. Download the newest release from the repository's **Releases** page
   (https://github.com/dfeldt91-blip/E-M1-Miii/releases/latest):
   `E-M1-III-Mod-Builder-mac-apple-silicon.zip` (M1/M2/M3/M4 Macs) or `…-mac-intel.zip`.
2. Unzip it (double-click). Move **E-M1 III Mod Builder.app** to Applications if you like.
3. The app is not signed by Apple, so the first time: right-click (or Control-click) the app → **Open** →
   **Open**. If macOS still refuses (newer macOS versions), open **System Settings → Privacy & Security**,
   scroll down and click **Open Anyway**. Or run once in Terminal:
   `xattr -dr com.apple.quarantine "/Applications/E-M1 III Mod Builder.app"`

After a build, Finder opens with `E1399999.BIN` selected.

To build the app yourself on a Mac: `bash builder/mac/build_app.sh` (needs Python 3 from python.org).

## Windows app

From the same release page, download `E-M1-III-Mod-Builder-windows.zip`, unzip it and run
`E-M1 III Mod Builder.exe`. It is not signed, so Windows SmartScreen may say it "protected your PC":
click **More info**, then **Run anyway**. It works like the Mac app (`builder/windows/build_exe.sh`
builds it).

## Run it as a script

Needs Python 3.8 or newer, tkinter (included with the python.org installers for Windows and macOS),
and the `lz4` and `pillow` packages (Pillow draws the frame images):

```bash
python3 -m pip install lz4 pillow
```

```bash
python3 builder/em1iii_builder.py
```

Without a window:

```bash
python3 builder/em1iii_builder.py --list
```

```bash
python3 builder/em1iii_builder.py --cli --mods panorama,hhrs_flash --out ~/E-M1III-firmware
```

`--mods all` or `--mods none` (stock 1.6, for going back to stock).
`--stock FILE` uses a file you already downloaded; it must be the official 1.6 file.

The download and your settings are kept in `~/.em1iii-mod-builder/`.

## Mods

| id | Mod | Camera status |
|---|---|---|
| `panorama` | Panorama aspect 65:24 (replaces 7:6) | worked (1.5 build) |
| `multiexp` | Multiple Exposure with 3 and 4 frames | worked (1.5 build) |
| `stack_any_lens` | In-camera focus stacking with any lens | worked (1.5 build) |
| `stack16` | Focus stacking up to 16 frames | not tested |
| `keyline_mono` | Key Line II in black and white | worked (1.5 build) |
| `arrow_keys` | More arrow-key functions | not tested |
| `hhrs_flash` | Flash in handheld High Res | worked (1.5 build) |
| `hires_art` | Art filters in High Res (colour/tone only) | worked (1.5 build) |
| `scp_menu` | SCP bottom-right cell (Button Function) opens the main menu, titled "Menu" | worked (1.6, 1.679) |
| `sharp_scale` | Sharpness −2 off, −1 25 %, 0 50 %, +1 75 %, +2 100 % (stock +2) | worked (1.6, 1.680) |
| `cmode_video` | Assign to Custom Mode works in movie mode; that C slot then opens in video | worked (1.6, 1.681) |
| `white_frame` | Frame art effect as a plain white border; width setting (% of the short side) | worked (1.6, 1.664) |
| `white_frame_panorama` | White frame in Panorama (needs `panorama` and `white_frame`) | worked (1.6, 1.665) |
| `underwater_mono` | Underwater picture mode in black and white; tint setting | worked (1.6, 1.674) |
| `custom_looks` | Custom = six Caduceus film looks (pick them here); Custom's base-mode list on the camera shows the look names | worked (1.6, 1.691); option *Load looks from SD card*: Custom shows Look 1-6, first half-press reads `EM1MOD/LOOKS.BIN` (button *Write card file*) - not camera-tested (1.696) |
| `xpan_icon` | "XPAN" icons for Panorama on the SCP (needs `panorama`) | 1.666: XPAN in the option lists; main SCP cell shows a 17:9 label |

All mods were developed and tested on a 1.5-based file. For 1.6 each one was checked byte by byte:
every changed byte, the code and data around it, and every firmware address the new code uses are
the same in 1.5 and 1.6. The exception is Panorama, where four addresses moved in 1.6 and were adjusted
(`adapt_16` in `tools/patch_aspect.py`). Nothing has run on a camera with 1.6 yet.

## Install on the camera

1. Charge the battery fully.
2. Copy `E1399999.BIN` to the SD card as `DCOLYMP/E1399999.BIN`. `DCOLYMP` is a folder at the top level
   of the card, next to `DCIM`. It must be the only `E139….BIN` file on the card.
3. With the camera off, hold **OK** and switch it on to start the card update. Wait until the light
   stops (it may blink or simply go out), then switch the camera off and on.
4. Delete `DCOLYMP/E1399999.BIN` from the card afterwards.

To go back to stock, build with no mods.

## Credits

The film looks in Custom (`custom_looks`) and the colour-engine research behind them come from
**Caduceus** by cakelesscoder, Apache License 2.0: https://github.com/cakelesscoder/caduceus-ep7
(recipes from its `sim/recipes/library_v2.json` and `library_v3.json`; the hue/lightness method from
fishcu's PEN-F HSL work, https://github.com/fishcu/oly_fw_analysis, which Caduceus builds on).

## For developers

`mods.json` is generated from the patch tools in `tools/`:

```bash
MN10300_BIN=/path/to/mn10300-elf/bin python3 tools/make_modpack.py OLY_E_139_1600_0000_0000.BIN builder/mods.json
```

It runs each tool on the official file on its own and records the changed bytes: block 0 at runtime
addresses (both olycompress blobs expanded), other blocks at plain offsets. Each mod also stores a
SHA-256 of the stock bytes under its edits. The generator fails if two mods change the same byte, or if
the merged edit lists differ from running all tools one after another. `tools/modcore.py` holds the
download, apply and rebuild code that the app uses.
