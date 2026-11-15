#!/usr/bin/env python3
"""Exposure presets on Myset 2/3/4 (EXPERIMENTAL prototype, E-M1 Mark III, 1.5-based).

  MN10300_BIN=... python3 tools/patch_hold_presets.py IN.BIN OUT.BIN [--version 0x1616]

Button functions -> actions: function table 0x60f23444 {fallback, code, action}; codes 3348..3351 =
MYSET_1..4 (actions 3..6, type 2). The Myset press handler 0x60cc97db (blob B) toggles: start
(0x60cc9822, loads Custom Mode 15..18) or end (0x60cc993e, restore). GUI setting API (blob B):
set 0x60cb1a73(d0 sid, d1 value), get 0x60cb1b1e(d0 sid) -> d0.

Prototype: Myset 2 / 3 / 4 become ISO (sid 6) / Shutter (sid 4) / Aperture (sid 3) presets, toggle:
  press (off -> on): prev = get(sid); if a preset is stored, set(sid, preset)
  press (on -> off): preset = get(sid) (keeps any dial change made meanwhile); set(sid, prev)
Myset 1 stays stock. State in RAM (boot-copied base section, starts 0xff = no preset), so presets
are lost at power-off.
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
SITE, STOCK, BACK = 0x60cc97db, bytes.fromhex("9792838a01"), 0x60cc97e0
STUB, VARS, SIDS = 0x600d6c00, 0x600d6cc0, 0x600d6cbc
SRC = """cmp 4,d0
bcs stock
cmp 7,d0
bcc stock
mov d0,d3
add -4,d3
mov sids,a0
mov d3,a1
add a0,a1
movbu (a1),d2
mov d3,d0
asl2 d0
mov d0,d1
add d0,d0
add d1,d0
mov vars,a2
add d0,a2
mov (a2),d0
cmp 1,d0
bne turn_on
mov d2,d0
call get,[d2,a2],24
mov d0,(8,a2)
mov (4,a2),d1
mov d2,d0
call set,[d2,a2],20
clr d0
mov d0,(a2)
ret [d2,d3,a2,a3],20
turn_on:
mov d2,d0
call get,[d2,a2],24
mov d0,(4,a2)
mov (8,a2),d1
cmp -1,d1
beq mark
mov d2,d0
call set,[d2,a2],20
mark:
mov 1,d0
mov d0,(a2)
ret [d2,d3,a2,a3],20
stock:
mov a1,a3
mov a0,a2
mov d0,d3
mov 1,d2
jmp back"""


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    import patch_aspect
    m = bytearray(main)
    check(set(m[off(STUB - 16):off(VARS + 48)]) == {0xff}, "stub/vars area not free")
    stub = patch_aspect.assemble_syms(SRC, STUB, {"back": BACK, "sids": SIDS, "vars": VARS,
                                                  "get": 0x60cb1b1e, "set": 0x60cb1a73})
    check(STUB + len(stub) <= SIDS, "stub too long (%d)" % len(stub))
    m[off(STUB):off(STUB) + len(stub)] = stub
    m[off(SIDS):off(SIDS) + 3] = bytes([6, 4, 3])
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    g = SITE - BLOB_B
    check(bytes(gui[g:g + 5]) == STOCK, "Myset handler entry differs")
    gui[g:g + 5] = b"\xdc" + struct.pack("<i", STUB - SITE)
    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")
    print("  Myset hook %#x -> stub %#x (%d B), vars %#x; blob B %#x -> %#x" % (SITE, STUB, len(stub), VARS, csz, len(c)))
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
