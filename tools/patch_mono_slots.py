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
   4. Deletes the art-filter "Star Light Effect" (5) option from its Add Effects
      pickers and validator, and hides the two "Shade Effect" values (8/9) from
      the validator. There is no Off placeholder left in the Star Light slot.
      They have caused camera problems.
   5. Disables Star Light Effect at runtime: both image-processing snapshot
      builders read Add Effect (property 0xf5d1) through a stub that turns
      value 5 into Off, so a stored selection can no longer make the effect run.

Needs MN10300_BIN (the mn10300-elf assembler) for the runtime stub. The
compressed GUI blob is recompressed and checked round-trip. Every stock byte
relied on is checked before writing.
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
STR_STAR_LIGHT, STR_OFF = 0x300, 0x5ae

# Runtime disable of Star Light Effect. Both snapshot builders read property
# 0xf5d1 (Add Effect) into job +26825. Route those two reads through a stub that
# coerces value 5 to Off (0), so the effect cannot run even if a saved setting
# still contains 5. The stub sits at 0x600d2f80: immediately after the High Res
# art identity map (0x600d2f00 + 26 * 4 bytes, checked with 0x10 bytes of slack),
# and outside every other mod's code/data area.
STAR_STUB = 0x600d2f80
STAR_SITES = (0x602c31fa, 0x6147cf82)
STAR_PRE = bytes.fromhex("fcccd1f50000900004")
PROP_GET = 0x6005fa9c
STAR_STUB_SRC = """call prop,[d2,d3],12
extbu d0
cmp 5,d0
bne 1f
clr d0
1:
ret [],4
"""

# Art-filter "Add Effects" validators. Value 5 is Star Light Effect; 8/9 are
# the two Shade effects. Star Light is removed from the list and the Shade values
# are mapped to 7 (Proton Accumulation), so menus cannot select them.
BAD_EFFECT_VALIDATORS = (
    (0x604dd250, 0x59e, 0x604d9615),
    (0x604dddb8, 0x292, 0x604d9946),
    (0x604dddcc, 0x36d, 0x604d9946),
    (0x604ddde0, 0x36e, 0x604d9946),
    (0x604dea24, 0x362, 0x604d9bcf),
    (0x604e057c, 0x590, 0x604da2d6),
    (0x604e0590, 0x591, 0x604da2d6),
)
ADD_EFFECT_STOCK = bytes([0, 1, 2, 4, 3, 5, 6, 7, 8, 9])
ADD_EFFECT_SHADE_HIDDEN = bytes([0, 1, 2, 4, 3, 5, 6, 7, 7, 7])
ADD_EFFECT_HIDDEN = bytes([0, 1, 2, 4, 3, 6, 7, 7])

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
    """Rename 0x091 and 0xca9, allocating UTF-16 strings in free padding.

    Allocation is even-aligned and never reuses bytes written by an earlier
    string, so it works when this mod is chained with other language mods.
    It is also idempotent.
    """
    d = bytearray(blk1)
    a, n = struct.unpack_from("<II", d, 16 * LANG_SECTION)
    o = a - B1_FLASH
    sec = d[o:o + n]
    tab_end = LANG_TAB + 4 * LANG_COUNT
    t = sec.find("OlympusLanguage_enutft".encode("utf-16le"))
    check(t > tab_end, "language trailer not found")

    used = []

    def bounds(sid):
        p = struct.unpack_from("<I", sec, LANG_TAB + 4 * sid)[0]
        s = p - LANG_RAM
        check(0 <= s < len(sec), "string 0x%03x pointer out of range" % sid)
        e = s
        while e + 1 < len(sec) and sec[e:e + 2] != b"\0\0":
            e += 2
        check(e + 2 <= len(sec), "string 0x%03x is not terminated" % sid)
        return s, e + 2

    def reserve(s, e):
        for a0, b0 in used:
            check(e <= a0 or s >= b0, "language string allocations overlap")
        used.append((s, e))

    def allocate(raw):
        for at in range(tab_end + (tab_end & 1), t - len(raw) + 1, 2):
            if any(at < b0 and a0 < at + len(raw) for a0, b0 in used):
                continue
            if all(b == 0 for b in sec[at:at + len(raw)]):
                sec[at:at + len(raw)] = raw
                reserve(at, at + len(raw))
                return at
        check(False, "not enough even-aligned free space for renamed string")

    for sid, old, new in ((STR_IFINISH, "i-Enhance", NEW_NAME),
                          (0xca9, "@A089@i-Enhance", "@A089@" + NEW_NAME)):
        s, e = bounds(sid)
        current = sec[s:e - 2].decode("utf-16le")
        if current == new:
            if s >= tab_end:
                reserve(s, e)
            print("  language: string 0x%03x already '%s', skipping" % (sid, new))
            continue
        check(current == old, "string 0x%03x is not %r (got %r)" % (sid, old, current))
        at = allocate(new.encode("utf-16le") + b"\0\0")
        struct.pack_into("<I", sec, LANG_TAB + 4 * sid, LANG_RAM + at)
        print("  language: string 0x%03x %r -> %r" % (sid, old, new))

    for sid, _old, new in ((STR_IFINISH, "i-Enhance", NEW_NAME),
                           (0xca9, "@A089@i-Enhance", "@A089@" + NEW_NAME)):
        s, e = bounds(sid)
        check(sec[s:e - 2].decode("utf-16le") == new,
              "renamed string 0x%03x did not round-trip" % sid)

    d[o:o + n] = sec
    return bytes(d)


def hide_bad_effects(m):
    """Remove art-filter Star Light (5) and Shade (8/9) from their validators.

    Menus enumerate the validator, so shortening each list to the first eight
    values hides both Shade options. Star Light is replaced by Off in place so
    no count shift is needed. The list tail is set to the last safe value too,
    in case any code ignores the shortened count.
    """
    groups = {}
    for rec, sid, lp in BAD_EFFECT_VALIDATORS:
        groups.setdefault(lp, []).append((rec, sid))

    for lp, recs in groups.items():
        lo = off(lp)
        cur = bytes(m[lo:lo + 10])
        check(cur in (ADD_EFFECT_STOCK, ADD_EFFECT_SHADE_HIDDEN, ADD_EFFECT_HIDDEN),
              "art-effect validator list %#x differs from stock" % lp)
        if cur != ADD_EFFECT_HIDDEN:
            m[lo:lo + 10] = ADD_EFFECT_HIDDEN
        for rec, sid in recs:
            o = off(rec)
            got = struct.unpack_from("<HHIIHHBBH", m, o)
            check((got[0], got[2], got[3], got[5], got[7]) == (sid, lp, 0, 1, 1),
                  "art-effect validator %#x differs from stock" % rec)
            expected = 10 if cur == ADD_EFFECT_STOCK else 8
            check(got[4] == expected,
                  "art-effect validator %#x has an unexpected count" % rec)
            struct.pack_into("<H", m, o + 12, 8)
            print("  validator: hidden Star Light Effect (5) and Shade Effects (8/9) for setting 0x%03x" % sid)
    return m


def hide_star_effect_gui(gui):
    """Relabel every Star Light Effect option entry as Off.

    The validators above hide the value from settings, but the Add Effects
    pickers in blob B have their own 12-byte option records (value, type,
    string id, condition). Change value 5 to 0 and the label to Off so the
    option cannot be selected or shown as Star Light any more.
    """
    n = 0
    for o in range(0, len(gui) - 12 + 1, 4):
        value, kind, sid, _cond = struct.unpack_from("<IHHI", gui, o)
        if value == 5 and sid == STR_STAR_LIGHT:
            struct.pack_into("<I", gui, o, 0)
            struct.pack_into("<H", gui, o + 6, STR_OFF)
            n += 1
    check(n == 16, "expected 16 Star Light GUI options, found %d" % n)
    print("  GUI: %d Star Light Effect options -> Off" % n)
    return gui


def disable_star_light(m):
    """Make value 5 of property 0xf5d1 behave as Off in both snapshot builders.

    Validator/GUI changes only stop new selections; a value already saved in
    settings would still be read by the capture code. Replacing the two property
    calls with a small stub removes the effect itself.
    """
    import patch_aspect  # needs MN10300_BIN

    stub = patch_aspect.assemble_syms(STAR_STUB_SRC, STAR_STUB, {"prop": PROP_GET})
    check(len(stub) <= 0x40, "star-light stub too long")
    area = m[off(STAR_STUB):off(STAR_STUB) + 0x40]
    if bytes(area[:len(stub)]) != stub:
        check(set(area) == {0xff}, "star-light stub area %#x is not free" % STAR_STUB)
        m[off(STAR_STUB):off(STAR_STUB) + len(stub)] = stub

    for site in STAR_SITES:
        check(bytes(m[off(site) - 9:off(site)]) == STAR_PRE,
              "Add Effect read at %#x differs from stock" % site)
        stock_call = patch_aspect.assemble_syms("call prop,[d2,d3],12", site, {"prop": PROP_GET})
        new_call = patch_aspect.assemble_syms("call star,[],4", site, {"star": STAR_STUB})
        check(len(stock_call) == len(new_call) == 7, "star-light call length differs")
        cur = bytes(m[off(site):off(site) + 7])
        check(cur in (stock_call, new_call), "unexpected call at %#x" % site)
        if cur != new_call:
            m[off(site):off(site) + 7] = new_call
    print("  runtime: Add Effect 5 (Star Light) -> Off at %s via stub %#x"
          % (", ".join("%#x" % a for a in STAR_SITES), STAR_STUB))
    return m


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

    hide_bad_effects(m)
    disable_star_light(m)

    # --- GUI: re-label and re-order the three Picture Mode menu lists (in place) ---
    check(bytes(m[BLOB_B_OFF:BLOB_B_OFF + 11]) == b"olycompress", "blob B header not found")
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    hide_star_effect_gui(gui)

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
