#!/usr/bin/env python3
"""patch_mono_slots.py - make extra monochrome picture profile slots.

  python3 tools/patch_mono_slots.py IN.BIN OUT.BIN [--version 0x1750] [--report]

E-M1 Mark III 1.6. Takes the stock firmware and:

  1. Copies the stock Monotone entry (pipeline 5, filter 1) into the
     i-Finish, Underwater and e-Portrait slots of the 0x6f Picture Mode
     validator list, so they render as Monotone (stock black and white) with
     Monotone's picture profile settings.
  2. Renames "i-Enhance" (strings 0x091, 0xca9) to "Monochrome II" in the
     language block (block 1).
  3. Re-labels i-Finish, Monotone, Underwater and e-Portrait in the Picture
     Mode menu lists as "Monochrome II/1/2/3" and moves i-Finish after Monotone.

Verified-data-only except for the compressed GUI blob, which is recompressed
and checked round-trip. Every byte relied on is checked before writing.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
REC = 0x604da7bc
LIST = 0x604bc4f4
ALT = 0x604ae834
ELEM, N_STOCK = 64, 26
STOCK_REC = bytes.fromhex("6f008000f4c44b6034e84a608006400000060000")
STOCK_ALT = [7, 0, 1, 2, 5, 3, 6, 0x14, 0x1c, 0x15, 8, 9, 10, 11, 12, 13, 14,
             15, 16, 17, 18, 19, 0x1a, 0x1b, 0x3c, 0x3f]

BLOB_B, BLOB_B_OFF, BLOB_END = 0x60c6c000, 0xc4afe0, 0x612f1000
MENU_DESCS = (0x611af718, 0x61206bc8, 0x6128837c)
MENU_HEAD = [7, 0, 1, 2, 5, 3, 6, 0x14, 0x1c, 0x15]
STR_MONO1, STR_MONO2, STR_MONO3 = 0xac5, 0xac6, 0xac7

# Language block constants
B1_FLASH = 0x42400000
LANG_SECTION = 8
LANG_TAB = 0x32c9c
LANG_COUNT = 3929
LANG_RAM = 0xa402b560
STR_IFINISH = 0x091
NEW_NAME = "Monochrome II"

I_IFINISH, I_MONO1, I_CUSTOM, I_EPORTRAIT, I_UNDERWATER = 0, 5, 6, 7, 8


def off(addr):
    return addr - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch_lang(blk1):
    """Rename string 0x091 'i-Enhance' -> 'Monochrome II' and 0xca9 similarly."""
    d = bytearray(blk1)
    a, n = struct.unpack_from("<II", d, 16 * LANG_SECTION)
    o = a - B1_FLASH
    sec = d[o:o + n]
    tab_end = LANG_TAB + 4 * LANG_COUNT
    t = sec.find("OlympusLanguage_enutft".encode("utf-16le"))
    check(t > tab_end, "language trailer not found")
    free = t - tab_end
    check(set(sec[tab_end:t]) == {0}, "padding after pointer table is not free")

    # 0x091
    p = struct.unpack_from("<I", sec, LANG_TAB + 4 * STR_IFINISH)[0]
    s = p - LANG_RAM
    e = s
    while sec[e:e + 2] != b"\0\0":
        e += 2
    old_str = sec[s:e].decode("utf-16le")
    check(old_str == "i-Enhance", "string 0x%03x is not 'i-Enhance' (got %r)" % (STR_IFINISH, old_str))

    at = tab_end
    raw = NEW_NAME.encode("utf-16le") + b"\0\0"
    check(at + len(raw) + 2 <= t, "not enough free space")
    sec[at:at + len(raw)] = raw
    struct.pack_into("<I", sec, LANG_TAB + 4 * STR_IFINISH, LANG_RAM + at)
    at += len(raw)
    print("  language: string 0x%03x 'i-Enhance' -> '%s'" % (STR_IFINISH, NEW_NAME))

    # 0xca9
    p2 = struct.unpack_from("<I", sec, LANG_TAB + 4 * 0xca9)[0]
    s2 = p2 - LANG_RAM
    e2 = s2
    while sec[e2:e2 + 2] != b"\0\0":
        e2 += 2
    old_str2 = sec[s2:e2].decode("utf-16le")
    check(old_str2 == "@A089@i-Enhance", "string 0xca9 unexpected: %r" % old_str2)
    raw2 = "@A089@Monochrome II".encode("utf-16le") + b"\0\0"
    check(at + len(raw2) + 2 <= t, "not enough free space")
    sec[at:at + len(raw2)] = raw2
    struct.pack_into("<I", sec, LANG_TAB + 4 * 0xca9, LANG_RAM + at)
    at += len(raw2)
    print("  language: string 0xca9 '@A089@i-Enhance' -> '@A089@Monochrome II'")

    d[o:o + n] = sec
    return bytes(d)


def patch(main):
    m = bytearray(main)

    # --- validator list ---
    check(m[off(REC):off(REC) + 20] == STOCK_REC, "validator record of 0x6f differs from stock")
    alt = list(struct.unpack_from("<%dI" % N_STOCK, m, off(ALT)))
    check(alt == STOCK_ALT, "stock GUI value list differs")

    def entry(k):
        return bytes(m[off(LIST) + ELEM * k:off(LIST) + ELEM * (k + 1)])

    e_ifinish = entry(I_IFINISH)
    e_mono1 = entry(I_MONO1)
    check(e_ifinish[0] == 7 and e_mono1[0] == 5, "stock entries differ")

    mono_entry = entry(I_MONO1)

    # Copy Monotone entry to i-Finish, Underwater and e-Portrait slots
    for idx in (I_IFINISH, I_UNDERWATER, I_EPORTRAIT):
        m[off(LIST) + ELEM * idx:off(LIST) + ELEM * (idx + 1)] = mono_entry
    print("  validator: i-Finish, Underwater & e-Portrait -> Monotone ({5,1})")

    # --- GUI: re-label and re-order the three Picture Mode menu lists (in place) ---
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")

    for d in MENU_DESCS:
        sid, n, lp = struct.unpack_from("<HHI", gui, d - BLOB_B)
        check((sid, n) == (0x6f, 54), "menu descriptor %#x differs" % d)
        es = [struct.unpack_from("<IHHI", gui, lp - BLOB_B + 12 * k) for k in range(n)]
        check([e[0] for e in es[:10]] == MENU_HEAD, "menu list %#x differs" % lp)
        check(all(e[1] == 3 for e in es), "menu list %#x has a non-icon entry" % lp)

        new = es[:]
        new[0] = (es[0][0], 4, STR_IFINISH, es[0][3])
        new[I_MONO1] = (es[I_MONO1][0], 4, STR_MONO1, es[I_MONO1][3])
        new[I_UNDERWATER] = (es[I_UNDERWATER][0], 4, STR_MONO2, es[I_UNDERWATER][3])
        new[I_EPORTRAIT] = (es[I_EPORTRAIT][0], 4, STR_MONO3, es[I_EPORTRAIT][3])
        new[0:10] = [es[1], es[2], es[3], es[4], new[I_MONO1], new[0], es[6], new[I_EPORTRAIT], new[I_UNDERWATER], es[9]]
        data = b"".join(struct.pack("<IHHI", *e) for e in new)
        gui[lp - BLOB_B:lp - BLOB_B + len(data)] = data
    print("  3 menu lists: i-Finish moved after Monotone, relabeled")

    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob B does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob B does not decode")
    print("  blob B %#x -> %#x" % (csz, len(c)))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    b0 = blocks[0]
    check(b0["info"]["type"] == "OE" and b0["info"]["model"] == 0x1390
          and b0["info"]["flags"] == 0x100, "first block is not the E-M1 III main code block")
    new_main = patch(b0["plain"])
    new_b1 = patch_lang(blocks[1]["plain"])
    ver = None
    if "--version" in argv:
        ver = int(argv[argv.index("--version") + 1], 0)
        check(0 < ver <= 0x9999 and all(((ver >> s) & 0xf) <= 9 for s in (0, 4, 8, 12)),
              "--version must be BCD, e.g. 0x1750")
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            check(struct.unpack_from("<H", head, 16)[0] == struct.unpack_from("<H", tail, 16)[0],
                  "main block head/tail versions differ")
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        plain = new_main if i == 0 else (new_b1 if i == 1 else b["plain"])
        out += olyfw.build_block(bytes(head), plain, bytes(tail))
    check(len(out) == len(fw), "size changed")
    diff = [i for i in range(len(fw)) if fw[i] != out[i]] if "--report" in argv else None
    with open(dst, "wb") as fh:
        fh.write(out)
    again = olyfw.unpack_blocks(open(dst, "rb").read())
    check(all(b["stored"] == b["calc"] for b in again), "output checksum check failed")
    print("wrote %s  sha256 %s" % (dst, hashlib.sha256(out).hexdigest()))
    if diff is not None:
        print("  file bytes changed: %d" % len(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PY