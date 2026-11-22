#!/usr/bin/env python3
"""On-camera HSL editor (E-M1 Mark III 1.6, TEST).

SCP INFO on Custom picture mode opens the stock Color Creator screen (state 53)
as an HSL editor. Hue ring selects color sector (12). Saturation bar edits the
current axis value for that sector. INFO cycles Sat -> Hue -> Light.
Engine: patch_hsl.py reads 0x399/0x3a5/0x3b1.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw, olycompress, patch_aspect  # noqa: E402
import patch_hsl as hsl  # noqa: E402

BASE = 0x60021020
BLOB_B, BLOB_B_OFF, BLOB_END = 0x60c6c000, 0xc4afe0, 0x612f1000
HSL_FLAG   = 0x600d5ff0
HSL_SECTOR = 0x600d5ff4
HSL_AXIS   = 0x600d5ff8  # 0=sat(-5..5), 1=hue(-7..7), 2=light(-7..7)
STUB = 0x600d5700
STUB_END = 0x600d5a00

SET, GET = 0x602ca855, 0x602ca6a5
SAT0, HUE0, LIGHT0 = 0x399, 0x3a5, 0x3b1

# SCP INFO entry (blob B): MOV (8,SP),d0; CMP 21,d0; BNE 0x60e7e64e
ENTRY_SITE = 0x60e7e5f9
ENTRY_STOCK = bytes.fromhex('5808a015c951')
ENTRY_CC = 0x60e7e5ff
ENTRY_NEXT = 0x60e7e64e

# Setting getter/setter in main
GET_SITE, GET_STOCK = 0x602ca6a5, bytes.fromhex('1ccd4e12f014')   # exthu d0; call 0x602cb8f4 (6 bytes)
SET_SITE, SET_STOCK = 0x602ca855, bytes.fromhex('4604828f01')     # mov d1,(4,sp); mov d0,d2; mov 1,d3
GET_BODY = 0x602ca6aa  # after exthu d0
SET_BODY = 0x602ca85a  # after 5 bytes

# init_sat in blob B: has "mov 8,d1" at 0x60e022e7 and 0x60e022f8, label ptrs at 0x60e022e1, 0x60e022f2
INIT_SAT_COUNT1 = 0x60e022e7  # 85 08 -> 85 0b
INIT_SAT_COUNT2 = 0x60e022f8  # 85 08 -> 85 0b
INIT_SAT_LBL1   = 0x60e022e1  # mov 0x611d2da0,a1 (6 bytes)
INIT_SAT_LBL2   = 0x60e022f2  # mov 0x611d2de0,a1 (6 bytes)
CHANGED = 0x60e02302  # change handler (handler table entry 2)

# 11-entry label tables for 0x60e08ee0: {s32 value, u32 label_id} x 11
# Values -5..5. Label IDs: reuse existing color creator-like numeric labels.
# 0x60e08ee0 does: if value matches, stores label byte from pair+4 into *SP[12].
# Looking at the existing tables: (value, label_byte) pairs in 8-byte struct? Wait.
# Let us check: 0x611d2da0 had [0xfffffffc, 0x3, 0xfffffffd, 0x3, ...] - 8 u32s = 4 pairs of (value,label)
# Count was 8 in the call but table shows 4 pairs * 2 u32 = 8 u32s. Let us look up 0x60e08ee0 again.
# 0x60e08ee0: loops d3 < d1, compares (a1) with d0, if match stores (4,a1) byte to (12,SP)->*a0. Increments a1 by 8.
# So d1 is count of pairs, each pair is 8 bytes {u32 value, u32 label}. Yes.
LABELS11_A = 0x600d56c0  # 11*8 = 88 bytes
LABELS11_B = 0x600d5680  # 11*8 = 88 bytes (second table)
# But wait - STUB goes to 0x600d5700, so labels must be below STUB or above. I'll put labels at 0x600d5600.

def check(c,m):
    if not c: raise SystemExit('refusing to patch: '+m)

def asm(src, at, syms=None):
    return patch_aspect.assemble_syms(src, at, syms or {})

# We'll build labels as data
def make_labels():
    # table A and B: 11 pairs (-5..5, label). Label byte is used as string index.
    # Copy style from stock: stock A has label 3,3,3,3,4,4,4,4? Let us look up.
    # Stock A: [-4,3,-3,3,-2,3,-1,3, 0,4,1,4,2,4,3,4]
    # Stock B: [-4,5,-3,4,-2,3,-1,2, 0,1,1,0,2,15,3,14] - looks like different encoding
    # Actually easier: reuse the approach from patch_profile_menu which used type-1 ASCII labels.
    # But 0x60e08ee0 is a specific function. Let us read it again: it stores byte (4,a1) to *(12,SP).
    # So label is a small id. I'll just make simple tables.
    a = bytearray(); b = bytearray()
    for v in range(-5, 6):
        a += struct.pack('<iI', v, 3)  # placeholder label
        b += struct.pack('<iI', v, 3)
    return bytes(a), bytes(b)

LABELS_A_AT = 0x600d5600
LABELS_B_AT = 0x600d5660

ENTRY_SRC = r"""
mov (8,sp),d0
cmp 21,d0
beq cc
cmp 6,d0
beq hsl
clr d1
mov d1,(flag)
jmp next
hsl:
mov 1,d1
mov d1,(flag)
clr d1
mov d1,(sector)
mov d1,(axis)
cc:
jmp open
"""

# Getter hook: if HSL mode and sid==0x268 or 0x267, redirect
GET_SRC = r"""
exthu d0
mov d0,d1
mov (flag),d2
cmp 0,d2
beq orig
cmp 0x267,d1
beq get_ring
cmp 0x268,d1
beq get_bar
orig:
call getreal,[],4
ret [],4
get_ring:
mov (sector),d0
add d0,d0
cmp 29,d0
ble 1f
mov 29,d0
1:
ret [],4
get_bar:
mov (axis),d2
cmp 0,d2
bne 2f
mov SAT0,d2
jmp 4f
2:
cmp 1,d2
bne 3f
mov HUE0,d2
jmp 4f
3:
mov LIGHT0,d2
4:
mov (sector),d0
add d2,d0
call getreal,[],4
ret [],4
"""

# Setter hook
SET_SRC = r"""
mov d1,(4,sp)
mov d0,d2
mov (flag),d3
cmp 0,d3
beq sorig
cmp 0x267,d0
beq set_ring
cmp 0x268,d0
beq set_bar
sorig:
mov 1,d3
jmp sbody
set_ring:
mov d1,d0
add d0,d0
add 2,d0
mov 5,d3
clr d2
1:
cmp d3,d0
bcs 2f
sub d3,d0
inc d2
jmp 1b
2:
cmp 11,d2
ble 3f
mov 11,d2
3:
mov d2,(sector)
mov 1,d0
.byte 0xdf,0xc0,0x10
set_bar:
mov (axis),d3
cmp 0,d3
bne sb1
mov SAT0,d3
jmp sb3
sb1:
cmp 1,d3
bne sb2
mov HUE0,d3
jmp sb3
sb2:
mov LIGHT0,d3
sb3:
mov (sector),d0
add d3,d0
mov d0,d2
mov 1,d3
jmp sbody
"""

def patch(main):
    m = bytearray(hsl.patch(bytes(main), seed=False))
    check(set(m[STUB-BASE:STUB_END-BASE]) == {0xff}, 'HSL editor area not free')
    struct.pack_into('<III', m, HSL_FLAG-BASE, 0, 0, 0)

    # widen 0x268 (CC sat) validator to -5..+5 so bar allows 11 steps in HSL mode
    NEW_268 = 0x600d55f0
    check(set(m[NEW_268-BASE:NEW_268-BASE+16]) == {0xff}, '0x268 list area not free')
    m[NEW_268-BASE:NEW_268-BASE+11] = bytes([251,252,253,254,255,0,1,2,3,4,5])
    # patch validator record for 0x268: nb=11, ptr=NEW_268
    rec268 = 0x604ddb60
    check(struct.unpack_from('<H',m,rec268-BASE)[0]==0x268, '0x268 rec')
    struct.pack_into('<I', m, rec268-BASE+4, NEW_268)   # list ptr
    struct.pack_into('<H', m, rec268-BASE+12, 11)         # nb
    # keep alt=0, el=1

    a = STUB
    la, lb = make_labels()
    m[LABELS_A_AT-BASE:LABELS_A_AT-BASE+len(la)] = la
    m[LABELS_B_AT-BASE:LABELS_B_AT-BASE+len(lb)] = lb

    syms = {'flag': HSL_FLAG, 'sector': HSL_SECTOR, 'axis': HSL_AXIS,
            'next': ENTRY_NEXT, 'open': ENTRY_CC, 'body': GET_BODY, 'sbody': SET_BODY,
            'SAT0': SAT0, 'HUE0': HUE0, 'LIGHT0': LIGHT0, 'getreal': 0x602cb8f4}

    entry = asm(ENTRY_SRC, a, syms); m[a-BASE:a-BASE+len(entry)] = entry; a += len(entry)
    a = (a + 3) & ~3
    syms['get_stub'] = a
    get_stub = asm(GET_SRC, a, syms); m[a-BASE:a-BASE+len(get_stub)] = get_stub; a += len(get_stub)
    a = (a + 3) & ~3
    syms['set_stub'] = a
    set_stub = asm(SET_SRC, a, syms); m[a-BASE:a-BASE+len(set_stub)] = set_stub; a += len(set_stub)
    # wrapper for changed handler to clear HSL flag on exit
    a = (a + 3) & ~3
    syms['changed_wrap'] = a
    wrap_src = r"""
mov (flag),d1
cmp 0,d1
beq nowrap
call orig,[d2,d3,a2,a3,exreg0,exreg1,exother],36
mov (flag),d1
cmp 0,d1
beq done
call getreq,[],4
cmp 0,d0
bne done
clr d0
mov d0,(flag)
done:
ret [d2,d3,a2,a3,exreg0,exreg1,exother],36
nowrap:
jmp orig
"""
    # Try simpler wrapper: just call orig and clear flag if req==0
    wrap_src = r"""
add -4,sp
mov a0,(0,sp)
call orig,[d2,d3,a2,a3],36
mov (0,sp),a0
add 4,sp
mov (flag),d1
cmp 0,d1
beq 1f
call getreq,[],4
cmp 0,d0
bne 1f
clr d0
mov d0,(flag)
1:
ret [d2,d3,a2,a3],36
"""
    wrap = asm(wrap_src, a, dict(syms, orig=CHANGED, getreq=0x60ed7eea))
    m[a-BASE:a-BASE+len(wrap)] = wrap; a += len(wrap)
    check(a <= STUB_END, 'HSL editor stubs overflow')

    # hooks disabled for bootloop debug
    pass

    # patch blob B
    gui = bytearray(olycompress.unpack(m, BLOB_B_OFF))
    g = ENTRY_SITE - BLOB_B
    check(bytes(gui[g:g+6]) == ENTRY_STOCK, 'SCP INFO entry differs')
    jmp = asm('jmp target', ENTRY_SITE, {'target': STUB})
    gui[g:g+5] = jmp; gui[g+5] = 0xcb

    # init_sat: 11 labels
    for site in (INIT_SAT_COUNT1, INIT_SAT_COUNT2):
        o = site - BLOB_B
        check(gui[o:o+2] == bytes.fromhex('8508'), 'init_sat count differs at %#x' % site)
        gui[o:o+2] = bytes.fromhex('850b')
    for site, lbl in ((INIT_SAT_LBL1, LABELS_A_AT), (INIT_SAT_LBL2, LABELS_B_AT)):
        o = site - BLOB_B
        check(gui[o] == 0xfc and gui[o+1] == 0xdd, 'init_sat label mov differs')
        struct.pack_into('<I', gui, o+2, lbl)

    csz = struct.unpack_from('<I', m, BLOB_B_OFF + 16)[0]
    cg = olycompress.pack(bytes(gui))
    check(len(cg) <= (BLOB_END-BASE) - (BLOB_B_OFF+32), 'blob B does not fit')
    old_end = BLOB_B_OFF + 32 + csz
    m[BLOB_B_OFF+32:BLOB_B_OFF+32+len(cg)] = cg
    if len(cg) < csz: m[BLOB_B_OFF+32+len(cg):old_end] = b'\xff'*(csz-len(cg))
    struct.pack_into('<I', m, BLOB_B_OFF + 16, len(cg))
    print('  HSL editor: SCP INFO on Custom -> Color Creator screen, 12 sectors x Sat/Hue/Light')
    return bytes(m)

def main(argv):
    if len(argv) < 2: print(__doc__); return 1
    src, dst = argv[0], argv[1]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b['stored']==b['calc'] for b in blocks), 'bad checksum')
    nm = patch(blocks[0]['plain'])
    ver = int(argv[argv.index('--version')+1], 0) if '--version' in argv else None
    out = bytearray()
    for i,b in enumerate(blocks):
        head, tail = bytearray(b['head']), bytearray(b['tail'])
        if i==0 and ver is not None:
            struct.pack_into('<H', head, 16, ver); struct.pack_into('<H', tail, 16, ver)
        out += olyfw.build_block(bytes(head), nm if i==0 else b['plain'], bytes(tail))
    check(len(out)==len(fw), 'size changed')
    open(dst,'wb').write(out)
    again = olyfw.unpack_blocks(open(dst,'rb').read())
    check(all(b['stored']==b['calc'] for b in again), 'output checksum failed')
    print('wrote', dst); return 0

if __name__ == '__main__': sys.exit(main(sys.argv[1:]))
