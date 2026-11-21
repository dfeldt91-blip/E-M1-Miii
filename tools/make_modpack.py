#!/usr/bin/env python3
"""Regenerate builder/mods.json from the patch tools (developer step, not needed by users).

  MN10300_BIN=.../bin python3 tools/make_modpack.py OLY_E_139_1600_0000_0000.BIN [builder/mods.json]

Runs every patch tool below on the official 1.6 file on its own, expands both olycompress blobs of the
result and records the changed bytes as {runtime address, new bytes}. Only new bytes are stored, plus
a SHA-256 of the stock bytes under each mod's edits (so the builder can tell if the base is wrong
without the pack containing OM's firmware). Fails if two mods touch the same byte, or if all mods
applied together differ from running the tools one after another.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import olyfw  # noqa: E402
import modcore  # noqa: E402

# id, tool, extra args, title, description, camera status, requires
MODS = [
    ("panorama", "patch_aspect.py", ["--stage18"], "Panorama aspect (65:24)",
     "Replaces the 7:6 aspect with 65:24 'Panorama': menu, live-view frame, AF areas, ORF frame.",
     "Worked on the camera (1.5 build).", []),
    ("multiexp", "patch_multiexp.py", ["--no-rebuild", "--overlay"], "Multiple Exposure: 3 and 4 frames",
     "Multiple Exposure accepts 3 or 4 frames. The live overlay should stay visible after every shot except the last, so you can compose the next frame on the accumulated image.",
     "3 and 4 frames worked on the camera (1.5 build); overlay after shots 2 and 3: test 1.746, awaiting camera result.", []),
    ("stack_any_lens", "patch_stack_any_lens.py", [], "Focus stacking with any lens",
     "Removes the lens check for in-camera focus stacking (the change in E1399999_Focus_Stack.BIN).",
     "Worked on the camera (1.5 build).", []),
    ("keyline_mono", "patch_keyline_mono.py", [], "Key Line II in black and white",
     "Art filter Key Line II gets a grey (monochrome) toning instead of colour.",
     "Worked on the camera (1.5 build).", []),
    ("arrow_keys", "patch_buttons.py", [], "More arrow-key functions",
     "The arrow keys can be assigned 25 functions for stills and 15 for movies.",
     "Not tested on the camera yet.", []),
    ("hhrs_flash", "patch_hhrs_flash.py", [], "Flash in handheld High Res",
     "Allows the flash setting in handheld High Res Shot and offers both Fill In and Manual flash "
     "with every flash type (tripod and handheld).",
     "Flash worked on the camera (1.5 build); Fill In + Manual for all flash types: test 1.745.", []),
    ("hires_art", "patch_hires_art.py", [], "Art filters in High Res",
     "Allows art filters and e-Portrait with High Res Shot. The JPEG gets the colour and tone, "
     "not the effect pass (no soft focus, frames or edges).",
     "Worked on the camera (1.5 build), colour only.", []),
    ("scp_menu", "patch_scp_menu.py", [], "SCP button cell opens the main menu",
     "The bottom-right cell of the Super Control Panel (Button Function) opens the main menu instead, "
     "like pressing MENU on the SCP.",
     "Worked on the camera (1.6 build 1.679, menu and title).", []),
    ("sharp_scale", "patch_sharp_off.py", [], "Sharpness -2 = off (linear scale)",
     "Sharpness becomes a straight scale of the stock +2 strength: -2 off, -1 25 %, 0 50 %, +1 75 %, "
     "+2 100 %. Stock -2 still sharpens. Flat and Log video keep their stock sharpening.",
     "Worked on the camera (1.6 build 1.680).", []),
    ("cmode_video", "patch_cmode_video.py", [], "Custom Modes C1-C4 in video",
     "Assign to Custom Mode also works with the dial on movie. A C slot saved there opens in video "
     "mode with its movie settings; a slot saved in a photo mode stays photo.",
     "Worked on the camera (1.6 build 1.681).", []),
    ("filename_underscore", "patch_filename_char.py", [], "Underscore in Edit Filename",
     "Edit Filename also offers '_' (after Z), for sRGB and Adobe RGB, so a file name can start with "
     "an underscore. Note: by the DCF standard a leading '_' marks Adobe RGB files.",
     "Worked on the camera (1.6 build 1.700).", []),
    ("iso_auto_low", "patch_iso_auto_low.py", [], "ISO-Auto down to L64",
     "ISO-Auto can go down to ISO 64 instead of stopping at 200. In M it always can; in P, A and S set "
     "ISO-Auto Default to 200 for no floor (Default 250 or higher still works as the floor). Upper Limit "
     "and the menus are unchanged.",
     "Camera: M down to 64 (1.706); P/A/S version in 1.708/1.709.", []),
    ("rec_limit", "patch_rec_limit.py", [], "Movie recording limit 9 hours",
     "Raises the 29-minute (and 2-hour) movie recording limit to 9 hours. The camera still starts a new "
     "file at the file-size limit; card space, battery and the heat cut-out still stop recording. Same "
     "change as Caduceus' camera-tested E-P7 patch.",
     "Built into test 1.709.", []),
    ("art_gradation", "patch_art_gradation.py", [], "More tone curves in Gradation",
     "Gradation (every picture mode, menu and Super Control Panel) gets 19 more curves after Low Key, from "
     "washed out to contrasty: Faded Matte, Washed Out, Soft Matte, Airy Pastel, Low Con Film, Faded Blacks, "
     "Cine Rolloff, Matte S Curve, Neutral Soft, Bright Open, Soft S Curve, Film S Curve, Crisp, Dark Moody, Punchy S Curve, Slide Film, "
     "Hard S Curve, Crushed Silver, Graphic (names in English menus). Highlight & Shadow Control applies on top. "
     "Two more options, Custom1 and Custom2, take your own curves: draw them with 'Edit curve' (empty = no change). "
     "The small Gradation cell in the SCP grid shows AUTO for all the new options; Contrast has no effect with them.",
     "Art curve version worked on the camera (1.719 / 1.728); user slots 1.740; designed set: test 1.741.", []),
]


# Generated at build time by the app (tools/modcore.py GENERATORS): id, title, description, status,
# requires, options {name: {label, default, min, max}}
def _look_options():
    import patch_looks as pl
    choices = [[k, v["name"]] for k, v in pl.LOOKS.items() if k != "portra400"]
    o = {"look%d" % (i + 1): {"label": "%s slot" % pl.MENU_NAMES[i], "default": pl.DEFAULT6[i], "choices": choices}
         for i in range(6)}
    o["sd"] = {"label": "Load looks from SD card (not camera-tested)", "default": "off",
               "choices": [["off", "No"], ["on", "Yes: Look 1-6, card file"]]}
    return o


GENERATED = [
    ("white_frame", "Frame art effect: plain white border",
     "The Frame art effect becomes a clean white border instead of the grungy film edge.",
     "Worked on the camera (1.6 build 1.664).", [],
     {"width_pct": {"label": "Border width (% of the short side)", "default": 3, "min": 0.5, "max": 20}}),
    ("white_frame_panorama", "White frame in Panorama",
     "Adds the white-border Frame masks for the Panorama aspect (stock has none there: the camera froze).",
     "Worked on the camera (1.6 build 1.665).", ["panorama", "white_frame"], {}),
    ("xpan_icon", "XPAN icon for Panorama on the SCP",
     "Panorama gets its own \"XPAN\" icons in the Super Control Panel (list, highlighted and current-value "
     "cell) instead of the 16:9 icon. Adds three icons to the camera's icon store.",
     "Camera 1.666: XPAN in the SCP option lists; the main SCP cell shows a 17:9 label.", ["panorama"], {}),
    ("custom_looks", "Film looks in Custom (Caduceus recipes)",
     "Custom becomes a film-look mode: hue, saturation and lightness per colour from Caduceus's film "
     "recipes (31 looks). Pick six here; on the camera choose between them in Picture Mode > Custom > "
     "first item, whose list shows the look names. Other picture modes and menus are unchanged. "
     "Custom's own base-mode look (Vivid, Natural...) is replaced; tone, grain and WB shift of the "
     "recipes are not applied yet. With 'Load looks from SD card', Custom's list shows Look 1-6 and, at the "
     "first half-press after switching on, the camera reads EM1MOD/LOOKS.BIN from the card in slot 1 "
     "(button 'Write card file' below); without the file it uses the six looks picked here. "
     "Looks: Caduceus by cakelesscoder (Apache-2.0).",
     "Worked on the camera (1.6 build 1.691).", [], _look_options()),
    ("owner_title", "Owner name and phone in the main menu",
     "The 'Shooting Menu 1' title at the top of the main menu shows your text instead, e.g. your name "
     "and phone number, so a lost or stolen camera can be traced back to you. Up to 36 characters; "
     "'@' (email) does not display. English menus only.",
     "Worked on the camera (1.6 build 1.701; an email with @ did not display).", [],
     {"text": {"label": "Owner text (name, phone)", "default": "", "text": True, "max_len": 36}}),
]


def run_tool(tool, args, src, dst):
    r = subprocess.run([sys.executable, os.path.join(HERE, tool), src, dst] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("%s failed:\n%s%s" % (tool, r.stdout, r.stderr))


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    src = argv[0]
    dst = argv[1] if len(argv) > 1 else os.path.join(HERE, "..", "builder", "mods.json")
    fw = olyfw.read(src)
    sha = hashlib.sha256(fw).hexdigest()
    if sha != modcore.STOCK_SHA256:
        sys.exit("not the official 1.6 file (sha256 %s)" % sha)
    sblocks = olyfw.unpack_blocks(fw)
    stock = modcore.runtime_image(sblocks[0]["plain"])
    splains = [b["plain"] for b in sblocks]
    pack = {"format": 1, "firmware": {"name": modcore.STOCK_NAME, "sha256": sha, "size": len(fw)}, "mods": []}
    owner = {}
    merged = [bytearray(stock)] + [bytearray(p) for p in splains[1:]]
    with tempfile.TemporaryDirectory() as tmp:
        for mid, tool, args, title, desc, status, req in MODS:
            out = os.path.join(tmp, mid + ".BIN")
            run_tool(tool, args, src, out)
            edits = modcore.block_diffs(sblocks, olyfw.unpack_blocks(olyfw.read(out)))
            for blk, a, new in edits:
                o = a - modcore.BASE if blk == 0 else a
                for x in range(o, o + len(new)):
                    if (blk, x) in owner:
                        sys.exit("%s and %s both change block %d %#x" % (owner[(blk, x)], mid, blk, a))
                    owner[(blk, x)] = mid
                merged[blk][o:o + len(new)] = new
            pack["mods"].append({
                "id": mid, "title": title, "description": desc, "camera": status, "requires": req,
                "stock_sha256": modcore.stock_digest(stock, edits, splains),
                "edits": [[blk, "%#x" % a, new.hex()] for blk, a, new in edits]})
            print("%-15s %3d edits %6d bytes  blocks %s" % (mid, len(edits), sum(len(n) for b, a, n in edits),
                                                         sorted({b for b, a, n in edits})))
        # all tools one after another must give the same image as the merged edit lists
        cur = src
        for mid, tool, args, *_ in MODS:
            nxt = os.path.join(tmp, "chain_" + mid + ".BIN")
            run_tool(tool, args, cur, nxt)
            cur = nxt
        cb = olyfw.unpack_blocks(olyfw.read(cur))
        chain = [modcore.runtime_image(cb[0]["plain"])] + [b["plain"] for b in cb[1:]]
        if chain != [bytes(x) for x in merged]:
            sys.exit("merged edit lists differ from the chained tools")
        print("merged edit lists == chained tools")
    for m in pack["mods"]:                 # edit-list mods that also take build-time options
        if m["id"] == "art_gradation":
            m["generator"] = "art_gradation"
            m["options"] = {"curve%d" % i: {"label": "Custom%d curve (in:out points, 0-255)" % i, "default": "",
                                            "text": True, "curve": True} for i in (1, 2)}
    for mid, title, desc, status, req, opts in GENERATED:
        pack["mods"].append({"id": mid, "title": title, "description": desc, "camera": status, "requires": req,
                             "generator": mid, "options": opts})
    with open(dst, "w") as fh:
        json.dump(pack, fh, indent=1)
        fh.write("\n")
    print("wrote", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
