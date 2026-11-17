#!/usr/bin/env python3
"""240 fps High Speed movie (EXPERIMENTAL, E-M1 Mark III 1.6). Stage 1: sensor mode.

  MN10300_BIN=... python3 tools/patch_hs240.py IN.BIN OUT.BIN [--version 0x1697]

Stock High Speed movie (FHD 120 fps) runs the sensor in MSSC (120 fps). The sensor driver (cam.c,
status names at 0x6160edb3, jump table 0x6160efbc) also has an LSSC state (240 fps), and the
exposure code picks 240 fps live-view rates (0x604325b7.., AE tables 0xbf00/0xbf01/0xbf0a/0xbf0b).
Cam command mode numbers (0x6013cd3c, table 0x601cd4ac): 0 HSSC, 1 MSSC, 2 LSSC, 3 CLIP, 4 HSHR,
5 MSHR, 6 4K, 7 C4K, 8 PD, 9 MSPD, 10 LSPD, 11 HQ, 12 FULL, 13 FULL_LQ.

The exposure movie set-up 0x60437545.. copies the current capture mode (0x62167f30) into its request
(24,SP) and then asks the debug override 0x60445254 (shell command "exp movie cap N", byte
0x6216c4ac): when (16,a2) == 1 or (12,a2) == 3 and the override is set, it replaces the mode
(cap 5/6 "LSSC AB/A field" -> 2).

Patch: after that call (0x604375e7), a stub keeps the override and, with the same condition and no
override, turns mode 1 (MSSC) into 2 (LSSC), as "exp movie cap 5" would.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
SITE, SITE_STOCK, BACK = 0x604375e7, bytes.fromhex("14a001c90758305c1860"), 0x604375f1
CALL_STOCK = (0x604375d7, bytes.fromhex("f8020cf806103c2030dd74dc0000"))   # args + call 0x60445254
STUB = 0x600d6ac0
SRC = """extbu d0
cmp 1,d0
bne 1f
mov (48,sp),d0
mov (24,sp),a0
mov d0,(a0)
jmp back
1:
mov (16,a2),d1
cmp 1,d1
beq 2f
mov (12,a2),d0
cmp 3,d0
bne 9f
2:
mov (24,sp),a0
mov (a0),d0
cmp 1,d0
bne 9f
mov 2,d0
mov d0,(a0)
9:
jmp back"""


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_at(m, base):
    """M: bytearray holding the base section at runtime address BASE."""
    import patch_aspect
    o = lambda a: a - base  # noqa: E731
    check(bytes(m[o(SITE):o(SITE) + len(SITE_STOCK)]) == SITE_STOCK, "override use at %#x differs" % SITE)
    a, b = CALL_STOCK
    check(bytes(m[o(a):o(a) + len(b)]) == b, "override call at %#x differs" % a)
    stub = patch_aspect.assemble_syms(SRC, STUB, {"back": BACK})
    check(len(stub) <= 0x40 and m[o(STUB):o(STUB) + 0x40] == b"\xff" * 0x40, "stub space not free")
    jmp = patch_aspect.assemble_syms("jmp stub", SITE, {"stub": STUB})
    check(len(jmp) == 5, "jump is not 5 bytes")
    m[o(STUB):o(STUB) + len(stub)] = stub
    m[o(SITE):o(SITE) + len(SITE_STOCK)] = jmp + b"\xcb" * (len(SITE_STOCK) - 5)
    return len(stub)


def patch(main):
    m = bytearray(main)
    n = patch_at(m, BASE)
    print("  High Speed movie sensor MSSC (120 fps) -> LSSC (240 fps) (stub %d B at %#x)" % (n, STUB))
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
