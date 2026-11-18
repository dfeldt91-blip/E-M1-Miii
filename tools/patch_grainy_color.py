#!/usr/bin/env python3
"""Grainy Film in colour (TEST, E-M1 Mark III 1.6).

  python3 tools/patch_grainy_color.py IN.BIN OUT.BIN [--both] [--version 0x1731]

Grainy Film is black and white only because of its toning entry, not its grain: the toning lookup
0x603dfd00 (hash 0x6053e67c, {key-4, handler}; see patch_keyline_mono.py) gives Grainy Film I/II
(0x1010068 / 0x1020068) handler 0x603dfd4a, which always returns a mono vector. Picture modes use
the default handler 0x603dfdc7: colour unless the mode is Monochrome. Pointing Grainy Film II (and
with --both also I) at the default handler keeps its grain chain (art builder only; the picture-mode
builder has no grain modules) and gives colour output. Its tone curve is used only for sub-mode
0x100, so Contrast works as in picture modes. 1.731 (toning entry only) previewed in colour but shot
mono: the photo pass 0x603dfe9f calls the lookup again with the mono flag for Grainy keys; 1.732
also skips that call.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
SLOTS = {"I": (0x6053e69c, 0x1010068), "II": (0x6053e6a4, 0x1020068)}
# photo pass 0x101 (0x603dfe9f): `cmp KEY,d0` for Grainy I / II, then the toning lookup with the mono
# flag set. The key operand is changed to a key no job has, so the pass takes the colour path.
PHOTO_CMP = {"I": (0x603dfef3, 0x1010068, 0x10e0068), "II": (0x603dfefb, 0x1020068, 0x10f0068)}
STOCK_H, COLOUR = 0x603dfd4a, 0x603dfdc7


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    m = bytearray(blocks[0]["plain"])
    for name in (("I", "II") if "--both" in argv else ("II",)):
        slot, key = SLOTS[name]
        o = slot - BASE
        check(struct.unpack_from("<II", m, o) == (key - 4, STOCK_H), "Grainy Film %s toning entry differs" % name)
        struct.pack_into("<I", m, o + 4, COLOUR)
        print("  Grainy Film %s toning: %#x -> %#x (colour)" % (name, STOCK_H, COLOUR))
        site, old, new = PHOTO_CMP[name]
        o = site - BASE
        check(bytes(m[o:o + 6]) == b"\xfc\xc8" + struct.pack("<I", old), "Grainy Film %s photo compare differs" % name)
        struct.pack_into("<I", m, o + 2, new)
        print("  Grainy Film %s photo pass: mono toning call skipped" % name)
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), bytes(m) if i == 0 else b["plain"], bytes(tail))
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
