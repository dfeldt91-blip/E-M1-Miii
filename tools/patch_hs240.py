#!/usr/bin/env python3
"""240 fps High Speed movie (EXPERIMENTAL, E-M1 Mark III 1.6). Stage 2: sensor mode at the source.

  MN10300_BIN=... python3 tools/patch_hs240.py IN.BIN OUT.BIN [--version 0x1698]

Stock High Speed movie (FHD 120 fps) runs the sensor at 120 fps. The sensor driver (cam.c, status
names at 0x6160edb3, jump table 0x6160efbc) also has 240 fps states, and the exposure code picks
240 fps live-view rates (0x604325b7.., AE tables 0xbf00/0xbf01/0xbf0a/0xbf0b).
Cam command modes (0x6013cd3f, table 0x601cd4b0): 0 HSSC, 1 MSSC (120), 2 LSSC (240), 3 CLIP,
4 HSHR, 5 MSHR, 6 4K, 7 C4K, 8 PD, 9 MSPD (120, phase detect), 10 LSPD (240, phase detect), 11 HQ,
12 FULL, 13 FULL_LQ. The debug override 0x60445254 ("exp movie cap 5/6", byte 0x6216c4ac) maps to
the same numbers.

Camera 1.697 (stage 1: only the movie set-up 0x60437547 turned 1 into 2): no change, 120 fps.

Stage 2: the exposure capture-mode builder 0x60436f1e (all five callers; it writes the 12-byte
mode record whose first word becomes 0x62167f30) ends `call 0x604398f1,[d2,d3,a2,a3],32; ret
[d2,a2,a3],84` at 0x60436f3b. That becomes `jmp stub`: the stub makes the call, then turns mode 1
into 2 and 9 into 10 in the record (d2), and returns. Applies in every mode (photo live view at
120 fps too), as a test.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
SITE, SITE_STOCK = 0x60436f3b, bytes.fromhex("cdb629f020dfb054")   # call 0x604398f1 ; ret
STUB = 0x600d6ac0
SRC = """call tgt,[d2,d3,a2,a3],32
mov d2,a0
mov (a0),d0
cmp 1,d0
bne 1f
mov 2,d0
mov d0,(a0)
1:
cmp 9,d0
bne 2f
mov 10,d0
mov d0,(a0)
2:
.byte 0xdf,0xb0,0x54"""


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_at(m, base):
    """M: bytearray holding the base section at runtime address BASE."""
    import patch_aspect
    o = lambda a: a - base  # noqa: E731
    check(bytes(m[o(SITE):o(SITE) + len(SITE_STOCK)]) == SITE_STOCK, "mode builder end at %#x differs" % SITE)
    stub = patch_aspect.assemble_syms(SRC, STUB, {"tgt": 0x604398f1})
    check(len(stub) <= 0x40 and m[o(STUB):o(STUB) + 0x40] == b"\xff" * 0x40, "stub space not free")
    jmp = patch_aspect.assemble_syms("jmp stub", SITE, {"stub": STUB})
    check(len(jmp) == 5, "jump is not 5 bytes")
    m[o(STUB):o(STUB) + len(stub)] = stub
    m[o(SITE):o(SITE) + len(SITE_STOCK)] = jmp + b"\xcb" * (len(SITE_STOCK) - 5)
    return len(stub)


def patch(main):
    m = bytearray(main)
    n = patch_at(m, BASE)
    print("  sensor modes MSSC/MSPD (120 fps) -> LSSC/LSPD (240 fps) (stub %d B at %#x)" % (n, STUB))
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
