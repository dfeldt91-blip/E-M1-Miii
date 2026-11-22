#!/usr/bin/env python3
"""Per-picture-mode Highlight & Shadow control (EXPERIMENTAL, UNTESTED, E-M1 Mark III 1.6).

   python3 tools/patch_per_mode_tone.py IN.BIN OUT.BIN [--version 0x1699]

Data-only patch: adds TONE_CONTROL_HIGH/MIDDLE/LOW (0x17f/0x2b2/0x17e) to the
Picture Mode (0x6f) entry of the component table at 0x60469ca2, so the mode
bundle includes the H&S adjustment. See docs/PER_MODE_TONE.md.

UNTESTED: whether the settings core save/restores these per mode, and whether
the menus expose per-mode editing, is NOT verified. Camera testing required.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
ENTRY = 0x60469ca2          # component-table entry for picture mode (0x6f)
STOCK = bytes([0x6f,0x00,0x6f,0x00,0xaf,0x06,0x80,0x0c] + [0x00]*26)
NEW = bytes([0x6f,0x00,0x6f,0x00,0xaf,0x06,0x7f,0x01,0xb2,0x02,0x7e,0x01,0x80,0x0c] + [0x00]*20)


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    m = bytearray(main)
    check(bytes(m[off(ENTRY):off(ENTRY) + 34]) == STOCK,
          "picture-mode component entry at %#x differs from stock" % ENTRY)
    m[off(ENTRY):off(ENTRY) + 34] = NEW
    print("  added TONE_CONTROL (0x17f/0x2b2/0x17e) to picture-mode component list (UNTESTED)")
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
    print("wrote %s  sha256 %s  (EXPERIMENTAL/UNTESTED)" % (dst, __import__("hashlib").sha256(out).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
