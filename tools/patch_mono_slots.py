#!/usr/bin/env python3
"""patch_mono_slots.py - make Underwater and e-Portrait extra monochrome slots.

  python3 tools/patch_mono_slots.py IN.BIN OUT.BIN [--version 0x1750] [--report]

E-M1 Mark III 1.6. Takes the stock firmware and:

  1. Points the Underwater and e-Portrait entries of the stock 0x6f Picture Mode
     validator list at "pipeline 12 / filter value 2" and "pipeline 12 /
     filter value 3" respectively, copied from the stock DIAL_MONOCHROME_CREATOR
     list (setting 0x3c6). That makes each render as a Monochrome Profile.
  2. Changes their GUI values to Mono Profile 2/3 (0x3a/0x3b) so the camera
     recognises them as picture profiles and shows the Mono Profile controls
     (level / grain / shading) instead of Underwater's / e-Portrait's.
  3. Re-labels the Picture Mode menu lists (all three GUI copies in blob B) so
     Monotone, Underwater and e-Portrait read "Monochrome Profile 1/2/3" and
     sit together, in that order, right where Monotone used to be. Custom moves
     after them.

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
DIAL_MONO_LIST = 0x604c3cf4
ELEM, N_STOCK = 64, 26
STOCK_REC = bytes.fromhex("6f008000f4c44b6034e84a608006400000060000")
STOCK_ALT = [7, 0, 1, 2, 5, 3, 6, 0x14, 0x1c, 0x15, 8, 9, 10, 11, 12, 13, 14,
             15, 16, 17, 18, 19, 0x1a, 0x1b, 0x3c, 0x3f]

BLOB_B, BLOB_B_OFF, BLOB_END = 0x60c6c000, 0xc4afe0, 0x612f1000
MENU_DESCS = (0x611af718, 0x61206bc8, 0x6128837c)
# stock first 10 GUI values (before our changes)
MENU_HEAD = [7, 0, 1, 2, 5, 3, 6, 0x14, 0x1c, 0x15]
STR_MONO1, STR_MONO2, STR_MONO3 = 0xac5, 0xac6, 0xac7

I_MONO1, I_CUSTOM, I_EPORTRAIT, I_UNDERWATER = 5, 6, 7, 8


def off(addr):
    return addr - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def patch(main):
    m = bytearray(main)

    # --- validator list: stock record, entries and DIAL_MONO presets ---
    check(m[off(REC):off(REC) + 20] == STOCK_REC, "validator record of 0x6f differs from stock")
    alt = list(struct.unpack_from("<%dI" % N_STOCK, m, off(ALT)))
    check(alt == STOCK_ALT, "stock GUI value list differs")
    check(alt[I_EPORTRAIT] == 0x14 and alt[I_UNDERWATER] == 0x1c and alt[I_MONO1] == 3
          and alt[I_CUSTOM] == 6, "stock menu values at the target slots differ")

    def entry(k):
        return bytes(m[off(LIST) + ELEM * k:off(LIST) + ELEM * (k + 1)])

    e_mono1, e_custom, e_ep, e_uw = (entry(k) for k in
                                    (I_MONO1, I_CUSTOM, I_EPORTRAIT, I_UNDERWATER))
    check(e_mono1[0] == 5 and e_custom[0] == 6 and e_ep[0] == 8 and e_uw[0] == 10,
          "stock validator entries at the target slots differ")

    dial = [bytes(m[off(DIAL_MONO_LIST) + ELEM * k:off(DIAL_MONO_LIST) + ELEM * (k + 1)])
            for k in range(4)]
    check([d[0] for d in dial] == [2, 12, 12, 12], "DIAL_MONO list layout differs")
    check([int.from_bytes(d[4:8], "little") for d in dial[1:]] == [1, 2, 3],
          "DIAL_MONO preset slots are not 1/2/3")
    check(all(set(d[1:4] + d[8:]) == {0} for d in dial[1:]), "DIAL_MONO entries are not plain")
    slot2, slot3 = dial[2], dial[3]

    # Underwater (index 8) -> preset slot 2; e-Portrait (index 7) -> preset slot 3
    m[off(LIST) + ELEM * I_UNDERWATER:off(LIST) + ELEM * (I_UNDERWATER + 1)] = slot2
    m[off(LIST) + ELEM * I_EPORTRAIT:off(LIST) + ELEM * (I_EPORTRAIT + 1)] = slot3
    # change GUI values: Underwater 0x1c -> 0x3a (Mono Profile 2), e-Portrait 0x14 -> 0x3b (Mono Profile 3)
    alt[I_UNDERWATER] = 0x3a
    alt[I_EPORTRAIT] = 0x3b
    struct.pack_into("<%dI" % N_STOCK, m, off(ALT), *alt)
    print("  validator: Underwater -> {12,2} GUI 0x3a; e-Portrait -> {12,3} GUI 0x3b")

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

        mono1, custom, ep, uw = es[I_MONO1], es[I_CUSTOM], es[I_EPORTRAIT], es[I_UNDERWATER]
        check((mono1[1], mono1[2]) == (3, 0x5e1) and (custom[1], custom[2]) == (3, 0x5e2),
              "Monotone / Custom menu entries differ")
        check((ep[1], ep[2]) == (3, 0xd86) and (uw[1], uw[2]) == (3, 0x19a9),
              "e-Portrait / Underwater menu entries differ")

        new = es[:]
        # Monotone -> Mono Profile 1 (keep GUI 3, label string)
        new[I_MONO1] = (mono1[0], 4, STR_MONO1, mono1[3])
        # Underwater -> Mono Profile 2 (GUI 0x3a, label string)
        new[I_UNDERWATER] = (0x3a, 4, STR_MONO2, uw[3])
        # e-Portrait -> Mono Profile 3 (GUI 0x3b, label string)
        new[I_EPORTRAIT] = (0x3b, 4, STR_MONO3, ep[3])
        # Custom stays
        new[I_CUSTOM] = (custom[0], 3, custom[2], custom[3])
        # reorder: Mono 1, Mono 2 (UW), Mono 3 (EP), Custom
        new[I_MONO1:I_UNDERWATER + 1] = [new[I_MONO1], new[I_UNDERWATER],
                                        new[I_EPORTRAIT], new[I_CUSTOM]]
        data = b"".join(struct.pack("<IHHI", *e) for e in new)
        gui[lp - BLOB_B:lp - BLOB_B + len(data)] = data
    print("  3 menu lists: Monochrome Profile 1/2/3 together, Custom after them")

    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode")
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
        out += olyfw.build_block(bytes(head), new_main if i == 0 else b["plain"], bytes(tail))
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