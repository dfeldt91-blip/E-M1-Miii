#!/usr/bin/env python3
"""Custom Modes C1-C4 remember photo / video (EXPERIMENTAL, E-M1 Mark III 1.6). Stage 1: menu.

  MN10300_BIN=... python3 tools/patch_cmode_video.py IN.BIN OUT.BIN --test1 [--version 0x1681]

Stock: C1-C4 already save and recall the movie settings, but "Assign to Custom Mode" cannot be used
while the mode dial is on movie, and a C position is always a photo mode.
GUI ids: menu item 0xd1d "Reset / Custom Modes" (title string 0xc4c), its entries 0x13df "Assign to
Custom Mode" (0xc4d) and 0x13e0 "Recall from Custom Mode" (0xc4e); label records
{u32 id, u16 4, u16 string, u32 cond} e.g. 0x611ae8e4 / 0x611bd5e0. Shooting mode: setting 0x1a
MODE_CAMERA (movie exposure modes 76, 77, 89, 90 = MODE_EXPOSE_MOVIE_SELECT); core mode setter
0x602caa2c (mcon_if_camera_set).

--test1 (diagnostic): the menu's "is this setting changeable" check 0x608d522f (blob A; nonzero =
yes) answers yes for 0xd1d, 0x13df and 0x13e0. Shows whether this check is what greys out
Assign to Custom Mode in movie mode.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
BLOB_A, BLOB_A_OFF, BLOB_B_OFF = 0x60803000, 0x7e1fe0, 0xc4afe0
CHG_CHECK, CHG_STOCK = 0x608d522f, bytes.fromhex("f1e20cfadae513")   # mov d0,a2; clr d3; cmp 5093,a2
CHG_STUB = 0x600d6a80
CHG_SRC = """cmp 0xd1d,d0
beq yes
cmp 0x13df,d0
beq yes
cmp 0x13e0,d0
beq yes
mov d0,a2
clr d3
cmp 0x13e5,a2
jmp back
yes:
mov 1,d0
ret [d2,d3,a2],28"""


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    import patch_aspect
    m = bytearray(main)
    check(set(m[off(CHG_STUB):off(CHG_STUB) + 0x40]) == {0xff}, "stub area not free")
    acsz = struct.unpack_from("<I", m, BLOB_A_OFF + 16)[0]
    a = bytearray(olycompress.unpack(m, BLOB_A_OFF))
    check(olycompress.pack(bytes(a)) == bytes(m[BLOB_A_OFF + 32:BLOB_A_OFF + 32 + acsz]),
          "blob A does not recompress identically")
    check(bytes(a[CHG_CHECK - BLOB_A:CHG_CHECK - BLOB_A + 7]) == CHG_STOCK, "check entry differs")
    stub = patch_aspect.assemble_syms(CHG_SRC, CHG_STUB, {"back": CHG_CHECK + 7})
    check(len(stub) <= 0x40, "stub too long")
    m[off(CHG_STUB):off(CHG_STUB) + len(stub)] = stub
    a[CHG_CHECK - BLOB_A:CHG_CHECK - BLOB_A + 7] = (b"\xdc" + struct.pack("<i", CHG_STUB - CHG_CHECK)
                                                    + b"\xcb\xcb")
    ca = olycompress.pack(bytes(a))
    check(len(ca) <= BLOB_B_OFF - (BLOB_A_OFF + 32), "blob A does not fit")
    old_end = BLOB_A_OFF + 32 + acsz
    m[BLOB_A_OFF + 32:BLOB_A_OFF + 32 + len(ca)] = ca
    if len(ca) < acsz:
        m[BLOB_A_OFF + 32 + len(ca):old_end] = b"\xff" * (old_end - BLOB_A_OFF - 32 - len(ca))
    struct.pack_into("<I", m, BLOB_A_OFF + 16, len(ca))
    check(olycompress.unpack(m, BLOB_A_OFF) == bytes(a), "blob A does not decode to the edit")
    print("  changeable hook %#x -> stub %#x (%d B); blob A %#x -> %#x" % (CHG_CHECK, CHG_STUB, len(stub), acsz, len(ca)))
    return bytes(m)


def main(argv):
    if len(argv) < 3 or "--test1" not in argv:
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
