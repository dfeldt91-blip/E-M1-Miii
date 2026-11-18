#!/usr/bin/env python3
"""Bleach Bypass II without its softening (TEST, E-M1 Mark III 1.6). Base section only.

  python3 tools/patch_bleach2.py IN.BIN OUT.BIN --bit|--pass|--detail|--params [--version 0x1720]

Bleach Bypass II (job key 0x0102007b) differs from Bleach Bypass I in a few places
(docs/ART_FILTERS.md). Which one softens the photo is not known yet, so each test removes one:

--bit   0x603ddb0d: `cmp 0x0102007b,d0; bne` sets bit 28 of request control word +8 only for
        Bleach Bypass II (the colour stage 0x603def13 tests that bit). The key becomes 0x010f007b
        (no such job), so the bit stays clear as for every other mode.
--pass  Photo chain (handler 0x60384d7f, live-view flag job +11320 == 0): slot {0x60385e18,
        0x60385f31}, then the extra pass 0x603870db (own buffers, runs last). The second slot is
        dropped: `mov 0x603870db,d1; jmp 0x60384f0a` -> `mov 1,d3; jmp 0x60384f10` (the state the
        stock path reaches after storing it). Live view never runs that pass.
--detail 0x603ce1a8 returns 0 for Grainy I/II, Vintage II and Bleach Bypass II (`cmp 0x102007b,d3` at
        0x603ce1d4), else 1 unless ISO-dependent cases; callers store it at job +1862 (likely the
        fine-detail / sharpening stage). The Bleach II operand becomes 0x10f007b, so it returns 1.
        (1.720 --bit and 1.721 --pass made no visible difference.)
--params 0x603e3d98 (hash 0x6053ea8c on key-11) picks a parameter-set index per pass; Bleach II's
        handler 0x603e3e89 returns 34 / 35 for passes 0xa01 / 0xa02. Its entry is pointed at the
        default 0x603e3ef4 (the index other filters get). (1.734 --detail: no change.)
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
BIT_SITE, BIT_STOCK, BIT_NEW = 0x603ddb0d, bytes.fromhex("fcc87b000201"), bytes.fromhex("fcc87b000f01")
PASS_SITE, PASS_STOCK = 0x60384dfc, bytes.fromhex("fccddb703860cc0801")
DETAIL_SITE, DETAIL_STOCK, DETAIL_NEW = 0x603ce1d4, bytes.fromhex("fccb7b000201"), bytes.fromhex("fccb7b000f01")
PARAM_SLOT, PARAM_STOCK, PARAM_DEFAULT = 0x6053eaa4, (0x102007b - 11, 0x603e3e89), 0x603e3ef4
PASS_NEW = bytes.fromhex("8f01") + b"\xcc" + struct.pack("<h", 0x60384f10 - (PASS_SITE + 2)) + b"\xcb" * 4


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main, which):
    m = bytearray(main)
    o = lambda a: a - BASE  # noqa: E731
    if "bit" in which:
        check(bytes(m[o(BIT_SITE):o(BIT_SITE) + 6]) == BIT_STOCK, "Bleach II bit-28 compare differs")
        m[o(BIT_SITE):o(BIT_SITE) + 6] = BIT_NEW
        print("  Bleach Bypass II: request +8 bit 28 no longer set")
    if "pass" in which:
        check(bytes(m[o(PASS_SITE):o(PASS_SITE) + 9]) == PASS_STOCK, "Bleach II chain differs")
        check(len(PASS_NEW) == 9, "replacement length")
        m[o(PASS_SITE):o(PASS_SITE) + 9] = PASS_NEW
        print("  Bleach Bypass II: photo chain without the final pass 0x603870db")
    if "detail" in which:
        check(bytes(m[o(DETAIL_SITE):o(DETAIL_SITE) + 6]) == DETAIL_STOCK, "Bleach II detail compare differs")
        m[o(DETAIL_SITE):o(DETAIL_SITE) + 6] = DETAIL_NEW
        print("  Bleach Bypass II: detail flag (job +1862) as for other filters")
    if "params" in which:
        check(struct.unpack_from("<II", m, o(PARAM_SLOT)) == PARAM_STOCK, "Bleach II parameter-set entry differs")
        struct.pack_into("<I", m, o(PARAM_SLOT) + 4, PARAM_DEFAULT)
        print("  Bleach Bypass II: default parameter set instead of 34 / 35")
    return bytes(m)


def main(argv):
    which = [w for w in ("bit", "pass", "detail", "params") if "--" + w in argv]
    if len(argv) < 3 or not which:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_main = patch(blocks[0]["plain"], which)
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
