#!/usr/bin/env python3
"""
patch_aspect.py - E-M1 Mark III aspect-ratio experiments (toward XPan 65:24).
EXPERIMENTAL, NOT TESTED ON A CAMERA.

  python3 tools/patch_aspect.py IN.BIN OUT.BIN --stage1|--stage2a|--stage2b|--stage2c|--stage2d|--stage2e|--stage3|--labeltest|--labeltest2|--titletest [--version 0x1530]

Stage 1 (diagnostic): drop 3:4 from the Image Aspect validator list.
  Record 0x604dc954 (setting 0x10d MODE_ASPECT_RATIO), u8 list 0x604d93da =
  [1,3,2,4,9]; byte count 5 -> 4 leaves [1,3,2,4]. If 3:4 disappears from the
  menu / SCP, validator edits drive the menus on this body (as on the E-P7).

Stage 2a: allow hidden aspect id 6 (stock 7:6, to become 65:24 in stage 3).
  New u8 list [1,3,2,4,9,6] at 0x600d7000 (verified 0xff padding in the base
  section, see docs/PICTURE_MODE_PATCH.md); record list pointer -> 0x600d7000,
  byte count 5 -> 6. No menu label yet (labels live in the LZ4 GUI blob).

Stage 2b: stage 2a + option-list entries so value 6 is selectable and labelled.
  Menu descriptors {0x10d, 6, list} at 0x611af720 / 0x61206bd0 / 0x61288384 and
  the Live Control/SCP row {0x10d, 5, listA, listB} at 0x611fe0e4 are inside
  LZ4 GUI blob B (0x60c6c000). New lists go in free space 0x600d7010..; the
  menu gets {6, type 4, string 0xf1 "Panorama"} before 17:9, the SCP lists get
  value 6 with the 16:9 icons. Blob B is recompressed with LZ4 HC level 12
  (reproduces the stock blobs byte for byte) and verified by decoding.

Label test (diagnostic): relabel the 4:3 entry of the three aspect option lists
  inside GUI blob B (0x611af064, 0x61206514, 0x61287cc8) from 0x124 "4:3" to
  0xf1 "Panorama", in place. Shows whether blob-B edits reach the camera and
  whether these lists label the Image Aspect menu.

Stage 2c: stage 2a + the real menu label list (screen record 0x61294774, shared
  count 6; list 0x612941d4 = values 1,2,3,4,9,10, confirmed on camera by label
  test 2): its 17:9 entry {10, 4, 0xcbd} becomes {6, 4, 0xf1 "Panorama"} in place
  (17:9 is never offered for stills: 10 is not in the validator list). Plus the
  SCP/Live Control row {0x10d, 5 -> 6} with value 6 using the 16:9 icons.

Stage 2d: everything at once. Camera results showed the main menu enumerates
  the option lists of the menu descriptors (2b) but takes the label from list
  0x612941d4 (2c); a value missing from either shows blank/unselectable or not
  at all. 2d = 2a + the 2b option lists + the 2c label + the LV row + the SCP
  item table row 17 at 0x611eeedc ({17, A, B, 5}, icon lists in order
  1,3,2,9,4; the E-P7 "row 16" equivalent), each given value 6 with 16:9 icons.

Stage 2e: 2d + the setting restriction rules (record 0x60492f00 for 0x10d,
  13 rules {IF terms, MAP {from,to}}, evaluated by 0x602d4bb5; the step code
  0x602cb5f9 skips any value the check 0x602d51ee rejects with 0x100). Rule 12
  (IF setting 44 == 0, i.e. stills) maps 1,3,2,4,9,10 -> 1,3,2,4,9,1; value 6
  is not a target, so it is skipped. Its map is relocated with {6, 6} added.

Stage 3: 2e + 65:24 capture geometry for id 6 (E-P7 ASPECT.md 1d / v5):
  width/height size-class rows W 0x60549864 / H 0x60549a14 (row id 6): width =
  max(4:3, 16:9) per class, height = width*24/65 rounded to 16 (L 5184x1920),
  classes stock leaves 0 stay 0; ORF AspectFrame jump entry id 6 -> width-
  limited case 0x6041f44b; LV/AF u8 ratio pair 0x6025ab44 7:6 -> 65:24.

Label test 2 (diagnostic): same as the label test, for the value-ordered list
  0x612941d4 (values 1,2,3,4,9,10, referenced by the screen record at 0x61294774).

Title test (diagnostic): change the "Image Aspect" row title (string 0x46) to
  0xf1 "Panorama" in every menu item record {u32 0x10d, u16 4, u16 0x46, u32 cond}
  inside GUI blob B. Shows whether blob-B edits reach the running camera.

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
import olycompress  # noqa: E402

BASE = 0x60021020
ASPECT_REC = 0x604dc954
STOCK_ASPECT_REC = bytes.fromhex("0d018000da934d60000000000500010000010000")
ASPECT_LIST = 0x604d93da
NEW_LIST = 0x600d7000
FREE_LO, FREE_HI = 0x600d6ff0, 0x600d7800


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def stage1(m):
    check(bytes(m[off(ASPECT_REC):off(ASPECT_REC) + 20]) == STOCK_ASPECT_REC, "aspect record differs from stock")
    check(list(m[off(ASPECT_LIST):off(ASPECT_LIST) + 5]) == [1, 3, 2, 4, 9], "aspect list differs from stock")
    struct.pack_into("<H", m, off(ASPECT_REC) + 12, 4)


def stage2a(m):
    check(bytes(m[off(ASPECT_REC):off(ASPECT_REC) + 20]) == STOCK_ASPECT_REC, "aspect record differs from stock")
    check(list(m[off(ASPECT_LIST):off(ASPECT_LIST) + 5]) == [1, 3, 2, 4, 9], "aspect list differs from stock")
    check(set(m[off(FREE_LO):off(FREE_HI)]) == {0xff}, "target area is not free 0xff padding")
    new = bytes([1, 3, 2, 4, 9, 6])
    m[off(NEW_LIST):off(NEW_LIST) + len(new)] = new
    struct.pack_into("<I", m, off(ASPECT_REC) + 4, NEW_LIST)
    struct.pack_into("<H", m, off(ASPECT_REC) + 12, len(new))


BLOB_B, BLOB_B_OFF = 0x60c6c000, 0xc4afe0
BLOB_END = 0x612f1000          # end of B's unpack area = end of 0xff space in the raw image
MENU_DESCS = (0x611af720, 0x61206bd0, 0x61288384)
LV_ROW = 0x611fe0e4
PANORAMA = 0xf1


def ents(img, base, p, n):
    return [struct.unpack_from("<IHHI", img, p - base + 12 * k) for k in range(n)]


def pack_ents(es):
    return b"".join(struct.pack("<IHHI", *e) for e in es)


def stage2b(m):
    stage2a(m)
    import lz4.block
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz, usz = struct.unpack_from("<II", m, BLOB_B_OFF + 16)
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(lz4.block.compress(bytes(gui), mode="high_compression", compression=12, store_size=False)
          == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]), "stock blob B does not recompress identically")
    g = lambda a: a - BLOB_B          # noqa: E731  runtime addr -> offset in unpacked blob B
    free = NEW_LIST + 0x10
    for d in MENU_DESCS:
        sid, n, p = struct.unpack_from("<HHI", gui, g(d))
        check((sid, n) == (0x10d, 6), "menu descriptor %#x differs" % d)
        es = ents(gui, BLOB_B, p, n)
        check([e[0] for e in es] == [1, 3, 2, 4, 9, 10] and all(e[1] == 4 for e in es), "menu list %#x differs" % p)
        cond = es[0][3]
        new = es[:5] + [(6, 4, PANORAMA, cond)] + es[5:]
        m[off(free):off(free) + 84] = pack_ents(new)
        struct.pack_into("<HI", gui, g(d) + 2, len(new), free)
        free += 0x60
    sid, n, pa, pb = struct.unpack_from("<HHII", gui, g(LV_ROW))
    check((sid, n) == (0x10d, 5), "LV row differs")
    for i, p in enumerate((pa, pb)):
        es = ents(gui, BLOB_B, p, n)
        check([e[0] for e in es] == [1, 3, 2, 4, 9] and all(e[1] == 3 for e in es), "LV list %#x differs" % p)
        e169 = es[1]
        new = es + [(6, 3, e169[2], e169[3])]
        m[off(free):off(free) + 72] = pack_ents(new)
        struct.pack_into("<I", gui, g(LV_ROW) + 4 + 4 * i, free)
        free += 0x50
    struct.pack_into("<H", gui, g(LV_ROW) + 2, 6)
    check(free <= FREE_HI, "new lists overflow the free area")
    c = lz4.block.compress(bytes(gui), mode="high_compression", compression=12, store_size=False)
    room = off(BLOB_END) - (BLOB_B_OFF + 32)
    check(len(c) <= room, "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  blob B: %#x -> %#x compressed bytes" % (csz, len(c)))


LISTS_IN_B = (0x611af064, 0x61206514, 0x61287cc8)
MENU_LABELS = 0x612941d4          # real Image Aspect label list (6 entries, shared count)


def stage2c(m):
    stage2a(m)
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "stock blob B does not recompress identically")
    es = ents(gui, BLOB_B, MENU_LABELS, 6)
    check([e[0] for e in es] == [1, 2, 3, 4, 9, 10] and all(e[1] == 4 for e in es), "menu label list differs")
    check(es[5][2] == 0xcbd, "17:9 entry differs")
    struct.pack_into("<IHHI", gui, MENU_LABELS - BLOB_B + 12 * 5, 6, 4, PANORAMA, es[5][3])
    sid, n, pa, pb = struct.unpack_from("<HHII", gui, LV_ROW - BLOB_B)
    check((sid, n) == (0x10d, 5), "LV row differs")
    free = NEW_LIST + 0x130
    for i, p in enumerate((pa, pb)):
        e = ents(gui, BLOB_B, p, n)
        check([x[0] for x in e] == [1, 3, 2, 4, 9] and all(x[1] == 3 for x in e), "LV list %#x differs" % p)
        new = e + [(6, 3, e[1][2], e[1][3])]
        m[off(free):off(free) + 72] = pack_ents(new)
        struct.pack_into("<I", gui, LV_ROW - BLOB_B + 4 + 4 * i, free)
        free += 0x50
    struct.pack_into("<H", gui, LV_ROW - BLOB_B + 2, 6)
    check(free <= FREE_HI, "new lists overflow the free area")
    repack_b(m, gui, csz)


SCP_ROW17 = 0x611eeedc         # {u32 17, A, B, u32 count 5}: SCP item table row for aspect


def stage2d(m):
    """2a + menu option lists (2b) + menu label list (2c) + both SCP icon tables."""
    stage2a(m)
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "stock blob B does not recompress identically")
    g = lambda a: a - BLOB_B          # noqa: E731
    free = NEW_LIST + 0x10
    # menu option lists: insert {6, 4, Panorama} before 17:9
    for d in MENU_DESCS:
        sid, n, p = struct.unpack_from("<HHI", gui, g(d))
        check((sid, n) == (0x10d, 6), "menu descriptor %#x differs" % d)
        es = ents(gui, BLOB_B, p, n)
        check([e[0] for e in es] == [1, 3, 2, 4, 9, 10] and all(e[1] == 4 for e in es), "menu list %#x differs" % p)
        new = es[:5] + [(6, 4, PANORAMA, es[0][3])] + es[5:]
        m[off(free):off(free) + 84] = pack_ents(new)
        struct.pack_into("<HI", gui, g(d) + 2, len(new), free)
        free += 0x60
    # menu label list (screen record 0x61294774): 17:9 entry -> Panorama
    es = ents(gui, BLOB_B, MENU_LABELS, 6)
    check([e[0] for e in es] == [1, 2, 3, 4, 9, 10] and all(e[1] == 4 for e in es), "menu label list differs")
    check(es[5][2] == 0xcbd, "17:9 entry differs")
    struct.pack_into("<IHHI", gui, g(MENU_LABELS) + 12 * 5, 6, 4, PANORAMA, es[5][3])
    # SCP / Live Control row {0x10d, 5, A, B}
    sid, n, pa, pb = struct.unpack_from("<HHII", gui, g(LV_ROW))
    check((sid, n) == (0x10d, 5), "LV row differs")
    for i, p in enumerate((pa, pb)):
        e = ents(gui, BLOB_B, p, n)
        check([x[0] for x in e] == [1, 3, 2, 4, 9] and all(x[1] == 3 for x in e), "LV list %#x differs" % p)
        m[off(free):off(free) + 72] = pack_ents(e + [(6, 3, e[1][2], e[1][3])])
        struct.pack_into("<I", gui, g(LV_ROW) + 4 + 4 * i, free)
        free += 0x50
    struct.pack_into("<H", gui, g(LV_ROW) + 2, 6)
    # SCP item table row 17 {17, A, B, 5} (values 1,3,2,9,4)
    key, pa, pb, n = struct.unpack_from("<IIII", gui, g(SCP_ROW17))
    check((key, n) == (17, 5), "SCP row 17 differs")
    for i, p in enumerate((pa, pb)):
        e = ents(gui, BLOB_B, p, n)
        check([x[0] for x in e] == [1, 3, 2, 9, 4] and all(x[1] == 3 for x in e), "SCP row-17 list %#x differs" % p)
        m[off(free):off(free) + 72] = pack_ents(e + [(6, 3, e[1][2], e[1][3])])
        struct.pack_into("<I", gui, g(SCP_ROW17) + 4 + 4 * i, free)
        free += 0x50
    struct.pack_into("<I", gui, g(SCP_ROW17) + 12, 6)
    check(free <= FREE_HI, "new lists overflow the free area")
    repack_b(m, gui, csz)


RULE12 = 0x6048a918   # aspect restriction rule {IF 44==0 (stills), MAP 0x6048a840, 6}
STOCK_MAP12 = [(1, 1), (3, 3), (2, 2), (4, 4), (9, 9), (10, 1)]


def stage2e(m):
    """2d + allow 6 in the stills restriction rule (rule engine 0x602d4bb5)."""
    stage2d(m)
    r = off(RULE12)
    cp, cn, mp, mn = struct.unpack_from("<IHxxIHxx", m, r)
    check((cn, mn) == (1, 6) and tuple(m[off(cp):off(cp) + 4]) == (0x2c, 0, 0, 0), "rule 12 differs")
    check([struct.unpack_from("<HH", m, off(mp) + 4 * k) for k in range(6)] == STOCK_MAP12, "rule 12 map differs")
    new = NEW_LIST + 0x280
    check(set(m[off(new):off(new) + 0x20]) == {0xff}, "rule map target not free")
    data = b"".join(struct.pack("<HH", *e) for e in STOCK_MAP12 + [(6, 6)])
    m[off(new):off(new) + len(data)] = data
    struct.pack_into("<I", m, r + 8, new)
    struct.pack_into("<H", m, r + 12, 7)


W_TAB, H_TAB = 0x60549864, 0x60549a14   # u16[24] per aspect id 1..9 (48 B rows), size classes
FRAME_JT = 0x60549770                    # ORF AspectFrame jump table, index id-1 (dispatch 0x6041f441)
FRAME_WIDE, FRAME_TALL = 0x6041f44b, 0x6041f474
RATIO_U8 = 0x6025ab38                    # u8 (w,h) per id 0..10, boot-copied .data (LV/AF ratio)
XPAN_W, XPAN_H = 65, 24


def row(m, tab, i):
    return list(struct.unpack_from("<24H", m, off(tab + 48 * (i - 1))))


def stage3(m):
    """2e + 65:24 capture geometry for id 6 (E-P7 v5 recipe)."""
    stage2e(m)
    w1, w3, w6, h6 = row(m, W_TAB, 1), row(m, W_TAB, 3), row(m, W_TAB, 6), row(m, H_TAB, 6)
    check(w1[0] == 5184 and w3[0] == 5184 and (w6[0], h6[0]) == (4544, 3888), "size tables differ")
    nw, nh = [], []
    for c in range(24):
        if w6[c] == 0:
            nw.append(0); nh.append(h6[c]); continue
        w = max(w1[c], w3[c])
        nw.append(w); nh.append(max(16, int(w * XPAN_H / XPAN_W / 16 + 0.5) * 16))
    struct.pack_into("<24H", m, off(W_TAB + 48 * 5), *nw)
    struct.pack_into("<24H", m, off(H_TAB + 48 * 5), *nh)
    jt = list(struct.unpack_from("<9I", m, off(FRAME_JT)))
    check(jt[5] == FRAME_TALL and jt[1] == jt[2] == FRAME_WIDE, "frame jump table differs")
    struct.pack_into("<I", m, off(FRAME_JT) + 4 * 5, FRAME_WIDE)
    r = list(m[off(RATIO_U8):off(RATIO_U8) + 22])
    check(r == [0, 0, 4, 3, 3, 2, 16, 9, 6, 6, 5, 4, 7, 6, 6, 5, 7, 5, 3, 4, 17, 9], "ratio table differs")
    m[off(RATIO_U8) + 12:off(RATIO_U8) + 14] = bytes([XPAN_W, XPAN_H])
    print("  id 6 sizes: " + ", ".join("%dx%d" % (a, b) for a, b in zip(nw, nh) if a))


def repack_b(m, gui, csz):
    c = olycompress.pack(bytes(gui))
    room = off(BLOB_END) - (BLOB_B_OFF + 32)
    check(len(c) <= room, "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  blob B: %#x -> %#x compressed bytes" % (csz, len(c)))


def labeltest(m, lists=LISTS_IN_B):
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "stock blob B does not recompress identically")
    for p in lists:
        v, t, sid, cond = struct.unpack_from("<IHHI", gui, p - BLOB_B)
        check((v, t, sid) == (1, 4, 0x124), "list %#x does not start with the 4:3 entry" % p)
        struct.pack_into("<H", gui, p - BLOB_B + 6, PANORAMA)
    repack_b(m, gui, csz)


def titletest(m):
    import re
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "stock blob B does not recompress identically")
    hits = []
    # two record layouts: {u32 0x10d, u16 4, u16 0x46, u32 cond} and
    # {u32 0x10d, u32 0, u16 4, u16 0x46, u32 cond}
    for pat, so in ((struct.pack("<IHH", 0x10d, 4, 0x46), 6), (struct.pack("<IIHH", 0x10d, 0, 4, 0x46), 10)):
        for mm in re.finditer(re.escape(pat), bytes(gui)):
            o = mm.start()
            cond = struct.unpack_from("<I", gui, o + so + 2)[0]
            check(0x60000000 <= cond < 0x62000000, "item at %#x has no condition pointer" % (BLOB_B + o))
            hits.append(o + so)
    check(len(hits) >= 10, "expected many Image Aspect item records, found %d" % len(hits))
    for so in hits:
        struct.pack_into("<H", gui, so, PANORAMA)
    print("  retitled %d Image Aspect item records" % len(hits))
    repack_b(m, gui, csz)


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
    if "--stage1" in argv:
        stage1(m)
    elif "--stage2a" in argv:
        stage2a(m)
    elif "--stage2b" in argv:
        stage2b(m)
    elif "--stage2c" in argv:
        stage2c(m)
    elif "--stage2d" in argv:
        stage2d(m)
    elif "--stage2e" in argv:
        stage2e(m)
    elif "--stage3" in argv:
        stage3(m)
    elif "--labeltest2" in argv:
        labeltest(m, (0x612941d4,))
    elif "--labeltest" in argv:
        labeltest(m)
    elif "--titletest" in argv:
        titletest(m)
    else:
        check(False, "no stage selected")
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
    lp, cnt = struct.unpack_from("<IxxxxH", a0, off(ASPECT_REC) + 4)
    print("wrote %s  sha256 %s" % (dst, hashlib.sha256(out).hexdigest()))
    print("  aspect list at %#x: %s" % (lp, list(a0[off(lp):off(lp) + cnt])))
    print("  main block version: %#06x" % struct.unpack_from("<H", again[0]["head"], 16)[0])
    print("  file bytes changed: %d" % sum(1 for x, y in zip(fw, out) if x != y))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
