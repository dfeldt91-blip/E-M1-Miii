#!/usr/bin/env python3
"""Key Line II in black and white (EXPERIMENTAL, E-M1 Mark III, 1.5-based).

  python3 tools/patch_keyline_mono.py IN.BIN OUT.BIN [--version 0x1611]

Mono comes from the chroma stage, not the colour table (caduceus-ep7 docs/WB_AND_MONO.md B5): a
toning lookup 0x603dfd00 (main) returns a vector {1, Cb, Cr, Cb, Cr} from the table at 0x6051b964
(grey 80 80, sepia 75 8d, ...) or 0 for colour, and the stage writes it to the job's colour output.
The lookup is a 16-slot hash at 0x6053e67c ({u32 key-4, u32 handler}, index (key-4) & 15). Key Line I
(0x1010077) and II (0x1020077) use handler 0x603dfdb5: grey only when a variant word == 0x501,
else colour. This patch sets Key Line II's handler to 0x603dfe09 (always the grey vector).
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
SLOT = 0x6053e6ac
STOCK = (0x1020077 - 4, 0x603dfdb5)
GREY = 0x603dfe09


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
    o = SLOT - BASE
    check(struct.unpack_from("<II", m, o) == STOCK, "Key Line II toning entry differs")
    check(((STOCK[0]) & 15) * 8 + 0x6053e67c <= SLOT, "slot not in probe order")
    struct.pack_into("<I", m, o + 4, GREY)
    print("  Key Line II toning: %#x -> %#x (grey)" % (STOCK[1], GREY))
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
