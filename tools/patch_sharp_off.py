#!/usr/bin/env python3
"""Sharpness as a linear scale: -2 off, -1 25 %, 0 50 %, +1 75 %, +2 100 % (EXPERIMENTAL, E-M1 III 1.6).

  MN10300_BIN=... python3 tools/patch_sharp_off.py IN.BIN OUT.BIN [--version 0x1680]

The ISP sharpening gain helper (0x603dae.. - 0x603db002, same shape as the E-P7's 0x603ab8fe,
caduceus-ep7 docs/SHARPENING_OFF.md): index = base[class] + Sharpness (request +1795, signed byte,
loaded at 0x603daf60), clamped to 0..10; gain = table[index] x amount / 256 (table 0x6051b4a8
[0, 16, 64, 112, 184, 256, 256, ...], or 0x6051b626 / the +1811 variant), then x d1 / 256 and capped
at 255, stored through (44,SP) +2 at 0x603dafff. Base tables 0x6051b49c = 6,5,4,4,6,7 and
0x6051b4a2 = 5,5,4,4,5,6. Flat/Log jobs (key 0x7d0/0x7d1) take Sharpness + 4 at 0x603daf4c instead.
Stock -2 still leaves 16..256/256 of the gain (index 2..5 by class).

Patch (normal path only; Flat/Log unchanged):
- 0x603daf60 `movbu (1795,a0),d2; extb d2` -> `mov 2,d2` + nops: the gain is computed as at +2.
- 0x603dafee (`mov (44,sp),a0; movbu (55,sp),d0`, final gain in d1) -> jmp stub: unless the job
  key is 0x7d0/0x7d1, d1 = d1 x (Sharpness + 2) / 4 (Sharpness clamped to -2..+2); then the two
  replaced instructions and jmp 0x603daff3.
So +2 = stock +2 (100 %), +1 75 %, 0 50 %, -1 25 %, -2 0 (no sharpening, a gain stock firmware
also uses for some art filters). Settings, menus and EXIF keep the -2..+2 values.

The special-job early-out at 0x603da879 jumps straight to END with d1 = 0, without ever
setting (48,SP) (HDR takes this path after the shutter release). The old stub dereferenced
that uninitialised slot on every Sharpness value, so the camera rebooted. The stub now
returns immediately when d1 == 0: there is no gain to scale, so it never reads (48,SP)
on the early-out path.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
LOAD, LOAD_STOCK = 0x603daf60, bytes.fromhex("fa48030712")      # movbu (1795,a0),d2 ; extb d2
END, END_STOCK, BACK = 0x603dafee, bytes.fromhex("5c2cf8b837"), 0x603daff3
FLAT_STOCK = (0x603daf3b, bytes.fromhex("5c3070fac8d007c808fac8d107"))
STUB = 0x600d6a40
SRC = """cmp 0,d1
beq 9f
mov (48,sp),a0
mov (a0),d0
cmp 0x7d0,d0
beq 9f
cmp 0x7d1,d0
beq 9f
mov (12,sp),a0
movbu (1795,a0),d0
extb d0
add 2,d0
cmp 0,d0
bge 1f
clr d0
1:
cmp 4,d0
ble 2f
mov 4,d0
2:
mulu d0,d1
lsr 2,d1
9:
mov (44,sp),a0
movbu (55,sp),d0
jmp back"""


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_at(m, base):
    """M: bytearray holding the base section at runtime address BASE."""
    import patch_aspect
    o = lambda a: a - base  # noqa: E731
    check(bytes(m[o(LOAD):o(LOAD) + 5]) == LOAD_STOCK, "sharpness load at %#x differs" % LOAD)
    check(bytes(m[o(END):o(END) + 5]) == END_STOCK, "gain store at %#x differs" % END)
    a, b = FLAT_STOCK
    check(bytes(m[o(a):o(a) + len(b)]) == b, "Flat/Log test at %#x differs" % a)
    stub = patch_aspect.assemble_syms(SRC, STUB, {"back": BACK})
    check(len(stub) <= 0x40 and m[o(STUB):o(STUB) + 0x40] == b"\xff" * 0x40, "stub space not free")
    jmp = patch_aspect.assemble_syms("jmp stub", END, {"stub": STUB})
    check(len(jmp) == 5, "jump is not 5 bytes")
    m[o(STUB):o(STUB) + len(stub)] = stub
    m[o(END):o(END) + 5] = jmp
    m[o(LOAD):o(LOAD) + 5] = bytes.fromhex("8a02cbcbcb")             # mov 2,d2 ; nop x3
    return len(stub)


def patch(main):
    m = bytearray(main)
    n = patch_at(m, BASE)
    print("  sharpness -2..+2 -> 0/25/50/75/100 %% (stub %d B at %#x)" % (n, STUB))
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
