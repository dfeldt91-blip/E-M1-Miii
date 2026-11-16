#!/usr/bin/env python3
"""Looks in the Custom picture mode (EXPERIMENTAL, E-M1 Mark III 1.6). Stage 1: colour engine.

  MN10300_BIN=... python3 tools/patch_looks.py IN.BIN OUT.BIN --test1 [--version 0x1682]

Goal: Caduceus-style looks (caduceus-ep7, fishcu oly_fw_analysis PEN-F HSL) shot through the Custom
picture mode, picked on the computer; later stages load them from the card on the first half-press.

Colour engine on this body (same code as the E-P7 1.1, caduceus docs/HSL_PORT.md):
- Picture Mode list (setting 0x6f, 0x604bc4f4, 64-byte entries): Custom (GUI 6) entry 6 -> pipeline 11
  (Color Profile), the 1.595 repurpose (tools/patch_picture_modes.py --repurpose).
- Colour selector 0x603def13..: `cmp 11,d1; bne` (job key 11 = Color Profile), `add 0x718,a3`
  (request saturation), `mov 0x60529b50,a0` (COLOR table), then at 0x603def9a
  `call 0x603ded29,[d2,d3,a2,a3],96` (stock bytes cd 8f fd f0 60, identical to the E-P7's 0x603b02d9),
  resume 0x603def9f. The selector's a2 = context; context +12 = colour output.
- Builder 0x603ded29 output: 12 records of 24 bytes from output +688 (2 x 6 loop), hue (s16) at
  record +18, lightness (s16) at +22; control word 0xfff at +976. Hue units: 1000 per editor step
  (PEN-F/Caduceus range -7000..7000), lightness -300..300.

--test1: after the builder, every record gets hue +3000 and lightness 0 (an obvious colour shift,
Custom only, photos and live view). Shows that the hook and the record layout are right.
Camera 1.682: Custom colours shifted (live view and photo), other modes normal; Custom's base mode
(e.g. Monotone) no longer matters.

--test2 (colour map): hue 0; lightness -300 on record 0 and +300 on record 3, all others 0.
On the E-P7 the records are wheel sectors in the order 2*(r%6)+r/6, so record 0 and record 3
should be opposite colours (sectors 0 and 6).
Camera 1.683: yellow darker, blue lighter -> record 0 = yellow (sector 0), record 3 = blue (sector 6),
as the E-P7 order predicts.

--test3 (wheel direction): lightness -300 on record 6 (sector 1) and +300 on record 9 (sector 7).
If the wheel runs yellow -> green -> cyan -> blue, the darker colour is yellow-green and the brighter
one blue-violet; if it runs yellow -> orange -> red -> magenta -> blue, orange darker and cyan-blue
brighter.
Camera 1.684: orange darker -> the wheel runs yellow, orange, orange-red, red, magenta, violet, blue,
blue-cyan, cyan, green-cyan, green, yellow-green (sector 0..11), the order of caduceus-ep7's
sim/recipes (sector_order). Record r = sector 2*(r%6)+r/6, as on the E-P7.

--look NAME: a Caduceus recipe (LOOKS) in Custom: hue/lightness per sector (steps -7..7 through
fishcu's tables) and saturation per sector (-5..5): the builder reads one s8 per sector, in sector
order, from the request at a1 (+0x718); the stub writes the look's values there before the call.
Tone, contrast, WB shift, grain and bloom are not applied yet.
Camera 1.685 (portra): Custom clearly muted, live view = JPEG.

--test4 (unhide Color Profile, diagnostic, with --look): menus list Picture Mode values the API
canSettingValue (0x10208 -> 0x608d58ce(sid d0, GUI value d1); for 111 a class check 0x608d784a, then
the core check 0x602ca813) accepts. The hook answers yes for (0x6f, 54..56) (Color Profile 1-3), and
the 0x6f validator gets a 27th entry {11, 0} -> GUI 54 (as DIAL_NON's), list/alt copied to free space.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
PM_LIST, PM_ELEM, CUSTOM_IDX = 0x604bc4f4, 64, 6
SITE, SITE_STOCK, RESUME, BUILDER = 0x603def9a, bytes.fromhex("cd8ffdf060"), 0x603def9f, 0x603ded29
SITE_PRE = bytes.fromhex("fad318079dfcac20a75260fcdc509b5260")   # add 0x718,a3; mov a3,a1; movhu (..),d0; mov tab,a0
STUB = 0x600d5a00
SRC = """add -12,sp
mov d0,(0,sp)
mov d1,(4,sp)
mov a0,(8,sp)
mov sat,a0
clr d1
2:
movbu (d1,a0),d0
movbu d0,(d1,a1)
inc d1
cmp 12,d1
bne 2b
mov (0,sp),d0
mov (4,sp),d1
mov (8,sp),a0
add 12,sp
call builder,[d2,d3,a2,a3],96
mov (12,a2),a0
add 688,a0
mov hl,a1
mov 12,d1
1:
movhu (a1),d0
movhu d0,(18,a0)
movhu (2,a1),d0
movhu d0,(22,a0)
add 4,a1
add 24,a0
add -1,d1
bne 1b
jmp resume
.balign 2
hl:
"""


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def hl_table(hues, lights, sats):
    return ("".join(" .hword %d,%d\n" % (h, l) for h, l in zip(hues, lights)) + "sat:\n" +
            "".join(" .byte %d\n" % s for s in sats))


# Caduceus look steps (sector order yellow, orange, orange-red, red, magenta, violet, blue, blue-cyan,
# cyan, green-cyan, green, yellow-green) -> native record values. Record r holds sector
# 2*(r%6)+r/6; hue/lightness step tables from fishcu's PEN-F HSL (image_parameters.s).
HUE_LUT = [7000, 6000, 5000, 4000, 3000, 2000, 1000, 0, -1000, -2000, -3000, -4000, -5000, -6000, -7000]
LIGHT_LUT = [-300, -250, -200, -150, -100, -50, -25, 0, 25, 50, 100, 150, 200, 250, 300]
SECTOR = [2 * (r % 6) + r // 6 for r in range(12)]
from looks_library import LOOKS  # noqa: E402  (Caduceus recipes, Apache-2.0)
LOOKS = dict(LOOKS, portra400=LOOKS["portra"])


def look_values(look):
    hues = [HUE_LUT[max(-7, min(7, look["hue"][SECTOR[r]])) + 7] for r in range(12)]
    lights = [LIGHT_LUT[max(-7, min(7, look["light"][SECTOR[r]])) + 7] for r in range(12)]
    sats = [max(-5, min(5, s)) for s in look["sat"]]          # sector order, read by the builder
    return hues, lights, sats


# The stub assembled from SRC at STUB (for builds without binutils, e.g. the mod builder app);
# --look builds check that it still matches. Data follows: 12 x {hue, lightness} s16 at +0x50
# (label hl), 12 s8 saturations at +0x80 (label sat).
CODE = bytes.fromhex(
    "f8fef4420046044308fcdc805a0d6004f404f44544a50cc9f9580059045c08f8fe0cdd07933000f060"
    "f8220cfad0b002fcdd505a0d60850cf061f87012f86102f870162104201829ffc9efdc54953000")
JMP = bytes.fromhex("dc666acfff")       # jmp STUB at SITE
HL_OFF, SAT_OFF = 0x50, 0x80


def patch_at(m, base, key):
    """Write look KEY (looks_library) into M (bytearray holding the base section at runtime address
    BASE) without an assembler. Returns the look's name."""
    o = lambda a: a - base  # noqa: E731
    check(key in LOOKS, "unknown look %r" % key)
    hues, lights, sats = look_values(LOOKS[key])
    e = o(PM_LIST) + PM_ELEM * CUSTOM_IDX
    check(struct.unpack_from("<I", m, e)[0] == 6, "Custom picture-mode entry differs")
    check(bytes(m[o(SITE):o(SITE) + 5]) == SITE_STOCK, "colour builder call differs")
    check(bytes(m[o(SITE) - len(SITE_PRE):o(SITE)]) == SITE_PRE, "colour selector differs")
    check(set(m[o(STUB):o(STUB) + 0x100]) == {0xff}, "stub area not free")
    data = b"".join(struct.pack("<hh", h, l) for h, l in zip(hues, lights))
    m[e:e + PM_ELEM] = struct.pack("<I", 11) + bytes(PM_ELEM - 4)
    m[o(STUB):o(STUB) + len(CODE)] = CODE
    m[o(STUB) + HL_OFF:o(STUB) + HL_OFF + 48] = data
    m[o(STUB) + SAT_OFF:o(STUB) + SAT_OFF + 12] = bytes(s & 0xff for s in sats)
    m[o(SITE):o(SITE) + 5] = JMP
    return LOOKS[key]["name"]


def patch(main, hues, lights, sats=(0,) * 12):
    import patch_aspect
    m = bytearray(main)
    e = off(PM_LIST) + PM_ELEM * CUSTOM_IDX
    check(struct.unpack_from("<I", m, e)[0] == 6, "Custom picture-mode entry differs")
    check(bytes(m[off(SITE):off(SITE) + 5]) == SITE_STOCK, "colour builder call differs")
    check(bytes(m[off(SITE) - len(SITE_PRE):off(SITE)]) == SITE_PRE, "colour selector differs")
    check(set(m[off(STUB):off(STUB) + 0x100]) == {0xff}, "stub area not free")
    stub = patch_aspect.assemble_syms(SRC + hl_table(hues, lights, sats), STUB,
                                      {"builder": BUILDER, "resume": RESUME})
    check(len(stub) <= 0x100, "stub too long")
    jmp = patch_aspect.assemble_syms("jmp stub", SITE, {"stub": STUB})
    check(len(jmp) == 5, "jump is not 5 bytes")
    m[e:e + PM_ELEM] = struct.pack("<I", 11) + bytes(PM_ELEM - 4)
    m[off(STUB):off(STUB) + len(stub)] = stub
    m[off(SITE):off(SITE) + 5] = jmp
    print("  Custom -> Color Profile; H/L hook %#x -> stub %#x (%d B)" % (SITE, STUB, len(stub)))
    return bytes(m)


BLOB_A, BLOB_A_OFF, BLOB_B_OFF = 0x60803000, 0x7e1fe0, 0xc4afe0
CAN_SITE, CAN_STOCK, CAN_BACK = 0x608d58d3, bytes.fromhex("928386aaff"), 0x608d58d8
REC, REC_STOCK = 0x604da7bc, bytes.fromhex("6f008000f4c44b6034e84a608006400000060000")
PM_ALT, NON_LIST, NON_ALT = 0x604ae834, 0x604c3df4, 0x604aefc4
NEW_LIST, NEW_ALT, CAN_STUB = 0x600d62e0, 0x600d5b00, 0x600d5b80
CAN_SRC = """cmp 0x6f,d0
bne 1f
cmp 54,d1
bcs 1f
cmp 57,d1
bcc 1f
mov 1,d0
ret [d2,d3,a2],16
1:
mov a0,a2
mov d0,d3
mov d1,d2
cmp -1,d2
jmp back"""


def unhide(main):
    import patch_aspect
    import olycompress
    m = bytearray(main)
    check(bytes(m[off(REC):off(REC) + 20]) == REC_STOCK, "0x6f validator record differs")
    n = 26
    lst = bytes(m[off(PM_LIST):off(PM_LIST) + PM_ELEM * n])
    alt = bytes(m[off(PM_ALT):off(PM_ALT) + 4 * n])
    non = [bytes(m[off(NON_LIST) + PM_ELEM * k:off(NON_LIST) + PM_ELEM * (k + 1)]) for k in range(n)]
    non_alt = struct.unpack_from("<%dI" % n, m, off(NON_ALT))
    k11 = [k for k, e in enumerate(non) if struct.unpack_from("<I", e)[0] == 11]
    check(len(k11) == 1 and non_alt[k11[0]] == 54, "DIAL_NON Color Profile entry differs")
    for a, size in ((NEW_LIST, PM_ELEM * (n + 1)), (NEW_ALT, 4 * (n + 1)), (CAN_STUB, 0x40)):
        check(set(m[off(a):off(a) + size]) == {0xff}, "area %#x not free" % a)
    m[off(NEW_LIST):off(NEW_LIST) + PM_ELEM * (n + 1)] = lst + non[k11[0]]
    m[off(NEW_ALT):off(NEW_ALT) + 4 * (n + 1)] = alt + struct.pack("<I", 54)
    struct.pack_into("<II", m, off(REC) + 4, NEW_LIST, NEW_ALT)
    struct.pack_into("<H", m, off(REC) + 12, PM_ELEM * (n + 1))
    stub = patch_aspect.assemble_syms(CAN_SRC, CAN_STUB, {"back": CAN_BACK})
    check(len(stub) <= 0x40, "stub too long")
    m[off(CAN_STUB):off(CAN_STUB) + len(stub)] = stub
    acsz = struct.unpack_from("<I", m, BLOB_A_OFF + 16)[0]
    a = bytearray(olycompress.unpack(m, BLOB_A_OFF))
    check(olycompress.pack(bytes(a)) == bytes(m[BLOB_A_OFF + 32:BLOB_A_OFF + 32 + acsz]),
          "blob A does not recompress identically")
    check(bytes(a[CAN_SITE - BLOB_A:CAN_SITE - BLOB_A + 5]) == CAN_STOCK, "canSettingValue entry differs")
    a[CAN_SITE - BLOB_A:CAN_SITE - BLOB_A + 5] = b"\xdc" + struct.pack("<i", CAN_STUB - CAN_SITE)
    ca = olycompress.pack(bytes(a))
    check(len(ca) <= BLOB_B_OFF - (BLOB_A_OFF + 32), "blob A does not fit")
    old_end = BLOB_A_OFF + 32 + acsz
    m[BLOB_A_OFF + 32:BLOB_A_OFF + 32 + len(ca)] = ca
    if len(ca) < acsz:
        m[BLOB_A_OFF + 32 + len(ca):old_end] = b"\xff" * (old_end - BLOB_A_OFF - 32 - len(ca))
    struct.pack_into("<I", m, BLOB_A_OFF + 16, len(ca))
    check(olycompress.unpack(m, BLOB_A_OFF) == bytes(a), "blob A does not decode to the edit")
    print("  unhide: 0x6f list +{11,0}->54; canSettingValue hook %#x -> %#x (%d B)" % (CAN_SITE, CAN_STUB, len(stub)))
    return bytes(m)


def main(argv):
    if len(argv) < 3 or not any(x in argv for x in ("--test1", "--test2", "--test3", "--look", "--test4")):
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    hues, lights = [3000] * 12, [0] * 12
    if "--test2" in argv:
        hues, lights = [0] * 12, [0] * 12
        lights[0], lights[3] = -300, 300
    sats = [0] * 12
    if "--look" in argv:
        key = argv[argv.index("--look") + 1]
        hues, lights, sats = look_values(LOOKS[key])
    if "--test3" in argv:
        hues, lights = [0] * 12, [0] * 12
        lights[6], lights[9] = -300, 300
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_main = patch(blocks[0]["plain"], hues, lights, sats)
    if "--look" in argv:
        alt = bytearray(blocks[0]["plain"])
        patch_at(alt, BASE, key)
        check(bytes(alt) == new_main, "pre-assembled stub (CODE) differs from the assembled one")
    if "--test4" in argv:
        new_main = unhide(new_main)
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
