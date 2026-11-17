#!/usr/bin/env python3
"""Edit Filename: '_' as a character choice (EXPERIMENTAL, E-M1 Mark III 1.6).

  python3 tools/patch_filename_char.py IN.BIN OUT.BIN [--version 0x1699]

Settings 0x93..0x96 MODE_FILENAME_CUSTOM_SRGB1..4 and 0x97..0x9a ..._ADOBE1..4 hold one character
each (0x20 = Off, keep the stock character). 0x602cca00 reads the four of the current colour space
(setting 60) into the DCF prefix (0x60310950 -> 0x600469ae, slot struct 0xa2747bc4 + 0x5d8 x slot
+ 10); the name builder 0x6065268f writes 'P', month (hex), day, number, then copies every
character that is not 0x20 over it, with no check of the character.

The Edit Filename picker (blob B): descriptors at 0x61295740 / 0x61295754 {u16 key (0 sRGB, 1 Adobe
RGB), u16 count 37, title, ?, list, ?} (looked up by key at 0x60ec5132); the list at 0x6129554c is
37 records {u32 value, u16 type, u16 label, u32 ptr}: {0x20, 4, string 0x6a8 "Off"} and
{'0'..'9', 'A'..'Z', 5 = one UTF-16 character at ptr}.

Patch: a 38-entry list at 0x600d9000 (0xff padding in the base section, copied at boot): the stock 37
plus {'_', 5, ptr 0x600411fe (the '_' of the UTF-16 table at 0x600411c2)}; both descriptors point
to it with count 38.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF = 0x60c6c000, 0xc4afe0
DESCS = (0x61295740, 0x61295754)
LIST, N = 0x6129554c, 37
NEW_LIST = 0x600d9000
UNDERSCORE = 0x600411fe
CHARS = [0x20] + list(range(0x30, 0x3a)) + list(range(0x41, 0x5b))


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def off(a):
    return a - BASE


def patch(main):
    m = bytearray(main)
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    g = lambda a: a - BLOB_B  # noqa: E731
    recs = [struct.unpack_from("<IHHI", gui, g(LIST) + 12 * k) for k in range(N)]
    check([r[0] for r in recs] == CHARS, "picker values differ")
    check(recs[0][1:3] == (4, 0x6a8) and all(r[1:3] == (5, 0) for r in recs[1:]), "picker records differ")
    check(all(m[off(r[3]):off(r[3]) + 2] == bytes([r[0], 0]) or gui[g(r[3]):g(r[3]) + 2] == bytes([r[0], 0])
              for r in recs[1:]), "picker characters differ")
    for k, d in enumerate(DESCS):
        key, n, title, x, lp, y = struct.unpack_from("<HHIIII", gui, g(d))
        check((key, n, lp) == (k, N, LIST), "descriptor %#x differs" % d)
    check(m[off(UNDERSCORE):off(UNDERSCORE) + 4] == "_`".encode("utf-16le"), "no UTF-16 '_' at %#x" % UNDERSCORE)
    new = recs + [(0x5f, 5, 0, UNDERSCORE)]
    data = b"".join(struct.pack("<IHHI", *r) for r in new)
    check(set(m[off(NEW_LIST) - 16:off(NEW_LIST) + len(data) + 16]) == {0xff}, "list area not free")
    m[off(NEW_LIST):off(NEW_LIST) + len(data)] = data
    for d in DESCS:
        struct.pack_into("<H", gui, g(d) + 2, len(new))
        struct.pack_into("<I", gui, g(d) + 12, NEW_LIST)
    cg = olycompress.pack(bytes(gui))
    check(len(cg) <= (0x612f1000 - BASE) - (BLOB_B_OFF + 32), "blob B does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(cg)] = cg
    if len(cg) < csz:
        m[BLOB_B_OFF + 32 + len(cg):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(cg))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(cg))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "blob B does not decode to the edit")
    print("  Edit Filename picker: %d -> %d characters (+ '_'), list at %#x; blob B %#x -> %#x"
          % (N, len(new), NEW_LIST, csz, len(cg)))
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
    print("wrote %s  sha256 %s  version %#06x" % (dst, hashlib.sha256(out).hexdigest(),
                                                   struct.unpack_from("<H", again[0]["head"], 16)[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
