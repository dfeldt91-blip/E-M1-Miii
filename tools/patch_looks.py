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
Camera 1.686: nothing new in the menus or SCP. Dropped; the menus' list comes from elsewhere.

--looks K1,K2,K3,K4,K5,K6 (stage 2, picker): six looks in Custom, picked on the camera with Custom's
base mode (setting 0xd3, GUI values i-Finish 7, Vivid 0, Natural 1, Muted 2, Portrait 5, Monotone 3,
in that menu order = looks 1..6). The stub reads 0xd3 through the settings getter 0x602ca6a5
(`call ..,[],4`, sid in d0, GUI value out) before and after the builder call and indexes a 6 x 60-byte
table {12 x (hue, lightness) s16, 12 x s8 saturation}.
Labels (Custom only): Custom's base-mode option lists (descriptors {0xd3, ..., list, 6}: 0x611b3f94 and
0x611b6f38, GUI copies 0x61269588/0x6126c5a0 and 0x61277bfc/0x6127ac8c) hold 12-byte entries
{u32 GUI value, u16 4, u16 string, u32 cond} with their own strings (@A0C6@Natural ... shared with
other menus). Each entry becomes type 1 {value, 1, unit string, ASCII pointer} (the form menus use
for "0.3 sec"), unit 0x1b (empty in every language), pointing at the look's name in base-section
free space after the stub. Other menus keep their labels.
Camera 1.688: every base mode gave Portra and the names did not change: 0x602ca8c5 does not return
the GUI value (fell through to look 2), and the menu draws plain-text names from other lists.
1.689: getter 0x602ca6a5 (what the API's getSetting uses; the Custom REMAP handler 0x60df7837
reads 0xd3 through the API), and the plain-text lists 0x611ec244, 0x611ecc28, 0x611ed420
({7 i-Enhance 0x91, 0 Vivid 0x679, 1 Natural 0x67a, 2 Muted 0xb7, 5 Portrait 0x67d, 3 Monochrome
0xb0, 6 Custom 0x5f}; first six relabelled, Custom kept) as well.
Camera 1.689: the names showed in the SCP Picture Mode options (wrong) and in Custom's settings list;
the main menu's Picture Mode screen kept the stock names. The three text lists are whole SCP Picture
Mode lists (descriptors at 0x611ef13c/0x611ef1a4 n 0x44, 0x611ef2a8 n 0x40, 0x611efc34 n 0x2a).
--diag-lists: label list k's names "k <name>" (k = 1, 2, 3 in TEXT_LISTS order) to see which list
Custom's settings use.
Camera 1.690: the SCP showed "1 ..." (TEXT_LISTS[0] is the SCP's list); Custom's settings showed the
un-numbered names, i.e. LABEL_LISTS. The main menu's Picture Mode screen stayed stock. So --labels
now patches LABEL_LISTS only (TEXT_LISTS only with --diag-lists).
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


GET = 0x602ca6a5          # core GUI-value getter (API getSetting 0x608a8ccf -> 0x608d57a2 -> here)
BASE_SID = 0xd3
MENU_ORDER = [7, 0, 1, 2, 5, 3]          # Custom base-mode GUI values in menu order -> looks 1..6
MENU_NAMES = ["i-Enhance", "Vivid", "Natural", "Muted", "Portrait", "Monochrome"]
DEFAULT6 = ["provia", "portra", "velvia", "cl_chrome", "kchrome", "cinestill"]
SRC6 = """add -20,sp
mov d0,(4,sp)
mov d1,(8,sp)
mov a0,(12,sp)
mov a1,(16,sp)
call pick,[],4
mov d0,a0
mov (16,sp),a1
clr d1
2:
movbu (48,a0),d0
movbu d0,(d1,a1)
inc a0
inc d1
cmp 12,d1
bne 2b
mov (4,sp),d0
mov (8,sp),d1
mov (12,sp),a0
mov (16,sp),a1
add 20,sp
call builder,[d2,d3,a2,a3],96
add -4,sp
call pick,[],4
add 4,sp
mov d0,a1
mov (12,a2),a0
add 688,a0
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
pick:
add -4,sp
mov 0xd3,d0
call get,[],4
add 4,sp
cmp 8,d0
bcs 3f
clr d0
3:
mov gmap,a0
movbu (d0,a0),d0
mov 60,d1
mulu d1,d0
mov looks,a0
add a0,d0
ret [],4
gmap:
"""


def looks6_src(keys):
    gmap = [0] * 8
    for i, g in enumerate(MENU_ORDER):
        gmap[g] = i
    s = SRC6 + "".join(" .byte %d\n" % x for x in gmap) + ".balign 4\nlooks:\n"
    for k in keys:
        hues, lights, sats = look_values(LOOKS[k])
        s += "".join(" .hword %d,%d\n" % (h, l) for h, l in zip(hues, lights))
        s += "".join(" .byte %d\n" % x for x in sats)
    return s


LABEL_LISTS = (0x611b3f94, 0x611b6f38, 0x61269588, 0x6126c5a0, 0x61277bfc, 0x6127ac8c)
LABEL_STOCK = [(7, 0xca9), (0, 0xcbe), (1, 0xcbf), (2, 0xcaf), (5, 0xcc0), (3, 0x26a)]
EMPTY_UNIT, NAMES = 0x1b, STUB + 0x200
BLOB_B = 0x60c6c000


TEXT_LISTS = (0x611ec244, 0x611ecc28, 0x611ed420)
TEXT_STOCK = [(7, 0x91), (0, 0x679), (1, 0x67a), (2, 0xb7), (5, 0x67d), (3, 0xb0)]


def label_patch(m, keys):
    import olycompress
    names = b""
    ptrs = []
    for k in keys:
        ptrs.append(NAMES + len(names))
        names += LOOKS[k]["name"].encode("ascii") + b"\0"
    check(set(m[off(NAMES):off(NAMES) + 0x200]) == {0xff}, "label area not free")
    m[off(NAMES):off(NAMES) + len(names)] = names
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    diag = "--diag-lists" in sys.argv
    if diag:
        for k in range(3):
            for j, key in enumerate(keys):
                ptrs.append(NAMES + len(names))
                names += ("%d %s" % (k + 1, LOOKS[key]["name"])).encode("ascii") + b"\0"
        check(len(names) <= 0x200, "labels too long")
        m[off(NAMES):off(NAMES) + len(names)] = names
    lists = [(x, LABEL_STOCK, 0) for x in LABEL_LISTS]
    if diag:
        lists += [(x, TEXT_STOCK, k + 1) for k, x in enumerate(TEXT_LISTS)]
    for lst, stock, k in lists:
        for i, (val, sid) in enumerate(stock):
            o = lst - BLOB_B + 12 * i
            v, ty, s = struct.unpack_from("<IHH", gui, o)
            check((v, ty, s) == (val, 4, sid), "base-mode label entry %#x differs" % (lst + 12 * i))
            look = MENU_ORDER.index(val)
            ptr = ptrs[6 * k + look] if (diag and k) else ptrs[look]
            struct.pack_into("<IHHI", gui, o, val, 1, EMPTY_UNIT, ptr)
    c = olycompress.pack(bytes(gui))
    check(len(c) <= (0x612f1000 - BASE) - (BLOB_B_OFF + 32), "recompressed blob B does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "blob B does not decode to the edit")
    print("  Custom base-mode labels -> %s" % ", ".join(LOOKS[k]["name"] for k in keys))


# SRC6 assembled at STUB (camera 1.691); data follows: gmap (8 B) at +0x8c, six 60-byte looks at +0x94,
# names at NAMES (STUB + 0x200). For builds without binutils (the mod builder app); --looks builds
# check that it still matches the assembler's output.
CODE6 = bytes.fromhex(
    "f8feec42044608430c4710cd55000004f1e05d1004f84030f4454144a50cc9f7580459085c0c5d10f8fe14ddfe923000"
    "f060f8fefccd2b000004f8fe04f1e1f8220cfad0b002850cf061f87012f86102f870162104201829ffc9efdc44953000"
    "f8fefc2cd300dd3f4c1f000004f8fe04a008c40300fcdc8c5a0d60f400853cf254fcdc945a0d60f150df0004")
GMAP_OFF, LOOKS_OFF = 0x8c, 0x94


def apply6(img, base, keys, labels=True):
    """Six looks in Custom without an assembler. IMG: bytearray of the runtime image (blobs unpacked)
    at runtime address BASE. Returns the look names in menu order."""
    o = lambda a: a - base  # noqa: E731
    check(len(keys) == 6 and all(k in LOOKS for k in keys), "six looks from the library are needed")
    e = o(PM_LIST) + PM_ELEM * CUSTOM_IDX
    check(struct.unpack_from("<I", img, e)[0] == 6, "Custom picture-mode entry differs")
    check(bytes(img[o(SITE):o(SITE) + 5]) == SITE_STOCK, "colour builder call differs")
    check(bytes(img[o(SITE) - len(SITE_PRE):o(SITE)]) == SITE_PRE, "colour selector differs")
    check(set(img[o(STUB):o(NAMES) + 0x200]) == {0xff}, "stub area not free")
    gmap = [0] * 8
    for i, g in enumerate(MENU_ORDER):
        gmap[g] = i
    data = b""
    for k in keys:
        hues, lights, sats = look_values(LOOKS[k])
        data += b"".join(struct.pack("<hh", h, l) for h, l in zip(hues, lights)) + bytes(s & 0xff for s in sats)
    img[e:e + PM_ELEM] = struct.pack("<I", 11) + bytes(PM_ELEM - 4)
    img[o(STUB):o(STUB) + len(CODE6)] = CODE6
    img[o(STUB) + GMAP_OFF:o(STUB) + GMAP_OFF + 8] = bytes(gmap)
    img[o(STUB) + LOOKS_OFF:o(STUB) + LOOKS_OFF + len(data)] = data
    img[o(SITE):o(SITE) + 5] = JMP
    if labels:
        names, ptrs = b"", []
        for k in keys:
            ptrs.append(NAMES + len(names))
            names += LOOKS[k]["name"].encode("ascii") + b"\0"
        img[o(NAMES):o(NAMES) + len(names)] = names
        for lst in LABEL_LISTS:
            for i, (val, sid) in enumerate(LABEL_STOCK):
                a = o(lst) + 12 * i
                check(struct.unpack_from("<IHH", img, a) == (val, 4, sid), "base-mode label entry %#x differs" % (lst + 12 * i))
                struct.pack_into("<IHHI", img, a, val, 1, EMPTY_UNIT, ptrs[MENU_ORDER.index(val)])
    return [LOOKS[k]["name"] for k in keys]


def patch6(main, keys):
    import patch_aspect
    check(len(keys) == 6 and all(k in LOOKS for k in keys), "--looks needs six looks from looks_library")
    m = bytearray(main)
    e = off(PM_LIST) + PM_ELEM * CUSTOM_IDX
    check(struct.unpack_from("<I", m, e)[0] == 6, "Custom picture-mode entry differs")
    check(bytes(m[off(SITE):off(SITE) + 5]) == SITE_STOCK, "colour builder call differs")
    check(bytes(m[off(SITE) - len(SITE_PRE):off(SITE)]) == SITE_PRE, "colour selector differs")
    check(set(m[off(STUB):off(STUB) + 0x200]) == {0xff}, "stub area not free")
    stub = patch_aspect.assemble_syms(looks6_src(keys), STUB, {"builder": BUILDER, "resume": RESUME, "get": GET})
    check(len(stub) <= 0x200, "stub too long")
    m[e:e + PM_ELEM] = struct.pack("<I", 11) + bytes(PM_ELEM - 4)
    m[off(STUB):off(STUB) + len(stub)] = stub
    m[off(SITE):off(SITE) + 5] = JMP
    if "--labels" in sys.argv:
        label_patch(m, keys)
    print("  Custom -> Color Profile, 6 looks by base mode: %s (stub %d B)" % (", ".join(keys), len(stub)))
    return bytes(m)


# ---------------------------------------------------------------- all looks in Custom's list
# --all31: Custom's base-mode setting 0xd3 gets one value per library look. Validator record 0x604da7d0
# {0xd3, list 0x604bcb74, alt 0x604ae89c, 6 x 64 B}: new list = the 6 stock entries + 25 copies of
# Natural's {2, 0...} entry, alt = stock GUI values + 64..88. Menus: the two descriptors per GUI copy
# ({0xd3, 4, title 0xcb, cond, list, n} and the continuation {.., cond, list, n}; at 0x611bb9d4/e4,
# 0x61271200/10, 0x6127f8ec/fc) point at new 31-entry type-1 lists (look names) plus each list's stock
# trailing entry, n 6 -> 31. The stub (SRC31) maps the GUI value through a 89-byte table to a look.
# Camera 1.692: 31 entries shown, but every new one showed/used the Natural position (Astia):
# identical components. 1.693: new entries {2, filter 16+i}: names right, but choosing one restarted the
# camera. 1.694: valid pairs (NEW_PAIRS, filters 0..8) and GUI values 4, 6, 8..30.
REC_D3, REC_D3_STOCK = 0x604da7d0, bytes.fromhex("d3008000" "74cb4b60" "9ce84a60" "8001" "4000" "0006" "0000")
D3_LIST, D3_ALT, D3_N = 0x604bcb74, 0x604ae89c, 6
NEW_VALUES = [4, 6] + list(range(8, 31))       # GUI values inside the 0..63 range the tables cover (1.693: 64+ restarted)
# valid {base mode, filter} pairs not used by the stock six ({7,0} {1,0} {2,0} {3,0} {4,0} {5,1}); filters 0..8
NEW_PAIRS = [(b, f) for b in (7, 1, 2, 3, 4) for f in (1, 2, 3, 4)] + [(5, 0), (5, 2), (5, 3), (5, 4), (2, 5)]
ALL_VALUES = MENU_ORDER + NEW_VALUES             # menu order: 6 stock positions, then the new ones
DESC_REFS = (0x611bb9d4, 0x611bb9e4, 0x61271200, 0x61271210, 0x6127f8ec, 0x6127f8fc)   # address of the list pointer
STUB31, GMAP31, NAMES31, LISTA31, LISTB31, ALT31 = 0x600d5800, 0x600d58a0, 0x600d5900, 0x600d5b00, 0x600d5c80, 0x600d5e00
LOOKS31, VLIST31 = 0x600d62e0, 0x600d77e0
SRC31 = SRC6.replace("cmp 8,d0", "cmp 89,d0").split("gmap:")[0]


def all_keys():
    return [k for k in LOOKS if k != "portra400"]


def apply31(img, base, keys=None, gui_img=True):
    """All library looks in Custom's list. IMG: runtime image bytearray at BASE (blob B unpacked)."""
    import patch_aspect
    o = lambda a: a - base  # noqa: E731
    keys = keys or all_keys()
    n = len(keys)
    check(n <= len(ALL_VALUES), "too many looks")
    e = o(PM_LIST) + PM_ELEM * CUSTOM_IDX
    check(struct.unpack_from("<I", img, e)[0] == 6, "Custom picture-mode entry differs")
    check(bytes(img[o(SITE):o(SITE) + 5]) == SITE_STOCK, "colour builder call differs")
    check(bytes(img[o(REC_D3):o(REC_D3) + 20]) == REC_D3_STOCK, "0xd3 validator record differs")
    for a, size in ((STUB31, 0x700), (LOOKS31, 60 * n), (VLIST31, 64 * n)):
        check(set(img[o(a):o(a) + size]) == {0xff}, "area %#x not free" % a)
    vals = ALL_VALUES[:n]
    # validator
    stock = bytes(img[o(D3_LIST):o(D3_LIST) + 64 * D3_N])
    nat = stock[64 * 2:64 * 3]                        # entry 2 = Natural {2, 0..} (GUI 1)
    check(struct.unpack_from("<I", nat)[0] == 2 and set(nat[4:]) == {0}, "Natural entry differs")
    # the camera identifies a value by its components {MODE_CUSTOM_COLORTONE +0, MODE_CUSTOM_FILTER 0x703 +4}
    # (compound table 0x60469774), so each new entry needs its own filter value (1.692: plain copies all
    # read back as Natural); 0x703 has no validator and is ignored for a colour base mode.
    extra = b"".join(struct.pack("<II", *NEW_PAIRS[i]) + nat[8:] for i in range(n - D3_N))
    img[o(VLIST31):o(VLIST31) + 64 * n] = stock + extra
    alt = list(struct.unpack_from("<%dI" % D3_N, img, o(D3_ALT)))
    check(alt == MENU_ORDER, "0xd3 GUI values differ")
    img[o(ALT31):o(ALT31) + 4 * n] = struct.pack("<%dI" % n, *vals)
    struct.pack_into("<II", img, o(REC_D3) + 4, VLIST31, ALT31)
    struct.pack_into("<H", img, o(REC_D3) + 12, 64 * n)
    # look table and value map
    gmap = [0] * 89
    for i, v in enumerate(vals):
        gmap[v] = i
    data = b""
    for k in keys:
        hues, lights, sats = look_values(LOOKS[k])
        data += b"".join(struct.pack("<hh", h, l) for h, l in zip(hues, lights)) + bytes(s & 0xff for s in sats)
    img[o(LOOKS31):o(LOOKS31) + len(data)] = data
    img[o(GMAP31):o(GMAP31) + 89] = bytes(gmap)
    code = CODE31 if CODE31 else patch_aspect.assemble_syms(SRC31, STUB31, {"builder": BUILDER, "resume": RESUME, "get": GET, "gmap": GMAP31, "looks": LOOKS31})
    check(len(code) <= GMAP31 - STUB31, "stub too long")
    img[o(STUB31):o(STUB31) + len(code)] = code
    img[e:e + PM_ELEM] = struct.pack("<I", 11) + bytes(PM_ELEM - 4)
    img[o(SITE):o(SITE) + 5] = b"\xdc" + struct.pack("<i", STUB31 - SITE)
    # names and menu lists
    names, ptrs = b"", []
    for k in keys:
        ptrs.append(NAMES31 + len(names))
        names += LOOKS[k]["name"].encode("ascii") + b"\0"
    check(len(names) <= LISTA31 - NAMES31, "names too long")
    img[o(NAMES31):o(NAMES31) + len(names)] = names
    for i, ref in enumerate(DESC_REFS):
        lst = struct.unpack_from("<I", img, o(ref))[0]
        check(lst in LABEL_LISTS and struct.unpack_from("<I", img, o(ref) + 4)[0] == 6, "descriptor %#x differs" % ref)
        trail = bytes(img[o(lst) + 72:o(lst) + 84])
        for j, (val, sid) in enumerate(LABEL_STOCK):
            v = struct.unpack_from("<IHH", img, o(lst) + 12 * j)
            check(v[0] == val and v[1] in (1, 4), "label entry %#x differs" % (lst + 12 * j))
        new = LISTA31 if i % 2 else LISTB31
        body = b"".join(struct.pack("<IHHI", v, 1, EMPTY_UNIT, p) for v, p in zip(vals, ptrs)) + trail
        img[o(new):o(new) + len(body)] = body
        struct.pack_into("<II", img, o(ref), new, n)
    return [LOOKS[k]["name"] for k in keys]


CODE31 = None


def patch31(main):
    import modcore
    img = bytearray(modcore.runtime_image(main))
    names = apply31(img, BASE)
    print("  Custom -> Color Profile, %d looks in Custom's list: %s" % (len(names), ", ".join(names)))
    return modcore.rebuild_main(main, img)


def main(argv):
    if len(argv) < 3 or not any(x in argv for x in ("--test1", "--test2", "--test3", "--look", "--test4", "--looks", "--all31")):
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
    if "--all31" in argv:
        new_main = patch31(blocks[0]["plain"])
    elif "--looks" in argv:
        keys6 = argv[argv.index("--looks") + 1].split(",")
        new_main = patch6(blocks[0]["plain"], keys6)
        if "--labels" in argv and "--diag-lists" not in argv:
            import modcore
            img = bytearray(modcore.runtime_image(blocks[0]["plain"]))
            apply6(img, BASE, keys6)
            check(modcore.rebuild_main(blocks[0]["plain"], img) == new_main,
                  "pre-assembled six-look stub (CODE6) differs from the assembled one")
    else:
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
