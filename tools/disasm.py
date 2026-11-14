#!/usr/bin/env python3
"""
disasm.py - disassemble MN103 (MN1030/AM30-family) code from an unpacked
Olympus firmware block.

  python3 tools/disasm.py BLOCK.bin START [COUNT] [--base 0x60021020]
  python3 tools/disasm.py BLOCK.bin --xref 0x601fa1c3 [--base ...]

START is a runtime address. The E-M1 Mark III main code block
(00_OE_40800000_f0100.bin) runs at 0x60021020 (same as E-M1 II / PEN-F).

The opcode table (tools/mn103/table.json) is generated from the MN1030
instruction manual in this repo by tools/mn103/build_table.py; several typos in
the manual's summary tables are corrected in tools/mn103/mn103.py.
Disassembly is a linear sweep, so data between functions decodes as junk.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mn103"))
import mn103  # noqa: E402


def sweep(code, base, start=0, end=None):
    off, end = start, len(code) if end is None else end
    while off < end:
        d = mn103.decode(code, off, base + off)
        if d is None:
            yield base + off, code[off:off + 1], None, None
            off += 1
        else:
            yield base + off, code[off:off + d[0]], d[1], d[2]
            off += d[0]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("block")
    p.add_argument("start", nargs="?", type=lambda s: int(s, 0))
    p.add_argument("count", nargs="?", type=int, default=40)
    p.add_argument("--base", type=lambda s: int(s, 0), default=0x60021020)
    p.add_argument("--xref", type=lambda s: int(s, 0),
                   help="list instructions that use this address as immediate/call target")
    a = p.parse_args()
    code = open(a.block, "rb").read()
    if a.xref is not None:
        needle = "0x%x" % a.xref
        for addr, raw, txt, info in sweep(code, a.base):
            if txt and (info.get("target") == a.xref or
                        any(t.strip("(),") == needle for t in txt.replace(",", " ").split())):
                print("%08x  %-22s %s" % (addr, raw.hex(" "), txt))
        return 0
    if a.start is None:
        p.error("START or --xref required")
    n = 0
    for addr, raw, txt, _ in sweep(code, a.base, a.start - a.base):
        print("%08x  %-22s %s" % (addr, raw.hex(" "), txt or "??"))
        n += 1
        if n >= a.count:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
