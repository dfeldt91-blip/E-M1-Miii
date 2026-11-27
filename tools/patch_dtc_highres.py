#!/usr/bin/env python3
"""Allow Digital Teleconverter in High Res / special drive modes (EXPERIMENTAL).
  python3 tools/patch_dtc_highres.py IN.BIN OUT.BIN [--version 0x1621]

MODE_DIGITAL_ZOOM_ONOFF (0x22) restriction record 0x60492e24 has 10 rules at
0x60488dd0. Rules 2..6 force DTC off when MODE_EXPOSE (0x18, the drive-mode
setting) is one of the five special drive values 0xb9..0xbd. Those values are
the High Res / other special drive modes; stock therefore forbids combining
DTC with High Res Shot.

Each rule is {u32 cond, u16 n, u32 map, u16 n}; the shared map 0x60470fc0 is
{0->0, 1->0} ("force off"). This tool repoints the map field of rules 2..6 at
the existing identity map 0x60480ee4 {0->0, 1->1}, so the user's DTC setting is
left untouched in those drive modes. Conditions and maps are shared with other
settings, so only the five rule-entry map pointers change (15 bytes differ in
stock 1.6; the high byte of each pointer is already 0x60).

This is the same technique used by tools/patch_hhrs_flash.py (MODE_STB_GENERAL
rule 3). It does NOT change the crop math, the 2x ceiling (0x21), or the High
Res capture path. Whether the resulting crop uses the stacked buffer has not
been proven statically; test on camera before trusting the output resolution.

Camera-tested on build 1.F: selecting High Res Shot from the Drive menu normally
(do not force 0x2f2 directly -- that alone freezes on shot) and switching Digital
Tele on produced an image that played back with no observed issues. The output
dimensions/EXIF were not reported, so the actual crop resolution is still
unmeasured.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
REC = 0x60492e24                 # restriction record for sid 0x22
RULES = 0x60488dd0               # its 16-byte rule entries
FORCE0, IDENT = 0x60470fc0, 0x60480ee4
SPECIAL_VALUES = [0xb9, 0xba, 0xbb, 0xbc, 0xbd]  # 0x18 values, rules 2..6
RULE_INDEXES = list(range(2, 7))


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def off(a):
    return a - BASE


def patch_main(main):
    m = bytearray(main)
    sid, flags, rp, cnt = struct.unpack_from("<HHIH", m, off(REC))
    check((sid, rp, cnt) == (0x22, RULES, 10),
          "MODE_DIGITAL_ZOOM_ONOFF restriction record differs")
    check([struct.unpack_from("<hh", m, off(FORCE0) + 4 * j) for j in range(2)] ==
          [(0, 0), (1, 0)], "force-0 map differs")
    check([struct.unpack_from("<hh", m, off(IDENT) + 4 * j) for j in range(2)] ==
          [(0, 0), (1, 1)], "identity map differs")

    for i, val in zip(RULE_INDEXES, SPECIAL_VALUES):
        o = off(RULES + 16 * i)
        cp, cn, mp, mn = struct.unpack_from("<IHxxIHxx", m, o)
        check(mp == FORCE0 and mn == 2 and cn == 1,
              "rule %d is not the expected force-off rule" % i)
        term = struct.unpack_from("<HHI", m, off(cp))
        check(term == (0x18, val, 0),
              "rule %d condition is not MODE_EXPOSE == %#x" % (i, val))

    for i in RULE_INDEXES:
        struct.pack_into("<I", m, off(RULES + 16 * i) + 8, IDENT)

    print("  MODE_DIGITAL_ZOOM_ONOFF rules 2-6: MODE_EXPOSE %s" %
          ", ".join("%#x" % v for v in SPECIAL_VALUES))
    print("  map %#x (force off) -> %#x (identity) in %d rules" %
          (FORCE0, IDENT, len(RULE_INDEXES)))
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
