#!/usr/bin/env python3
"""Frame for picture modes, switched by the SCP colour-space item (TEST, E-M1 Mark III 1.6).

  MN10300_BIN=... python3 tools/patch_frame_switch.py IN.BIN OUT.BIN [--version 0x1722]

Use with tools/patch_frame_white.py (--no-white --layer0-white): the Frame art effect's masks become
a clean white border. This patch lets that frame also run in the picture modes (not only art
filters), switched on and off by the Color Space setting (0x3c), which no longer sets the colour
space:

- Image: the chain builder (one function from 0x60384438) adds the Frame stage 0x6038873b when the
  job flags have 0x8000 (`btst 0x8000,d0; beq 0x603853b4` at 0x6038536c). That test jumps to a
  stub: for a non-art job (key 0x01VV00MM = art filter) with setting 0x3c = 1, it sets flag 0x8000
  in the job flags word (so the stage dispatcher 0x60388c36 also picks Frame).
- Colour space stays sRGB: the two capture snapshot builders read property 0x8bf1 (setting 0x3c)
  into job +26086 (0x602c2e31, 0x6147cf10); their property calls become `clr d0`.
- Labels: the SCP item (record 0x611ef250, icon lists 0x611ec6d0 / 0x611ec6e8) gets the Art Effect
  Off / Frame icons (0x213b/0x2134, 0x166/0x85e from record 0x611ef528); menus: title "Frame Effect"
  (string 0x2ff), values "Off" (0xbf) / "On" (0xc6).

Camera test: SCP, the former sRGB/AdobeRGB item: Off / Frame icons. Frame on, Picture Mode Natural:
white border in live view and on the photo; off: none. Art filters keep their own Art Effect.
Photos stay sRGB either way. File names may start with '_' while on (Adobe RGB naming), to check.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF, BLOB_B_END = 0x60c6c000, 0xc4afe0, 0x612f1000
SITE, SITE_STOCK = 0x6038536c, bytes.fromhex("faec0080c844")
YES, NO = 0x60385372, 0x603853b4
GET, SID = 0x602ca6a5, 0x3c
STUB = 0x600de000
SNAP = [0x602c2e31, 0x6147cf10]             # call 0x6005fa9c after `mov 0x8bf1,d0; mov 0,a0; clr d1`
SNAP_PRE = bytes.fromhex("fcccf18b0000900004")
SCP_REC, ART_REC = 0x611ef250, 0x611ef528
TITLE_OLD, TITLE_NEW, HELP = 0x58, 0x2ff, 0x1cf
VAL_OLD, VAL_NEW = {0x6aa: 0xbf, 0x673: 0xc6}, None
STUB_SRC = """mov (12,sp),a0
mov (a0),d0
btst 0x8000,d0
bne yes
mov (16,sp),a1
mov (a1),d1
lsr 24,d1
cmp 1,d1
beq no
mov SID,d0
call get,[],4
cmp 1,d0
bne no
mov (12,sp),a0
mov (a0),d0
or 0x8000,d0
mov d0,(a0)
yes:
jmp yeslbl
no:
jmp nolbl
"""


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    import patch_aspect
    m = bytearray(main)
    o = lambda a: a - BASE  # noqa: E731
    check(bytes(m[o(SITE):o(SITE) + 6]) == SITE_STOCK, "Frame stage test at %#x differs" % SITE)
    check(set(m[o(STUB):o(STUB) + 0x80]) == {0xff}, "stub area not free")
    src = STUB_SRC
    code = patch_aspect.assemble_syms(src, STUB, {"get": GET, "SID": SID, "yeslbl": YES, "nolbl": NO})
    m[o(STUB):o(STUB) + len(code)] = code
    jmp = patch_aspect.assemble_syms("jmp stub", SITE, {"stub": STUB})
    check(len(jmp) == 5, "jump length")
    m[o(SITE):o(SITE) + 6] = jmp + b"\xcb"
    for s in SNAP:
        check(bytes(m[o(s) - 9:o(s)]) == SNAP_PRE and m[o(s)] == 0xdd, "snapshot read at %#x differs" % s)
        m[o(s):o(s) + 7] = b"\x00" + b"\xcb" * 6          # clr d0 ; nop x6
    print("  Frame stage hook %#x -> stub %#x (%d B); colour space reads fixed to sRGB" % (SITE, STUB, len(code)))

    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    g = lambda a: a - BLOB_B  # noqa: E731
    rid, l1, l2, n, _ = struct.unpack_from("<5I", gui, g(SCP_REC))
    aid, a1, a2, an, _ = struct.unpack_from("<5I", gui, g(ART_REC))
    check(rid == 0x21 and n == 2 and aid == 0x2f, "SCP records differ")
    for cs, art in ((l1, a1), (l2, a2)):
        icons = {}
        for k in range(an):
            v, t, s, c = struct.unpack_from("<iHHI", gui, g(art) + 12 * k)
            icons.setdefault(v, s)
        for k in range(2):
            v, t, s, c = struct.unpack_from("<iHHI", gui, g(cs) + 12 * k)
            check(v == k and t == 3, "SCP colour-space icon list differs")
            struct.pack_into("<H", gui, g(cs) + 12 * k + 6, icons[3 if k else 0])
    nval = 0
    for i in range(0, len(gui) - 24, 4):
        a = struct.unpack_from("<iHHI", gui, i)
        b = struct.unpack_from("<iHHI", gui, i + 12)
        if (a[0], a[1], a[2], b[0], b[1], b[2]) == (0, 4, 0x6aa, 1, 4, 0x673):
            # only the colour-space item's lists (not Edit Filename's): referenced right after the
            # item's help label {4, 0x1cf, cond}, as its second list, or by the SCP text record
            ptr = struct.pack("<I", BLOB_B + i)
            j = gui.find(ptr)
            ok = False
            while j >= 0:
                before = struct.unpack_from("<HH", gui, j - 8)
                if before == (4, HELP) or struct.unpack_from("<HH", gui, j - 16) == (4, HELP) or \
                        struct.unpack_from("<I", gui, j + 4)[0] == 2:
                    ok = True
                j = gui.find(ptr, j + 1)
            if ok:
                struct.pack_into("<H", gui, i + 6, VAL_OLD[0x6aa])
                struct.pack_into("<H", gui, i + 12 + 6, VAL_OLD[0x673])
                nval += 1
    ntitle = 0
    pat = struct.pack("<HH", 4, TITLE_OLD)
    i = gui.find(pat)
    while i >= 0:
        if i % 4 == 0 and struct.unpack_from("<HH", gui, i + 8) == (4, HELP):
            struct.pack_into("<H", gui, i + 2, TITLE_NEW)
            ntitle += 1
        i = gui.find(pat, i + 1)
    check(nval >= 3 and ntitle >= 1, "labels: %d value lists, %d titles" % (nval, ntitle))
    cg = olycompress.pack(bytes(gui))
    check(len(cg) <= (BLOB_B_END - BASE) - (BLOB_B_OFF + 32), "blob B does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(cg)] = cg
    if len(cg) < csz:
        m[BLOB_B_OFF + 32 + len(cg):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(cg))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(cg))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "blob B does not decode to the edit")
    print("  labels: SCP icons Off/Frame, %d value lists Off/On, %d titles 'Frame Effect'" % (nval, ntitle))
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
