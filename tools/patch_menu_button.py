#!/usr/bin/env python3
"""Main Menu as a button function (EXPERIMENTAL, E-M1 Mark III 1.6).

  MN10300_BIN=... python3 tools/patch_menu_button.py IN.BIN OUT.BIN [--version 0x1676]

Adds "Menu" to the Button Function lists of the full custom buttons (after Live ND). Pressing the
button posts a MENU key press (0x900e) through the GUI key poster 0x60ed53a0(code, lparam) (stock
use: 0x60df5e06), so the camera reacts as if MENU had been pressed.

Slots (see docs/FINDINGS.md, "High Res Shot as a button function"): code 284 ("Backlit LCD") is
in every button table but in no button list on this body. Its function row 17 (284, 29, 69) ->
(284, 99, 3200): action 99 is a free type-2 action (0x60f22cfc), a no-op in the press jump table
0x60f37cdc -> stub. Its labels {code, type, label, cond}: icons 0x611d8a64 / 0x61296124 (type 3
icon 0x36) and name 0x61295f20 -> type 4 "Menu" (0xa7); help 0x6129649c -> "Menu".
Button lists: the 17 full-button validator lists (16 x 38 codes, 1 x 39) get 284 after 1680,
as two shared lists in base-section free space.
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
CODE, ACTION = 284, 99
ACTION_TYPES = 0x60f22cfc     # {u32 action, u32 type, u32 name}: type 2 -> press jump table
FUNC_ROW, FUNC_STOCK, FUNC_NEW = 0x60f2343c + 12 * 17, (284, 29, 69), (284, 99, 3200)
PRESS_TAB, NOOP = 0x60f37cdc, 0x60cc4aab
NAME = HELP = 0xa7                              # "Menu"
LABELS = [  # (entry, stock type, stock label, new type, new label)
    (0x611d8a64, 3, 0x36, 4, NAME),
    (0x61296124, 3, 0x36, 4, NAME),
    (0x61295f20, 4, 0x169, 4, NAME),
    (0x6129649c, 4, 0x170, 4, HELP),
]
FREE_LO, FREE_HI = 0x600d6900, 0x600d6a80
LIST38, LIST39, STUB = 0x600d6900, 0x600d6960, 0x600d69e0
RECS38 = [0x604db608 + 0x14 * k for k in range(16)]
REC39 = 0x604db748
STOCK38 = [3333, 44, 106, 84, 85, 3297, 88, 22, 3279, 3348, 3349, 3350, 3351, 3341, 34, 682, 1431,
           3352, 472, 603, 6, 9, 436, 567, 3408, 452, 765, 1139, 1292, 1072, 157, 3428, 1680, 3431,
           241, 36, 1872, 3200]
STOCK39 = [3209] + STOCK38
# Post a MENU key press (call frame as at 0x60df5e0e), then the dispatcher's RET.
SRC = """mov 0x900e,d0
clr d1
call post,[a2],64
jmp back"""


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def with_code(lst):
    i = lst.index(1680) + 1
    return lst[:i] + [CODE] + lst[i:]


def patch(main):
    import patch_aspect
    m = bytearray(main)
    check(set(m[off(FREE_LO):off(FREE_HI)]) == {0xff}, "free area not 0xff")
    # button lists
    for lst, at, recs in ((STOCK38, LIST38, RECS38), (STOCK39, LIST39, [REC39])):
        new = with_code(lst)
        m[off(at):off(at) + 2 * len(new)] = struct.pack("<%dH" % len(new), *new)
        for rec in recs:
            sid, fl, lp, _, nb, el = struct.unpack_from("<HHIIHH", m, off(rec))
            check((fl, nb, el) == (0x80, 2 * len(lst), 2), "record %#x differs" % rec)
            check(list(struct.unpack_from("<%dH" % len(lst), m, off(lp))) == lst, "list %#x differs" % lp)
            struct.pack_into("<I", m, off(rec) + 4, at)
            struct.pack_into("<H", m, off(rec) + 12, 2 * len(new))
    check(LIST38 + 2 * 39 <= LIST39 and LIST39 + 2 * 40 <= STUB, "lists overlap")
    stub = patch_aspect.assemble_syms(SRC, STUB, {"back": NOOP, "post": 0x60ed53a0})
    check(STUB + len(stub) <= FREE_HI, "stub too long")
    m[off(STUB):off(STUB) + len(stub)] = stub
    # blob B tables
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    g = lambda a: a - BLOB_B  # noqa: E731
    check(bytes(gui[g(NOOP):g(NOOP) + 3]) == bytes.fromhex("dff044"), "dispatcher RET differs")
    check(struct.unpack_from("<3I", gui, g(FUNC_ROW)) == FUNC_STOCK, "function table row differs")
    t = 0x60f2343c
    struct.pack_into("<3I", gui, g(FUNC_ROW), *FUNC_NEW)
    check(struct.unpack_from("<2I", gui, g(ACTION_TYPES) + 12 * ACTION) == (ACTION, 2),
          "action %d is not a type-2 (press table) action" % ACTION)
    check(ACTION not in [struct.unpack_from("<I", gui, g(t) + 12 * k + 4)[0] for k in range(62) if k != 17],
          "action %d is used by a function" % ACTION)
    p = g(PRESS_TAB) + 4 * (ACTION - 1)
    check(struct.unpack_from("<I", gui, p)[0] == NOOP, "press action %d is not free" % ACTION)
    struct.pack_into("<I", gui, p, STUB)
    for a, ty, lab, nty, nlab in LABELS:
        check(struct.unpack_from("<IHH", gui, g(a)) == (CODE, ty, lab), "label entry %#x differs" % a)
        struct.pack_into("<IHH", gui, g(a), CODE, nty, nlab)
    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  Menu button function: 17 button lists + %d; stub %#x (%d B); blob B %#x -> %#x" % (CODE, STUB, len(stub), csz, len(c)))
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
