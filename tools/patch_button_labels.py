#!/usr/bin/env python3
"""Rename the Button Function entries C2/C3/C4 to ISO / SS / Aperture (EXPERIMENTAL).
  python3 tools/patch_button_labels.py IN.BIN OUT.BIN [--version 0x1619]
Goes with patch_hold_presets.py (Myset 2/3/4 = ISO / shutter / aperture hold presets).

Labels: blob B label tables {u32 code, u16 type, u16 label, u32 cond}; type 3 = icon, type 4 =
string id. Codes 3349..3351 (MYSET_2..4):
  icon tables 0x611d8950 / 0x612960ac: type 3 icons 0x23b7 / 0x23b9 / 0x23b8 ("C2".."C4")
  name table 0x61295e3c: strings 0xda4..0xda6 "Custom Mode C2..C4"
  help table 0x612963a0: strings 0xda8..0xdaa "Switches @A0A7@..@A0A9@ on/off."
Icon entries become type 4 with the name strings. The strings are rewritten in place in the
English language section (block 1, section 8; string id = index + 2), padded with spaces to the
same length so every later string keeps its index. Other languages keep the stock text.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BLOB_B, BLOB_B_OFF, BLOB_END, BASE = 0x60c6c000, 0xc4afe0, 0x612f1000, 0x60021020
ICON_TABLES = (0x611d8950, 0x612960ac)       # address of the 3348 (MYSET_1) entry
CODES = {3349: (0x23b7, 0xda4), 3350: (0x23b9, 0xda5), 3351: (0x23b8, 0xda6)}
LANG_SECTION = 8
TEXT = {  # string id: (stock, new)
    0xda4: ("Custom Mode C2", "ISO"),
    0xda5: ("Custom Mode C3", "SS"),
    0xda6: ("Custom Mode C4", "Aperture"),
    0xda8: ("Switches @A0A7@ on/off.", "Hold: ISO preset."),
    0xda9: ("Switches @A0A8@ on/off.", "Hold: shutter preset."),
    0xdaa: ("Switches @A0A9@ on/off.", "Hold: aperture preset."),
}


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_lang(lang):
    t = bytearray(lang)
    a, n = struct.unpack_from("<II", t, 16 * LANG_SECTION)
    o = a - 0x42400000
    starts, cur = [], o
    for j in range(o, o + n - 1, 2):
        if t[j:j + 2] == b"\0\0":
            starts.append((cur, j))
            cur = j + 2
    for sid, (old, new) in TEXT.items():
        s, e = starts[sid - 2]
        check(t[s:e].decode("utf-16le") == old, "string %#x is not %r" % (sid, old))
        check(len(new) <= len(old), "replacement too long")
        t[s:e] = new.ljust(len(old)).encode("utf-16le")
    return bytes(t)


def patch_main(main):
    m = bytearray(main)
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    for t in ICON_TABLES:
        for i, (code, (icon, sid)) in enumerate(sorted(CODES.items()), 1):
            o = t - BLOB_B + 12 * i
            c, ty, lab = struct.unpack_from("<IHH", gui, o)
            check((c, ty, lab) == (code, 3, icon), "icon entry %#x differs" % (t + 12 * i))
            struct.pack_into("<HH", gui, o + 4, 4, sid)
    c = olycompress.pack(bytes(gui))
    check(len(c) <= (BLOB_END - BASE) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  icon entries -> text in %d tables; blob B %#x -> %#x" % (len(ICON_TABLES), csz, len(c)))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    plains = [b["plain"] for b in blocks]
    plains[0] = patch_main(plains[0])
    plains[1] = patch_lang(plains[1])
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), plains[i], bytes(tail))
    check(len(out) == len(fw), "size changed")
    with open(dst, "wb") as fh:
        fh.write(out)
    again = olyfw.unpack_blocks(open(dst, "rb").read())
    check(all(b["stored"] == b["calc"] for b in again), "output checksum check failed")
    print("wrote %s  sha256 %s  version %#06x" % (dst, hashlib.sha256(out).hexdigest(),
                                                   struct.unpack_from("<H", again[0]["head"], 16)[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
