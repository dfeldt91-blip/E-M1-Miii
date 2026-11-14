#!/usr/bin/env python3
"""
olycompress.py - decode Olympus "olycompress" blobs (E-M1 Mark III firmware).

Format (found in this firmware):
  +0x00  16 bytes  "olycompress" padded with spaces
  +0x10  u32 LE    compressed size (bytes after the 32-byte header)
  +0x14  u32 LE    uncompressed size
  +0x18  8 bytes   zero
  +0x20  ...       raw LZ4 block (no frame header)

In the main code block the blobs are unpacked IN PLACE at their own runtime
address (header address): on the E-M1 III 1.5-based image
  0x60803000 -> 0x469000 bytes, 0x60c6c000 -> 0x685000 bytes,
filling the 0xff-padded space reserved after them. These hold the GUI/OSD code.

Commands:
  list    BLOCK.bin                    find olycompress headers
  unpack  BLOCK.bin OFFSET OUT.bin     decode one blob (OFFSET = block offset)
  runtime MAIN.bin OUT.bin [BASE]      main block with every blob unpacked in place
                                       (BASE = runtime address of offset 0,
                                        default 0x60021020)
"""
import re
import struct
import sys

MAGIC = b"olycompress"


def lz4_block(src):
    i, out, n = 0, bytearray(), len(src)
    while i < n:
        tok = src[i]
        i += 1
        ll = tok >> 4
        if ll == 15:
            while True:
                x = src[i]
                i += 1
                ll += x
                if x != 255:
                    break
        out += src[i:i + ll]
        i += ll
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        if off == 0 or off > len(out):
            raise ValueError("bad match offset %d at input %#x" % (off, i))
        ml = tok & 15
        if ml == 15:
            while True:
                x = src[i]
                i += 1
                ml += x
                if x != 255:
                    break
        ml += 4
        s = len(out) - off
        if off >= ml:
            out += out[s:s + ml]
        else:
            for k in range(ml):
                out.append(out[s + k])
    return bytes(out)


def pack(raw):
    """LZ4 HC level 12 raw block: reproduces the stock blobs byte for byte."""
    import lz4.block
    return lz4.block.compress(raw, mode="high_compression", compression=12, store_size=False)


def headers(data):
    for m in re.finditer(re.escape(MAGIC), data):
        o = m.start()
        csz, usz = struct.unpack_from("<II", data, o + 16)
        if o + 32 + csz <= len(data):
            yield o, csz, usz


def unpack(data, o):
    csz, usz = struct.unpack_from("<II", data, o + 16)
    out = lz4_block(data[o + 32:o + 32 + csz])
    if len(out) != usz:
        raise ValueError("size mismatch: got %#x, header says %#x" % (len(out), usz))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[0]
    data = open(argv[1], "rb").read()
    if cmd == "list":
        for o, csz, usz in headers(data):
            print("offset %#09x  compressed %#x  uncompressed %#x" % (o, csz, usz))
    elif cmd == "unpack":
        out = unpack(data, int(argv[2], 0))
        open(argv[3], "wb").write(out)
        print("wrote %s (%#x bytes)" % (argv[3], len(out)))
    elif cmd == "runtime":
        img = bytearray(data)
        for o, csz, usz in list(headers(data)):
            out = unpack(data, o)
            if o + len(out) > len(img):
                raise ValueError("blob at %#x unpacks past the end of the block" % o)
            img[o:o + len(out)] = out
            print("unpacked %#x: %#x -> %#x bytes" % (o, csz, usz))
        open(argv[2], "wb").write(img)
        print("wrote", argv[2])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
