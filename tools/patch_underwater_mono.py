#!/usr/bin/env python3
"""Underwater picture mode -> black and white (EXPERIMENTAL, E-M1 Mark III 1.6).

  python3 tools/patch_underwater_mono.py IN.BIN OUT.BIN [--tint 0..4] [--version 0x1674]

Picture Mode validator list (setting 0x6f, 26 x 64-byte entries at 0x604bc4f4) {u32 pipeline type,
u32 slot}: Monotone {5, 1}, Underwater {10, 0} (GUI value 0x1c).
  1.672 Underwater -> {5, 1}: an alias of Monotone (the GUI finds the entry by type).
  1.673 Underwater -> {10, 1}: normal colour Underwater (the second field is not a mono flag).
1.674: the chroma toning lookup 0x603dfd00 (see patch_keyline_mono.py) is keyed by the pipeline
type: a 16-slot open hash at 0x6053e67c {u32 key-4, u32 handler}, index (key-4) & 15, linear
probe until the key or an empty slot (stored 0). Type 5 (Monotone) and 12 (Mono Profile) are in
it; 10 is not, so Underwater falls to the default (colour unless the job's mono flag is set).
This patch adds key 10 -> 0x603dfe09 (always the neutral grey vector) in empty slot 13, the first
empty slot on 10's probe path (6..13), so Underwater keeps its identity, menus and colour
processing, and its JPEG is toned grey. Tone fixed (neutral); no filter setting.
Camera 1.674: Underwater shoots black and white (live view too), a little brighter than Monotone
at default settings (Underwater's own tone tuning).
--tint N picks the toning: 0 neutral, 1 sepia, 2 blue, 3 purple, 4 green (the entry points of the
default handler that load each toning vector at 0x6051b964.. and return).
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
HASH, SLOTS = 0x6053e67c, 16
KEY, DEFAULT = 10, 0x603dfdc7
TINTS = [0x603dfe09, 0x603dfde9, 0x603dfdf1, 0x603dfdf9, 0x603dfe01]  # neutral, sepia, blue, purple, green
TINT_NAMES = ["neutral", "sepia", "blue", "purple", "green"]


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_at(m, base, tint=0):
    """M: bytearray holding the base section at runtime address BASE (block 0 plain or the runtime
    image; both have the base section at the same offsets)."""
    check(tint in range(len(TINTS)), "tint must be 0..4")
    o = HASH - base
    tab = [struct.unpack_from("<2I", m, o + 8 * k) for k in range(SLOTS)]
    check(all(k != KEY - 4 for k, h in tab), "type %d already has a toning entry" % KEY)
    i = (KEY - 4) & 15
    while tab[i][0] != 0:
        i = (i + 1) % SLOTS
    check(i == 13 and tab[i] == (0, DEFAULT), "unexpected toning table layout (slot %d)" % i)
    struct.pack_into("<2I", m, o + 8 * i, KEY - 4, TINTS[tint])
    return i


def patch(main, tint=0):
    m = bytearray(main)
    i = patch_at(m, BASE, tint)
    print("  toning table slot %d: type %d (Underwater) -> %s" % (i, KEY, TINT_NAMES[tint]))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    tint = int(argv[argv.index("--tint") + 1]) if "--tint" in argv else 0
    new_main = patch(blocks[0]["plain"], tint)
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
