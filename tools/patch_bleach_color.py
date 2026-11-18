#!/usr/bin/env python3
"""Bleach Bypass I with Bleach Bypass II's colour (TEST, E-M1 Mark III 1.6). Base section only.

  python3 tools/patch_bleach_color.py IN.BIN OUT.BIN [--curve] [--version 0x1737]

Bleach Bypass II's own colour data is its coefficient record 0x6053d31c (block 0x605283a8), chosen by
the coefficient switch 0x603de54d (64-slot hash 0x6053e004 on the job key, linear probing, an empty
key ends at the default record 0x6053cac8). Bleach II's entry {0x102007b, 0x603de718} loads that
record; Bleach I (0x101007b) has no entry and gets the default. Bleach I's probe starts at slot 59
and wraps to the first empty slot, 42 (0x6053e154); an entry for Bleach I is written there, with
Bleach II's handler. Keys that are not in the table still end at an empty slot (49).
--curve  also Bleach II's tone curve (identity) instead of Bleach I's (tone switch 0x603df193,
         key-11 entry 0x6053e2dc: handler 0x603df36e -> Bleach II's 0x603df377).
Bleach I keeps its own short chain (0x60385b6b), so no Bleach II softening.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
HASH, SLOTS = 0x6053e004, 64
BB1, BB2 = 0x101007b, 0x102007b
BB2_COEF_H, DEFAULT_H = 0x603de718, 0x603de7e4
TONE_SLOT, TONE_BB1, TONE_BB2 = 0x6053e2dc, 0x603df36e, 0x603df377


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main, curve):
    m = bytearray(main)
    o = lambda a: a - BASE  # noqa: E731
    ent = lambda j: struct.unpack_from("<II", m, o(HASH + 8 * j))  # noqa: E731
    check(any(ent(j) == (BB2, BB2_COEF_H) for j in range(SLOTS)), "Bleach II coefficient entry not found")
    j = BB1 & (SLOTS - 1)
    for _ in range(SLOTS):
        k, h = ent(j)
        check(k != BB1, "Bleach I already has an entry")
        if k == 0:
            break
        j = (j + 1) % SLOTS
    check(ent(j) == (0, DEFAULT_H), "no empty slot on Bleach I's probe path")
    struct.pack_into("<II", m, o(HASH + 8 * j), BB1, BB2_COEF_H)
    print("  Bleach I coefficient record: slot %d (%#x) -> Bleach II's (handler %#x)" % (j, HASH + 8 * j, BB2_COEF_H))
    if curve:
        check(struct.unpack_from("<II", m, o(TONE_SLOT)) == (BB1 - 11, TONE_BB1), "Bleach I tone entry differs")
        struct.pack_into("<I", m, o(TONE_SLOT) + 4, TONE_BB2)
        print("  Bleach I tone curve: Bleach II's (identity)")
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_main = patch(blocks[0]["plain"], "--curve" in argv)
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
