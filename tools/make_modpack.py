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
    ("multiexp", "patch_multiexp.py", [], "Multiple Exposure: 3 and 4 frames",
     "Multiple Exposure accepts 3 or 4 frames, with the merged shots shown as the live overlay.",
     "Worked on the camera (1.5 build).", []),
    ("stack_any_lens", "patch_stack_any_lens.py", [], "Focus stacking with any lens",
     "Removes the lens check for in-camera focus stacking (the change in E1399999_Focus_Stack.BIN).",
     "Worked on the camera (1.5 build).", []),
    ("stack16", "patch_focus_stack.py", [], "Focus stacking: up to 16 frames",
     "Focus stacking frame count goes up to 16 (stock 15; 16 is the merge engine limit).",
     "Not tested on the camera yet.", []),
    ("keyline_mono", "patch_keyline_mono.py", [], "Key Line II in black and white",
     "Art filter Key Line II gets a grey (monochrome) toning instead of colour.",
     "Worked on the camera (1.5 build).", []),
    ("arrow_keys", "patch_buttons.py", [], "More arrow-key functions",
     "The arrow keys can be assigned 25 functions for stills and 15 for movies.",
     "Not tested on the camera yet.", []),
    ("hold_presets", "patch_hold_presets.py", [], "ISO / shutter / aperture hold presets",
     "Myset 2/3/4 buttons become ISO / shutter / aperture presets: press applies, release restores.",
     "Toggle version worked (1.5 build); hold version not tested yet.", []),
    ("preset_labels", "patch_button_labels.py", [], "Preset button labels",
     "Shows C2 / C3 / C4 as ISO / SS / Aperture in the button-function screens.",
     "Not tested on the camera yet.", ["hold_presets"]),
    ("hhrs_flash", "patch_hhrs_flash.py", [], "Flash in handheld High Res",
     "Allows the flash setting in handheld High Res Shot.",
     "Worked on the camera (1.5 build).", []),
    ("hires_art", "patch_hires_art.py", [], "Art filters in High Res",
     "Allows art filters and e-Portrait with High Res Shot. The JPEG gets the colour and tone, "
     "not the effect pass (no soft focus, frames or edges).",
     "Worked on the camera (1.5 build), colour only.", []),
]


# Generated at build time by the app (tools/modcore.py GENERATORS): id, title, description, status,
# requires, options {name: {label, default, min, max}}
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
     "Not tested on the camera yet.", ["panorama"], {}),
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
