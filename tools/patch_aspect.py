#!/usr/bin/env python3
"""
patch_aspect.py - E-M1 Mark III aspect-ratio experiments (toward XPan 65:24).
EXPERIMENTAL, NOT TESTED ON A CAMERA.

  python3 tools/patch_aspect.py IN.BIN OUT.BIN --stage1 [--version 0x1530]

Stage 1 (diagnostic): drop 3:4 from the Image Aspect validator list.
  Record 0x604dc954 (setting 0x10d MODE_ASPECT_RATIO), u8 list 0x604d93da =
  [1,3,2,4,9]; byte count 5 -> 4 leaves [1,3,2,4]. If 3:4 disappears from the
  menu / SCP, validator edits drive the menus on this body (as on the E-P7).

--version sets the main block's header/trailer version (BCD) so the card
updater does not skip the file as "same version as installed".

Every byte the patch relies on is checked first.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
ASPECT_REC = 0x604dc954
STOCK_ASPECT_REC = bytes.fromhex("0d018000da934d60000000000500010000010000")
ASPECT_LIST = 0x604d93da


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def stage1(m):
    check(bytes(m[off(ASPECT_REC):off(ASPECT_REC) + 20]) == STOCK_ASPECT_REC, "aspect record differs from stock")
    check(list(m[off(ASPECT_LIST):off(ASPECT_LIST) + 5]) == [1, 3, 2, 4, 9], "aspect list differs from stock")
    struct.pack_into("<H", m, off(ASPECT_REC) + 12, 4)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    b0 = blocks[0]
    check(b0["info"]["model"] == 0x1390 and b0["info"]["flags"] == 0x100, "not the E-M1 III main block")
    m = bytearray(b0["plain"])
    check("--stage1" in argv, "no stage selected")
    stage1(m)
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        plain = bytes(m) if i == 0 else b["plain"]
        if i == 0 and ver is not None:
            check(all(((ver >> s) & 0xf) <= 9 for s in (0, 4, 8, 12)), "--version must be BCD")
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), plain, bytes(tail))
    check(len(out) == len(fw), "size changed")
    open(dst, "wb").write(out)
    again = olyfw.unpack_blocks(open(dst, "rb").read())
    check(all(b["stored"] == b["calc"] for b in again), "output checksum check failed")
    a0 = again[0]["plain"]
    cnt = struct.unpack_from("<H", a0, off(ASPECT_REC) + 12)[0]
    print("wrote %s  sha256 %s" % (dst, hashlib.sha256(out).hexdigest()))
    print("  aspect values now: %s" % list(a0[off(ASPECT_LIST):off(ASPECT_LIST) + cnt]))
    print("  main block version: %#06x" % struct.unpack_from("<H", again[0]["head"], 16)[0])
    print("  file bytes changed: %d" % sum(1 for x, y in zip(fw, out) if x != y))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
