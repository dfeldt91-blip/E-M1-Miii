#!/usr/bin/env python3
""""XPAN" icon for the Panorama aspect on the SCP (EXPERIMENTAL, E-M1 Mark III 1.6). Needs the Panorama mod.

  python3 tools/patch_xpan_icon.py IN.BIN OUT.BIN [--version 0x1666]      (IN must have Panorama)

GUI icons (block 1): the directory at block 1 offset 0 ({u32 flash address, u32 size, 0, 0}) lists
70 entries; entry 0 is an olycompress blob loaded to 0xa303d000 (reserved up to 0xa373d000, entry 69
loads there). Blob word 4 = icon table (0xa35b65d0, 10350 u32 pointers, all used). Each pointer is
a 24-byte descriptor {u16 format 14, u16 w, u16 h, u16 8, u32 0, u32 size, u32 data, u32 0} with the
pixel data right before it. Format 14: 4-byte header {12-bit h-1, 12-bit w-1, u8 0x0b}, then 64-bit
little-endian words of five 12-bit tokens {colour index << 4 | run - 1} (runs stop at row ends; the
last word is cut to the bytes needed). Decoding and re-encoding all 6816 such icons is byte exact.

SCP aspect icons: list A 0x1ee0 (16:9, 50x38), list B 0x1d7 (16:9 highlighted, 64x48), and the
current-value cell's part list 0x610661f4 (records {0xffff, 7, 7, icon}: 4:3 3:2 3:4 1:1 16:9 =
cell index 2..6, descriptor 0x610674e4 {.., u32 first 2 | count << 8, list, end}); the value->index map
0x611f2424 gives 17:9 (10) index 7, unused for stills.

This tool draws "XPAN" in the 16:9 icons' style (glyphs on the stock backgrounds), appends the three
icons and a copy of the icon table with three more entries (ids 10350-10352) to blob 0, points word 4
at the new table, recompresses the blob into free space in block 1 (0xbfffe0, flash 0x43000000) and
updates directory entry 0. Then the Panorama mod's SCP lists (value 6) get the new ids, the cell part
list gets a sixth record (index 7) at 0x600d2b00, and the Panorama cell remap stub (6 -> 3) becomes
6 -> 10 (index 7).
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
LOG = print
B1_FLASH = 0x42400020                 # block 1 plain offset 0
BLOB0_OFF, BLOB0_RAM, BLOB0_LIMIT = 0x7e0, 0xa303d000, 0xa373d000
TABLE, TABLE_N = 0xa35b65d0, 10350
NEW_BLOB_OFF = 0xbfffe0               # flash 0x43000000, zeros in stock block 1
ICON_A, ICON_B, ICON_CELL = 0x1ee0, 0x1d7, 0x1dc
LV_ROW, SCP_ROW17 = 0x611fe0e4, 0x611eeedc
CELL_DESC, CELL_LIST, CELL_LIST_END = 0x610674e4, 0x610661f4, 0x61066244
NEW_CELL_LIST = 0x600d2b00
REMAP_SITE = 0x60e1b2ef
STUB_BODY = bytes.fromhex("5808a006c90680034208")    # mov (8,sp),d0; cmp 6,d0; bne; mov 3,d0; mov d0,(8,sp)

X = ["###...###", "+##+.+##+", ".###.###.", ".+##+##+.", "..#####..", "..+###+..", "...###...", "...###...",
     "..+###+..", "..#####..", ".+##+##+.", ".###.###.", "+##+.+##+", "###...###", "###...###", "##+...+##",
     "##.....##"]
P = ["######+.", "#######+", "###..+##", "###...##", "###...##", "###..+##", "#######+", "######+."] + ["###....."] * 9
A = ["..+###+..", "..#####..", "..##+##..", ".+##.##+.", ".###.###.", ".##+.+##.", "+##...##+", "###...###",
     "###...###", "#########", "#########"] + ["###...###"] * 6
N = ["###...###", "####..###", "####..###", "#####.###", "###+#.###", "###+#+###", "###.#####", "###.+####",
     "###..####", "###..+###"] + ["###...###"] * 7
WORD = [X, P, A, N]


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


# ---------------------------------------------------------------- icon format 14

def decode(data, w, h):
    px = []
    b = data[4:]
    for k in range(0, len(b), 8):
        v = int.from_bytes(b[k:k + 8], "little")
        for j in range(5):
            if len(px) >= w * h:
                break
            t = (v >> (12 * j)) & 0xfff
            px.extend([t >> 4] * ((t & 15) + 1))
    check(len(px) == w * h, "icon does not decode to its size")
    return [px[y * w:(y + 1) * w] for y in range(h)]


def encode(rows, w, h, depth=0x0b):
    toks = []
    for row in rows:
        i = 0
        while i < w:
            c, n = row[i], 1
            while i + n < w and row[i + n] == c and n < 16:
                n += 1
            toks.append((c << 4) | (n - 1))
            i += n
    out = bytearray([(h - 1) & 0xff, ((h - 1) >> 8) | (((w - 1) & 15) << 4), (w - 1) >> 4, depth])
    for k in range(0, len(toks), 5):
        grp, v = toks[k:k + 5], 0
        for j, t in enumerate(grp):
            v |= t << (12 * j)
        out += v.to_bytes(8, "little")[:8 if len(grp) == 5 else (12 * len(grp) + 7) // 8]
    return bytes(out)


BLOB69_OFF, BLOB69_RAM = 0x9f11e0, 0xa373d000


def icon_of(blobs, i):
    """BLOBS: [(ram address, bytes)] of the loaded icon blobs; blobs[0] holds the table."""
    def at(a, n):
        for ram, data in blobs:
            if ram <= a and a + n <= ram + len(data):
                return data[a - ram:a - ram + n]
        check(False, "icon address %#x outside the blobs" % a)
    p = struct.unpack_from("<I", at(TABLE + 4 * i, 4))[0]
    f, w, h, depth, _, size, dp, _ = struct.unpack("<4HIIII", at(p, 24))
    check(f == 14 and 0 <= p - (dp + size) < 4, "icon %#x descriptor differs" % i)
    data = at(dp, size)
    return w, h, decode(data, w, h), data[3]


def scale(rows, nh, nw):
    h, w = len(rows), len(rows[0])
    return ["".join(rows[y * h // nh][x * w // nw] for x in range(nw)) for y in range(nh)]


def compose(blobs, base_id, top, bot, left, right, letter_h, aa, margins):
    """Stock icon BASE_ID with everything in rows TOP..BOT, cols LEFT..RIGHT that is not that row's
    background (colours seen in the MARGINS columns) replaced by background, then XPAN drawn in white.
    AA: index for the letters' edge pixels, or None for none (gradient backgrounds)."""
    w, h, rows, depth = icon_of(blobs, base_id)
    rows = [list(r) for r in rows]
    for y in range(top, bot):
        bgset = set(rows[y][x] for x in margins)
        seg = [v for v in rows[y][left:right] if v in bgset]
        bg = max(bgset, key=lambda v: seg.count(v))
        for x in range(left, right):
            if rows[y][x] not in bgset:
                rows[y][x] = bg
    letters = [scale(L, letter_h, len(L[0])) if letter_h != len(L) else L for L in WORD]
    total = sum(len(L[0]) for L in letters) + len(letters) - 1
    x = (w - total) // 2
    y0 = top + ((bot - top) - letter_h) // 2
    check(x >= left and x + total <= right, "XPAN does not fit")
    for L in letters:
        for dy, line in enumerate(L):
            for dx, ch in enumerate(line):
                if ch == "#":
                    rows[y0 + dy][x + dx] = 0x10
                elif ch == "+" and aa is not None:
                    rows[y0 + dy][x + dx] = aa
        x += len(L[0]) + 1
    return w, h, encode(rows, w, h, depth), rows


def make_icons(blobs):
    a = compose(blobs, ICON_A, 11, 28, 4, 46, 17, 5, (5, 6, 44))
    b = compose(blobs, ICON_B, 13, 36, 6, 58, 21, None, (6, 7, 56, 57))
    c = compose(blobs, ICON_CELL, 11, 28, 4, 46, 17, 5, (5, 6, 44))
    return [a, b, c]


# ---------------------------------------------------------------- install

def patch_block1(blk1, icons):
    d = bytearray(blk1)
    a0, s0 = struct.unpack_from("<II", d, 0)
    check((a0, s0) == (B1_FLASH + BLOB0_OFF, 0xc9e00), "block 1 directory entry 0 differs")
    check(bytes(d[BLOB0_OFF:BLOB0_OFF + 11]) == b"olycompress", "block 1 blob 0 header not found")
    g = bytearray(olycompress.unpack(d, BLOB0_OFF))
    check(struct.unpack_from("<I", g, 16)[0] == TABLE, "icon table pointer differs")
    tab = list(struct.unpack_from("<%dI" % TABLE_N, g, TABLE - BLOB0_RAM))
    check(all(v == 0 or BLOB0_RAM <= v < 0xa4000000 for v in tab) and
          not (0xa3000000 <= struct.unpack_from("<I", g, TABLE - BLOB0_RAM + 4 * TABLE_N)[0] < 0xa4000000),
          "icon table length differs")
    ids = []
    for w, h, data, _ in icons:
        while len(g) % 4:
            g.append(0)
        dp = BLOB0_RAM + len(g)
        g += data
        while len(g) % 4:
            g.append(0)
        desc = BLOB0_RAM + len(g)
        g += struct.pack("<4HIIII", 14, w, h, 8, 0, len(data), dp, 0)
        ids.append(TABLE_N + len(ids))
        tab.append(desc)
    while len(g) % 16:
        g.append(0)
    new_table = BLOB0_RAM + len(g)
    g += struct.pack("<%dI" % len(tab), *tab)
    struct.pack_into("<I", g, 16, new_table)
    check(BLOB0_RAM + len(g) <= BLOB0_LIMIT, "icon blob too large for its RAM area")
    c = olycompress.pack(bytes(g))
    hdr = bytearray(d[BLOB0_OFF:BLOB0_OFF + 32])
    struct.pack_into("<II", hdr, 16, len(c), len(g))
    blob = bytes(hdr) + c
    size = (len(blob) + 0x1ff) & ~0x1ff
    ends = []
    k = 0
    while True:
        a, s = struct.unpack_from("<II", d, 16 * k)
        if not B1_FLASH <= a < B1_FLASH + len(d):
            break
        ends.append(a - B1_FLASH + s)
        k += 1
    check(max(ends) <= NEW_BLOB_OFF and set(d[NEW_BLOB_OFF:NEW_BLOB_OFF + size]) == {0},
          "block 1 free space differs")
    d[NEW_BLOB_OFF:NEW_BLOB_OFF + len(blob)] = blob
    struct.pack_into("<II", d, 0, B1_FLASH + NEW_BLOB_OFF, size)
    check(olycompress.unpack(bytes(d), NEW_BLOB_OFF) == bytes(g), "new icon blob does not decode back")
    LOG("  icons %s -> ids %s, table %#x, blob 0 %#x -> %#x bytes at flash %#x"
        % ("/".join("%dx%d" % (w, h) for w, h, _, _ in icons), ids, new_table, s0, size, B1_FLASH + NEW_BLOB_OFF))
    return bytes(d), ids


def patch_main(img, ids):
    """IMG: main block with both blobs expanded (runtime image), edited in place."""
    o = lambda a: a - BASE                                     # noqa: E731
    u32 = lambda a: struct.unpack_from("<I", img, o(a))[0]     # noqa: E731
    id_a, id_b, id_cell = ids
    lists = []
    sid, n = struct.unpack_from("<HH", img, o(LV_ROW))
    check((sid, n) == (0x10d, 6), "SCP aspect row has no Panorama entry (Panorama mod missing?)")
    lists += [(u32(LV_ROW + 4), n, ICON_A, id_a), (u32(LV_ROW + 8), n, ICON_B, id_b)]
    key, pa, pb, n = struct.unpack_from("<IIII", img, o(SCP_ROW17))
    check((key, n) == (17, 6), "SCP item row 17 has no Panorama entry (Panorama mod missing?)")
    lists += [(pa, n, ICON_A, id_a), (pb, n, ICON_B, id_b)]
    for p, n, old, new in lists:
        hit = 0
        for k in range(n):
            val, typ, icn = struct.unpack_from("<IHH", img, o(p) + 12 * k)
            if val == 6:
                check(typ == 3 and icn == old, "Panorama list entry %#x differs" % p)
                struct.pack_into("<H", img, o(p) + 12 * k + 6, new)
                hit += 1
        check(hit == 1, "list %#x: no Panorama entry" % p)
    # current-value cell: part list + sixth record, remap 6 -> 10 (index 7)
    fl, lp, le = struct.unpack_from("<III", img, o(CELL_DESC) + 8)
    check((fl, lp, le) == (0x502, CELL_LIST, CELL_LIST_END), "cell part descriptor differs")
    recs = bytes(img[o(CELL_LIST):o(CELL_LIST_END)])
    check([struct.unpack_from("<4I", recs, 16 * k)[3] for k in range(5)] == [0x1dd, 0x1de, 0x1df, 0x976, 0x1dc],
          "cell part list differs")
    new = recs + struct.pack("<4I", 0xffff, 7, 7, id_cell)
    check(set(img[o(NEW_CELL_LIST) - 16:o(NEW_CELL_LIST) + len(new) + 16]) == {0xff}, "cell list area not free")
    img[o(NEW_CELL_LIST):o(NEW_CELL_LIST) + len(new)] = new
    struct.pack_into("<III", img, o(CELL_DESC) + 8, 0x602, NEW_CELL_LIST, NEW_CELL_LIST + len(new))
    j = img[o(REMAP_SITE)]
    check(j == 0xdc, "Panorama cell remap hook not found")
    stub = REMAP_SITE + struct.unpack_from("<i", img, o(REMAP_SITE) + 1)[0]
    body = bytes(img[o(stub) + 12:o(stub) + 12 + len(STUB_BODY)])
    check(body == STUB_BODY, "Panorama cell remap stub differs")
    img[o(stub) + 12 + 7] = 10
    LOG("  Panorama SCP lists -> icons %#x/%#x, cell list %#x (+ index 7 = icon %#x), cell remap 6 -> 10"
        % (id_a, id_b, NEW_CELL_LIST, id_cell))


def apply(img, plains):
    b1 = bytes(plains[1])
    check(struct.unpack_from("<I", b1, 16 * 69)[0] == B1_FLASH + BLOB69_OFF, "block 1 entry 69 differs")
    blobs = [(BLOB0_RAM, olycompress.unpack(b1, BLOB0_OFF)), (BLOB69_RAM, olycompress.unpack(b1, BLOB69_OFF))]
    icons = make_icons(blobs)
    plains[1][:], ids = patch_block1(bytes(plains[1]), [(w, h, data, rows) for w, h, data, rows in icons])
    patch_main(img, ids)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    import modcore
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    main_plain = blocks[0]["plain"]
    img = bytearray(modcore.runtime_image(main_plain))
    plains = [bytearray(b["plain"]) for b in blocks]
    apply(img, plains)
    out_main = modcore.rebuild_main(main_plain, img)
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), out_main if i == 0 else bytes(plains[i]), bytes(tail))
    check(len(out) == len(fw), "size changed")
    with open(dst, "wb") as fh:
        fh.write(out)
    again = olyfw.unpack_blocks(open(dst, "rb").read())
    check(all(b["stored"] == b["calc"] for b in again), "output checksum check failed")
    print("wrote %s  sha256 %s" % (dst, hashlib.sha256(out).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
