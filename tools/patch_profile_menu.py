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
Camera: both rows shown with their values, but could not be opened.

--test2: test1 + the "is this setting changeable" check 0x608d522f (blob A; nonzero = yes; used by
the menu item opener 0x60df667c through 0x6085c41b) answers yes for all Color/Mono Profile
settings 0x386-0x3e8. Without it they fall through to a group test (0x602ca813) that refuses them.
Camera: still could not be opened (another check in the generic item path).

--test3: no row swaps. Custom's Picture Mode submenu items are virtual: handler 0x60df7837 maps
each (SHARP/CONTRAST/SATURATION/TONE/EFFECT/MONOTONEFILTER/MONOTONECOLOR_CUSTOM) to a real setting
by Custom's base mode (setting 0xd3) through REMAP {u16 item, u32 list, u16 n} lists of
{u32 base GUI value, u16 real setting}. Custom renders as Color Profile (patch_picture_modes
--repurpose), so the base mode no longer matters for the image and selects a channel group instead:
Vivid/Natural/Muted/Portrait -> Contrast/Sharpness/Saturation = channels 1-3/4-6/7-9/10-12 of
preset 1 (VIVID_SET1_n); i-Finish -> CC2 contrast/sharpness SET1; Monotone -> Monochrome Profile
contrast/sharpness/filter/tint SET1. Keeps the test2 hook.
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
BLOB_A, BLOB_A_OFF = 0x60803000, 0x7e1fe0
CHG_CHECK, CHG_STOCK = 0x608d522f, bytes.fromhex("f1e20cfadae513")   # mov d0,a2; clr d3; cmp 5093,a2
CHG_STUB = 0x600d6c80
REMAP = 0x611cfdf0
SET1 = lambda ch: 0x399 + ch - 1                        # MODE_COLOR_CREATOR_2_VIVID_SET1_ch
# item -> {base GUI value: new real setting}
REMAP_NEW = {
    0xcd: {0: SET1(1), 1: SET1(4), 2: SET1(7), 5: SET1(10), 7: 0x38a, 3: 0x3cb},   # CONTRAST_CUSTOM
    0xce: {0: SET1(2), 1: SET1(5), 2: SET1(8), 5: SET1(11), 7: 0x387, 3: 0x3c8},   # SHARP_CUSTOM
    0xcf: {0: SET1(3), 1: SET1(6), 2: SET1(9), 5: SET1(12)},                       # SATURATION_LEVEL_CUSTOM
    0xd1: {3: 0x3d5},                                                              # filter -> mono filter
    0xd2: {3: 0x3d2},                                                              # tint -> mono tint
}
CHG_SRC = """cmp 0x386,d0
bcs orig
cmp 0x3e9,d0
bcc orig
mov 1,d0
ret [d2,d3,a2],28
orig:
mov d0,a2
clr d3
cmp 5093,a2
jmp back"""
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

    if "--test3" in sys.argv:
        n = 0
        for k in range(7):
            item, lp, cnt = struct.unpack_from("<HxxIH", gui, REMAP - BLOB_B + 12 * k)
            for j in range(cnt):
                base = struct.unpack_from("<I", gui, lp - BLOB_B + 8 * j)[0]
                if base in REMAP_NEW.get(item, {}):
                    struct.pack_into("<H", gui, lp - BLOB_B + 8 * j + 4, REMAP_NEW[item][base])
                    n += 1
        check(n == 18, "remap entries patched: %d" % n)
        print("  Custom remap: %d entries -> Color/Mono Profile settings" % n)
    rows = []
    if "--test3" in sys.argv:
        SW = []
    else:
        SW = SWAPS
    # page rows
    for pg in (PAGE1, PAGE1_ALT):
        rows += find_all(gui, struct.pack("<7H", *pg), 2) if SW else []
    check(len(rows) >= 2 or not SW, "Shooting Menu 1 row lists not found (%d)" % len(rows))
    for r in rows:
        for k, sid in enumerate(struct.unpack_from("<7H", gui, r)):
            for old, new, *_ in SW:
                if sid == old:
                    struct.pack_into("<H", gui, r + 2 * k, new)

    # option lists + ASCII labels in free space
    free = FREE_LO
    lists = {}
    for old, new, title, tl, hl, vals in SW:
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
    for old, new, title, tl, hl, vals in SW:
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
    check(not SW or (nlab >= 3 and ndesc >= 3), "labels %d / descriptors %d too few" % (nlab, ndesc))

    if "--test2" in sys.argv or "--test3" in sys.argv:
        import patch_aspect
        check(set(m[off(CHG_STUB):off(CHG_STUB + 0x40)]) == {0xff}, "stub area not free")
        acsz = struct.unpack_from("<I", m, BLOB_A_OFF + 16)[0]
        a = bytearray(olycompress.unpack(m, BLOB_A_OFF))
        check(bytes(a[CHG_CHECK - BLOB_A:CHG_CHECK - BLOB_A + 7]) == CHG_STOCK, "check entry differs")
        stub = patch_aspect.assemble_syms(CHG_SRC, CHG_STUB, {"back": CHG_CHECK + 7})
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
    if len(argv) < 3 or not any(x in argv for x in ("--test1", "--test2", "--test3")):
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
