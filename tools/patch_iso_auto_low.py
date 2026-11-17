#!/usr/bin/env python3
"""ISO-Auto down to L64 (EXPERIMENTAL, E-M1 Mark III 1.6). Stage 1.

  python3 tools/patch_iso_auto_low.py IN.BIN OUT.BIN [--version 0x1708]

ISO values are APEX Sv x 256: ISO 100 = 0x500, 1/3 EV = 0x55 (L64 0x455, L80 0x4aa, 100 0x500, 125
0x555, 160 0x5aa, 200 0x600 ... 6400 0xb00). ISO-Auto Set (menu "Upper Limit / Default") uses settings
0x68b MODE_ISO_LIMITER_STILL (upper limit) and 0x68d MODE_ISO_STANDARD_STILL (default; ISO-Auto
starts there and only rises), movie 0x68c / 0x68e. Their setting records (0x604dbf90 + 20 x k, {u16
id, u16 0x80, u32 values, u32 shown numbers, u16 bytes, u16 2, u32}) share the 16-value list 0x604d90e2
(0x600..0xb00) and the menu's numbers 0x604b0534 (u32 200, 250 .. 6400). 0x602ccac7.. keeps default <= upper limit. The exposure code clamps the ISO-Auto
values to 0x600..0xb00 at 0x604372ca (six per-mode copies 0x62167ed4..) and 0x60434633.

0x68d (stills Default) gets its own 21-value list at 0x600d9280: L64 L80 100 125 160, then 200..6400,
and its own number list at 0x600d92c0 (64 80 100 125 160 200 .. 6400); both clamps' lower bound
0x600 -> 0x455. Upper Limit and movie keep 200..6400.
Camera 1.703 (no number list): ISO-Auto went down to 64; the new menu entries were blank.
Camera 1.704 (Default's own number list): still blank. The "Upper Limit / Default" screen (menu item
0x68b) probably shows both columns through the 0x68b record, so 1.705 gives Upper Limit (0x68b) the
same two lists too (Upper Limit can then also be set to 64..160).
Camera 1.705 (lists on both records): the new entries were not shown at all and ISO-Auto stopped at
200. Camera 1.706 (clamps only): M goes down to 64 (Default ignored); in S and A, Default is the floor
(200 and up work). 0x604372b3.. clamps Default into the per-mode copies 0x62167ed4..ede, which S/A use
as the floor. 1.707: that clamp compares with 0x601 instead, so Default 200 gives L64 (no floor) and
Default 250+ keeps working as the floor; 0x60434633 (M, P?) floor L64.
Camera 1.707: still 200 in P/A/S (64 in M). 1.708: the ISO-Auto base 0x60433c7e: floor 0x600 -> 0x455,
and Default 200 -> L64 where it takes Default (cases 0xa000 / 0xa100); 0x604372ca back to 1.706.
Earlier note: Default is not the lower bound (Default 1000 still went down to 64). ISO-Auto's floor
is the hard 0x600 clamp above, so the clamps alone give ISO-Auto L64..Upper Limit. Default: clamps
only; --menu-lists adds the (still blank-labelled) Default/Upper Limit entries 64..160.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
REC_DEFAULT = 0x604dbfb8
REC_LIMIT = 0x604dbf90
STOCK_LIST = 0x604d90e2
STOCK_VALUES = [0x600 + 0x55 * k + (k // 3) for k in range(16)]
NEW_LIST = 0x600d9280
STOCK_NUMS, NEW_NUMS = 0x604b0534, 0x600d92c0
NUMS = [64, 80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600, 2000, 2500, 3200, 4000,
        5000, 6400]
LOW = [0x455, 0x4aa, 0x500, 0x555, 0x5aa]
# ISO-Auto base Sv 0x60433c7e (AE input struct copy 0x62167ddc: +24 iso_limiter, +26 iso_standard =
# Default): floor d3 = 0x600 (0x45c in another state); case 0xa000 / 0xa100 take Default (0 -> floor),
# 0x9f00 the upper limit; the result is clamped to floor..0xd00. Camera 1.707: P/A/S never below 200.
FLOOR = (0x60433c88, "2f0006", "2f5504")    # mov 0x600,d3 -> mov 0x455,d3
STUBS = [  # (site, stock bytes, back, stub address, source): Default 200 -> L64 in the 0xa000 / 0xa100 cases
    (0x60433ccc, "231af063f8be0ea000c82e", 0x60433d03, 0x600d9400, """add 26,a3
movhu (a3),d0
movhu (14,sp),d2
cmp 0,d0
beq 9f
movhu (a3),d2
cmp 0x600,d2
bne 9f
mov 0x455,d2
9:
jmp back"""),
    (0x60433cdb, "901af17cf060f8be0ea000c804f068", 0x60433cea, 0x600d9440, """mov 26,a0
add a3,a0
movhu (a0),d0
movhu (14,sp),d2
cmp 0,d0
beq 9f
movhu (a0),d2
cmp 0x600,d2
bne 9f
mov 0x455,d2
9:
jmp back"""),
]
CLAMPS = [  # (address, stock bytes, new bytes)
    (0x604372ca, "fac80006", "fac85504"),   # cmp 0x600,d0 -> cmp 0x455,d0
    (0x604372d0, "2e0006", "2e5504"),       # mov 0x600,d2 -> mov 0x455,d2
    (0x60434633, "fac80006", "fac85504"),
    (0x60434639, "2c0006", "2c5504"),       # mov 0x600,d0 -> mov 0x455,d0
]


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def off(a):
    return a - BASE


def patch_at(m, base, lists=False):
    o = lambda a: a - base  # noqa: E731
    for a, old, nw in CLAMPS:
        old, nw = bytes.fromhex(old), bytes.fromhex(nw)
        check(bytes(m[o(a):o(a) + len(old)]) == old, "clamp at %#x differs" % a)
        m[o(a):o(a) + len(nw)] = nw
    import patch_aspect
    a, old, nw = FLOOR
    check(bytes(m[o(a):o(a) + 3]) == bytes.fromhex(old), "ISO-Auto floor at %#x differs" % a)
    m[o(a):o(a) + 3] = bytes.fromhex(nw)
    for site, old, back, at, src in STUBS:
        old = bytes.fromhex(old)
        check(bytes(m[o(site):o(site) + len(old)]) == old, "Default load at %#x differs" % site)
        stub = patch_aspect.assemble_syms(src, at, {"back": back})
        check(len(stub) <= 0x40 and set(m[o(at):o(at) + 0x40]) == {0xff}, "stub space at %#x not free" % at)
        m[o(at):o(at) + len(stub)] = stub
        jmp = patch_aspect.assemble_syms("jmp stub", site, {"stub": at})
        check(len(jmp) == 5, "jump is not 5 bytes")
        m[o(site):o(site) + len(old)] = jmp + b"\xcb" * (len(old) - 5)
    if not lists:
        return 0
    for rec, sid0 in ((REC_DEFAULT, 0x68d), (REC_LIMIT, 0x68b)):
        sid, fl, vp, z, n, sz = struct.unpack_from("<HHIIHH", m, o(rec))
        check((sid, fl, vp, z, n, sz) == (sid0, 0x80, STOCK_LIST, STOCK_NUMS, 32, 2), "ISO-Auto record %#x differs" % sid0)
    check(list(struct.unpack_from("<16I", m, o(STOCK_NUMS))) == NUMS[5:], "ISO-Auto number list differs")
    vals = list(struct.unpack_from("<16H", m, o(STOCK_LIST)))
    check(vals == STOCK_VALUES, "ISO-Auto value list differs")
    new = LOW + vals
    data = struct.pack("<%dH" % len(new), *new)
    check(set(m[o(NEW_LIST) - 16:o(NEW_LIST) + len(data) + 16]) == {0xff}, "list area not free")
    m[o(NEW_LIST):o(NEW_LIST) + len(data)] = data
    nums = struct.pack("<%dI" % len(NUMS), *NUMS)
    check(set(m[o(NEW_NUMS) - 16:o(NEW_NUMS) + len(nums) + 16]) == {0xff}, "number list area not free")
    m[o(NEW_NUMS):o(NEW_NUMS) + len(nums)] = nums
    for rec in (REC_DEFAULT, REC_LIMIT):
        struct.pack_into("<I", m, o(rec) + 8, NEW_NUMS)
        struct.pack_into("<I", m, o(rec) + 4, NEW_LIST)
        struct.pack_into("<H", m, o(rec) + 12, len(data))
    return len(new)


def patch(main):
    m = bytearray(main)
    n = patch_at(m, BASE, "--menu-lists" in sys.argv)
    print("  ISO-Auto lower bound 200 -> L64" + (" + menu lists (%d values)" % n if n else ""))
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
