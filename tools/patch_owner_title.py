#!/usr/bin/env python3
"""Owner name / contact as the main menu's "Shooting Menu 1" title (EXPERIMENTAL, E-M1 Mark III 1.6).

  python3 tools/patch_owner_title.py IN.BIN OUT.BIN --text "NAME PHONE" [--text2 "..."] [--version 0x1701]

Language sections (block 1 directory entries 1..; English = entry 8, "OlympusLanguage_enutft"): UTF-16
strings, then a table of u32 RAM pointers, one per string id (English: table at section offset
0x32c9c, 3929 entries, section loaded at 0xa402b560), then zero padding, then the
"OlympusLanguage_..." trailer. String 0x2e1 = "Shooting Menu 1" (main menu tab title), 0x1ee =
"Shooting Menu 2". '@' starts icon codes in the text (e.g. "@A024@").

Patch: a text no longer than the stock one replaces it in place (space padded); a longer one goes into the zero padding after the pointer table (up to 36 characters), and
the string's pointer is repointed to it. Every other string is unchanged. English only.
--text2 (test) does the same for "Shooting Menu 2".
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

B1_FLASH = 0x42400000
SECTION = 8
TAB, COUNT, RAM = 0x32c9c, 3929, 0xa402b560
TRAILER = "OlympusLanguage_enutft"
MAX_CHARS = 36
TITLE1, TITLE2 = 0x2e1, 0x1ee
LOG = print
STOCK = {TITLE1: "Shooting Menu 1", TITLE2: "Shooting Menu 2"}


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def string_at(sec, p):
    o = p - RAM
    e = o
    while sec[e:e + 2] != b"\0\0":
        e += 2
    return sec[o:e].decode("utf-16le")


def patch_block1(blk1, texts):
    """TEXTS: {string id: new text}. Returns the new block 1 bytes."""
    d = bytearray(blk1)
    a, n = struct.unpack_from("<II", d, 16 * SECTION)
    o = a - B1_FLASH
    sec = d[o:o + n]
    tab_end = TAB + 4 * COUNT
    check(not (RAM <= struct.unpack_from("<I", sec, TAB - 4)[0] < RAM + n), "pointer table start differs")
    t = sec.find(TRAILER.encode("utf-16le"))
    check(t > tab_end, "language trailer not found")
    free = t - tab_end
    check(set(sec[tab_end:t]) == {0}, "padding after the pointer table is not free")
    at = tab_end
    for sid, text in texts.items():
        p = struct.unpack_from("<I", sec, TAB + 4 * sid)[0]
        check(string_at(sec, p) == STOCK[sid], "string %#x is not %r" % (sid, STOCK[sid]))
        check(0 < len(text) <= MAX_CHARS, "text must be 1..%d characters" % MAX_CHARS)
        raw = text.encode("utf-16le") + b"\0\0"
        if len(text) <= len(STOCK[sid]):          # fits in place: pad with spaces, keep the pointer
            sec[p - RAM:p - RAM + 2 * len(STOCK[sid])] = text.ljust(len(STOCK[sid])).encode("utf-16le")
            LOG("  string %#x %r -> %r (in place)" % (sid, STOCK[sid], text))
            continue
        check(at + len(raw) + 2 <= t, "not enough free space after the pointer table (%d bytes)" % free)
        sec[at:at + len(raw)] = raw
        struct.pack_into("<I", sec, TAB + 4 * sid, RAM + at)
        LOG("  string %#x %r -> %r (at section %#x)" % (sid, STOCK[sid], text, at))
        at += len(raw)
    d[o:o + n] = sec
    return bytes(d)


def main(argv):
    if len(argv) < 2 or "--text" not in argv:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    texts = {TITLE1: argv[argv.index("--text") + 1]}
    if "--text2" in argv:
        texts[TITLE2] = argv[argv.index("--text2") + 1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_b1 = patch_block1(blocks[1]["plain"], texts)
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), new_b1 if i == 1 else b["plain"], bytes(tail))
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
