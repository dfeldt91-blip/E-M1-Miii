#!/usr/bin/env python3
"""On-camera HSL editor, step 1 (TEST, E-M1 Mark III 1.6): Custom's colours come from settings.

  MN10300_BIN=... python3 tools/patch_hsl.py IN.BIN OUT.BIN --seed [--version 0x1713]

Plan: docs/HSL_EDITOR_PLAN.md. Storage = the hidden PEN-F Color Profile settings, 3 sets x 12 sectors
(sector order yellow, orange, orange-red, red, magenta, violet, blue, blue-cyan, cyan, green-cyan,
green, yellow-green):
  saturation 0x399 + s (-5..5), hue 0x3a5 + s (-7..7), lightness 0x3b1 + s (-7..7).

Engine (as tools/patch_looks.py): Custom (Picture Mode entry 6) -> pipeline 11 (Color Profile); the
builder call at 0x603def9a jumps to a stub that, before the builder, writes the 12 saturations
(getter 0x602ca6a5, clamped) into the request (+0x718), and after it writes hue/lightness into the
12 records (record r = sector 2*(r%6)+r/6, through fishcu's step tables). Values out of range are
clamped, so whatever the hidden settings hold by default, the result stays within the editor range.

--seed (test only, until the editor exists): INFO on Color Creator in the Super Control Panel first
writes red hue +7 (0x3a8), blue lightness +7 (0x3b7) and green saturation -5 (0x3a3) through the
GUI setter 0x602ca855, then opens the Color Creator screen as before (the call to PostEventToCA at
0x60e7e644, blob B, goes through the seed stub).

Camera test:
 1. Before pressing anything, Custom should look like Natural (the hidden settings' defaults are 0);
    any colour shift there means their defaults are not 0.
 2. Picture Mode Color Creator, SCP, INFO (the Color Creator screen opens), Back, then Picture Mode
    Custom: reds shift in hue, blues get lighter, greens get duller (live view and photos).
 3. Power off, battery out, back on: Custom still shows the shift (the values were saved).
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402
import patch_looks as pl  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF, BLOB_B_END = 0x60c6c000, 0xc4afe0, 0x612f1000
GET, SET, POST = 0x602ca6a5, 0x602ca855, 0x60ed53f2
SAT0, HUE0, LIGHT0 = 0x399, 0x3a5, 0x3b1
STUB, SEED = 0x600d5a00, 0x600d5c00
INFO_CALL = 0x60e7e644                       # call PostEventToCA,[d2,d3,a2],48 after mov 33,d0; mov 48,d1
INFO_STOCK = bytes.fromhex("80218530")        # at INFO_CALL - 4
SEEDS = [(HUE0 + 3, 7), (LIGHT0 + 6, 7), (SAT0 + 10, -5)]

ENGINE = """add -24,sp
mov d0,(4,sp)
mov d1,(8,sp)
mov a0,(12,sp)
mov a1,(16,sp)
clr d0
mov d0,(20,sp)
1:
mov (20,sp),d0
add SAT0,d0
call get,[],4
exth d0
mov 5,d1
cmp d1,d0
ble 2f
mov d1,d0
2:
mov -5,d1
cmp d1,d0
bge 3f
mov d1,d0
3:
mov (16,sp),a1
mov (20,sp),d1
movbu d0,(d1,a1)
inc d1
mov d1,(20,sp)
cmp 12,d1
bne 1b
mov (4,sp),d0
mov (8,sp),d1
mov (12,sp),a0
mov (16,sp),a1
add 24,sp
call builder,[d2,d3,a2,a3],96
add -16,sp
mov d2,(4,sp)
mov d3,(8,sp)
mov a3,(12,sp)
mov (12,a2),a3
add 688,a3
clr d2
4:
mov sect,a0
movbu (d2,a0),d3
mov d3,d0
add HUE0,d0
call get,[],4
call clamp7,[],4
mov hue,a0
movhu (d0,a0),d0
movhu d0,(18,a3)
mov d3,d0
add LIGHT0,d0
call get,[],4
call clamp7,[],4
mov light,a0
movhu (d0,a0),d0
movhu d0,(22,a3)
add 24,a3
inc d2
cmp 12,d2
bne 4b
mov (4,sp),d2
mov (8,sp),d3
mov (12,sp),a3
add 16,sp
jmp resume
clamp7:
exth d0
mov 7,d1
cmp d1,d0
ble 5f
mov d1,d0
5:
mov -7,d1
cmp d1,d0
bge 6f
mov d1,d0
6:
add 7,d0
add d0,d0
ret [],4
.balign 2
hue:
""" + "".join(" .hword %d\n" % v for v in pl.HUE_LUT) + "light:\n" + \
    "".join(" .hword %d\n" % v for v in pl.LIGHT_LUT) + "sect:\n" + \
    "".join(" .byte %d\n" % s for s in pl.SECTOR)

SEED_SRC = "add -12,sp\nmov d0,(4,sp)\nmov d1,(8,sp)\n" + "".join(
    "mov %#x,d0\nmov %d,d1\ncall set,[d2,d3],16\n" % (sid, val) for sid, val in SEEDS) + \
    "mov (4,sp),d0\nmov (8,sp),d1\nadd 12,sp\ncall post,[d2,d3,a2],48\nret [],4\n"


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def asm(src, at, syms):
    import patch_aspect
    return patch_aspect.assemble_syms(src, at, syms)


def patch(main, seed=False):
    m = bytearray(main)
    o = lambda a: a - BASE  # noqa: E731
    e = o(pl.PM_LIST) + pl.PM_ELEM * pl.CUSTOM_IDX
    check(struct.unpack_from("<I", m, e)[0] == 6, "Custom picture-mode entry differs")
    check(bytes(m[o(pl.SITE):o(pl.SITE) + 5]) == pl.SITE_STOCK, "colour builder call differs")
    check(bytes(m[o(pl.SITE) - len(pl.SITE_PRE):o(pl.SITE)]) == pl.SITE_PRE, "colour selector differs")
    check(set(m[o(STUB):o(STUB) + 0x300]) == {0xff}, "stub area not free")
    syms = dict(get=GET, set=SET, post=POST, builder=pl.BUILDER, resume=pl.RESUME,
                SAT0=SAT0, HUE0=HUE0, LIGHT0=LIGHT0)
    eng = asm(ENGINE, STUB, syms)
    check(len(eng) <= 0x200, "engine stub too long")
    jmp = asm("jmp stub", pl.SITE, {"stub": STUB})
    check(len(jmp) == 5, "jump is not 5 bytes")
    m[e:e + pl.PM_ELEM] = struct.pack("<I", 11) + bytes(pl.PM_ELEM - 4)
    m[o(STUB):o(STUB) + len(eng)] = eng
    m[o(pl.SITE):o(pl.SITE) + 5] = jmp
    print("  Custom -> Color Profile; HSL from settings %#x/%#x/%#x; stub %#x (%d B)"
          % (SAT0, HUE0, LIGHT0, STUB, len(eng)))
    if seed:
        sd = asm(SEED_SRC, SEED, syms)
        check(len(sd) <= 0x100, "seed stub too long")
        m[o(SEED):o(SEED) + len(sd)] = sd
        check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
        csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
        gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
        check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
              "blob B does not recompress identically")
        g = INFO_CALL - BLOB_B
        stock_call = asm("call post,[d2,d3,a2],48", INFO_CALL, syms)
        check(bytes(gui[g - 4:g]) == INFO_STOCK and bytes(gui[g:g + 7]) == stock_call,
              "SCP INFO Color Creator post differs")
        new_call = asm("call seed,[],4", INFO_CALL, dict(syms, seed=SEED))
        check(len(new_call) == 7, "seed call is not 7 bytes")
        gui[g:g + 7] = new_call
        cg = olycompress.pack(bytes(gui))
        check(len(cg) <= (BLOB_B_END - BASE) - (BLOB_B_OFF + 32), "blob B does not fit")
        old_end = BLOB_B_OFF + 32 + csz
        m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(cg)] = cg
        if len(cg) < csz:
            m[BLOB_B_OFF + 32 + len(cg):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(cg))
        struct.pack_into("<I", m, BLOB_B_OFF + 16, len(cg))
        check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "blob B does not decode to the edit")
        print("  seed: SCP INFO on Color Creator writes %s" %
              ", ".join("%#x=%d" % s for s in SEEDS))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_main = patch(blocks[0]["plain"], seed="--seed" in argv)
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
