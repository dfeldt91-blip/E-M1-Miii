#!/usr/bin/env python3
"""Focus stacking with any lens (E-M1 Mark III, official 1.6 / stock 1.5 layout).
  python3 tools/patch_stack_any_lens.py IN.BIN OUT.BIN [--version 0x1601]

fcs_check_focus_stacking_enable (0x606983e3, log string "fcs_check_focus_stacking_enable
stacking") returns 1 only if 0x6021882d (1.6) returns 0 and the lens check 0x602219d6 (1.6)
returns 1:
  606983f7  a0 01   cmp 1,d0
  606983f9  c9 04   bne 0x606983fd      ; lens not in the stacking list -> stays 0
  606983fb  8a 01   mov 1,d2
The base file E1399999_Focus_Stack.BIN (1.5 + this change) has nop nop (cb cb) at 0x606983f9,
so the lens result is ignored; this patch makes the same 2-byte change. Same address in 1.6.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
SITE = 0x606983f9
CONTEXT = bytes.fromhex("14a001c9048a01fca5ec1e1c62faed0002c811")    # 0x606983f6..
NEW = b"\xcb\xcb"


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_main(main):
    m = bytearray(main)
    o = SITE - 3 - BASE
    check(bytes(m[o:o + len(CONTEXT)]) == CONTEXT, "fcs_check_focus_stacking_enable differs")
    m[SITE - BASE:SITE - BASE + 2] = NEW
    print("  focus stacking lens check at %#x: bne -> nop nop" % SITE)
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    plains = [b["plain"] for b in blocks]
    plains[0] = patch_main(plains[0])
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), plains[i], bytes(tail))
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
