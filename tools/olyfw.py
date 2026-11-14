#!/usr/bin/env python3
"""
olyfw.py - unpack / repack Olympus (OM System) camera firmware .BIN files.

A cross-platform Python port of the block format, scrambling and checksum
logic from oly_fw_manip.exe (oly_fw_tools.zip), verified on E-M1 Mark III
firmware.

Commands:
  info   FW.BIN                 list the blocks and check their checksums
  unpack FW.BIN OUTDIR          write descrambled block bodies + manifest.json
  pack   OUTDIR NEW.BIN         rebuild a .BIN (rescramble, recompute checksums)
  verify FW.BIN                 unpack + repack in memory, check byte-identical

File layout:  <block><block>...  where  <block> = <head 32B><body><tail 32B>
Head/tail (little-endian, except the 2-char block type and big-endian model):
  0x00 2  block type ("OE" main CPU, "OM", "OA", "OL" ...)
  0x02 2  model id (big-endian, e.g. 0x1390 = E-M1 Mark III)
  0x04 4  unknown / zero
  0x08 4  loading address
  0x0C 4  body size
  0x10 2  version (BCD, e.g. 0x1500 = 1.5.0.0)
  0x14 2  flags (0x0000 = not scrambled, otherwise scrambled)
  0x1C 4  checksum (0 in head; in tail = -(sum of u32 words over
          head + DESCRAMBLED body + tail[0:28]))

!! A modified firmware can brick the camera. This tool only edits files;
!! it does not flash anything.
"""

import argparse
import hashlib
import json
import os
import struct
import sys
from array import array

HEAD_SIZE = 32

# descrambled[i] = scrambled[DESCRAMBLE[i]] ^ 0xFF, per 16-byte group
DESCRAMBLE = [1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15]
SCRAMBLE = [0] * 16
for _i, _p in enumerate(DESCRAMBLE):
    SCRAMBLE[_p] = _i

XOR_FF = bytes(b ^ 0xFF for b in range(256))

FLAG_NAMES = {
    0x0000: "code (plain)",
    0x0100: "code",
    0x0101: "text/fonts",
    0x0102: "images",
    0x0103: "sounds",
    0x0104: "images (overlay)",
    0x0105: "code (mju)",
    0x0106: "unknown",
}


def _shuffle(data, perm):
    if len(data) % 16:
        raise ValueError("data length must be a multiple of 16")
    out = bytearray(len(data))
    for j, p in enumerate(perm):
        out[j::16] = data[p::16]
    return bytes(out).translate(XOR_FF)


def descramble(data):
    return _shuffle(data, DESCRAMBLE)


def scramble(data):
    return _shuffle(data, SCRAMBLE)


def checksum(data):
    if len(data) % 4:
        raise ValueError("data length must be a multiple of 4")
    words = array("I")
    assert words.itemsize == 4
    words.frombytes(data)
    if sys.byteorder == "big":
        words.byteswap()
    return (-sum(words)) & 0xFFFFFFFF


def parse_head(h):
    return {
        "type": h[0:2].decode("latin-1"),
        "model": struct.unpack(">H", h[2:4])[0],
        "load_addr": struct.unpack("<I", h[8:12])[0],
        "size": struct.unpack("<I", h[12:16])[0],
        "version": struct.unpack("<H", h[16:18])[0],
        "flags": struct.unpack("<H", h[20:22])[0],
        "checksum": struct.unpack("<I", h[28:32])[0],
    }


def is_scrambled(flags):
    return flags != 0x0000  # same rule as oly_fw_manip.exe


def iter_blocks(fw):
    """Yield (offset, head_bytes, raw_body, tail_bytes, info)."""
    off = 0
    while off < len(fw):
        if off + 2 * HEAD_SIZE > len(fw):
            raise ValueError(f"truncated block at 0x{off:x}")
        head = fw[off:off + HEAD_SIZE]
        info = parse_head(head)
        size = info["size"]
        end = off + HEAD_SIZE + size + HEAD_SIZE
        if end > len(fw) or size % 16:
            raise ValueError(f"bad block size 0x{size:x} at 0x{off:x}")
        body = fw[off + HEAD_SIZE:off + HEAD_SIZE + size]
        tail = fw[end - HEAD_SIZE:end]
        yield off, head, body, tail, info
        off = end


def block_checksum(head, plain_body, tail):
    return checksum(head + plain_body + tail[:28])


def unpack_blocks(fw):
    blocks = []
    for off, head, body, tail, info in iter_blocks(fw):
        plain = descramble(body) if is_scrambled(info["flags"]) else bytes(body)
        stored = parse_head(tail)["checksum"]
        calc = block_checksum(head, plain, tail)
        blocks.append(dict(offset=off, head=bytes(head), tail=bytes(tail),
                           plain=plain, info=info, stored=stored, calc=calc))
    return blocks


def build_block(head, plain, tail):
    tail = bytearray(tail)
    tail[28:32] = struct.pack("<I", block_checksum(head, plain, tail))
    info = parse_head(head)
    body = scramble(plain) if is_scrambled(info["flags"]) else plain
    return head + body + bytes(tail)


def describe(info):
    return (f"{info['type']} model=0x{info['model']:04x} "
            f"load=0x{info['load_addr']:08x} size=0x{info['size']:08x} "
            f"ver=0x{info['version']:04x} flags=0x{info['flags']:04x} "
            f"({FLAG_NAMES.get(info['flags'], 'unknown')})")


def read(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data.startswith(b"version https://git-lfs"):
        sys.exit(f"{path} is a Git LFS pointer; run 'git lfs pull' first")
    return data


def cmd_info(args):
    fw = read(args.firmware)
    ok = True
    for i, b in enumerate(unpack_blocks(fw)):
        good = b["stored"] == b["calc"]
        ok &= good
        print(f"[{i}] @0x{b['offset']:08x} {describe(b['info'])} "
              f"checksum={'OK' if good else 'BAD'}")
    print(f"sha256 {hashlib.sha256(fw).hexdigest()}")
    return 0 if ok else 1


def cmd_unpack(args):
    fw = read(args.firmware)
    os.makedirs(args.outdir, exist_ok=True)
    manifest = {"source": os.path.basename(args.firmware),
                "source_sha256": hashlib.sha256(fw).hexdigest(),
                "blocks": []}
    for i, b in enumerate(unpack_blocks(fw)):
        info = b["info"]
        name = f"{i:02d}_{info['type']}_{info['load_addr']:08x}_f{info['flags']:04x}.bin"
        with open(os.path.join(args.outdir, name), "wb") as fh:
            fh.write(b["plain"])
        if b["stored"] != b["calc"]:
            print(f"warning: block {i} checksum mismatch", file=sys.stderr)
        manifest["blocks"].append({
            "file": name, "head": b["head"].hex(), "tail": b["tail"].hex(),
            "info": info, "body_sha256": hashlib.sha256(b["plain"]).hexdigest(),
        })
        print(f"[{i}] {describe(info)} -> {name}")
    with open(os.path.join(args.outdir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return 0


def cmd_pack(args):
    with open(os.path.join(args.indir, "manifest.json")) as fh:
        manifest = json.load(fh)
    out = bytearray()
    for i, m in enumerate(manifest["blocks"]):
        head, tail = bytes.fromhex(m["head"]), bytes.fromhex(m["tail"])
        with open(os.path.join(args.indir, m["file"]), "rb") as fh:
            plain = fh.read()
        if len(plain) != m["info"]["size"]:
            sys.exit(f"block {i} ({m['file']}): size changed from "
                     f"0x{m['info']['size']:x} to 0x{len(plain):x}; "
                     "patches must keep the block size")
        changed = hashlib.sha256(plain).hexdigest() != m["body_sha256"]
        print(f"[{i}] {m['file']}{'  (MODIFIED)' if changed else ''}")
        out += build_block(head, plain, tail)
    with open(args.output, "wb") as fh:
        fh.write(out)
    print(f"wrote {args.output} ({len(out)} bytes) "
          f"sha256 {hashlib.sha256(out).hexdigest()}")
    return 0


def cmd_verify(args):
    fw = read(args.firmware)
    rebuilt = b"".join(build_block(b["head"], b["plain"], b["tail"])
                       for b in unpack_blocks(fw))
    if rebuilt == fw:
        print("round trip OK: rebuilt file is byte-identical")
        return 0
    first = next(i for i, (x, y) in enumerate(zip(rebuilt, fw)) if x != y) \
        if len(rebuilt) == len(fw) else min(len(rebuilt), len(fw))
    print(f"round trip FAILED: first difference at 0x{first:x}")
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("firmware"); s.set_defaults(fn=cmd_info)
    s = sub.add_parser("unpack"); s.add_argument("firmware"); s.add_argument("outdir")
    s.set_defaults(fn=cmd_unpack)
    s = sub.add_parser("pack"); s.add_argument("indir"); s.add_argument("output")
    s.set_defaults(fn=cmd_pack)
    s = sub.add_parser("verify"); s.add_argument("firmware"); s.set_defaults(fn=cmd_verify)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
