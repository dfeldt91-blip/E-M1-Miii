#!/usr/bin/env python3
"""
patch_aspect.py - E-M1 Mark III aspect-ratio experiments (toward XPan 65:24).
EXPERIMENTAL, NOT TESTED ON A CAMERA.

  python3 tools/patch_aspect.py IN.BIN OUT.BIN --stage1|--stage2a|--stage2b [--version 0x1530]

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
