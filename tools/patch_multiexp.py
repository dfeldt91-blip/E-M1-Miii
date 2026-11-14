#!/usr/bin/env python3
"""Multiple Exposure with 3 or 4 frames (EXPERIMENTAL, E-M1 Mark III, 1.5-based).

  python3 tools/patch_multiexp.py IN.BIN OUT.BIN [--version 0x1601]

Port of the E-P7 Caduceus "Live ND" route A (docs/LIVE_ND.md there), data only:
  - validator record of MODE_MULTI_EXPOSURE_FRAME (0x10a) at 0x604dc904: u8 list [0, 2] ->
    new list [0, 2, 3, 4] in free space (5 froze the camera on test);
  - the three menu option lists {0 Off, 2 "2f"} (descriptors 0x611af8b0 / 0x61206d60 / 0x61288514 in
    blob B) -> 5-entry copies with the stock labels "3f" 1430, "4f" 1431, "5f" 1899.
Camera (1.601): the tab descriptors alone do not change the Number of Frames row. The row record
(36 B: {u32 sid, u16 4, u16 title, u32 cond, u32 list1, u32 n1, u32 0, u32 cond, u32 list2, u32 n2};
0x611bc7ac / 0x61271fd8 / 0x61280730) has two option lists of its own; both get the 5 entries too.
The sequencer (0x609c7bff / 0x609c857c / 0x609c8da5) already counts to the setting, and its frame
handle array is malloc(20) = 5 slots, so 5 is the ceiling. With Auto Gain On each frame gets 1/N
(an average); with it Off the frames are summed, as stock does for 2.
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
REC, STOCK_LIST = 0x604dc904, 0x604d93d2
DESCS = (0x611af8b0, 0x61206d60, 0x61288514)
ROWS = (0x611bc7ac, 0x61271fd8, 0x61280730)
FRAMES = [0, 2, 3, 4]          # camera: 5 froze and restarted the camera (1.602); 4 works
LABELS = {3: 1430, 4: 1431, 5: 1899}
FREE_LO, FREE_HI = 0x600d6d00, 0x600d6f80      # 0xff padding, unused by the aspect build


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    m = bytearray(main)
    check(set(m[off(FREE_LO - 16):off(FREE_HI)]) == {0xff}, "free area not 0xff")
    sid, fl, lp, ap, nb, el = struct.unpack_from("<HHIIHH", m, off(REC))
    check((sid, lp, nb, el) == (0x10a, STOCK_LIST, 2, 1), "validator record differs")
    check(list(m[off(lp):off(lp) + 2]) == [0, 2], "validator list differs")
    free = FREE_LO
    m[off(free):off(free) + len(FRAMES)] = bytes(FRAMES)
    struct.pack_into("<I", m, off(REC) + 4, free)
    struct.pack_into("<H", m, off(REC) + 12, len(FRAMES))
    vlist = free
    free += 16

    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    for d in DESCS:
        sid, n, ptr = struct.unpack_from("<HHI", gui, d - BLOB_B)
        check((sid, n) == (0x10a, 2), "descriptor %#x differs" % d)
        es = [struct.unpack_from("<IHHI", gui, ptr - BLOB_B + 12 * k) for k in range(2)]
        check([e[0] for e in es] == [0, 2] and all(e[1] == 4 for e in es), "option list %#x differs" % ptr)
        cond = es[1][3]
        new = es + [(v, 4, LABELS[v], cond) for v in FRAMES[2:]]
        data = b"".join(struct.pack("<IHHI", *e) for e in new)
        m[off(free):off(free) + len(data)] = data
        struct.pack_into("<HI", gui, d - BLOB_B + 2, len(new), free)
        free += (len(data) + 15) & ~15
    def ext(ptr):
        nonlocal free
        es = [struct.unpack_from("<IHHI", gui, ptr - BLOB_B + 12 * k) for k in range(2)]
        check([e[0] for e in es] == [0, 2] and all(e[1] == 4 for e in es), "row list %#x differs" % ptr)
        new = es + [(v, 4, LABELS[v], es[1][3]) for v in FRAMES[2:]]
        data = b"".join(struct.pack("<IHHI", *e) for e in new)
        m[off(free):off(free) + len(data)] = data
        at = free
        free += (len(data) + 15) & ~15
        return at
    for r in ROWS:
        sid, t, l, c, l1, n1, z, c2, l2, n2 = struct.unpack_from("<IHHIIIIIII", gui, r - BLOB_B)
        check((sid, t, n1, z, n2) == (0x10a, 4, 2, 0, 2), "row record %#x differs" % r)
        struct.pack_into("<II", gui, r - BLOB_B + 12, ext(l1), len(FRAMES))
        struct.pack_into("<II", gui, r - BLOB_B + 28, ext(l2), len(FRAMES))
    check(free <= FREE_HI, "free area overflow")

    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  validator list %#x %s, 3 option lists -> %d entries, data %#x-%#x, blob B %#x -> %#x"
          % (vlist, FRAMES, len(FRAMES), FREE_LO, free, csz, len(c)))
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
