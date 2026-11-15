#!/usr/bin/env python3
"""High Res Shot as a button function (EXPERIMENTAL, E-M1 Mark III 1.6).

  MN10300_BIN=... python3 tools/patch_hires_button.py IN.BIN OUT.BIN [--version 0x1667]

A button's setting value is a function code. Stock has no code for High Res Shot; this patch makes
770 (0x302, the Shooting Menu "High Res Shot" switch, values 0/1; tripod or handheld stays
MODE_PIXSHIFT_SR_HANDHELD 0x68f)
one, offered on the full custom buttons right after Live ND. Pressing the button switches High Res
on or off, like Live ND's on/off setting.

Code 284 ("Backlit LCD", a function for bodies with a backlit top LCD) is in every button table
but in no button's list on this body. Its slots are reused, so no table moves or grows:
  function table 0x60f2343c {code, action, alt}, row 17: (284, 29, 69) -> (770, 99, 3200)
  press jump table 0x60f37cdc[action - 1]: action 102 is a no-op (0x60cc4aab, the dispatcher's
      RET) -> stub in the base section, which toggles 0x302 with the GUI setting API
      (get 0x60cb1b1e, set 0x60cb1a73) and jumps to that RET
  label tables {u32 code, u16 type, u16 label, u32 cond} (type 3 icon, type 4 string):
      0x611d8a64 / 0x61296124 (icons) and 0x61295f20 (names): -> (770, 4, "High Res Shot")
      0x6129649c (help): -> (770, 4, "Takes and combines eight pictures ...")
Button lists (validator records {u16 sid, u16 0x80, u32 list, u32, u16 nbytes, u16 2}): the 17
full-button lists (16 x 38 codes, 1 x 39) get 770 after 1680 (Live ND); two new shared lists in
base-section free space.

Camera 1.667 used action 102: the picker showed High Res Shot, but the button switched the card
slot. 102 is a type-1 action (0x60f22cfc), handled by another dispatcher (0x60cd32d7), not the
press table.
1.668/1.669 toggled 0x2f2 (754, MODE_PIXSHIFT_SR): the High Res icon came on, but the camera froze
on the shot. 0x2f2 is the internal flag the camera derives from the menu switch 0x302 (770) once
the capture is set up (menu tables list 770 as "High Res Shot", next to Live ND 0x690; the E-P7
has the same pair as 775 / 758). The button now toggles 770.
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
CODE, OLD_CODE, ACTION = 770, 284, 99
ACTION_TYPES = 0x60f22cfc     # {u32 action, u32 type, u32 name}: type 2 -> press jump table
FUNC_ROW, FUNC_STOCK, FUNC_NEW = 0x60f2343c + 12 * 17, (284, 29, 69), (770, 99, 3200)
PRESS_TAB, NOOP = 0x60f37cdc, 0x60cc4aab
NAME, HELP = 0x986, 0x987                       # "High Res Shot", "Takes and combines eight ..."
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
# Same steps as the stock Live ND toggle 0x60cc4ace (key table 0x60f5846c): skip the change while
# busy (0x60ccaf7d != 0), toggle, then 0x60cb498e(8) (back to the shooting screen, which re-applies
# the shooting mode). 1.668 toggled without that last call: the camera restarted on the shot.
SRC = """call busy,[d2,a2],20
cmp 0,d0
bne refresh
mov 0x302,d0
call get,[d2,a2],24
cmp 0,d0
bne off
mov 0x302,d0
mov 1,d1
bra store
off:
mov 0x302,d0
clr d1
store:
call set,[d2,a2],20
refresh:
mov 8,d0
mov a3,a1
mov a2,a0
call shoot,[d2,d3,a2,a3],124
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
    stub = patch_aspect.assemble_syms(SRC, STUB, {"back": NOOP, "get": 0x60cb1b1e, "set": 0x60cb1a73,
                                                      "busy": 0x60ccaf7d, "shoot": 0x60cb498e})
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
    codes = [struct.unpack_from("<I", gui, g(t) + 12 * k)[0] for k in range(62)]
    check(CODE not in codes, "%d already in the function table" % CODE)
    struct.pack_into("<3I", gui, g(FUNC_ROW), *FUNC_NEW)
    check(struct.unpack_from("<2I", gui, g(ACTION_TYPES) + 12 * ACTION) == (ACTION, 2),
          "action %d is not a type-2 (press table) action" % ACTION)
    check(ACTION not in [struct.unpack_from("<I", gui, g(t) + 12 * k + 4)[0] for k in range(62) if k != 17],
          "action %d is used by a function" % ACTION)
    p = g(PRESS_TAB) + 4 * (ACTION - 1)
    check(struct.unpack_from("<I", gui, p)[0] == NOOP, "press action %d is not free" % ACTION)
    struct.pack_into("<I", gui, p, STUB)
    for a, ty, lab, nty, nlab in LABELS:
        check(struct.unpack_from("<IHH", gui, g(a)) == (OLD_CODE, ty, lab), "label entry %#x differs" % a)
        struct.pack_into("<IHH", gui, g(a), CODE, nty, nlab)
    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  17 button lists + %d; stub %#x (%d B); blob B %#x -> %#x" % (CODE, STUB, len(stub), csz, len(c)))
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
