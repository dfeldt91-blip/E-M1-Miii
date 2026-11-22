#!/usr/bin/env python3
"""Frame art effect in handheld High Res Shot (EXPERIMENTAL, E-M1 Mark III 1.6).

  MN10300_BIN=... python3 tools/patch_hires_frame.py IN.BIN OUT.BIN [--version 0x1732]

Use with patch_hires_art.py (art filters selectable in High Res) and patch_frame_white.py
(clean white border masks). The High Res capture sequence has no art-effect stage: the chain
dispatch sends its photo jobs to builder 0x60395eb9, which builds no mask/effect stages, so even
when the JPEG gets the selected art filter's colour and tone, the Frame border is never blended.

This patch makes photo jobs go through the art chain builder 0x60384438 (the only chain builder
that sets up art effect stages) while MODE_PIXSHIFT_SR (0x2f2) is on. The settings getter
0x602ca6a5 works in image code; a stub at 0x600df000 checks the High Res flag and jumps to the
art builder's dispatch target when it is set, otherwise the stock kind check runs unchanged.

Camera test needed: 1.727 sent *picture-mode* jobs through the art builder and rebooted; High Res
jobs may have the art-only setup that picture-mode jobs lacked. Use --version 0x1732.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
GET, SID = 0x602ca6a5, 0x2f2
DISP_SITE, DISP_STOCK = 0x60381706, bytes.fromhex("fa022c2ca00cc90a")
DISP_STUB = 0x600df000
DISP_ART, DISP_NORMAL = 0x6038170e, 0x60381716
DISP_SRC = """mov (11308,a2),d0
cmp 12,d0
beq 7f
mov SID,d0
call get,[],4
cmp 1,d0
bne 8f
7:
jmp art
8:
jmp normal
"""


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_main(main):
    import patch_aspect
    m = bytearray(main)
    o = lambda a: a - BASE  # noqa: E731
    check(bytes(m[o(DISP_SITE):o(DISP_SITE) + 8]) == DISP_STOCK, "chain dispatch differs")
    check(set(m[o(DISP_STUB):o(DISP_STUB) + 0x60]) == {0xff}, "stub area %#x not free" % DISP_STUB)
    code = patch_aspect.assemble_syms(DISP_SRC, DISP_STUB,
                                      {"get": GET, "SID": SID, "art": DISP_ART, "normal": DISP_NORMAL})
    check(len(code) <= 0x60, "stub too long (%d bytes)" % len(code))
    m[o(DISP_STUB):o(DISP_STUB) + len(code)] = code
    m[o(DISP_SITE):o(DISP_SITE) + 8] = patch_aspect.assemble_syms("jmp t", DISP_SITE, {"t": DISP_STUB}) + b"\xcb" * 3
    print("  High Res photo jobs -> art chain builder (%#x -> %#x, %d B stub)"
          % (DISP_SITE, DISP_STUB, len(code)))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    plains = [b["plain"] for b in blocks]
    plains[0] = patch_main(plains[0])
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), plains[i], bytes(tail))
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
