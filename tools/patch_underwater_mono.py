#!/usr/bin/env python3
"""Underwater picture mode -> a second Monotone (EXPERIMENTAL test, E-M1 Mark III 1.6).

  python3 tools/patch_underwater_mono.py IN.BIN OUT.BIN [--version 0x1672]

The Picture Mode validator list (setting 0x6f, 26 entries of 64 bytes at 0x604bc4f4) holds the
image-pipeline type of each entry: {u32 type, u32 flag, ...}; Monotone is entry 5 {5, 1},
Underwater entry 8 {10, 0} (GUI value 0x1c, label "Underwater"). Test 1.595 showed that this
type drives the image pipeline (e-Portrait set to 12 shot Monochrome Profile).
1.672 gave Underwater Monotone's {5, 1}: choosing Underwater selected Monotone (the GUI finds the
entry by type, so a duplicate type is an alias). 1.673 keeps type 10 and only sets the second
field (1 on Monotone only, perhaps a monochrome flag): {10, 1}.
Open question for the camera test: which contrast / sharpness / filter / tone values the
Underwater slot then uses (Monotone's current ones, defaults, or something else).
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
LIST, ELEM = 0x604bc4f4, 64
MONOTONE, UNDERWATER = 5, 8


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    m = bytearray(main)
    mono = off(LIST + ELEM * MONOTONE)
    uw = off(LIST + ELEM * UNDERWATER)
    check(struct.unpack_from("<2I", m, mono) == (5, 1), "Monotone entry differs")
    check(struct.unpack_from("<2I", m, uw) == (10, 0), "Underwater entry differs")
    check(set(m[uw + 8:uw + ELEM]) == {0}, "Underwater entry has more data than expected")
    struct.pack_into("<I", m, uw + 4, 1)
    print("  Underwater (entry 8) -> {10, 1}")
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
