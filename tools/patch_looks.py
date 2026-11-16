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
SRC = """call builder,[d2,d3,a2,a3],96
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


def hl_table(hues, lights):
    return "".join(" .hword %d,%d\n" % (h, l) for h, l in zip(hues, lights))


def patch(main, hues, lights):
    import patch_aspect
    m = bytearray(main)
    e = off(PM_LIST) + PM_ELEM * CUSTOM_IDX
    check(struct.unpack_from("<I", m, e)[0] == 6, "Custom picture-mode entry differs")
    check(bytes(m[off(SITE):off(SITE) + 5]) == SITE_STOCK, "colour builder call differs")
    check(bytes(m[off(SITE) - len(SITE_PRE):off(SITE)]) == SITE_PRE, "colour selector differs")
    check(set(m[off(STUB):off(STUB) + 0x100]) == {0xff}, "stub area not free")
    stub = patch_aspect.assemble_syms(SRC + hl_table(hues, lights), STUB,
                                      {"builder": BUILDER, "resume": RESUME})
    check(len(stub) <= 0x100, "stub too long")
    jmp = patch_aspect.assemble_syms("jmp stub", SITE, {"stub": STUB})
    check(len(jmp) == 5, "jump is not 5 bytes")
    m[e:e + PM_ELEM] = struct.pack("<I", 11) + bytes(PM_ELEM - 4)
    m[off(STUB):off(STUB) + len(stub)] = stub
    m[off(SITE):off(SITE) + 5] = jmp
    print("  Custom -> Color Profile; H/L hook %#x -> stub %#x (%d B)" % (SITE, STUB, len(stub)))
    return bytes(m)


def main(argv):
    if len(argv) < 3 or "--test1" not in argv:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    hues, lights = [3000] * 12, [0] * 12
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_main = patch(blocks[0]["plain"], hues, lights)
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
