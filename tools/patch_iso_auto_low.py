#!/usr/bin/env python3
"""ISO-Auto down to L64 (EXPERIMENTAL, E-M1 Mark III 1.6). Stage 1.

  python3 tools/patch_iso_auto_low.py IN.BIN OUT.BIN [--version 0x1703]

ISO values are APEX Sv x 256: ISO 100 = 0x500, 1/3 EV = 0x55 (L64 0x455, L80 0x4aa, 100 0x500, 125
0x555, 160 0x5aa, 200 0x600 ... 6400 0xb00). ISO-Auto Set (menu "Upper Limit / Default") uses settings
0x68b MODE_ISO_LIMITER_STILL (upper limit) and 0x68d MODE_ISO_STANDARD_STILL (default; ISO-Auto
starts there and only rises), movie 0x68c / 0x68e. Their setting records (0x604dbf90 + 20 x k, {u16
id, u16 0x80, u32 values, u32 ?, u16 bytes, u16 2, u32}) share the 16-value list 0x604d90e2
(0x600..0xb00). 0x602ccac7.. keeps default <= upper limit. The exposure code clamps the ISO-Auto
values to 0x600..0xb00 at 0x604372ca (six per-mode copies 0x62167ed4..) and 0x60434633.

Stage 1: 0x68d (stills Default) gets its own 21-value list at 0x600d9280: L64 L80 100 125 160, then
200..6400; both clamps' lower bound 0x600 -> 0x455. Upper Limit and movie keep 200..6400.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
REC_DEFAULT = 0x604dbfb8
STOCK_LIST = 0x604d90e2
STOCK_VALUES = [0x600 + 0x55 * k + (k // 3) for k in range(16)]
NEW_LIST = 0x600d9280
LOW = [0x455, 0x4aa, 0x500, 0x555, 0x5aa]
CLAMPS = [  # (address, stock bytes, new bytes)
    (0x604372ca, "fac80006", "fac85504"),   # cmp 0x600,d0 -> cmp 0x455,d0
    (0x604372d0, "2e0006", "2e5504"),       # mov 0x600,d2 -> mov 0x455,d2
    (0x60434633, "fac80006", "fac85504"),
    (0x60434639, "2c0006", "2c5504"),       # mov 0x600,d0 -> mov 0x455,d0
]


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def off(a):
    return a - BASE


def patch_at(m, base):
    o = lambda a: a - base  # noqa: E731
    sid, fl, vp, z, n, sz = struct.unpack_from("<HHIIHH", m, o(REC_DEFAULT))
    check((sid, fl, vp, n, sz) == (0x68d, 0x80, STOCK_LIST, 32, 2), "ISO-Auto Default record differs")
    vals = list(struct.unpack_from("<16H", m, o(STOCK_LIST)))
    check(vals == STOCK_VALUES, "ISO-Auto value list differs")
    new = LOW + vals
    data = struct.pack("<%dH" % len(new), *new)
    check(set(m[o(NEW_LIST) - 16:o(NEW_LIST) + len(data) + 16]) == {0xff}, "list area not free")
    m[o(NEW_LIST):o(NEW_LIST) + len(data)] = data
    struct.pack_into("<I", m, o(REC_DEFAULT) + 4, NEW_LIST)
    struct.pack_into("<H", m, o(REC_DEFAULT) + 12, len(data))
    for a, old, nw in CLAMPS:
        old, nw = bytes.fromhex(old), bytes.fromhex(nw)
        check(bytes(m[o(a):o(a) + len(old)]) == old, "clamp at %#x differs" % a)
        m[o(a):o(a) + len(nw)] = nw
    return len(new)


def patch(main):
    m = bytearray(main)
    n = patch_at(m, BASE)
    print("  ISO-Auto Default: %d values from L64 (list %#x); exposure clamps 200 -> L64" % (n, NEW_LIST))
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
