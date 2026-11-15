#!/usr/bin/env python3
"""Allow the flash setting in Handheld High Res Shot (EXPERIMENTAL).
  python3 tools/patch_hhrs_flash.py IN.BIN OUT.BIN [--version 0x1620]

Setting restriction rules (record table 0x6049299c, 20-byte records {u16 sid, u16 flags,
u32 rules, u16 count}; rules {u32 cond, u16 n, u32 map, u16 n}; cond terms {u16 sid, u16 value,
u32 0}; map {s16 from, s16 to}). MODE_STB_GENERAL (0x6d0, flash enable) has 7 rules, all using
the shared "force 0" map 0x60470fc0 {0->0, 1->0}. Rule 3 is
  IF MODE_PIXSHIFT_SR (0x2f2) == 1 AND MODE_PIXSHIFT_SR_HANDHELD (0x68f) == 1 -> flash off.
Its map pointer (rule entry 0x6048a958 + 8) is pointed at the existing identity map 0x60480ee4
{0->0, 1->1} instead. The condition record and both maps are shared, so they stay unchanged.
Tripod High Res has no such rule (flash already allowed there, with Charge Time).
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
RULE3 = 0x6048a958
COND, FORCE0, IDENT = 0x60474170, 0x60470fc0, 0x60480ee4


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def off(a):
    return a - BASE


def patch_main(main):
    m = bytearray(main)
    cp, cn, mp, mn = struct.unpack_from("<IHxxIHxx", m, off(RULE3))
    check((cp, cn, mp, mn) == (COND, 2, FORCE0, 2), "rule 3 of MODE_STB_GENERAL differs")
    terms = [struct.unpack_from("<HHI", m, off(COND) + 8 * j) for j in range(2)]
    check(terms == [(0x2f2, 1, 0), (0x68f, 1, 0)], "rule condition differs")
    check([struct.unpack_from("<hh", m, off(FORCE0) + 4 * j) for j in range(2)] == [(0, 0), (1, 0)],
          "force-0 map differs")
    check([struct.unpack_from("<hh", m, off(IDENT) + 4 * j) for j in range(2)] == [(0, 0), (1, 1)],
          "identity map differs")
    struct.pack_into("<I", m, off(RULE3) + 8, IDENT)
    print("  MODE_STB_GENERAL rule 3 (handheld high res -> flash off) map %#x -> %#x" % (FORCE0, IDENT))
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
