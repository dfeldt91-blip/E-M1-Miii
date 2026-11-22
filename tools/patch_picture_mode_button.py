#!/usr/bin/env python3
"""Picture Mode toggle on a Button Function entry (EXPERIMENTAL, NOT CAMERA-TESTED).

  python3 tools/patch_picture_mode_button.py IN.BIN OUT.BIN
      [--modes 0,1,2,3,4,5,6,7,9] [--all] [--version 0x17xx]

Adds "Picture Mode" (stock button-function code 284, stock label "Backlit LCD")
to the Button Function picker and makes a press cycle the Picture Mode setting
0x6f (MODE_COLORTONE) through a short list of stored indexes. Code 284 is not
in any stock button list, so no working assignment is replaced.

What is patched (runtime addresses):

  main block
    0x600d6100  new 39-entry Button Function validator list (stock 38 + 284)
    0x600d6180  66-byte MN103 stub: get(0x6f) -> next index -> set(0x6f)
    0x600d62e0  u16 cycle table, 0xffff terminated
    0x600d6320  new 40-entry validator list for the special button record
    0x604db608..0x604db734  16 full-button validator records -> new list, 76->78 bytes
    0x604db748  special validator record -> new list, 78->80 bytes

  GUI blob B (decompressed at 0x60c6c000, stored at main offset 0xc4afe0)
    0x60f2350c  code 284's function row: action 29 -> 99 (unused type-2 action)
    0x60f37e64  action 99 press jump: 0x60cc4aab (RET) -> the stub
    0x611d8a64 / 0x61296124  icon entries -> text "Picture Mode" (0xcb)
    0x61295f20              name 0x169 "Backlit LCD" -> 0xcb
    0x6129649c              help 0x170 "Back Light On/Off." -> 0xb0b

The stub calls the stock setting API 0x60cb1b1e(sid) / 0x60cb1a73(sid, value)
and tail-jumps to the stock action-99 return at 0x60cc4aab. The release jump
table is left alone, so the normal button-release cleanup still runs.

0x6f stores an INDEX into its 26-entry validator list at 0x604bc4f4. The first
indexes map to these displayed modes (confirmed on camera):
  0 i-Enhance, 1 Soft Focus, 2 Vivid, 3 Natural, 4 Muted, 5 Monochrome,
  6 Custom, 7 Underwater, 8 Color Creator, 9 Art Filter, 10..25 more filters.
The setter takes the DISPLAY VALUE directly (confirmed on camera), not a
validator-list index. The wanted values are:
  7 i-Enhance, 0 Vivid, 1 Natural, 2 Muted, 3 Monochrome.
The cycle table is left BYTE-FOR-BYTE as the stock 9-value list, because the
camera stores a parameter with the custom-button assignment and drops the
function if the table changes. Instead the stub maps the five values itself:
  7 -> 0 -> 1 -> 2 -> 3 -> 7.
Use --all/--modes to change the table for a fresh assignment.

Every byte the patch relies on is checked first. Requires no binutils: the
stub is pre-assembled below; set MN10300_BIN to also verify it against source.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402
import olycompress  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF, BLOB_END = 0x60c6c000, 0xc4afe0, 0x612f1000

# Flash padding. 0x600d6100..0x600d61cf and 0x600d62d0..0x600d6380 are unused
# by the shipped mods (panorama occupies 0x600d6200..0x600d62dd).
LIST_AT, STUB_AT, TABLE_AT, SPECIAL_AT = 0x600d6100, 0x600d6180, 0x600d62e0, 0x600d6320
FREE = ((0x600d6100, 0x600d61d0), (0x600d62e0, 0x600d6380))

STOCK_FULL = [3333, 44, 106, 84, 85, 3297, 88, 22, 3279, 3348, 3349, 3350,
              3351, 3341, 34, 682, 1431, 3352, 472, 603, 6, 9, 436, 567,
              3408, 452, 765, 1139, 1292, 1072, 157, 3428, 1680, 3431, 241,
              36, 1872, 3200]
SPECIAL_SID, SPECIAL_PREFIX = 0x38, 3209
FULL_RECS = (0x604db608, 0x604db61c, 0x604db630, 0x604db644, 0x604db658,
             0x604db66c, 0x604db680, 0x604db694, 0x604db6a8, 0x604db6bc,
             0x604db6d0, 0x604db6e4, 0x604db6f8, 0x604db70c, 0x604db720,
             0x604db734)
SPECIAL_REC = 0x604db748
BUTTON_CODE, ACTION = 284, 99
FUNC_ROW, JUMP_TABLE = 0x60f23504, 0x60f37e64
STOCK_ROW = (69, 284, 29)
STOCK_JUMP = 0x60cc4aab
BACK = 0x60cc4aab
GET, SET = 0x60cb1b1e, 0x60cb1a73
NAME_SID, HELP_SID = 0x0cb, 0xb0b            # "Picture Mode", "Select Picture Mode."
LABELS = (                                    # (address, stock code/type/label, new type/label)
    (0x611d8a64, (284, 3, 54),  (4, NAME_SID)),
    (0x61296124, (284, 3, 54),  (4, NAME_SID)),
    (0x61295f20, (284, 4, 0x169), (4, NAME_SID)),
    (0x6129649c, (284, 4, 0x170), (4, HELP_SID)),
)
DEFAULT_MODES = [0, 1, 2, 3, 4, 5, 6, 7, 9]  # unchanged; stub filters the cycle

# mn10300-elf-as / -ld / -objcopy at STUB_AT. Registers a2/d2 are saved by the
# CALL forms; d3 is scratch. The cycle table is deliberately NOT consulted: it
# stays stock so the camera keeps the custom-button assignment. This stub maps
# the five wanted values directly and treats anything else as a wrap to 0.
SRC = """mov 0x6f,d0
call get,[d2,a2],24
mov d0,d3
cmp 7,d3
bne L1
mov 0,d0
bra go
L1:
cmp 0,d3
bne L2
mov 1,d0
bra go
L2:
cmp 1,d3
bne L3
mov 2,d0
bra go
L3:
cmp 2,d3
bne L4
mov 3,d0
bra go
L4:
cmp 3,d3
bne L5
mov 7,d0
bra go
L5:
mov 7,d0
go:
mov d0,d1
mov 0x6f,d0
call set,[d2,a2],20
jmp back"""
STUB = bytes.fromhex(
    "806fdd9cb9bd00a01883af07c9068000ca24af00c9068001ca1caf01c9068002"
    "ca14af02c9068003ca0caf03c9068007ca04800781806fddbcb8bd00a014"
    "dcede8be00")


def off(a):
    return a - BASE


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def modes_from(args):
    if "--all" in args:
        return list(range(26))
    if "--modes" in args:
        try:
            modes = [int(x, 0) for x in args[args.index("--modes") + 1].split(",")]
        except (IndexError, ValueError):
            sys.exit("--modes needs a comma-separated list of 0x6f indexes")
    else:
        modes = list(DEFAULT_MODES)
    check(bool(modes) and all(0 <= m < 26 for m in modes), "modes must be 0..25")
    return modes


def patch_main(main, modes):
    import patch_aspect
    m = bytearray(main)
    new_list = STOCK_FULL[:-1] + [BUTTON_CODE, 3200]
    special = [SPECIAL_PREFIX] + new_list
    table = struct.pack("<%dH" % (len(modes) + 1), *modes, 0xffff)

    for lo, hi in FREE:
        check(set(m[off(lo):off(hi)]) == {0xff}, "free area %#x..%#x is not 0xff" % (lo, hi))
    check(set(m[off(SPECIAL_AT):off(SPECIAL_AT) + 2 * len(special)]) == {0xff},
          "special list area is not 0xff")

    # validator records: check the stock list behind each record before repointing
    for rec in FULL_RECS:
        sid, fl, lp, ap, nb, el = struct.unpack_from("<HHIIHH", m, off(rec))
        check((fl, nb, el) == (0x80, 76, 2), "full-button record %#x differs" % rec)
        check(list(struct.unpack_from("<38H", m, off(lp))) == STOCK_FULL,
              "stock list behind record %#x differs" % rec)
    sid, fl, lp, ap, nb, el = struct.unpack_from("<HHIIHH", m, off(SPECIAL_REC))
    check((sid, fl, nb, el) == (SPECIAL_SID, 0x80, 78, 2), "special record differs")
    check(list(struct.unpack_from("<39H", m, off(lp))) == [SPECIAL_PREFIX] + STOCK_FULL,
          "stock special list differs")

    m[off(LIST_AT):off(LIST_AT) + 2 * len(new_list)] = struct.pack("<%dH" % len(new_list), *new_list)
    m[off(SPECIAL_AT):off(SPECIAL_AT) + 2 * len(special)] = struct.pack("<%dH" % len(special), *special)
    m[off(TABLE_AT):off(TABLE_AT) + len(table)] = table

    if os.environ.get("MN10300_BIN"):
        assembled = patch_aspect.assemble_syms(SRC, STUB_AT, {
            "get": GET, "set": SET, "back": BACK})
        check(assembled == STUB, "pre-assembled stub differs from the assembled source")
    m[off(STUB_AT):off(STUB_AT) + len(STUB)] = STUB

    for rec in FULL_RECS:
        struct.pack_into("<I", m, off(rec) + 4, LIST_AT)
        struct.pack_into("<H", m, off(rec) + 12, 2 * len(new_list))
    struct.pack_into("<I", m, off(SPECIAL_REC) + 4, SPECIAL_AT)
    struct.pack_into("<H", m, off(SPECIAL_REC) + 12, 2 * len(special))

    # GUI blob B: labels, function row, action jump
    csz = struct.unpack_from("<I", m, BLOB_B_OFF + 16)[0]
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    check(olycompress.pack(bytes(gui)) == bytes(m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + csz]),
          "blob B does not recompress identically")
    for a, stock, (ty, lab) in LABELS:
        o = a - BLOB_B
        c, t, l = struct.unpack_from("<IHH", gui, o)
        check((c, t, l) == stock, "label entry %#x differs" % a)
        struct.pack_into("<HH", gui, o + 4, ty, lab)
    row = FUNC_ROW - BLOB_B
    check(struct.unpack_from("<3I", gui, row) == STOCK_ROW, "code 284 function row differs")
    struct.pack_into("<I", gui, row + 8, ACTION)
    j = JUMP_TABLE - BLOB_B
    check(struct.unpack_from("<I", gui, j)[0] == STOCK_JUMP, "action 99 jump entry differs")
    struct.pack_into("<I", gui, j, STUB_AT)

    c = olycompress.pack(bytes(gui))
    check(len(c) <= off(BLOB_END) - (BLOB_B_OFF + 32), "recompressed blob does not fit")
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF + 32:BLOB_B_OFF + 32 + len(c)] = c
    if len(c) < csz:
        m[BLOB_B_OFF + 32 + len(c):old_end] = b"\xff" * (old_end - BLOB_B_OFF - 32 - len(c))
    struct.pack_into("<I", m, BLOB_B_OFF + 16, len(c))
    check(olycompress.unpack(m, BLOB_B_OFF) == bytes(gui), "recompressed blob does not decode to the edit")

    print("  %d validator records + special -> code 284; cycles %d indexes; blob B %#x -> %#x"
          % (len(FULL_RECS) + 1, len(modes), csz, len(c)))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    modes = modes_from(argv)
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    new_main = patch_main(blocks[0]["plain"], modes)
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
    print("wrote %s  sha256 %s  version %#06x" % (
        dst, hashlib.sha256(out).hexdigest(), struct.unpack_from("<H", again[0]["head"], 16)[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
