#!/usr/bin/env python3
"""Focus Stacking: allow 16 frames (EXPERIMENTAL, E-M1 Mark III, 1.5-based).

  python3 tools/patch_focus_stack.py IN.BIN OUT.BIN [--version 0x1610]

MODE_FOCUS_STACKING_NUMBER (0x5b2) has no validator record; its menu item handler 0x60df6c95
(blob B) builds 13 options from the u32 table 0x611cdea0 (15, 14, ... 3) and resets values outside
3..15 to 3. The merge DevRec_Rec::recordMediaFocusStacking (0x60ae4871, blob A) clamps the frame
count to 16 and copies at most 16 frame ids, so 16 is the engine ceiling; more frames would be shot
and then dropped. This patch: new table 16..3 (14 entries), count 13 -> 14, clamp 15 -> 16.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF, BLOB_END = 0x60c6c000, 0xc4afe0, 0x612f1000
TABLE, NEW_TABLE = 0x611cdea0, 0x600d6f80
COUNT_SITE, CLAMP_SITE, PTR_SITE = 0x60df6ca3, 0x60df6cc6, 0x60df6d56
MAX = 16


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    m = bytearray(main)
    vals = list(range(MAX, 2, -1))
    check(set(m[off(NEW_TABLE - 16):off(NEW_TABLE + 4 * len(vals) + 16)]) == {0xff}, "table area not free")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    g = lambda a: a - BLOB_B          # noqa: E731
    check(list(struct.unpack_from("<13I", gui, g(TABLE))) == list(range(15, 2, -1)), "option table differs")
    check(bytes(gui[g(COUNT_SITE):g(COUNT_SITE) + 2]) == b"\x80\x0d", "count site differs")
    check(bytes(gui[g(CLAMP_SITE):g(CLAMP_SITE) + 2]) == b"\xa0\x0f", "clamp site differs")
    check(bytes(gui[g(PTR_SITE):g(PTR_SITE) + 6]) == b"\xfc\xdc" + struct.pack("<I", TABLE), "table load differs")
    m[off(NEW_TABLE):off(NEW_TABLE) + 4 * len(vals)] = struct.pack("<%dI" % len(vals), *vals)
    gui[g(COUNT_SITE) + 1] = len(vals)
    gui[g(CLAMP_SITE) + 1] = MAX
    struct.pack_into("<I", gui, g(PTR_SITE) + 2, NEW_TABLE)
    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  focus stacking: options %d..3 (%d) at %#x, clamp %d; blob B %#x -> %#x"
          % (MAX, len(vals), NEW_TABLE, MAX, csz, len(c)))
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
