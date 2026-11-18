#!/usr/bin/env python3
"""Art filter tone curves as Gradation options for the picture modes (TEST, E-M1 Mark III 1.6).

  MN10300_BIN=... python3 tools/patch_art_gradation.py IN.BIN OUT.BIN [--version 0x1715]

Gradation (Auto / High Key / Normal / Low Key) is chosen in the tone-curve selector 0x603df05c:
job +1797 = 1 -> High Key curve 0x6050af06, -1 -> Low Key 0x6050b106, 2 -> Auto, 0 -> the
Contrast-setting curves (docs/ART_FILTERS.md). The art filters use fixed 256-point curves from the
same bank. This adds 19 Gradation values, 3..21, one per distinct art-filter curve:

- Validator: the 14 settings that share the 4-value Gradation list (0x69, 0x136-0x13b, 0xd0
  Custom, 0x12e, 0xbb, 0xbf, 0xc3, 0xc7, 0xcc; records 0x604da80c..0x604da910, 64-byte entries
  {value, flag}, GUI alt list [3, 1, 2, 0]) get one shared list of 4 + 19 entries: the stock four,
  then raw values 3..21 with GUI values 4..22.
- Menus: the Gradation item records (42 sub-lists {cond, list, 4} in the three GUI copies, blob B)
  point at one shared option list: the stock four entries, then type-4 entries with the camera's own
  art filter name strings (1.716 used type-1 ASCII labels: options worked but showed blank).
- Image: `movbu (1797,a0),d0; extb d0` at 0x603df14e jumps to a stub that returns the art curve for
  values 3..21 and otherwise goes on as stock.

Camera test: Picture Mode Natural (or any mode), Gradation: the list should show the 19 new names
after Low Key. Pick e.g. "Pale&Light I" (lifted blacks) or "Grainy I" (very hard contrast):
live view and photo should change accordingly. Check that Auto / High / Normal / Low still work.
--diag-labels (1.718): Auto's label becomes "Pop Art I" (string 0xa75) and the first new value
(Pop Art I curve) is labelled "High Key" (0x267): shows whether label edits on existing values
show at all, and whether new values can show a string that this menu already draws.
Camera 1.719: works (curves, SCP icons). 1.719: the SCP Gradation picker (record 0x611ef014, icon lists) gets 23 entries; new ones use the
art filter icons from the SCP Picture Mode picker (record 0x611ef284). 1.718 (--diag-labels): no
visible change, i.e. the screen with blank entries is this icon picker, not the text lists.
--diag-cell (1.729): the Auto entry of the SCP Gradation icon lists gets the Pop Art I icons, to see
whether the SCP grid cell (which showed AUTO for the new values in 1.728) uses these lists at all.
1.728: the SCP panel label (cursor on Gradation, list at record 0x611ef038) also gets the 19 names.
Camera 1.719: works (curves; names and icons in the SCP picker); the SCP panel label stayed empty.
Camera 1.716: boots; the 19 options are listed and change live view and photos; labels blank
(type-1 ASCII entries are not drawn by this menu). 1.717: type-4 entries with the stock names:
still blank, so new values are not labelled from this list at all (as with the ISO extension).
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
SITE, SITE_STOCK, BACK = 0x603df14e, bytes.fromhex("fa40050710"), 0x603df153
FREE, FREE_END = 0x600dc000, 0x600df000   # padding below the vector table 0x600e0000 (0x600e0800+ is boot RAM)
RECORDS = [0x604da80c + 20 * i for i in range(14)]
REC_SIDS = [0x69, 0x136, 0x137, 0x138, 0x139, 0x13a, 0x13b, 0xd0, 0x12e, 0xbb, 0xbf, 0xc3, 0xc7, 0xcc]
STOCK_ALT = [3, 1, 2, 0]
# SCP icon pickers (blob B): record {id, icon list 1, icon list 2, n, 0}; list entries
# {GUI value, 3, icon id, cond}. Gradation 0x17 (4 entries), Picture Mode 0x22 (54, art icons).
GRAD_REC, PM_REC = 0x611ef014, 0x611ef284
# SCP panel label (cursor on Gradation): {list, n} at 0x611ef038 -> 0x611eb26c, 4 entries
# {3 "Shadow Adj", 1 "Gradation Normal", 2 "Gradation High Key", 0 "Gradation Low Key"}
SCP_TEXT = 0x611ef038
ART_GUI = [0x10008, 0x20008, 0x9, 0x1000a, 0x2000a, 0xb, 0x1000c, 0x2000c, 0x1000d, 0x2000d, 0x1000e,
           0x1000f, 0x2000f, 0x10, 0x10011, 0x1001a, 0x2001a, 0x3001a, 0x1003c]
# ^ SCP Picture Mode value (variant << 16 | art GUI index) of each curve's filter
CURVES = [  # (label, curve, string id) in menu order; curves from tools/art_filter_dump.py, strings
    # are the camera's own art filter names (@A050@/@A051@/@A052@ = the I/II/III glyphs)
    ("Pop Art I", 0x6050b566, 0xa75), ("Pop Art II", 0x6050c9a2, 0xa76), ("Soft Focus", 0x6050b306, 0x44),
    ("Pale&Light I", 0x6050b7a2, 0xa77), ("Pale&Light II", 0x6050c7a2, 0xa78), ("Light Tone", 0x6050b9a2, 0x41),
    ("Grainy I", 0x6050eba2, 0xa79), ("Grainy II", 0x6050eda2, 0xa7a), ("Pin Hole I", 0x6050bba2, 0xa7b),
    ("Pin Hole II", 0x6050cba2, 0xa7c), ("Diorama", 0x6050bfa2, 0x3d), ("Cross Proc. I", 0x6050c1a2, 0xa80),
    ("Cross Proc. II", 0x6050dfa2, 0xa81), ("Gentle Sepia", 0x6050c5a2, 0x3f), ("Dramatic Tone", 0x6050cfa2, 0x3e),
    ("Vintage I", 0x6050e1a2, 0xa88), ("Vintage II", 0x6050e3a2, 0xa89), ("Vintage III", 0x6050e5a2, 0xa8a),
    ("Bleach Bypass I", 0x6050e7a2, 0xcde),
]
# User curve slots (filled by the mod builder app, tools/modcore.py): 256 x u16 (0..1023) each at
# USER_DATA + 512 * i, identity until the app writes a curve. Labels are the camera's own "Custom1" /
# "Custom2" strings; SCP icon = the Custom picture mode's (GUI 6).
USER_DATA = 0x600dec00
USER = [("Custom1", 0x734), ("Custom2", 0x735)]
IDENTITY = 0x60508f06
N_ART = len(CURVES)
CURVES = CURVES + [(lab, USER_DATA + 512 * i, sid) for i, (lab, sid) in enumerate(USER)]
ART_GUI = ART_GUI + [6] * len(USER)
N = len(CURVES)
STUB_SRC = """movbu (1797,a0),d0
extb d0
cmp 3,d0
blt 1f
cmp %d,d0
bge 1f
add -3,d0
asl2 d0
mov tab,a0
mov (d0,a0),a0
ret [d2,d3,a2,a3],24
1:
jmp back
""" % (3 + N)


LOOKUP = 0x60e08efa
CELL_SRC = """cmp l1,a1
beq 1f
cmp l2,a1
beq 1f
jmp orig
1:
mov a1,a2
mov %(n)d,d3
2:
mov (a2),d2
cmp d2,d0
beq 3f
add 12,a2
add -1,d3
bne 2b
clr d3
mov d3,mdr
mov %(n)d,d2
divu d2,d0
mov mdr,d0
mov d0,d2
add d2,d2
add d0,d2
asl2 d2
mov (d2,a1),d0
3:
mov %(n)d,d1
orig:
mov a0,(4,sp)
clr d2
clr d3
cmp d2,d1
jmp back
"""


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


DIAG = "--diag-labels" in sys.argv


def patch(main):
    import patch_aspect
    m = bytearray(main)
    o = lambda a: a - BASE  # noqa: E731
    check(set(m[o(FREE):o(FREE_END)]) == {0xff}, "free area %#x-%#x not free" % (FREE, FREE_END))
    for i in range(len(USER)):     # user slots start as the identity curve
        m[o(USER_DATA + 512 * i):o(USER_DATA + 512 * (i + 1))] = m[o(IDENTITY):o(IDENTITY) + 512]
    check(bytes(m[o(SITE):o(SITE) + 5]) == SITE_STOCK, "Gradation read at %#x differs" % SITE)
    for c in CURVES[:N_ART]:
        v = struct.unpack_from("<256H", m, o(c[1]))
        check(v[0] < 300 and v[255] > 800 and all(v[i] <= v[i + 1] for i in range(255)), "curve %#x differs" % c[1])
    stock_list = None
    for rec, sid in zip(RECORDS, REC_SIDS):
        r = bytes(m[o(rec):o(rec) + 20])
        lst, alt = struct.unpack_from("<II", r, 4)
        check(struct.unpack_from("<H", r, 0)[0] == sid and struct.unpack_from("<H", r, 12)[0] == 256
              and r[17] == 6, "Gradation record %#x differs" % rec)
        check(list(struct.unpack_from("<4i", m, o(alt))) == STOCK_ALT, "alt list %#x differs" % alt)
        body = bytes(m[o(lst):o(lst) + 256])
        stock_list = stock_list or body
        check(body == stock_list, "value list %#x differs" % lst)
    check([struct.unpack_from("<i", stock_list, 64 * j)[0] for j in range(4)] == [0, 0, 1, -1],
          "Gradation values differ")

    a = FREE
    vlist = a
    data = bytearray(stock_list)
    for i in range(N):
        e = bytearray(64)
        struct.pack_into("<i", e, 0, 3 + i)
        data += e
    a += len(data)
    m[o(vlist):o(vlist) + len(data)] = data
    alist = a
    alt = STOCK_ALT + [4 + i for i in range(N)]
    m[o(alist):o(alist) + 4 * len(alt)] = struct.pack("<%di" % len(alt), *alt)
    a += 4 * len(alt)
    tab = (a + 3) & ~3
    m[o(tab):o(tab) + 4 * N] = struct.pack("<%dI" % N, *[c[1] for c in CURVES])
    a = tab + 4 * N
    stub = (a + 15) & ~15
    code = patch_aspect.assemble_syms(STUB_SRC, stub, {"tab": tab, "back": BACK})
    m[o(stub):o(stub) + len(code)] = code
    a = stub + len(code)
    for rec in RECORDS:
        struct.pack_into("<II", m, o(rec) + 4, vlist, alist)
        struct.pack_into("<H", m, o(rec) + 12, 64 * (4 + N))
    jmp = patch_aspect.assemble_syms("jmp stub", SITE, {"stub": stub})
    check(len(jmp) == 5, "jump is not 5 bytes")
    m[o(SITE):o(SITE) + 5] = jmp

    # menus (blob B): one shared option list, stock four entries first
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    lists = []
    for i in range(0, len(gui) - 48, 4):
        e = [struct.unpack_from("<iHHI", gui, i + 12 * k) for k in range(4)]
        if [x[0] for x in e] == [3, 2, 1, 0] and e[1][2] == 0x267 and e[3][2] == 0x269:
            lists.append(i)
    check(len(lists) == 42, "Gradation option lists: %d (expected 42)" % len(lists))
    olist = (a + 15) & ~15
    stock4 = bytes(gui[lists[0]:lists[0] + 48])
    cond = struct.unpack_from("<I", stock4, 8)[0]
    ol = bytearray(stock4)
    for i in range(N):
        ol += struct.pack("<IHHI", 4 + i, 4, CURVES[i][2], cond)
    if DIAG:     # label diagnostic: Auto -> "Pop Art I", first new value -> "High Key"
        struct.pack_into("<H", ol, 6, 0xa75)
        struct.pack_into("<H", ol, 48 + 6, 0x267)
    m[o(olist):o(olist) + len(ol)] = ol
    a = olist + len(ol)
    # SCP Gradation icon picker: new entries take the art filter's icons from the Picture Mode picker
    def ent(p, k):
        return struct.unpack_from("<iHHI", gui, p - BLOB_B + 12 * k)
    rid, g1, g2, gn, _ = struct.unpack_from("<5I", gui, GRAD_REC - BLOB_B)
    pid, p1, p2, pn, _ = struct.unpack_from("<5I", gui, PM_REC - BLOB_B)
    check(rid == 0x17 and gn == 4 and ent(g1, 0)[:3] == (3, 3, 0x2130), "SCP Gradation record differs")
    check(pid == 0x22 and pn == 54, "SCP Picture Mode record differs")
    new = []
    for src, pm in ((g1, p1), (g2, p2)):
        icons = {ent(pm, k)[0]: ent(pm, k)[2] for k in range(pn)}
        lst = bytearray(gui[src - BLOB_B:src - BLOB_B + 48])
        c = ent(src, 0)[3]
        for i, gv in enumerate(ART_GUI):
            check(gv in icons, "no Picture Mode icon for GUI value %#x" % gv)
            lst += struct.pack("<iHHI", 4 + i, 3, icons[gv], c)
        a = (a + 15) & ~15
        m[o(a):o(a) + len(lst)] = lst
        new.append(a)
        a += len(lst)
    if "--diag-cell" in sys.argv:   # 1.729: stock Auto entry shows the Pop Art I icons
        for nl in new:
            struct.pack_into("<H", m, o(nl) + 6, struct.unpack_from("<H", m, o(nl) + 48 + 6)[0])
    struct.pack_into("<IIII", gui, GRAD_REC - BLOB_B + 4, new[0], new[1], 4 + N, 0)
    print("  SCP Gradation icons: record %#x -> %#x / %#x (%d entries)" % (GRAD_REC, new[0], new[1], 4 + N))
    tl, tn = struct.unpack_from("<II", gui, SCP_TEXT - BLOB_B)
    check(tn == 4 and [ent(tl, k)[0] for k in range(4)] == [3, 1, 2, 0] and ent(tl, 2)[2] == 0x8c,
          "SCP Gradation text list differs")
    tc = ent(tl, 0)[3]
    lst = bytearray(gui[tl - BLOB_B:tl - BLOB_B + 48])
    for i in range(N):
        lst += struct.pack("<iHHI", 4 + i, 4, CURVES[i][2], tc)
    a = (a + 15) & ~15
    m[o(a):o(a) + len(lst)] = lst
    struct.pack_into("<II", gui, SCP_TEXT - BLOB_B, a, 4 + N)
    print("  SCP Gradation panel names: %#x -> %#x (%d entries)" % (SCP_TEXT, a, 4 + N))
    a += len(lst)
    if "--cell" in sys.argv:
        # SCP grid cell: icon lookup 0x60e08efa(d0 value, a1 list, d1 count). For the Gradation icon
        # lists, search all 4 + N entries (the caller may pass the stock count 4); if the value is
        # still not found, show entry (value mod 4+N) so the icon tells which value was passed.
        check(bytes(gui[LOOKUP - BLOB_B:LOOKUP - BLOB_B + 5]) == bytes.fromhex("4304080ca9"), "icon lookup differs")
        a = (a + 15) & ~15
        code = patch_aspect.assemble_syms(CELL_SRC % {"n": 4 + N}, a,
                                          {"l1": new[0], "l2": new[1], "back": LOOKUP + 5})
        m[o(a):o(a) + len(code)] = code
        gui[LOOKUP - BLOB_B:LOOKUP - BLOB_B + 5] = b"\xdc" + struct.pack("<i", a - LOOKUP)
        print("  SCP grid cell: icon lookup hook %#x -> %#x" % (LOOKUP, a))
        a += len(code)
    check(a <= USER_DATA, "free area overflow")
    nref = 0
    for li in lists:
        ptr = BLOB_B + li
        pat = struct.pack("<II", ptr, 4)
        i = gui.find(pat)
        while i >= 0:
            if i % 4 == 0:
                struct.pack_into("<II", gui, i, olist, 4 + N)
                nref += 1
            i = gui.find(pat, i + 1)
    check(nref == 42, "Gradation item references: %d (expected 42)" % nref)
    cg = olycompress.pack(bytes(gui))
    check(len(cg) <= (BLOB_B_END - BASE) - (BLOB_B_OFF + 32), "blob B does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(cg)] = cg
    if len(cg) < csz:
        m[BLOB_B_OFF + 32 + len(cg):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(cg))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(cg))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "blob B does not decode to the edit")
    print("  Gradation +%d art curves: 14 records -> list %#x/alt %#x, stub %#x, %d menu refs -> %#x "
          "(cond %#x), data to %#x" % (N, vlist, alist, stub, nref, olist, cond, a))
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
