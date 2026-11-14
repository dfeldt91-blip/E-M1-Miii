#!/usr/bin/env python3
"""Color Profile settings in the normal menu (EXPERIMENTAL, E-M1 Mark III, 1.5-based).

  python3 tools/patch_profile_menu.py IN.BIN OUT.BIN --test1 [--version 0x1596]

IN.BIN is normally the output of patch_picture_modes.py --repurpose (Custom renders as Color
Profile, pipeline 11).

GUI menu model (blob B, runtime addresses; three GUI copies of every table):
  page table      {u16 flags, u16 rows (7), u32 row list}; row list = u16 setting ids
                  (Shooting Menu 1: 0xd1d Reset, 0x6f Picture Mode, 0xa Quality, 0x10d Aspect,
                  0x22 Digital Tele, 0xcc1 Drive, 0x1dd Interval) at 0x611ca818
  label tables    12-byte {u32 setting, u16 4, u16 string id, u32 cond}: item title, and a
                  second table with the help text
  descriptors     per tab {u16 setting, u16 n, u32 option list}; options 12-byte
                  {u32 value, u16 type, u16 string id, u32 cond}; type 4 = string id label,
                  type 1 = ASCII label pointer in the last field with the string id as unit

--test1: Shooting Menu 1 row "Digital Tele-converter" (0x22) -> MODE_COLOR_CREATOR_2_VIVID_SET1_1
(0x399, -5..+5, title "Saturation"); row "Intrvl. Sh./Time Lapse" (0x1dd) ->
MODE_COLOR_CREATOR_2_SELECT (0x386, 0..3, title "Color Profile 1").
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF, BLOB_END = 0x60c6c000, 0xc4afe0, 0x612f1000
FREE_LO, FREE_HI = 0x600d6b80, 0x600d7000      # 0xff padding, unused by the other patches
EMPTY_STR = 8                                   # empty English string (unit for type-1 labels)
PAGE1 = [0xd1d, 0x6f, 0xa, 0x10d, 0x22, 0xcc1, 0x1dd]
PAGE1_ALT = [0xd1d, 0x647, 0xa, 0x10d, 0x22, 0xcc1, 0x1dd]

# (old setting, new setting, title string, title label of old, help label of old, values)
SWAPS = [
    (0x22, 0x399, 227, 0x16b, 0x194, list(range(-5, 6))),
    (0x1dd, 0x386, 2749, 0x5a0, 0x5a1, [0, 1, 2, 3]),
]


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def find_all(buf, pat, align):
    out, i = [], buf.find(pat)
    while i >= 0:
        if i % align == 0:
            out.append(i)
        i = buf.find(pat, i + 1)
    return out


def patch(main):
    m = bytearray(main)
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    check(set(m[off(FREE_LO - 16):off(FREE_HI)]) == {0xff}, "free area not 0xff")

    # page rows
    rows = []
    for pg in (PAGE1, PAGE1_ALT):
        rows += find_all(gui, struct.pack("<7H", *pg), 2)
    check(len(rows) >= 2, "Shooting Menu 1 row lists not found (%d)" % len(rows))
    for r in rows:
        for k, sid in enumerate(struct.unpack_from("<7H", gui, r)):
            for old, new, *_ in SWAPS:
                if sid == old:
                    struct.pack_into("<H", gui, r + 2 * k, new)

    # option lists + ASCII labels in free space
    free = FREE_LO
    lists = {}
    for old, new, title, tl, hl, vals in SWAPS:
        strs = {}
        for v in vals:
            s = (("%+d" % v) if v else "0") if min(vals) < 0 else str(v)
            strs[v] = free
            b = s.encode() + b"\0"
            m[off(free):off(free) + len(b)] = b
            free += (len(b) + 3) & ~3
        lists[new] = free
        for v in vals:
            m[off(free):off(free) + 12] = struct.pack("<IHHI", v & 0xffffffff, 1, EMPTY_STR, strs[v])
            free += 12
        free = (free + 15) & ~15
    check(free <= FREE_HI, "free area overflow")

    nlab = ndesc = 0
    for old, new, title, tl, hl, vals in SWAPS:
        # titles and help texts
        for lab, newlab in ((tl, title), (hl, None)):
            for i in find_all(gui, struct.pack("<IHH", old, 4, lab), 4):
                struct.pack_into("<I", gui, i, new)
                if newlab is not None:
                    struct.pack_into("<H", gui, i + 6, newlab)
                nlab += 1
        # descriptors {old, 2, list(Off/On)}
        for i in find_all(gui, struct.pack("<HH", old, 2), 4):
            ptr = struct.unpack_from("<I", gui, i + 4)[0]
            if not (BLOB_B <= ptr < BLOB_B + len(gui)):
                continue
            e = [struct.unpack_from("<IHHI", gui, ptr - BLOB_B + 12 * j) for j in range(2)]
            if [x[0] for x in e] == [0, 1] and all(x[1] == 4 for x in e):
                struct.pack_into("<HHI", gui, i, new, len(vals), lists[new])
                ndesc += 1
    check(nlab >= 3 and ndesc >= 3, "labels %d / descriptors %d too few" % (nlab, ndesc))

    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  rows %d, labels %d, descriptors %d, data %#x-%#x, blob B %#x -> %#x"
          % (len(rows), nlab, ndesc, FREE_LO, free, csz, len(c)))
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
