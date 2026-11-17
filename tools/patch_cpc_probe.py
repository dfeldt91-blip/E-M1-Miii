#!/usr/bin/env python3
"""Color Profile editor probe (DIAGNOSTIC, E-M1 Mark III 1.6). Step 1 of the on-camera HSL editor.

  python3 tools/patch_cpc_probe.py IN.BIN OUT.BIN [--version 0x1712]

Goal: an on-camera HSL editor for the Custom look (12 colour sectors, hue / saturation / lightness),
like fishcu's PEN-F HSL mod and Caduceus on the E-P7, which both extend the stock Color Profile
("COLOR_CREATOR_2") wheel editor. The E-M1 III still has that feature's settings (0x386 select,
0x399..0x3bc = 3 sets x 12 sector saturations, cursors 0x43c / 0x441..0x445), its menu strings
("Color Profile 1-3", 0xabd..), and the wheel's data packer 0x609ec110 (kind 5: cursor + 12 values),
but no menu opens an editor for it (docs/FINDINGS.md "Editor search").

Lead: the shooting GUI's event-33 handler 0x60cd2a2e maps param 48 -> state 53 (the classic Color
Creator screen), 50 -> 52, 51 -> 0x60cd1cd2, and 49 -> state 69, which no code posts.

Probe: the SCP INFO handler 0x60e7e4e1, for Picture Mode 21 (Color Creator), posts (33, 48) at
0x60e7e640 (`mov 33,d0; mov 48,d1` = 80 21 85 30). This changes 48 -> 49 (one byte at 0x60e7e643, in
blob B), so INFO on Color Creator in the SCP requests state 69 instead. What opens there tells us
whether state 69 is the Color Profile editor. Everything else is unchanged; the classic Color Creator
screen is still reachable from other paths (e.g. the Multi Function / button), which post (33, 48)
from other sites.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF, BLOB_B_END = 0x60c6c000, 0xc4afe0, 0x612f1000
SITE, STOCK, NEW = 0x60e7e640, bytes.fromhex("80218530"), bytes.fromhex("80218531")


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    m = bytearray(main)
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    o = SITE - BLOB_B
    check(bytes(gui[o:o + 4]) == STOCK, "SCP INFO Color Creator post at %#x differs" % SITE)
    gui[o:o + 4] = NEW
    cg = olycompress.pack(bytes(gui))
    check(len(cg) <= (BLOB_B_END - BASE) - (BLOB_B_OFF + 32), "blob B does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(cg)] = cg
    if len(cg) < csz:
        m[BLOB_B_OFF + 32 + len(cg):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(cg))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(cg))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "blob B does not decode to the edit")
    print("  SCP INFO on Color Creator posts (33, 49) -> GUI state 69 (probe)")
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_main = patch(blocks[0]["plain"])
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), new_main if i == 0 else b["plain"], bytes(tail))
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
