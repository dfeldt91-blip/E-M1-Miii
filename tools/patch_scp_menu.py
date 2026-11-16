#!/usr/bin/env python3
"""SCP button-function cell opens the main menu (EXPERIMENTAL, E-M1 Mark III 1.6).

  MN10300_BIN=... python3 tools/patch_scp_menu.py IN.BIN OUT.BIN [--version 0x1675]

SsMenuLv state machine (blob B): descriptor 0x6124a6d4 {22 states, 111 events, 140 handlers,
matrix 0x61249c9c (event-major, matrix[ev * 22 + state - 1]), handlers 0x61249a6c, event map
0x612496f4 ({u32 code, u32 index}: 0x900c OK = 6, 0x900e MENU = 7), entry 0x6124a628, exit
0x6124a680}. State 3 = Super Control Panel: OK -> 0x60e7bef5, MENU -> 0x60e7c352 (posts camera
event (18, 7) through 0x60ed53f2 and returns 0x104).

The OK handler 0x60e7bef5 reads the cell's setting id; the bottom-right cell is
MODE_CUSTOM_SW_SCP_STILL (0x563), which returns (4, 9) = the Button Function screen. This patch
replaces the body of that case (from 0x60e7c208, right after `cmp 0x563,d1; bne`) with what MENU
does in the SCP: post (18, 7), then return 0x104 through the handler's common exit 0x60e7c342
(d2 << 8 | a3). The movie cell (0x1b5, handled in another state) is unchanged.
Camera 1.675/1.676: the cell opens the main menu.
Title: the SCP cell title table (pairs {u32 string, u32 n}, e.g. 0x611f0ff8 "@A003@AF Mode" 6,
"@A003@WB" 7, "@A003@Kelvin" 28) has {0xc73 "@A003@Button Function", 12} at 0x611f1010 -> "Menu"
(0xa7). The Custom Menu item (setting 0xd1a) uses its own records with 0xc73 and is unchanged.
Camera 1.679: the SCP cell is titled "Menu" and opens the main menu.
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
SITE, CASE_END = 0x60e7c208, 0x60e7c274
STOCK_CMP = bytes.fromhex("fac96305c96e")          # cmp 0x563,d1 ; bne 0x60e7c274 at 0x60e7c202
STOCK_MENU = bytes.fromhex("f8fefc80128507dd99900500e0302c0401df0004")   # SCP MENU handler 0x60e7c352
MENU_HANDLER, EXIT, POST = 0x60e7c352, 0x60e7c342, 0x60ed53f2
TITLE, TITLE_STOCK, TITLE_NEW = 0x611f1010, (0xc73, 12), 0xa7   # "Menu"
SRC = """mov 18,d0
mov 7,d1
call post,[d2,d3,a2],48
mov 1,d2
mov 4,a3
jmp exit"""


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    import patch_aspect
    m = bytearray(main)
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    g = lambda a: a - BLOB_B  # noqa: E731
    check(bytes(gui[g(SITE) - 6:g(SITE)]) == STOCK_CMP, "cell 0x563 case differs")
    check(bytes(gui[g(MENU_HANDLER):g(MENU_HANDLER) + len(STOCK_MENU)]) == STOCK_MENU, "SCP MENU handler differs")
    code = patch_aspect.assemble_syms(SRC, SITE, {"post": POST, "exit": EXIT})
    check(SITE + len(code) <= CASE_END, "stub too long")
    gui[g(SITE):g(SITE) + len(code)] = code
    check(struct.unpack_from("<2I", gui, g(TITLE)) == TITLE_STOCK, "SCP title entry differs")
    struct.pack_into("<I", gui, g(TITLE), TITLE_NEW)
    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  SCP cell 0x563 OK -> main menu (%d B at %#x); blob B %#x -> %#x" % (len(code), SITE, csz, len(c)))
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
