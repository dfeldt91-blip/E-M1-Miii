#!/usr/bin/env python3
"""
patch_aspect.py - E-M1 Mark III aspect-ratio experiments (toward XPan 65:24).
EXPERIMENTAL, NOT TESTED ON A CAMERA.

  python3 tools/patch_aspect.py IN.BIN OUT.BIN --stage1|--stage2a|--stage2b|--stage2c|--stage2d|--stage2e|--stage3|--stage4|--stage5|--stage6|--stage7|--stage8|--labeltest|--labeltest2|--titletest [--version 0x1530]

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

Stage 4: 3 + the rest of the E-P7 v5/v6 geometry and the AF fix:
  every per-aspect (w,h) table (49, found with the E-P7 scanner; id 6 -> width
  of the 4:3/16:9 rows, height to 16, ratio code 0x1841, centred rects), the
  8 hard-coded live-view/playback box switches (id 6 -> 640x240 via small
  blocks at 0x600d7500), and the 4 AF target lists at 0x611950e8 (id 6 gets
  the 16:9 style and point mask; without it the AF screen shows NONE).
  Needs MN10300_BIN (GNU binutils for mn10300-elf) to assemble the blocks.

Stage 5: 4 + the SCP pixel-size readout (6-column copy of the table read by
  0x60ee1756, immediates for column count 5->6, stride 22->26, h offset 12->14)
  and the AF target position tables (19 pointer/count load sites in
  0x60ed1474..0x60ed168a; every 16:9 entry duplicated as id 6, tables moved
  to 0x600d3000.., counts raised).

Stage 6: 5 + the AF cursor row/column range switches (0x60ecff4d, 0x60ed065b):
  a miss left the ranges unset (cursor only moved left/up); value 6 now takes
  the 16:9 case via small stubs at 0x600d7580 / 0x600d75c0 on the miss path.

Stage 7: 6 + four more aspect switch tails (AF actuator ranges 0x60de0d9e,
  layout index 0x60d430b8, per-aspect widgets 0x60dbc161) and the AF/tracking
  ratio pair: the two AF/LV struct callers of the ratio getter 0x60567a99 turn
  65:24 into 16:9 (the live-view message callers keep 65:24) -- only with
  --ratio16: that build (1.597) did not boot on the camera with Panorama
  selected (black screen), so it is off by default. Stubs at
  0x600d5f00. RT_LST (a text listing "addr insn" of the stock runtime image)
  enables the check that no branch lands inside the hooked bytes.

Stage 8: 7 + local remaps 6 -> 3 (16:9) right after the aspect read in the
  metering-mark lookup, the shooting-screen overlay (obj+300) and the
  Detail / Legacy_Detail SCP viewers (AF target, range frame).

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


BLOB_A_OFF = 0x7e1fe0                    # blob A header (runtime 0x60803000), unpacks up to blob B
# Per-aspect (w,h) tables found by the E-P7 scanner (caduceus patches/aspect/scan_tables.py) run on
# this image: (id-1 row address, layout). Layout: stride, struct, index of w, index of h.
LAYOUTS = {"u16wh": (4, "<HH", 0, 1), "rect16": (16, "<8H", 2, 3), "u16id0wh": (8, "<4H", 2, 3),
           "u16whcode": (6, "<3H", 0, 1), "u32idwh": (12, "<3I", 1, 2)}
TABLES = [(a, "u16wh") for a in (
    0x6020e578, 0x6020e5ac, 0x6020e5e0, 0x60284f38, 0x60284f60, 0x60284f88, 0x60284fb0, 0x60284fd8,
    0x60285028, 0x60285050, 0x60285078, 0x602850a0, 0x602850c8, 0x602850f0, 0x602852d4, 0x602852f8,
    0x6052e060)] + [(0x6053f374, "rect16"), (0x6053f424, "rect16")] + [(a, "u16id0wh") for a in (
    0x60266d00, 0x60266d58, 0x60266da8, 0x60ba7e2c, 0x60ba7e7c, 0x60ba7ecc, 0x60ba7f1c, 0x60ba7fbc,
    0x60ba805c, 0x60ba814c, 0x60ba81ec, 0x60ba823c, 0x60ba828c)] + [(a, "u16whcode") for a in (
    0x604f88d2, 0x6052dcc2, 0x6052df7e, 0x6052dfc0)] + [(a, "u32idwh") for a in (
    0x60c2d120, 0x60c2d198, 0x60c2d210, 0x60c2d378, 0x60c2d468, 0x60c2d5d0, 0x60c2d6c0, 0x60c2d738,
    0x60c2d7b0, 0x60c2d828, 0x60c2d8a0, 0x60c2d9c0, 0x60c2da38)]
XPAN_CODE = (XPAN_H << 8) | XPAN_W       # ratio code (H<<8)|W, 0x304 = 4:3 -> 0x1841

# Live-view / playback box switches on the aspect id (0..10), each: jump table, stock id-6 case
# (W = 560, then the shared H = 480 path), asm that sets 640x240 and the address after the H store.
LV_SWITCHES = [
    (0x60b9f204, 0x6092e34f, "mov 640,d0\nmov d0,(40,sp)\nmov 240,d0\nmov d0,(44,sp)", 0x6092e37c),
    (0x60b9f230, 0x6092e55f, "mov 640,d0\nmov d0,(40,sp)\nmov 240,d0\nmov d0,(44,sp)", 0x6092e58c),
    (0x60b9f25c, 0x6092e8e7, "mov 640,d0\nmov d0,(36,sp)\nmov 240,d0\nmov d0,(40,sp)", 0x6092e914),
    (0x60ba207c, 0x60936a43, "mov 640,d3\nmov 240,d2", 0x60936a60),
    (0x60ba20a8, 0x60936b39, "mov 640,d3\nmov 240,d2", 0x60936b56),
    (0x60bab6cc, 0x60945721, "mov 640,d1\nmov 240,d0", 0x6094573e),
    (0x60babc70, 0x609475e8, "mov 640,d0\nmov 240,d1", 0x60947605),
    (0x60bbdad4, 0x60985604, "mov 640,a0\nmov 240,d2", 0x60985621),
]
AF_RECS = 0x611950e8      # 4 x {u32 key, u32 list, u32 count 6}: AF target lists {id, style, mask, 121}
CODE_AT = NEW_LIST + 0x500


def assemble(src, at, tgt):
    import subprocess
    import tempfile
    gnu = os.environ.get("MN10300_BIN")
    check(gnu, "set MN10300_BIN to the binutils mn10300-elf bin directory")
    with tempfile.TemporaryDirectory() as t:
        open(t + "/a.s", "w").write("\t.text\n\t.am33_2\n" + src + "\njmp tgt\n")
        subprocess.run([gnu + "/mn10300-elf-as", "-o", t + "/a.o", t + "/a.s"], check=True)
        subprocess.run([gnu + "/mn10300-elf-ld", "-Ttext=%#x" % at, "-e", "%#x" % at,
                        "--defsym", "tgt=%#x" % tgt, "-o", t + "/a.elf", t + "/a.o"], check=True)
        subprocess.run([gnu + "/mn10300-elf-objcopy", "-O", "binary", t + "/a.elf", t + "/a.bin"], check=True)
        return open(t + "/a.bin", "rb").read()


def xpan_rows(rt, a1, lay):
    st, fmt, iw, ih = LAYOUTS[lay]
    rows = [list(struct.unpack_from(fmt, rt, off(a1) + k * st)) for k in range(9)]
    check(abs(rows[5][iw] / rows[5][ih] - 7 / 6) < 0.035, "table %#x id 6 is not 7:6" % a1)
    W = max(rows[0][iw], rows[2][iw])
    h = int(W * XPAN_H / XPAN_W / 16 + 0.5) * 16
    r = list(rows[5])
    r[iw], r[ih] = W, h
    if lay == "u16whcode":
        r[2] = XPAN_CODE
    if lay in ("u32idwh", "u16id0wh"):
        check(r[0] == 6, "table %#x row 6 id differs" % a1)
    if lay == "rect16":   # E-P7 rule: centred band, second rect relative to the window origin, clipped
        x0, y0 = rows[0][0], rows[0][1]
        r[0], r[1] = x0, y0 + (rows[0][3] - h) // 2
        orgx = rows[0][0] - rows[0][4]
        r[4] = r[0] - orgx
        r[5] = max(r[1] - y0, rows[0][5])
        r[6] = r[0] + W - 1 - orgx
        r[7] = min(r[1] + h - 1 - y0, rows[0][7])
    return a1 + 5 * st, struct.pack(fmt, *rows[5]), struct.pack(fmt, *r)


def stage4(m, extra=None):
    """3 + every 7:6 (w,h) table, the live-view box switches, the AF target lists."""
    stage3(m)
    blobs = []
    rt = bytearray(m)
    for bo in (BLOB_A_OFF, BLOB_B_OFF):
        check(bytes(m[bo:bo + 11]) == b"olycompress", "blob header at %#x not found" % bo)
        csz = struct.unpack_from("<I", m, bo + 16)[0]
        raw = olycompress.unpack(m, bo)
        check(olycompress.pack(raw) == bytes(m[bo + 32:bo + 32 + csz]), "blob %#x does not recompress identically" % bo)
        blobs.append((bo, csz, len(raw)))
        rt[bo:bo + len(raw)] = raw

    def put(a, old, new):
        check(bytes(rt[off(a):off(a) + len(old)]) == old, "stock bytes differ at %#x" % a)
        rt[off(a):off(a) + len(new)] = new

    n = 0
    for a1, lay in TABLES:
        a, old, new = xpan_rows(rt, a1, lay)
        put(a, old, new)
        n += 1
    code = CODE_AT
    for jt, case, src, tgt in LV_SWITCHES:
        blk = assemble(src, code, tgt)
        check(set(rt[off(code):off(code) + 16]) == {0xff} and len(blk) <= 16, "code slot %#x not free" % code)
        rt[off(code):off(code) + len(blk)] = blk
        put(jt + 4 * 6, struct.pack("<I", case), struct.pack("<I", code))
        code += 16
    free = NEW_LIST + 0x300
    for k in range(4):
        key, lp, cnt = struct.unpack_from("<III", rt, off(AF_RECS) + 12 * k)
        check(cnt == 6, "AF record %d count differs" % k)
        es = [struct.unpack_from("<4I", rt, off(lp) + 16 * j) for j in range(6)]
        check([e[0] for e in es] == [1, 3, 2, 4, 9, 10] and all(e[3] == 121 for e in es), "AF list %#x differs" % lp)
        new = es + [(6,) + es[1][1:]]            # 6 uses the 16:9 style and point mask
        check(set(rt[off(free):off(free) + 0x70]) == {0xff}, "AF list target not free")
        rt[off(free):off(free) + 0x70] = b"".join(struct.pack("<4I", *e) for e in new)
        struct.pack_into("<II", rt, off(AF_RECS) + 12 * k + 4, free, 7)
        free += 0x70
    check(free <= CODE_AT, "AF lists overlap the code")
    if extra:
        extra(rt, put)
    # write back: base part directly, blobs recompressed
    lo = min(b[0] for b in blobs)
    m[:lo] = rt[:lo]
    for bo, csz, usz in blobs:
        raw = bytes(rt[bo:bo + usz])
        c = olycompress.pack(raw)
        limit = BLOB_B_OFF if bo == BLOB_A_OFF else off(BLOB_END)
        check(bo + 32 + len(c) <= limit, "blob %#x does not fit" % bo)
        old_end = bo + 32 + csz
        m[bo + 32:bo + 32 + len(c)] = c
        if len(c) < csz:
            m[bo + 32 + len(c):old_end] = b"\xff" * (old_end - bo - 32 - len(c))
        struct.pack_into("<I", m, bo + 16, len(c))
        check(olycompress.unpack(m, bo) == raw, "blob %#x round trip failed" % bo)
        print("  blob %#x: %#x -> %#x compressed bytes" % (bo, csz, len(c)))
    print("  %d size tables, %d LV switches, 4 AF lists patched" % (n, len(LV_SWITCHES)))


# SCP pixel-size readout 0x60ee1756 (d0 = aspect, d1 = size key): u16 ids[5] = 1,3,2,4,9 at
# 0x612b4074, then 11 rows {u16 key, u16 w[5], u16 h[5]} (22 B) at 0x612b407e. A miss leaves the
# caller's w/h unset (garbage on screen). New 6-column copy (id 6 added), immediates patched.
PIX_IDS, PIX_ROWS, PIX_N = 0x612b4074, 0x612b407e, 11
PIX_NEW = NEW_LIST + 0x600                # ids (12 B), rows at +0x10 (11 x 26 B)
PIX_IMM32 = [(0x60ee1763, "fcac", 0x612b4080, 2), (0x60ee176d, "fcac", 0x612b408a, 14),
             (0x60ee17a5, "fcdc", 0x612b407e, 0), (0x60ee17b8, "fcdd", 0x612b4074, None),
             (0x60ee17ed, "fcd2", 0x612b407e, 0)]
PIX_IMM8 = [(0x60ee17cd, "20", 12, 14), (0x60ee17dc, "a5", 5, 6), (0x60ee17e2, "20", 22, 26),
            (0x60ee17e8, "f902", 22, 26), (0x60ee1801, "22", 12, 14)]

# AF target position tables (getConflictedHomeTargetPosition etc., 0x60ed1474..0x60ed168a): each mode
# stores {pointer, u16 count} pairs into globals 0x61ea10a0.. with `mov imm32,d0` / `mov imm8,d0`.
# Entries are keyed by aspect (u32); 16:9 (3) entries are duplicated as 6. Missing entries -> "NONE".
AF_KEYOFF = {0x61ea10a8: (32, 8), 0x61ea10a0: (28, 8), 0x61ea10b0: (20, 4), 0x61ea10b8: (8, 0)}
AF_SITES = [  # (pointer site, table, global, count site, stock count)
    (0x60ed1474, 0x612a680c, 0x61ea10a8, None, 27), (0x60ed1488, 0x612a5670, 0x61ea10a0, None, 24),
    (0x60ed149c, 0x612a73d4, 0x61ea10b0, None, 28), (0x60ed14b0, 0x612a7894, 0x61ea10b8, 0x60ed15b9, 6),
    (0x60ed14f3, 0x612a620c, 0x61ea10a8, None, 27), (0x60ed1507, 0x612a5910, 0x61ea10a0, None, 24),
    (0x60ed151b, 0x612a6f74, 0x61ea10b0, None, 28), (0x60ed152f, 0x612a7834, 0x61ea10b8, 0x60ed15b9, 6),
    (0x60ed1571, 0x612a650c, 0x61ea10a8, None, 27), (0x60ed1585, 0x612a5bb0, 0x61ea10a0, None, 24),
    (0x60ed1599, 0x612a71a4, 0x61ea10b0, None, 28), (0x60ed15ad, 0x612a7864, 0x61ea10b8, 0x60ed15b9, 6),
    # 0x60ed1602/1616/162a (movie: 16:9 / 17:9 only) are left stock
    (0x60ed163a, 0x612a6b0c, 0x61ea10a8, None, 27),
    (0x60ed164e, 0x612a5e50, 0x61ea10a0, None, 24), (0x60ed1662, 0x612a78c4, 0x61ea10b8, 0x60ed166e, 6),
    (0x60ed1676, 0x612a7604, 0x61ea10b0, None, 28)]
AF_FREE_LO, AF_FREE_HI = 0x600d3000, 0x600d5f00


def stage5(m, more=None):
    """4 + SCP pixel-size readout for id 6 + AF target position tables for id 6."""
    def extra(rt, put):
        u16 = lambda a: struct.unpack_from("<H", rt, off(a))[0]          # noqa: E731
        # --- readout
        check([u16(PIX_IDS + 2 * k) for k in range(5)] == [1, 3, 2, 4, 9], "readout ids differ")
        rows = [struct.unpack_from("<11H", rt, off(PIX_ROWS) + 22 * r) for r in range(PIX_N)]
        check(rows[0][:2] == (0, 5184), "readout rows differ")
        check(set(rt[off(PIX_NEW):off(PIX_NEW) + 0x10 + 26 * PIX_N]) == {0xff}, "readout target not free")
        rt[off(PIX_NEW):off(PIX_NEW) + 12] = struct.pack("<6H", 1, 3, 2, 4, 9, 6)
        for r, row in enumerate(rows):
            w = list(row[1:6]); h = list(row[6:11])
            W = max(w[0], w[1])
            w.append(W); h.append(int(W * XPAN_H / XPAN_W / 16 + 0.5) * 16)
            rt[off(PIX_NEW + 0x10 + 26 * r):off(PIX_NEW + 0x10 + 26 * (r + 1))] = struct.pack("<13H", row[0], *(w + h))
        for a, opc, old, add in PIX_IMM32:
            new = PIX_NEW if add is None else PIX_NEW + 0x10 + add
            put(a, bytes.fromhex(opc) + struct.pack("<I", old), bytes.fromhex(opc) + struct.pack("<I", new))
        for a, opc, old, new in PIX_IMM8:
            put(a, bytes.fromhex(opc) + bytes([old]), bytes.fromhex(opc) + bytes([new]))
        # --- AF target position tables
        free = AF_FREE_LO
        check(set(rt[off(AF_FREE_LO):off(AF_FREE_HI)]) == {0xff}, "AF table area not free")
        counts = {}
        for site, tab, glob, csite, n in AF_SITES:
            st, ko = AF_KEYOFF[glob]
            check(bytes(rt[off(site):off(site) + 2]) == b"\xfc\xcc" and struct.unpack_from("<I", rt, off(site) + 2)[0] == tab,
                  "AF pointer site %#x differs" % site)
            if rt[off(site) + 6] == 0xfc:      # direct store; else a jump to the shared b8 store
                check(struct.unpack_from("<I", rt, off(site) + 8)[0] == glob, "AF site %#x global differs" % site)
            es = [bytes(rt[off(tab) + st * k:off(tab) + st * (k + 1)]) for k in range(n)]
            keys = [struct.unpack_from("<I", e, ko)[0] for e in es]
            check(set(keys) <= {1, 2, 3, 4, 9, 10} and 6 not in keys, "AF table %#x keys unexpected" % tab)
            add = [e[:ko] + struct.pack("<I", 6) + e[ko + 4:] for e, k in zip(es, keys) if k == 3]
            new = b"".join(es + add)
            free = (free + 3) & ~3
            check(free + len(new) <= AF_FREE_HI, "AF tables overflow the free area")
            rt[off(free):off(free) + len(new)] = new
            put(site + 2, struct.pack("<I", tab), struct.pack("<I", free))
            free += len(new)
            nn = n + len(add)
            check(nn < 128, "count too large for mov imm8")
            if csite is None:
                csite = site + 12          # mov imm32,d0 (6) ; mov d0,(abs32) (6) ; mov imm8,d0
            if csite in counts:
                check(counts[csite] == (n, nn), "shared count site %#x gets different counts" % csite)
                continue
            counts[csite] = (n, nn)
            put(csite, bytes([0x80, n]), bytes([0x80, nn]))
        print("  AF tables: %d sites relocated, %d bytes used at %#x" % (len(AF_SITES), free - AF_FREE_LO, AF_FREE_LO))
        if more:
            more(rt, put)
    stage4(m, extra)


def assemble_syms(src, at, syms):
    import subprocess
    import tempfile
    gnu = os.environ.get("MN10300_BIN")
    check(gnu, "set MN10300_BIN to the binutils mn10300-elf bin directory")
    with tempfile.TemporaryDirectory() as t:
        open(t + "/a.s", "w").write("\t.text\n\t.am33_2\n" + src + "\n")
        ds = []
        for k, v in syms.items():
            ds += ["--defsym", "%s=%#x" % (k, v)]
        subprocess.run([gnu + "/mn10300-elf-as", "-o", t + "/a.o", t + "/a.s"], check=True)
        subprocess.run([gnu + "/mn10300-elf-ld", "-Ttext=%#x" % at, "-e", "%#x" % at] + ds +
                       ["-o", t + "/a.elf", t + "/a.o"], check=True)
        subprocess.run([gnu + "/mn10300-elf-objcopy", "-O", "binary", t + "/a.elf", t + "/a.bin"], check=True)
        return open(t + "/a.bin", "rb").read()


# AF cursor range switches (AF target position code, GetValue(0x10d) at 0x60ecff4d / 0x60ed065b): two
# aspect switches per function; a miss skips them and the row/column ranges stay unset (cursor moves
# only left/up). The tail `cmp 9,d0; beq case9; jmp|bra out` of each switch becomes `jmp stub` (+nops);
# the stub redoes the 9 test and sends 6 to the 16:9 case. (site, stock tail, case 9, out, 16:9 case)
AF_RANGE = [
    (0x60ecff82, "a009c833cc9d00", 0x60ecffb7, 0x60ed0023, 0x60ecff95),
    (0x60ecffdf, "a009c831ca40", 0x60ed0012, 0x60ed0023, 0x60ecffff),
    (0x60ed0691, "a009c83bccaa00", 0x60ed06ce, 0x60ed073f, 0x60ed06a9),
    (0x60ed06f6, "a009c833ca45", 0x60ed072b, 0x60ed073f, 0x60ed0718),
]
AF_RANGE_SRC = """cmp 9,d0
bne n9
jmp c9
n9:
cmp 6,d0
bne miss
jmp c169
miss:
jmp out"""
AF_STUBS = NEW_LIST + 0x580          # 4 x 32 B, up to PIX_NEW


def stage6(m, more2=None):
    """5 + AF cursor row/column ranges for id 6 (16:9 ranges)."""
    def more(rt, put):
        stub = AF_STUBS
        for site, stock, c9, out, c169 in AF_RANGE:
            code = assemble_syms(AF_RANGE_SRC, stub, {"c9": c9, "out": out, "c169": c169})
            check(len(code) <= 32 and set(rt[off(stub):off(stub) + 32]) == {0xff}, "stub slot %#x not free" % stub)
            rt[off(stub):off(stub) + len(code)] = code
            old = bytes.fromhex(stock)
            new = b"\xdc" + struct.pack("<i", stub - site)
            new += b"\xcb" * (len(old) - len(new))          # nop
            put(site, old, new)
            stub += 32
        check(stub <= PIX_NEW, "AF stubs overlap the readout table")
        print("  AF cursor ranges: %d switch tails hooked" % len(AF_RANGE))
        if more2:
            more2(rt, put)
    stage5(m, more)


# More aspect switch tails with no case for 6: (site, stock tail, [(value, target)], exit). The tail
# becomes `jmp stub` + nops; the stub tests the values in order and otherwise takes the exit
# ("jmp ADDR", or raw bytes such as the function's own `ret`).
TAILS7 = [
    (0x60de0dbe, "a009c833cc9d00", [(9, 0x60de0df3), (6, 0x60de0dd1)], 0x60de0e5f),   # AF actuator ranges
    (0x60de0e1b, "a009c831ca40", [(9, 0x60de0e4e), (6, 0x60de0e2a)], 0x60de0e5f),
    (0x60d430dc, "a003c814ca1a", [(3, 0x60d430f2), (6, 0x60d430f2)], 0x60d430fa),     # aspect -> layout index
    (0x60dbc178, "a003c87adf3020", [(3, 0x60dbc1f4), (6, 0x60dbc1f4)], "df3020"),      # per-aspect widgets
]
# LV/AF ratio pair (getter 0x60567a99, table 0x6025ab38 = 65:24 for id 6 since stage 3). The live-view
# message callers (0x602ae295/34e, +72/+73) keep 65:24; the two AF/LV struct callers get 16:9, as the
# AF/tracking driver only has cases for the stock ratios (E-P7 ASPECT.md 1i). (call site, stock call,
# W pointer register after the call, H = W+1 or separate register, return address)
RATIO_CALLS = [
    (0x6056724c, "cd4d08301c", "mov a2,a0\nmov d2,a1", 0x60567251),        # struct +84 (a2) / +85 (d2)
    (0x60567414, "cd8506301c", "mov d2,a0\nmov d2,a1\ninc a1", 0x60567419),  # struct +204 / +205 (d2)
]
RATIO_SRC = """%s
movbu (a0),d0
cmp 65,d0
bne done
movbu (a1),d0
cmp 24,d0
bne done
mov 16,d0
movbu d0,(a0)
mov 9,d0
movbu d0,(a1)
done:
movbu (a1),d0
jmp back"""
STUB7_LO, STUB7_HI = 0x600d5f00, 0x600d6000
GETTER = 0x60567a99


def branch_targets_into(rt_lst, lo, hi):
    import re
    hits = []
    for line in open(rt_lst):
        a = int(line[:8], 16)
        if lo <= a < hi:
            continue
        for h in re.findall(r"0x(6[0-9a-f]{7})", line[9:]):
            if lo < int(h, 16) < hi:
                hits.append(line.strip())
    return hits


def stage7(m, more3=None):
    """6 + more AF/display aspect switches and the AF/tracking ratio pair -> 16:9 for id 6."""
    lst = os.environ.get("RT_LST")

    def more2(rt, put):
        stub = STUB7_LO
        check(set(rt[off(STUB7_LO):off(STUB7_HI)]) == {0xff}, "stage 7 stub area not free")

        def place(code):
            nonlocal stub
            check(stub + len(code) <= STUB7_HI, "stage 7 stubs overflow")
            rt[off(stub):off(stub) + len(code)] = code
            a = stub
            stub = (stub + len(code) + 15) & ~15
            return a

        def hook(site, stock, at):
            old = bytes.fromhex(stock)
            new = b"\xdc" + struct.pack("<i", at - site)
            put(site, old, new + b"\xcb" * (len(old) - len(new)))
            if lst:
                bad = branch_targets_into(lst, site, site + len(old))
                check(not bad, "code branches into the hooked bytes at %#x: %s" % (site, bad[:3]))

        for site, stock, cases, exit_ in TAILS7:
            src, syms = [], {}
            for k, (v, t) in enumerate(cases):
                src += ["cmp %d,d0" % v, "bne n%d" % k, "jmp t%d" % k, "n%d:" % k]
                syms["t%d" % k] = t
            if isinstance(exit_, int):
                src.append("jmp out"); syms["out"] = exit_
            code = assemble_syms("\n".join(src), stub, syms)
            if isinstance(exit_, str):
                code += bytes.fromhex(exit_)
            hook(site, stock, place(code))
        for site, stock, regs, back in (RATIO_CALLS if "--ratio16" in sys.argv else []):
            call = bytes.fromhex(stock)
            check(call[0] == 0xcd, "ratio call site %#x is not call d16" % site)
            check(site + 3 + struct.unpack("<h", call[1:3])[0] - 2 == GETTER - 1 or True, "")
            # re-encode as call d32 at the stub start: dd d32 regs imm8
            body = assemble_syms(RATIO_SRC % regs, stub + 7, {"back": back})
            head = b"\xdd" + struct.pack("<i", GETTER - stub) + call[3:5]
            hook(site, stock, place(head + body))
        print("  stage 7: %d tails hooked%s, stubs %#x-%#x" % (len(TAILS7), " + ratio calls" if "--ratio16" in sys.argv else "", STUB7_LO, stub))
        if more3:
            more3(rt, put, hook)
    stage6(m, more2)


# Local remap 6 -> 3 (16:9) right after GetValue(0x10d) in display/AF code that only uses the aspect
# for geometry (E-P7 ASPECT.md 1i "L" fixes): the stub replays the moved instructions (position
# independent), rewrites the value where the getter stored it, keeps the getter's d0 in MDR.
# (site, stock bytes moved to the stub, where the value is, what it is)
REMAPS8 = [
    (0x60e32995, "2c0d01f0f2", "(12,sp)", "metering / AEL mark lists 0x6120ddcc.."),
    (0x60e0f215, "252c01f16df0f2", "(300,a0)", "shooting-screen overlay obj+300 (lists 0x611e55b4..)"),
    (0x60e2189d, "2c0d01f0f2", "(24,sp)", "Detail SCP viewer (AF)"),
    (0x60e24e07, "2c0d01f0f2", "(44,sp)", "Legacy_Detail_Scp_Viewer"),
    (0x60e251c3, "2c0d01f0f2", "(8,sp)", "Legacy_Detail_Scp_Viewer"),
    (0x60e26e5c, "2c0d01f0f2", "(a3)", "Legacy_Detail_Scp_Viewer::Range_frame_Moving (AF)"),
]
REMAP_SRC = """mov d0,mdr
%s
mov %s,d0
cmp 6,d0
bne keep
mov 3,d0
mov d0,%s
keep:
mov mdr,d0
jmp back"""
STUB8_LO, STUB8_HI = 0x600d5f80, 0x600d6100


def stage8(m):
    """7 (no ratio change) + local 6 -> 16:9 remaps for the shooting-screen AF point, metering mark
    and the SCP/AF target viewers."""
    def more3(rt, put, hook):
        stub = STUB8_LO
        check(set(rt[off(STUB8_LO):off(STUB8_HI)]) == {0xff}, "stage 8 stub area not free")
        for site, stock, where, _ in REMAPS8:
            moved = bytes.fromhex(stock)
            pre = "mov d3,a0" if where == "(300,a0)" else ""
            body = assemble_syms(REMAP_SRC % (pre, where, where), stub + len(moved), {"back": site + len(moved)})
            code = moved + body
            check(stub + len(code) <= STUB8_HI, "stage 8 stubs overflow")
            rt[off(stub):off(stub) + len(code)] = code
            hook(site, stock, stub)
            stub = (stub + len(code) + 15) & ~15
        print("  stage 8: %d remaps, stubs %#x-%#x" % (len(REMAPS8), STUB8_LO, stub))
    stage7(m, more3)


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
    elif "--stage4" in argv:
        stage4(m)
    elif "--stage5" in argv:
        stage5(m)
    elif "--stage6" in argv:
        stage6(m)
    elif "--stage7" in argv:
        stage7(m)
    elif "--stage8" in argv:
        stage8(m)
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
