#!/usr/bin/env python3
"""White Edge Art Effect experiments (EXPERIMENTAL, E-M1 Mark III, 1.5-based).

  python3 tools/patch_white_edge.py IN.BIN OUT.BIN --probe1 [--version 0x1612]

White Edge (Art Effect 4): converter 0x6041dbd1 sets job flag 0x2000; the builder (0x603859f3) asks
the cached generator 0x6039ae27 for a mask sized to the image; 0x6039c4fb fills the parameter block
(entry+12: +8 mode 2060, +10..+18 five x 128, +20/+22 0, +24/+26 half of +12/+14, +72 0x8000,
+76 0x11106) and has the image engine render the mask (0x60366351). The stage setup 0x603887bb copies
16 words of it into the blend stage with mode 0x500.

--probe1: the five 128 values (and so the two halves) -> 255 (`mov 128,d0` at 0x6039c674).
  (Not flashed: White Edge is a radial fade, so a hard version would be an oval, not a rectangle.)

--frame-white: Frame (Art Effect 3, job flag 0x8000) has a rectangular film-border mask; its stage
setup 0x6038873b loads two mask layers and blend mode 0x300 (768), where White Edge uses 0x500
(1280, toward white). Give Frame mode 0x500 on both paths (stage +1838 at 0x60388777, +656 at
0x603887ae) to see whether the mode sets the colour.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
PROBES = {
    "--probe1": [(0x6039c674, bytes.fromhex("2c8000"), bytes.fromhex("2cff00"))],
    "--frame-white": [(0x60388777, bytes.fromhex("2c0003"), bytes.fromhex("2c0005")),
                      (0x603887ae, bytes.fromhex("2c0003"), bytes.fromhex("2c0005"))],
}


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def main(argv):
    sel = [p for p in PROBES if p in argv]
    if len(argv) < 2 or len(sel) != 1:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    m = bytearray(blocks[0]["plain"])
    for addr, stock, new in PROBES[sel[0]]:
        o = addr - BASE
        check(bytes(m[o:o + len(stock)]) == stock, "bytes at %#x differ" % addr)
        m[o:o + len(new)] = new
        print("  %#x: %s -> %s" % (addr, stock.hex(), new.hex()))
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
