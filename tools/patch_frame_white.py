#!/usr/bin/env python3
"""Art Effect "Frame" -> plain rectangular border (EXPERIMENTAL, E-M1 Mark III 1.5 / 1.6).

  python3 tools/patch_frame_white.py IN.BIN OUT.BIN --no-white --layer0-white [--panorama] [--width-pct 3]
                                    [--version 0x1665]

The Frame effect (Art Effect 3, job flag 0x8000) blends two mask layers. They are JPEGs in block 2
(identical in 1.5 and 1.6), each after a 64-byte header {7-byte date, u8 aspect W, u8 aspect H,
u8 layer, zeros}; no size is stored, the JPEG runs to its EOI and is followed by zero padding:
  layer 0: black inside, white ragged "film" edge (the grungy look)
  layer 1: white inside, hard black band (~2.2 % of the short side)
13 pairs: full size 3:2 3:4 4:3 1:1 16:9, live view 640x480 1280x720 1920x1080, and 1024x688 576x768
1024x768 768x768 1024x576. Each image is redrawn as the same clean rectangle: layer 0 white band /
black inside, layer 1 black band / white inside, band = WIDTH % of the short side rounded to the
16x8 JPEG block grid (so the edges stay exact). Same size, baseline 4:2:2, same quantisation tables.

--layer1-white: layer 1 all white instead of the band. Camera 1.661 (both layers as bands + mode 0x500):
white shows, but as a "transparent T" with white at the top and lower left/right, so 0x500 reads
Frame's two-layer setup differently. Stock reading (mode 0x300): layer 1 = colour (black band), layer 0 =
how much of it (the ragged rim). So 1.663 keeps 0x300 (--no-white) and makes layer 1 all white.
Camera 1.663: no frame at all. So with 0x300 layer 1 is WHERE (black = frame, white = photo) and layer 0
is WHAT is painted there (stock: white ragged rim fading to black inside the band).
--layer0-white: layer 0 all white, layer 1 the clean black band (1.664) -> white band of WIDTH %.
Camera 1.664: clean white border in every aspect except Panorama (wrong frame in the SCP, nothing in
live view, freeze on the shot): see --panorama below.

Colour: the stage setup 0x6038873b gives Frame blend mode 0x300; White Edge uses 0x500 (toward
white). Unless --no-white, both Frame paths get 0x500 (0x60388777 and 0x603887ae, same in 1.6).
"""
import hashlib
import io
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
MODE_SITES = [0x60388777, 0x603887ae]
MODE_STOCK, MODE_WHITE = bytes.fromhex("2c0003"), bytes.fromhex("2c0005")
# (block 2 offset of the JPEG, width, height, aspect W, aspect H, layer)
IMAGES = [
    (0x240820, 5184, 3456, 3, 2, 0), (0x2f5c20, 5184, 3456, 3, 2, 1),
    (0x356c20, 2912, 3888, 3, 4, 0), (0x3d4820, 2912, 3888, 3, 4, 1),
    (0x413820, 5184, 3888, 4, 3, 0), (0x4e4620, 5184, 3888, 4, 3, 1),
    (0x54a820, 3888, 3888, 6, 6, 0), (0x5ee020, 3888, 3888, 6, 6, 1),
    (0x63d420, 5184, 2920, 16, 9, 0), (0x6e8620, 5184, 2920, 16, 9, 1),
    (0x73a420, 640, 480, 4, 3, 0), (0x740c20, 640, 480, 4, 3, 1),
    (0x743e20, 1280, 720, 16, 9, 0), (0x755020, 1280, 720, 16, 9, 1),
    (0x75be20, 1920, 1080, 16, 9, 0), (0x77b220, 1920, 1080, 16, 9, 1),
    (0x789220, 1024, 688, 3, 2, 0), (0x797820, 1024, 688, 3, 2, 1),
    (0x79d020, 576, 768, 3, 4, 0), (0x7a6220, 576, 768, 3, 4, 1),
    (0x7aa620, 1024, 768, 4, 3, 0), (0x7b7a20, 1024, 768, 4, 3, 1),
    (0x7be220, 768, 768, 6, 6, 0), (0x7c9e20, 768, 768, 6, 6, 1),
    (0x7cea20, 1024, 576, 16, 9, 0), (0x7dc220, 1024, 576, 16, 9, 1),
]


LOG = print          # the mod builder points this at its own log


def check(cond, msg):
    if not cond:
        sys.exit("refusing to patch: " + msg)


def jpeg_len(d, s):
    """Length of the JPEG at S up to and including EOI (walks the markers, then the scan)."""
    i = s + 2
    while True:
        check(d[i] == 0xff, "bad JPEG marker at %#x" % i)
        m, ln = d[i + 1], struct.unpack(">H", d[i + 2:i + 4])[0]
        i += 2 + ln
        if m == 0xda:
            break
    while True:
        i = d.index(b"\xff", i)
        if d[i + 1] == 0xd9:
            return i + 2 - s
        i += 2 if d[i + 1] in (0x00,) or 0xd0 <= d[i + 1] <= 0xd7 else 1


def sof(d, s):
    i = s + 2
    while True:
        m, ln = d[i + 1], struct.unpack(">H", d[i + 2:i + 4])[0]
        if m == 0xc0:
            seg = d[i + 4:i + 2 + ln]
            h, w = struct.unpack(">HH", seg[1:5])
            comps = [(seg[6 + 3 * k], seg[7 + 3 * k], seg[8 + 3 * k]) for k in range(seg[5])]
            return w, h, comps
        check(m != 0xda, "no baseline SOF0")
        i += 2 + ln


def band(w, h, pct):
    b = max(16, int(round(min(w, h) * pct / 100.0 / 16.0)) * 16)
    return b


def colours(layer, fill):
    """(inside, band) grey levels of LAYER; FILL = 'l1' (layer 1 all white) or 'l0' (layer 0 all white)."""
    if layer == 0:
        return (255, 255) if fill == "l0" else (0, 255)
    return (255, 255) if fill == "l1" else (255, 0)


def render(orig, w, h, layer, pct, fill=None, b=None):
    from PIL import Image, ImageDraw
    src = Image.open(io.BytesIO(orig))
    b = band(w, h, pct) if b is None else b
    inner, edge = colours(layer, fill)
    im = Image.new("L", (w, h), edge)
    ImageDraw.Draw(im).rectangle((b, b, w - b - 1, h - b - 1), fill=inner)
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", qtables=src.quantization, subsampling=1, optimize=False,
                           progressive=False)
    return out.getvalue(), b


def is_clean(jpg, w, h, b, inner, edge):
    """The decoded JPEG equals the intended band image within 2 grey levels."""
    from PIL import Image, ImageChops, ImageDraw
    want = Image.new("L", (w, h), edge)
    ImageDraw.Draw(want).rectangle((b, b, w - b - 1, h - b - 1), fill=inner)
    got = Image.open(io.BytesIO(jpg)).convert("L")
    return got.size == (w, h) and ImageChops.difference(got, want).getextrema()[1] <= 2


def patch_images(blk2, pct, fill=None):
    d = bytearray(blk2)
    for off, w, h, aw, ah, layer in IMAGES:
        hdr = bytes(d[off - 0x40:off - 0x30])
        check(hdr[7:11] == bytes([aw, ah, layer, 0]) and hdr[0] in (0xdb, 0xdd, 0xdf) and hdr[1] == 0x07,
              "image header at %#x differs" % off)
        n = jpeg_len(d, off)
        sw, sh, comps = sof(d, off)
        check((sw, sh) == (w, h) and comps == [(1, 0x21, 0), (2, 0x11, 1), (3, 0x11, 1)],
              "image at %#x is not %dx%d 4:2:2" % (off, w, h))
        pad = d[off + n:off + n + 4]
        check(set(pad) == {0}, "no zero padding after the image at %#x" % off)
        new, b = render(bytes(d[off:off + n]), w, h, layer, pct, fill)
        check(len(new) <= n, "new image at %#x is larger than the old one" % off)
        check(is_clean(new, w, h, b, *colours(layer, fill)), "re-encoded image at %#x is not clean" % off)
        d[off:off + n] = new + bytes(n - len(new))
        LOG("  %dx%d %d:%d layer %d: band %d px, %d -> %d bytes" % (w, h, aw, ah, layer, b, n, len(new)))
    return bytes(d)


# --- Panorama (aspect id 6, the old 7:6 slot): no Frame masks in stock -> freeze. The mask lookup
# 0x6039ba66 reads the per-aspect row at 0x6052e0b0 + 12 * id: {u16 full layer 0, full layer 1,
# preview layer 0, preview layer 1, preview w, preview h} (resource numbers in the block 2 archive;
# 0xffff = none). The archive (header 0x3e0, directory 0x400: {u32 flash address of the 64-byte image
# header, u32 size}, 40 entries, 64 slots) has 6.8 MB of zeros after its last entry (0x880de0).
# --panorama adds entries 40-43 (5184x1920 and 1024x384, layers 0/1) there and fills row 6.
ROWS, PAN_ROW = 0x6052e0b0, 6
DIR, ARCH_FLASH, FREE_LO, FREE_HI = 0x400, 0x43f00020, 0x880de0, 0xefffc0
PAN_IMAGES = [(5184, 1920, 0), (5184, 1920, 1), (1024, 384, 0), (1024, 384, 1)]


def panorama_images(blk2, pct, fill):
    d = bytearray(blk2)
    n = 0
    while struct.unpack_from("<II", d, DIR + 16 * n) != (0, 0):
        n += 1
    check(n == 40 and set(d[DIR + 16 * n:DIR + 16 * (n + 4)]) == {0}, "archive directory differs")
    last_a, last_s = struct.unpack_from("<II", d, DIR + 16 * (n - 1))
    check(last_a - ARCH_FLASH + last_s == FREE_LO and set(d[FREE_LO:FREE_LO + 0x100000]) == {0},
          "archive free space differs")
    src = bytes(d[0x63d420:0x63d420 + jpeg_len(d, 0x63d420)])      # 16:9 layer 0: quantisation tables
    hdr = bytes(d[0x63d3e0:0x63d420])
    at, ids = FREE_LO, []
    for k, (w, h, layer) in enumerate(PAN_IMAGES):
        b = band(w, w * 9 // 16, pct)                                # same band as 16:9 at this width
        jpg, _ = render(src, w, h, layer, 0, fill, b)
        check(is_clean(jpg, w, h, b, *colours(layer, fill)), "Panorama image %dx%d is not clean" % (w, h))
        blob = hdr[:7] + bytes([65, 24, layer]) + hdr[10:] + jpg
        size = (len(blob) + 0x1ff) & ~0x1ff
        check(at + size <= FREE_HI, "archive full")
        d[at:at + len(blob)] = blob
        struct.pack_into("<II", d, DIR + 16 * (n + k), ARCH_FLASH + at, size)
        ids.append(n + k)
        LOG("  Panorama %dx%d layer %d: entry %d at %#x, band %d px, %d bytes" % (w, h, layer, n + k, at, b, len(jpg)))
        at += size
    return bytes(d), ids


def panorama_row(main, ids):
    m = bytearray(main)
    o = ROWS + 12 * PAN_ROW - BASE
    check(struct.unpack_from("<6H", m, o) == (0xffff,) * 4 + (0, 0), "Frame mask row for aspect 6 differs")
    struct.pack_into("<6H", m, o, *ids, 1024, 384)
    LOG("  Frame mask row %d -> entries %s" % (PAN_ROW, ids))
    return bytes(m)


def patch_main(main):
    m = bytearray(main)
    for a in MODE_SITES:
        o = a - BASE
        check(bytes(m[o:o + 3]) == MODE_STOCK, "Frame blend mode at %#x differs" % a)
        m[o:o + 3] = MODE_WHITE
    print("  Frame blend mode 0x300 -> 0x500 (White Edge's) at %s" % ", ".join("%#x" % a for a in MODE_SITES))
    return bytes(m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src, dst = argv[0], argv[1]
    pct = float(argv[argv.index("--width-pct") + 1]) if "--width-pct" in argv else 3.0
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    plains = [b["plain"] for b in blocks]
    fill = "l1" if "--layer1-white" in argv else "l0" if "--layer0-white" in argv else None
    plains[2] = patch_images(plains[2], pct, fill)
    if "--panorama" in argv:
        plains[2], ids = panorama_images(plains[2], pct, fill)
        plains[0] = panorama_row(plains[0], ids)
    if "--no-white" not in argv:
        plains[0] = patch_main(plains[0])
    ver = int(argv[argv.index("--version") + 1], 0) if "--version" in argv else None
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tail = bytearray(b["head"]), bytearray(b["tail"])
        if i == 0 and ver is not None:
            struct.pack_into("<H", head, 16, ver)
            struct.pack_into("<H", tail, 16, ver)
        out += olyfw.build_block(bytes(head), plains[i], bytes(tail))
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
