#!/usr/bin/env python3
"""More functions on the arrow keys (EXPERIMENTAL, E-M1 Mark III, 1.5-based).

  python3 tools/patch_buttons.py IN.BIN OUT.BIN [--version 0x1614]

Buttons are settings whose value is a function code; the dispatcher runs any code from any button,
only the validator list limits what the Button Function picker offers (caduceus-ep7 docs/BUTTONS.md;
the picker labels by value from a shared list, 0x611d9120 on this body, which covers every code).
Stock E-M1 III: full buttons (CUSTOM_SW_1-6/12-14/17/22-28) 38 codes; arrow keys CUSTOM_SW_8/10/19/21
only 9; movie arrows MOVIE_CUSTOM_SW_8/10/19/21 only 7. This patch gives the arrows a longer list
(stock entries kept first, Off last) in free space and repoints their records.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
FREE_LO, FREE_HI = 0x600d6b80, 0x600d6c80
# (validator record, stock list) for stills and movie arrow keys
STILL = [(0x604db75c, 0x604d89b6), (0x604db770, 0x604d89c8), (0x604db798, 0x604d89de), (0x604db7ac, 0x604d89f0)]
MOVIE = [(0x604db928, 0x604d8d38), (0x604db93c, 0x604d8d46), (0x604db964, 0x604d8d58), (0x604db978, 0x604d8d66)]
STILL_STOCK = [3341, 16, 3265, 6, 9, 425, 3409, 88, 3200]
MOVIE_STOCK = [3341, 6, 9, 425, 3409, 88, 3200]
# RAW, digital tele, peaking, HDR, BKT, keystone, fisheye, Live ND, IS, face, natural view (S-OVF),
# lens info, focus limiter, preset MF, focus ring lock, LV state, 3428 (level [I])
STILL_ADD = [22, 34, 567, 472, 603, 682, 1431, 1680, 157, 241, 765, 1072, 1139, 1292, 1872, 452, 3428]
MOVIE_ADD = [34, 567, 241, 1072, 1292, 1872, 452, 3428]


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    m = bytearray(main)
    check(set(m[off(FREE_LO - 16):off(FREE_HI)]) == {0xff}, "free area not 0xff")
    free = FREE_LO
    for recs, stock, add in ((STILL, STILL_STOCK, STILL_ADD), (MOVIE, MOVIE_STOCK, MOVIE_ADD)):
        new = stock[:-1] + add + [3200]
        at = free
        m[off(at):off(at) + 2 * len(new)] = struct.pack("<%dH" % len(new), *new)
        free = (free + 2 * len(new) + 15) & ~15
        for rec, lp in recs:
            sid, fl, p, ap, nb, el = struct.unpack_from("<HHIIHH", m, off(rec))
            check((fl, p, nb, el) == (0x80, lp, 2 * len(stock), 2), "record %#x differs" % rec)
            check(list(struct.unpack_from("<%dH" % len(stock), m, off(lp))) == stock, "list %#x differs" % lp)
            struct.pack_into("<I", m, off(rec) + 4, at)
            struct.pack_into("<H", m, off(rec) + 12, 2 * len(new))
        print("  %d arrow records -> %d codes at %#x" % (len(recs), len(new), at))
    check(free <= FREE_HI, "free area overflow")
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
