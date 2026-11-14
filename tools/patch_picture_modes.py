#!/usr/bin/env python3
"""
patch_picture_modes.py - add Color Profile and Monochrome Profile to the
E-M1 Mark III Picture Mode list (data-only patch, EXPERIMENTAL, UNTESTED ON A CAMERA).

  python3 tools/patch_picture_modes.py IN.BIN OUT.BIN [--report] [--version 0x1510]

--aspect-test (diagnostic) drops 3:4 from the Image Aspect validator list
(record 0x604dc954: byte count 5 -> 4, list [1,3,2,4,9] -> [1,3,2,4]) to show
whether main-block validator edits reach the camera's menus.

--version sets the version field (BCD, e.g. 0x1510 = 1.5.1.0) in the main code
block's header and trailer, so a successful install can be told apart and so
the camera does not treat the file as the version it already has.

What it changes (main code block, component 0x100, all addresses = runtime
addresses, block offset = address - 0x60021020):

  * validator record of setting 0x6f (MODE_COLORTONE, the Picture Mode) at
    0x604da7bc: list pointer, alt (GUI value) pointer, byte count 1664 -> 1792
  * writes a new 28-entry list at 0x600d7000 (stock 26 entries + the
    "pipeline mode 11" (Color Profile) and "12" (Mono Profile) entries copied
    from the stock dial-less list DIAL_NON, setting 0x385)
  * writes a new 28-entry GUI value list at 0x600d7700 (stock 26 values +
    0x36 = 54 Color Profile, 0x39 = 57 Mono Profile, as in DIAL_NON's alt list)

0x600d7000-0x600d7800 is 0xff padding inside the base section that the boot
code copies from flash (0x60030000-0x600e0800); no code reference into it was
found (docs/FINDINGS.md).

Every byte the patch relies on is checked first; the script refuses to write
anything if the input is not the expected firmware layout.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020          # runtime address of main block offset 0
REC = 0x604da7bc           # validator record of sid 0x6f
STOCK_REC = bytes.fromhex("6f008000f4c44b6034e84a608006400000060000")
LIST, ALT = 0x604bc4f4, 0x604ae834      # stock 0x6f list / alt list
NON_LIST, NON_ALT = 0x604c3df4, 0x604aefc4   # DIAL_NON list / alt list
NEW_LIST, NEW_ALT = 0x600d7000, 0x600d7700
FREE_LO, FREE_HI = 0x600d6ff0, 0x600d7800    # must be all 0xff (16-byte guard)
# --low: put the lists at 0x600d6400 instead, so the patch can go on top of patch_aspect.py
# output (which uses 0x600d7000-0x600d7800 and stubs up to 0x600d62e0)
if "--low" in sys.argv:
    NEW_LIST, NEW_ALT = 0x600d6400, 0x600d6b00
    FREE_LO, FREE_HI = 0x600d63f0, 0x600d6b80
ELEM, N_STOCK = 64, 26
ASPECT_REC = 0x604dc954
STOCK_ASPECT_REC = bytes.fromhex("0d018000da934d6000000000050001000001000000"[:40])
STOCK_ALT = [7, 0, 1, 2, 5, 3, 6, 0x14, 0x1c, 0x15, 8, 9, 10, 11, 12, 13, 14,
             15, 16, 17, 18, 19, 0x1a, 0x1b, 0x3c, 0x3f]
STOCK_MODES = [7, 1, 2, 3, 4, 5, 6, 8, 10, 9, 100, 101, 102, 103, 104, 105,
               106, 107, 108, 109, 119, 120, 121, 122, 123, 124]


def off(addr):
    return addr - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def aspect_test(m):
    check(bytes(m[off(ASPECT_REC):off(ASPECT_REC) + 20]) == STOCK_ASPECT_REC, "aspect record differs from stock")
    check(list(m[off(0x604d93da):off(0x604d93da) + 5]) == [1, 3, 2, 4, 9], "aspect list differs from stock")
    struct.pack_into("<H", m, off(ASPECT_REC) + 12, 4)


def patch_main(main, aspect=False):
    m = bytearray(main)
    if aspect:
        aspect_test(m)
    check(m[off(REC):off(REC) + 20] == STOCK_REC, "validator record of 0x6f differs from stock")
    stock = [bytes(m[off(LIST) + ELEM * k:off(LIST) + ELEM * (k + 1)]) for k in range(N_STOCK)]
    check([e[0] for e in stock] == STOCK_MODES, "stock Picture Mode list differs")
    alt = list(struct.unpack_from("<%dI" % N_STOCK, m, off(ALT)))
    check(alt == STOCK_ALT, "stock GUI value list differs")
    non = [bytes(m[off(NON_LIST) + ELEM * k:off(NON_LIST) + ELEM * (k + 1)]) for k in range(N_STOCK)]
    non_alt = list(struct.unpack_from("<%dI" % N_STOCK, m, off(NON_ALT)))
    k11 = [k for k, e in enumerate(non) if e[0] == 11]
    k12 = [k for k, e in enumerate(non) if e[0] == 12]
    check(len(k11) == 1 and len(k12) == 1, "DIAL_NON list does not hold one 11 and one 12 entry")
    e11, e12 = non[k11[0]], non[k12[0]]
    check(set(e11[1:]) == {0} and set(e12[1:]) == {0}, "DIAL_NON 11/12 entries are not plain")
    check(non_alt[k11[0]] == 0x36 and non_alt[k12[0]] == 0x39, "DIAL_NON GUI values are not 54/57")
    check(set(m[off(FREE_LO):off(FREE_HI)]) == {0xff}, "target area is not free 0xff padding")

    new_list = b"".join(stock) + e11 + e12
    new_alt = struct.pack("<%dI" % (N_STOCK + 2), *(STOCK_ALT + [0x36, 0x39]))
    m[off(NEW_LIST):off(NEW_LIST) + len(new_list)] = new_list
    m[off(NEW_ALT):off(NEW_ALT) + len(new_alt)] = new_alt
    rec = bytearray(STOCK_REC)
    struct.pack_into("<IIH", rec, 4, NEW_LIST, NEW_ALT, len(new_list))
    m[off(REC):off(REC) + 20] = rec
    return bytes(m), len(new_list), len(new_alt)


# --menu (step 2): the Picture Mode menu option lists (3 descriptors in blob B, {u16 sid, u16 n,
# u32 list} of 12-byte {u32 GUI value, u16 3 = icon, u16 icon id, u32 cond}) and the 32 restriction
# rules of 0x6f (record 0x60492848 -> rules {IF terms, MAP {u16 from, u16 to}} keyed by GUI value)
# only know the 26 stock values. Give both 54 (Color Profile) and 57 (Monochrome Profile):
# menu entries after Color Creator with the Live Control icons 4436 / 4437, and in every rule map the
# target Color Creator (21) gets.
BLOB_B, BLOB_B_OFF, BLOB_END = 0x60c6c000, 0xc4afe0, 0x612f1000
MENU_DESCS = (0x611af718, 0x61206bc8, 0x6128837c)
RULES, N_RULES = 0x60476160, 32
NEW_ICONS = {0x36: 4436, 0x39: 4437}
MENU_AT, MAPS_AT = 0x600d7800, 0x600d2500
TOGGLES = 0x611cfbc0


def patch_menu(main):
    import olycompress
    m = bytearray(main)
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    check(set(m[off(MENU_AT - 16):off(0x600d8000)]) == {0xff}, "menu list area not free")
    check(set(m[off(MAPS_AT - 16):off(0x600d3000)]) == {0xff}, "rule map area not free")
    free = MENU_AT
    for d in MENU_DESCS:
        sid, n, lp = struct.unpack_from("<HHI", gui, d - BLOB_B)
        check((sid, n) == (0x6f, 54), "menu descriptor %#x differs" % d)
        es = [struct.unpack_from("<IHHI", gui, lp - BLOB_B + 12 * k) for k in range(n)]
        check([e[0] for e in es[:10]] == [7, 0, 1, 2, 5, 3, 6, 20, 28, 21] and all(e[1] == 3 for e in es),
              "menu list %#x differs" % lp)
        cond = es[9][3]
        new = es[:10] + [(v, 3, ic, cond) for v, ic in sorted(NEW_ICONS.items())] + es[10:]
        data = b"".join(struct.pack("<IHHI", *e) for e in new)
        m[off(free):off(free) + len(data)] = data
        struct.pack_into("<HI", gui, d - BLOB_B + 2, len(new), free)
        free += (len(data) + 15) & ~15
    check(free <= 0x600d8000, "menu lists overflow")
    maps = {}
    nxt = MAPS_AT
    for k in range(N_RULES):
        r = off(RULES + 16 * k)
        cp, cn, mp, mn = struct.unpack_from("<IHxxIHxx", m, r)
        check(mn == 26, "rule %d map size differs" % k)
        if mp not in maps:
            pairs = [struct.unpack_from("<HH", m, off(mp) + 4 * j) for j in range(mn)]
            check([a for a, b in pairs] == STOCK_ALT, "rule %d map keys differ" % k)
            to21 = dict(pairs)[21]
            pairs += [(v, v if to21 == 21 else to21) for v in sorted(NEW_ICONS)]
            data = b"".join(struct.pack("<HH", a, b) for a, b in pairs)
            m[off(nxt):off(nxt) + len(data)] = data
            maps[mp] = nxt
            nxt += (len(data) + 15) & ~15
        struct.pack_into("<I", m, r + 8, maps[mp])
        struct.pack_into("<H", m, r + 12, 28)
    check(nxt <= 0x600d3000, "rule maps overflow")
    if "--toggles" in sys.argv:
        # step 3: the list builder 0x60df8fa1 keeps a value only if its {GUI value, ONOFF sid} entry in
        # TOGGLES (26 x 8 B) has ONOFF == 1. 54/57 use COLOR_CREATOR_2_SET1_ONOFF 0x40e /
        # MONOCHROME_CREATOR_SET1_ONOFF 0x411, which this body never sets; use Color Creator's 0x24a.
        t = TOGGLES - BLOB_B
        tog = [struct.unpack_from("<II", gui, t + 8 * k) for k in range(26)]
        check(tog[0] == (7, 0x157) and tog[23] == (0x15, 0x24a) and tog[24] == (0x36, 0x40e)
              and tog[25] == (0x39, 0x411), "toggle table differs")
        struct.pack_into("<I", gui, t + 8 * 24 + 4, 0x24a)
        struct.pack_into("<I", gui, t + 8 * 25 + 4, 0x24a)
        print("  toggles: 54/57 -> ONOFF 0x24a")
    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  menu: 3 lists -> 56 entries at %#x-%#x; %d rule maps -> 28 pairs at %#x-%#x; blob B %#x -> %#x"
          % (MENU_AT, free, len(maps), MAPS_AT, nxt, csz, len(c)))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    b0 = blocks[0]
    check(b0["info"]["type"] == "OE" and b0["info"]["model"] == 0x1390 and b0["info"]["flags"] == 0x100,
          "first block is not the E-M1 III main code block")
    new_main, nl, na = patch_main(b0["plain"], aspect="--aspect-test" in argv)
    if "--menu" in argv:
        new_main = patch_menu(new_main)
    ver = None
    if "--version" in argv:
        ver = int(argv[argv.index("--version") + 1], 0)
        check(0 < ver <= 0x9999 and all(((ver >> s) & 0xf) <= 9 for s in (0, 4, 8, 12)),
              "--version must be BCD, e.g. 0x1510")
    out = bytearray()
    for i, b in enumerate(blocks):
        plain = new_main if i == 0 else b["plain"]
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            check(struct.unpack_from("<H", head, 16)[0] == struct.unpack_from("<H", tail, 16)[0],
                  "main block head/tail versions differ")
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), plain, bytes(tail))
    check(len(out) == len(fw), "size changed")
    diff = [i for i in range(len(fw)) if fw[i] != out[i]] if "--report" in argv else None
    with open(dst, "wb") as fh:
        fh.write(out)
    # re-verify the written file
    again = olyfw.unpack_blocks(open(dst, "rb").read())
    check(all(b["stored"] == b["calc"] for b in again), "output checksum check failed")
    rec = again[0]["plain"][off(REC):off(REC) + 20]
    print("wrote %s  sha256 %s" % (dst, hashlib.sha256(out).hexdigest()))
    print("  0x6f record now: %s (list %#x, alt %#x, %d bytes)" % (rec.hex(" "), NEW_LIST, NEW_ALT, nl))
    print("  new list %d bytes at %#x, GUI values %d bytes at %#x" % (nl, NEW_LIST, na, NEW_ALT))
    asp = struct.unpack_from("<H", again[0]["plain"], off(ASPECT_REC) + 12)[0]
    print("  aspect validator bytes: %d %s" % (asp, "(3:4 removed)" if asp == 4 else "(stock)"))
    print("  main block version: %#06x" % struct.unpack_from("<H", again[0]["head"], 16)[0])
    if diff is not None:
        print("  file bytes changed: %d" % len(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
