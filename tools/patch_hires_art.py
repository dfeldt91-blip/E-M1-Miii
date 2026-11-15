#!/usr/bin/env python3
"""Allow art filters / e-Portrait with High Res Shot (EXPERIMENTAL).
  python3 tools/patch_hires_art.py IN.BIN OUT.BIN [--version 0x1622]

Setting restriction rules (record table 0x604920dc, see patch_hhrs_flash.py). MODE_COLORTONE
(0x6f, picture mode) record 0x60492848 has 32 rules; rule 7 (entry 0x604761d0) is
  IF MODE_PIXSHIFT_SR (0x2f2) == 1 -> map 0x60475d50
which keeps 7, 0, 1, 2, 5, 3, 6, 28, 21 and maps 20 (e-Portrait), 8-19, 26, 27, 60, 63 (art
filters) to 1. That map is shared by 10 rules (bracketing, focus stacking, fisheye ...), so rule 7
gets its own identity map over the same 26 values at 0x600d2f00 (0xff padding in the
boot-copied base section; read-only data only).
Camera 1.622: art filters selectable with High Res, no freezes; the JPEG gets the filter's colour/tone
but not the effect pass (soft focus, white edge, other effects): the High Res sequence
(iseq_pixshift_sr) has no art-effect step. Kept as is.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
RULE7, STOCK_MAP, NEW_MAP = 0x604761d0, 0x60475d50, 0x600d2f00
VALUES = [7, 0, 1, 2, 5, 3, 6, 20, 28, 21, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 26, 27, 60, 63]
KEEP = {7, 0, 1, 2, 5, 3, 6, 28, 21}


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def off(a):
    return a - BASE


def patch_main(main):
    m = bytearray(main)
    cp, cn, mp, mn = struct.unpack_from("<IHxxIHxx", m, off(RULE7))
    check(cn == 1 and struct.unpack_from("<HHI", m, off(cp)) == (0x2f2, 1, 0), "rule 7 condition differs")
    check((mp, mn) == (STOCK_MAP, len(VALUES)), "rule 7 map differs")
    stock = [struct.unpack_from("<hh", m, off(mp) + 4 * j) for j in range(mn)]
    check(stock == [(v, v if v in KEEP else 1) for v in VALUES], "stock High Res picture-mode map differs")
    data = b"".join(struct.pack("<hh", v, v) for v in VALUES)
    check(set(m[off(NEW_MAP) - 16:off(NEW_MAP) + len(data) + 16]) == {0xff}, "map target not free")
    m[off(NEW_MAP):off(NEW_MAP) + len(data)] = data
    struct.pack_into("<I", m, off(RULE7) + 8, NEW_MAP)
    print("  MODE_COLORTONE rule 7 (High Res) map %#x -> identity %#x (%d values)" % (STOCK_MAP, NEW_MAP, len(VALUES)))
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
