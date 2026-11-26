#!/usr/bin/env python3
"""Dissect the art filters' image parameters (E-M1 Mark III 1.6). Read-only.

  python3 tools/art_filter_dump.py FIRMWARE.BIN OUT.md [CURVES.png]

Reads the main block of a firmware file (stock or modded; only the base section is used, no
blob decompression) and writes a per-filter report of every parameter stage mapped so far
(docs/ART_FILTERS.md explains the stages). Each mapping below was taken from the code; the tool
checks that every table address still occurs as an immediate inside the handler it came from,
so a different firmware version fails loudly instead of printing wrong data.

Job keys: the image pipeline tags each job 0x01VV00MM, MM = picture-mode code (art filters
0x64-0x6d, 0x77-0x7c), VV = variant (1 = I, 2 = II, 3 = III).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olyfw  # noqa: E402

BASE = 0x60021020
FILTERS = [  # (code, name, variants), menu order; codes from the Picture Mode list 0x604bc4f4
    (0x64, "Pop Art", 2), (0x65, "Soft Focus", 1), (0x66, "Pale & Light Color", 2),
    (0x67, "Light Tone", 1), (0x68, "Grainy Film", 2), (0x69, "Pin Hole", 3),
    (0x6a, "Diorama", 2), (0x6b, "Cross Process", 2), (0x6c, "Gentle Sepia", 1),
    (0x6d, "Dramatic Tone", 2), (0x77, "Key Line", 2), (0x78, "Watercolor", 2),
    (0x79, "Vintage", 3), (0x7a, "Partial Color", 3), (0x7b, "Bleach Bypass", 2),
    (0x7c, "Instant Film", 1),
]
ROMAN = {1: "I", 2: "II", 3: "III"}

# --- stage A: colour parameters, 2 x 6 s16 -> request +100..+123 (switch 0x603dd128, table
# 0x6053d884; key not offset). (handler, first table, second table); None = default
# 0x6051b032 / 0x6051b03e (normal picture modes); "zero" = 0x603dd0aa clears all 12.
A_DEFAULT = (0x6051b032, 0x6051b03e)
A = {
    (0x64, 1): (0x603dd239, 0x6051b0f2, 0x6051b0fe), (0x64, 2): (0x603dd286, 0x6051b1b2, 0x6051b1be),
    (0x65, 1): (0x603dd22a, 0x6051b0da, 0x6051b0e6),
    (0x66, 1): (0x603dd248, 0x6051b13a, 0x6051b146), (0x66, 2): (0x603dd277, 0x6051b19a, 0x6051b1a6),
    (0x67, 1): (0x603dd257, 0x6051b152, 0x6051b15e),
    (0x69, 1): (0x603dd295, 0x6051b16a, 0x6051b176), (0x69, 2): (0x603dd295, 0x6051b16a, 0x6051b176),
    (0x69, 3): (0x603dd295, 0x6051b16a, 0x6051b176),
    (0x6a, 1): (0x603dd268, 0x6051b182, 0x6051b18e), (0x6a, 2): (0x603dd268, 0x6051b182, 0x6051b18e),
    (0x6d, 1): "zero", (0x6d, 2): "zero",
    (0x78, 1): (0x603dd2ca, 0x6051b23a, 0x6051b246), (0x78, 2): (0x603dd2ca, 0x6051b23a, 0x6051b246),
    (0x79, 2): (0x603dd2dc, 0x6051b252, 0x6051b25e),
}

# --- stage B: contrast / tone curve, 256 x u16 (0..1023) (selector 0x603df05c, switch
# 0x603df193 on key - 11). Normal modes: one of five curves by the Contrast setting.
# "cond" = depends on the job (see doc); value = curve.
B_IDENTITY = 0x60508f06
B = {
    (0x64, 1): (0x603df232, 0x6050b566), (0x64, 2): (0x603df29c, 0x6050c9a2),
    (0x65, 1): (0x603df229, 0x6050b306),
    (0x66, 1): (0x603df23b, 0x6050b7a2), (0x66, 2): (0x603df293, 0x6050c7a2),
    (0x67, 1): (0x603df244, 0x6050b9a2),
    (0x68, 1): (0x603df256, 0x6050eba2), (0x68, 2): (0x603df2ae, 0x6050eda2),
    (0x69, 1): (0x603df24d, 0x6050bba2), (0x69, 2): (0x603df2a5, 0x6050cba2),
    (0x69, 3): (0x603df2a5, 0x6050cba2),
    (0x6a, 1): (0x603df26f, 0x6050bfa2), (0x6a, 2): (0x603df26f, 0x6050bfa2),
    (0x6b, 1): (0x603df278, 0x6050c1a2), (0x6b, 2): (0x603df2ec, 0x6050dfa2),
    (0x6c, 1): (0x603df28a, 0x6050c5a2),
    (0x6d, 1): (0x603df2c7, 0x6050cfa2), (0x6d, 2): (0x603df2c7, 0x6050cfa2),
    (0x77, 1): (0x603df2dc, "cond"), (0x77, 2): (0x603df2dc, "cond"),
    (0x78, 1): (0x603df2f5, "cond"), (0x78, 2): (0x603df319, "cond"),
    (0x79, 1): (0x603df34a, 0x6050e1a2), (0x79, 2): (0x603df353, 0x6050e3a2),
    (0x79, 3): (0x603df35c, 0x6050e5a2),
    (0x7a, 1): (0x603df365, None), (0x7a, 2): (0x603df368, None), (0x7a, 3): (0x603df36b, None),
    (0x7b, 1): (0x603df36e, 0x6050e7a2), (0x7b, 2): (0x603df377, None),
    (0x7c, 1): (0x603df37a, 0x6050e9a2),
}
# conditions on the curve (job fields: +14 & 0xf00 = sub-mode, (4,job)->+12 = pass code)
B_NOTE = {
    0x68: "only when job +14 & 0xf00 == 0x100; otherwise the normal Contrast path",
    0x77: "pass 0x501: flat 1023 table 0x6053d3b4 (all white, line pass) + flag; other passes: normal path",
    0x78: "pass 0x601 or sub-mode 0x100/0x40: identity; otherwise flat 1023 table 0x6053d3b4 + flag",
    0x7c: "only in pass 0x0b00 (clips at 1/4 input: not the main tone curve); other passes: normal path",
}

# --- stage C: 3x3 colour matrix, s16, 256 = 1.0 (0x603dbf28). Only Pop Art has its own.
C = {(0x64, 1): (0x603dbf6e, 0x6051affc), (0x64, 2): (0x603dbf6e, 0x6051affc)}

# --- stage D: 13-pointer record, first pointer -> request +16 coefficient block
# (0x603de54d, switch 0x603de57d; key not offset). Default record 0x6053cac8.
D_DEFAULT = 0x6053cac8
D = {
    (0x6b, 2): (0x603de6e2, 0x6053d1e4), (0x6d, 1): (0x603de6cd, 0x6053d17c),
    (0x6d, 2): (0x603de6cd, 0x6053d17c),
    (0x78, 1): (0x603de6eb, 0x6053d218), (0x78, 2): (0x603de6f4, 0x6053d24c),
    (0x7a, 1): (0x603de6fd, 0x6053d280), (0x7a, 2): (0x603de706, 0x6053d2b4),
    (0x7a, 3): (0x603de70f, 0x6053d2e8),
    (0x7b, 2): (0x603de718, 0x6053d31c), (0x7c, 1): (0x603de721, 0x6053d350),
}

# --- stage E: 100-byte register record (switch 0x603d88b1 on key - 8). Default for
# unlisted keys: none (stock path). Shared records: 0x604f8f32, 0x604f8ece.
E = {
    (0x64, 1): (0x603d88e3, 0x604f8f96), (0x64, 2): (0x603d88ff, 0x604f9252),
    (0x66, 1): (0x603d88ec, 0x604f91ee), (0x69, 3): (0x603d890a, 0x604f8f32),
}
for k in [(0x65, 1), (0x67, 1), (0x66, 2), (0x69, 1), (0x69, 2), (0x6a, 1), (0x6a, 2), (0x6b, 1), (0x6b, 2)]:
    E[k] = (0x603d8919, 0x604f8f32)
for k in [(0x78, 1), (0x78, 2), (0x79, 1), (0x79, 2), (0x79, 3), (0x7a, 1), (0x7a, 2), (0x7a, 3),
          (0x7b, 1), (0x7b, 2), (0x7c, 1)]:
    E[k] = (0x603d8922, 0x604f8ece)

# --- stage F: coarse legacy hints about extra processing modules. The dispatch is now
# decoded in docs/ART_FILTER_CHAIN.md; these strings predate the two-table dispatch and
# should not be treated as definitive per-variant module lists.
F = {
    0x64: "0x60386fc2 (also Diorama), 0x60383c5b", 0x68: "0x60383d99 ... 0x603839fd 0x60388169 0x60388295 0x60388384 0x60383a1f",
    0x6a: "0x6038619b 0x60384353 ... 0x6038605d", 0x6c: "0x60386442 0x6038655b (short chain)",
    0x6d: "0x6038621c 0x60386283", 0x77: "0x603867f7 0x60386a81 0x60386d77 0x6038685b 0x6038696b 0x60386bab ... 0x60386d06",
    0x78: "0x60387606 0x60387716 0x6038781d ... 0x60387978", 0x79: "0x60388596 (short chain)",
    0x7b: "I: 0x60385b6b (short chain); II: shared + 0x603870db", 0x7c: "0x60387a4c ... 0x60387c2a",
}


def check(cond, msg):
    if not cond:
        sys.exit("art_filter_dump: " + msg)


class Img:
    def __init__(self, main):
        self.m = main

    def raw(self, a, n):
        return self.m[a - BASE:a - BASE + n]

    def h(self, a, n):
        return list(struct.unpack_from("<%dh" % n, self.m, a - BASE))

    def uh(self, a, n):
        return list(struct.unpack_from("<%dH" % n, self.m, a - BASE))

    def has_imm(self, handler, value, span=0x30):
        return struct.pack("<I", value) in self.raw(handler, span)


def verify(img):
    n = 0
    for tab in (A, B, C, D, E):
        for k, v in tab.items():
            if not isinstance(v, tuple):
                continue
            handler, *vals = v
            for x in vals:
                if isinstance(x, int):
                    check(img.has_imm(handler, x), "table %#x not loaded at %#x (%s)" % (x, handler, k))
                    n += 1
    return n


def curve_summary(c):
    pts = [c[i] for i in (0, 32, 64, 96, 128, 160, 192, 224, 255)]
    return " ".join("%4d" % p for p in pts)


def report(img, png=None):
    out = []
    w = out.append
    w("# Art filter parameters (E-M1 Mark III 1.6), generated by tools/art_filter_dump.py\n")
    w("Curves: 256 points, output 0..1023; shown at inputs 0, 32, ..., 224, 255 "
      "(identity = 0 128 257 385 514 642 770 899 1023).\n")
    curves = {}
    for code, name, nv in FILTERS:
        for v in range(1, nv + 1):
            k = (code, v)
            title = "%s %s" % (name, ROMAN[v]) if nv > 1 else name
            w("\n## %s  (job key 0x01%02x00%02x)\n" % (title, v, code))
            a = A.get(k)
            if a == "zero":
                w("- Colour parameters (req +100): all 12 cleared (0x603dd0aa)")
            else:
                t1, t2 = (a[1], a[2]) if a else A_DEFAULT
                w("- Colour parameters (req +100): A %s @%#x, B %s @%#x%s" %
                  (img.h(t1, 6), t1, img.h(t2, 6), t2, "" if a else "  (default)"))
            b = B.get(k)
            note = ("  [" + B_NOTE[code] + "]") if code in B_NOTE else ""
            if b is None:
                w("- Tone curve: normal path (Contrast setting)")
            elif b[1] == "cond":
                w("- Tone curve: conditional (handler %#x)%s" % (b[0], note))
            elif b[1] is None:
                w("- Tone curve: identity %#x (no curve)" % B_IDENTITY)
            else:
                c = img.uh(b[1], 256)
                if code != 0x7c:
                    curves[title] = c
                w("- Tone curve @%#x: %s%s" % (b[1], curve_summary(c), note))
            c = C.get(k)
            if c:
                mx = img.h(c[1], 9)
                w("- Colour matrix @%#x (/256): %s %s %s" % (c[1], mx[0:3], mx[3:6], mx[6:9]))
            else:
                w("- Colour matrix: base only")
            dd = D.get(k)
            rec = dd[1] if dd else D_DEFAULT
            p0 = struct.unpack_from("<I", img.m, rec - BASE)[0]
            w("- Coefficient record @%#x -> block @%#x%s" % (rec, p0, "" if dd else " (default)"))
            e = E.get(k)
            w("- Register record (100 B): %s" % ("@%#x" % e[1] if e else "none / stock"))
            if code in F:
                w("- Extra modules: %s" % F[code])
    if png:
        draw(curves, png)
    return "\n".join(out) + "\n"


def draw(curves, path):
    from PIL import Image, ImageDraw
    cols = 4
    names = list(curves)
    rows = (len(names) + cols - 1) // cols
    cw, ch, pad = 260, 230, 24
    im = Image.new("RGB", (cols * cw, rows * ch), "white")
    dr = ImageDraw.Draw(im)
    for i, n in enumerate(names):
        x0, y0 = (i % cols) * cw + pad, (i // cols) * ch + pad
        s = cw - 2 * pad
        dr.rectangle([x0, y0, x0 + s, y0 + s - 20], outline=(180, 180, 180))
        dr.line([x0, y0 + s - 20, x0 + s, y0], fill=(210, 210, 210))
        c = curves[n]
        pts = [(x0 + j * s / 255, y0 + (s - 20) - c[j] * (s - 20) / 1023) for j in range(256)]
        dr.line(pts, fill=(30, 90, 200), width=2)
        dr.text((x0, y0 + s - 14), n, fill=(0, 0, 0))
    im.save(path)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    blocks = olyfw.unpack_blocks(olyfw.read(argv[0]))
    img = Img(blocks[0]["plain"])
    n = verify(img)
    md = report(img, argv[2] if len(argv) > 2 else None)
    open(argv[1], "w").write(md)
    print("verified %d table references; wrote %s" % (n, argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
