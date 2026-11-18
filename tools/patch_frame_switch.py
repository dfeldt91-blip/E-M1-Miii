#!/usr/bin/env python3
"""Frame for picture modes, switched by the SCP colour-space item (TEST, E-M1 Mark III 1.6).

  MN10300_BIN=... python3 tools/patch_frame_switch.py IN.BIN OUT.BIN [--version 0x1722]

Use with tools/patch_frame_white.py (--no-white --layer0-white): the Frame art effect's masks become
a clean white border. This patch lets that frame also run in the picture modes (not only art
filters), switched on and off by the Color Space setting (0x3c), which no longer sets the colour
space:

- Image: the capture snapshot builders read the Art Effect (property 0xf5d1) into job +26825
  (0x602c31fa, 0x6147cf82). That read goes through a stub: no effect set and the colour-space
  property 0x8bf1 = 1 -> Art Effect 3 (Frame), so the job is built as with a real Frame selection.
  (1.722 set job flag 0x8000 in the chain builder instead: no frame.)
- Colour space stays sRGB: the two capture snapshot builders read property 0x8bf1 (setting 0x3c)
  into job +26086 (0x602c2e31, 0x6147cf10); their property calls become `clr d0`.
- Labels: menus: title "Frame Effect" (string 0x2ff), values Off (0x5ae) / On (0xc6). SCP icons stay
  sRGB / Adobe RGB: SCP icon ids are per picker (1.722 used the Art Effect picker's ids and got
  "Off" / "2f 1.0EV"); the SCP title still read "Color Space".

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
PROP_GET = 0x6005fa9c                      # property read: d0 = property, a0 = 0, d1 = 0
EFF_SITES = [0x602c31fa, 0x6147cf82]        # call PROP_GET after `mov 0xf5d1,d0; mov 0,a0; clr d1`
EFF_PRE = bytes.fromhex("fcccd1f50000900004")
STUB = 0x600de000
SNAP = [0x602c2e31, 0x6147cf10]             # call 0x6005fa9c after `mov 0x8bf1,d0; mov 0,a0; clr d1`
SNAP_PRE = bytes.fromhex("fcccf18b0000900004")
SCP_REC, ART_REC = 0x611ef250, 0x611ef528
TITLE_OLD, TITLE_NEW, HELP = 0x58, 0x2ff, 0x1cf
VAL_OLD = {0x6aa: 0x5ae, 0x673: 0xc6}   # -> the Off / On strings every On/Off menu uses
EFF_SRC = """call prop,[d2,d3],12
cmp 0,d0
bne 9f
mov 0x8bf1,d0
mov 0,a0
clr d1
call prop,[d2,d3],12
cmp 1,d0
beq 8f
clr d0
bra 9f
8:
mov 3,d0
9:
ret [],4
"""


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    import patch_aspect
    m = bytearray(main)
    o = lambda a: a - BASE  # noqa: E731
    check(set(m[o(STUB):o(STUB) + 0x80]) == {0xff}, "stub area not free")
    code = patch_aspect.assemble_syms(EFF_SRC, STUB, {"prop": PROP_GET})
    m[o(STUB):o(STUB) + len(code)] = code
    for site in EFF_SITES:
        check(bytes(m[o(site) - 9:o(site)]) == EFF_PRE and m[o(site)] == 0xdd and
              bytes(m[o(site) + 5:o(site) + 7]) == bytes.fromhex("c00c"), "Art Effect read at %#x differs" % site)
        call = patch_aspect.assemble_syms("call eff,[],4", site, {"eff": STUB})
        check(len(call) == 7, "call length")
        m[o(site):o(site) + 7] = call
    for s in SNAP:
        check(bytes(m[o(s) - 9:o(s)]) == SNAP_PRE and m[o(s)] == 0xdd, "snapshot read at %#x differs" % s)
        m[o(s):o(s) + 7] = b"\x00" + b"\xcb" * 6          # clr d0 ; nop x6
    print("  Art Effect reads %s -> stub %#x (%d B): Frame when the switch is on; colour space reads fixed to sRGB"
          % (", ".join("%#x" % x for x in EFF_SITES), STUB, len(code)))

    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    g = lambda a: a - BLOB_B  # noqa: E731
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
    print("  labels: %d value lists Off/On, %d titles 'Frame Effect'" % (nval, ntitle))
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
