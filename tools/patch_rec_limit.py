#!/usr/bin/env python3
"""Movie recording limit raised from 29 min / 2 h to 9 h (EXPERIMENTAL, E-M1 Mark III 1.6).

  python3 tools/patch_rec_limit.py IN.BIN OUT.BIN [--version 0x1709]

Same routine as Caduceus' E-P7 rec_limit (camera-tested there: 1740 s / 7200 s -> 32400 s):
- 0x603442f5: per movie type, types 3/6/8/9 -> 1740 s (29 min, 0x60344312 `mov 0x6cc,d0`), type 4 ->
  7200 s (2 h, 0x60344317 `mov 0x1c20,d0`).
- 0x603435bb `mov 0x6cc,d1`: remaining recording time capped at 1740 s.
- 0x60352732 `mov 0x6cc,d2`: (0x7ec000 - used) / rate capped at 1740 s.
All four become 32400 s (9 h). File splitting at the card's file-size limit, card space, battery and
the heat cut-out still apply.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
NEW = 32400
EDITS = [  # (address, stock instruction bytes)
    (0x60344312, "2ccc06"),   # mov 1740,d0
    (0x60344317, "2c201c"),   # mov 7200,d0
    (0x603435bb, "2dcc06"),   # mov 1740,d1
    (0x60352732, "2ecc06"),   # mov 1740,d2
]


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_at(m, base):
    for a, old in EDITS:
        old = bytes.fromhex(old)
        o = a - base
        check(bytes(m[o:o + 3]) == old, "limit at %#x differs" % a)
        m[o + 1:o + 3] = struct.pack("<H", NEW)


def patch(main):
    m = bytearray(main)
    patch_at(m, BASE)
    print("  movie recording limit 1740 s / 7200 s -> %d s (%d places)" % (NEW, len(EDITS)))
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
