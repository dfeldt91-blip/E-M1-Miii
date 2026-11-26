#!/usr/bin/env python3
"""Probe and edit the built-in Art Filters (E-M1 Mark III, firmware 1.6 BASE).

  python3 tools/patch_art_styles.py FIRMWARE.BIN --probe
  python3 tools/patch_art_styles.py FIRMWARE.BIN --modules
  python3 tools/patch_art_styles.py FIRMWARE.BIN OUT.BIN STYLES.json [--version 0x1622]

Read-only probe mode prints every mapped table for every art filter, including which
filters share a table (so an edit would affect all of them). `--modules` prints the
decoded chain-module roles and handler xrefs.

Edit mode applies the proven, safe parts of the art-filter system:
  * 256-point tone curve (512 bytes, 0..1023)
  * the two 6 x s16 colour-parameter tables written to request +100..+123
  * Pop Art's 3 x 3 s16 colour matrix (/256)
  * the 16 x 24-bit "register words" in the 100-byte register records (raw,
    experimental: their visual meaning is not decoded)

The colour parameters are proven to be written as A[0..5] then B[0..5] to
request +100..+122, but no CPU reader was found; their meaning is still unproven
and they are exposed as raw s16 values for camera experimentation. Coefficient
records are probe-only. Effect modules are decoded separately in
docs/ART_FILTER_CHAIN.md but are not editable by this tool yet.

Shared tables cannot be given different values per filter: the firmware uses one
handler for e.g. Pin Hole I/II/III and Diorama I/II. The tool refuses such a config.

STYLES.json example:
{
  "pop_art_1": {
    "curve": "0:0 64:40 128:80 192:140 255:255",
    "colour_a": [53, 76, 100, 56, -1, 48],
    "colour_b": [1, 8, 10, 0, 22, -10],
    "matrix": [273, -14, -3, -7, 266, -3, -7, -14, 277],
    "register_words": [0, 0, 0, 10485783, 2785149, 2785408, 10518915, 65512,
                       65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535]
  },
  "vintage_3": {"curve": [0, 117, 256, 435, 578, 698, 803, 893, 973]}
}
Curve points are in:out with out 0..255 (rescaled to 0..1023); a raw 256-value
list may also be given (values 0..1023).
"""
import collections
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import art_filter_dump as afd  # noqa: E402
import modcore  # noqa: E402
import olyfw  # noqa: E402

BASE = afd.BASE
CHAIN_PRIMARY = 0x6052dab0
CHAIN_SECONDARY = 0x6052dbb0

# Handler contents decoded from the chain builder. These are conditional module
# summaries, not fixed chains; see docs/ART_FILTER_CHAIN.md.
CHAIN_HANDLERS = {
    0x603845c1: "grain-like: 60383c69; else 603839fd/60383a1f, 60388169/603880f0, 603884e2",
    0x6038468e: "opt 6038621c; v2: 60386283/60383c5b/603843b0; else 6038639c",
    0x6038472e: "grain-like: 60383c69; else 603839fd/60387e4e/60387f68/60388076",
    0x603847bc: "60386442, opt 60383c5b, 603866da",
    0x603847f4: "603867f7/60386a81/60386e97",
    0x60384858: "60386fc2, opt 60383c5b, 60387254",
    0x603848a2: "60385dbe",
    0x603848dd: "if job+0x2c38==0: 60385e18/60385f31/60387254",
    0x60384927: "secondary miss",
    0x6038497a: "60383d99 or grain chain with 60388169/60388295/603884e2/60388384",
    0x60384a38: "job+0x2c45=0..3: 6038619b/60383c5b/60384353/6038605d/60383d99; else 60383d99",
    0x60384abc: "6038621c, 60386283 (+60383c5b/60384353 if v2)",
    0x60384b1c: "grain-like: 603839fd/60387e4e/60387f68",
    0x60384b6d: "60386442, opt 60383c5b, 6038655b",
    0x60384ba2: "short: 603867f7/60386a81/60386d77; else full line chain",
    0x60384c53: "60387606/60387716/6038781d/60387978",
    0x60384cc4: "60386fc2, opt 60383c5b",
    0x60384cee: "60383d99/60383c69/603875f5 or 6038735f/6038746f",
    0x60384d63: "60388596",
    0x60384d71: "60385b6b",
    0x60384d7f: "60383c69/60385f5b... or 60385e18/60385f31/603870db",
    0x60384e05: "60387a4c + line/fade chain ending 60387254/60387e0f",
    0x60384ec7: "generic chain",
}

# Decoded chain modules: address -> (role, proven handler xrefs). See
# docs/ART_FILTER_CHAIN.md for descriptors, pass IDs and patch sites.
MODULE_SEMANTICS = {
    0x603839fd: ("grain init A (keeps PRNG state)", "6038460a"),
    0x60383a1f: ("grain init B (clears PRNG)", "60384617"),
    0x60383c5b: ("grain dispatcher wrapper -> 603985de", "6038463d"),
    0x60383c69: ("grain chain-tail updater A", "603845da, 60384517"),
    0x60383ccb: ("grain variant-II slot 0 updater", "603844ea"),
    0x60383cd9: ("grain variant-II slot 2 updater", "603844fc"),
    0x60383d99: ("type 0x305 grain wrapper (flags 0x1060)", "60384a02, 60384a1b"),
    0x60388169: ("grain layer setup, flags 0x1010", "6038462f, 6038465e"),
    0x60388295: ("grain continuation setup, flags 0x1010", "6038464c"),
    0x603880f0: ("variant-I word1 partner", "60384665"),
    0x603884e2: ("grain finalizer, allocator 0x1010", "60384678"),
    0x6038619b: ("Diorama setup, 0x302/0x1000", "60384a78"),
    0x6038605d: ("Diorama companion, flags 0x1070", "60384aa2"),
    0x60386fc2: ("Pop Art / Diorama setup, 0x302/0x1000", "6038485d, 60384cc9"),
    0x60387254: ("Pop Art / Cross setup, 0x304/0x10a0", "60384887, 60384906, 60384eb4"),
    0x60384353: ("secondary grain/key slot dispatcher", "chain builder"),
    0x603867f7: ("Key Line staging, pass 0x500", "6038481d, 60384bc9, 60384bf6"),
    0x6038685b: ("Key Line line/threshold pass 0x501", "60384c04"),
    0x6038696b: ("Key Line follow-up pass 0x502", "60384c1f"),
    0x60386a81: ("Key Line fill/setup pass 0x503", "6038482c, 60384bd8, 60384c12"),
    0x60386bab: ("Key Line combine pass 0x504", "60384c37, 60384c40"),
    0x60386d06: ("Key Line alternate combine pass 0x504", "60384c4b"),
    0x60386d77: ("Key Line short-path pass 0x505", "60384be7"),
    0x60386e97: ("Key Line short-path callback patcher", "6038483b"),
    0x60387606: ("Watercolor first pass 0x600", "60384c80"),
    0x60387716: ("Watercolor second pass 0x601", "60384c8d"),
    0x6038781d: ("Watercolor combine pass 0x602", "60384ca5, 60384cae"),
    0x60387978: ("Watercolor texture pass, worker 0x10b0", "60384cb9"),
    0x6038621c: ("Dramatic Tone staging, pass 0x400", "6038469f, 60384acd"),
    0x60386283: ("Dramatic Tone main pass 0x401", "603846b7, 60384ae5, 60384b0f"),
    0x6038639c: ("Dramatic Tone callback installer", "603846fa"),
    0x60386442: ("Gentle Sepia first pass 0x200/0x201", "603847c1, 60384b72"),
    0x6038655b: ("Gentle Sepia final pass 0x201", "60384b99"),
    0x603866da: ("Gentle Sepia slot finisher", "603847eb"),
    0x60385dbe: ("Bleach Bypass I pass installer", "603848aa"),
    0x603870db: ("Bleach II / Instant Film extra pass", "60384dfc, 60384ea6"),
    0x60387a4c: ("Instant Film texture pass, worker 0x10b0", "60384e0a"),
    0x60387c2a: ("Instant Film finalizer, passes 0xb00..0xb04", "60384e5d, 60384e8b"),
    0x60388596: ("Vintage final pass", "60384d68"),
}


def check(cond, msg):
    if not cond:
        sys.exit("patch_art_styles: " + msg)


def off(a):
    return a - BASE


def filter_names():
    """name -> (code, variant) for accepted config keys."""
    out = {}
    for code, name, nv in afd.FILTERS:
        base = name.lower().replace("&", "and").replace(" ", "_").replace("-", "_")
        for v in range(1, nv + 1):
            roman = afd.ROMAN[v].lower()
            out["%s_%d" % (base, v)] = (code, v)
            out["%s_%s" % (base, roman)] = (code, v)
            out["art_0x%02x_%d" % (code, v)] = (code, v)
        if nv == 1:
            out[base] = (code, 1)
            out["art_0x%02x" % code] = (code, 1)
    return out


NAMES = filter_names()


def title(k):
    code, v = k
    name = next(n for c, n, nv in afd.FILTERS if c == code)
    nv = next(nv for c, n, nv in afd.FILTERS if c == code)
    return "%s %s" % (name, afd.ROMAN[v]) if nv > 1 else name


def key_str(k):
    return "0x01%02x00%02x" % (k[1], k[0])


def a_tables(k):
    a = afd.A.get(k)
    return (a[1], a[2]) if isinstance(a, tuple) and len(a) == 3 else afd.A_DEFAULT


def curve_table(k):
    b = afd.B.get(k)
    if b and isinstance(b[1], int):
        return b[1]
    return None


def matrix_table(k):
    c = afd.C.get(k)
    return c[1] if c else None


def coeff_record(k):
    d = afd.D.get(k)
    return d[1] if d else afd.D_DEFAULT


def coeff_block(main, rec):
    return struct.unpack_from("<I", main, off(rec))[0]


def coeff_windows(main, block):
    """12 signed triples actually consumed by 0x603c59cf (read-only probe)."""
    return [struct.unpack_from("<3h", main, off(block) + 0x0c + 0x1c * n) for n in range(12)]


def register_record(k):
    e = afd.E.get(k)
    return e[1] if e else None


def register_words(main, rec):
    """16 x 24-bit words from one 50-byte row of a register record."""
    row = main[off(rec):off(rec) + 50]
    check(main[off(rec) + 50:off(rec) + 100] == row,
          "register record %#x rows differ" % rec)
    a, b, c = row[0:16], row[16:32], row[33:49]
    return [(c[i] << 16) | (b[i] << 8) | a[i] for i in range(16)]


def pack_register_words(words, scalar=0):
    """Rebuild both 50-byte rows; byte +49 stays zero."""
    a = bytes(w & 0xff for w in words)
    b = bytes((w >> 8) & 0xff for w in words)
    c = bytes((w >> 16) & 0xff for w in words)
    row = a + b + bytes([scalar & 0xff]) + c + b"\x00"
    check(len(row) == 50, "bad register row")
    return row * 2


def all_keys():
    return [(code, v) for code, name, nv in afd.FILTERS for v in range(1, nv + 1)]


def groups(table_fn):
    g = collections.defaultdict(list)
    for k in all_keys():
        a = table_fn(k)
        if a is not None:
            g[a].append(k)
    return g


def curve_values(main, addr):
    return list(struct.unpack_from("<256H", main, off(addr)))


def a_values(main, addr):
    return list(struct.unpack_from("<6h", main, off(addr)))


def matrix_values(main, addr):
    return list(struct.unpack_from("<9h", main, off(addr)))


def hash_entries(main, base, count):
    out = []
    for i in range(count):
        k, h = struct.unpack_from("<II", main, off(base) + 8 * i)
        if k or h:
            out.append((i, k, h))
    return out


def probe_chain(main):
    """Print the two chain hash tables. Module lists are decoded separately."""
    for label, base, count in (("primary", CHAIN_PRIMARY, 32),
                               ("secondary", CHAIN_SECONDARY, 16)):
        print("%s chain hash %#x:" % (label, base))
        for i, k, h in hash_entries(main, base, count):
            summary = CHAIN_HANDLERS.get(h)
            extra = ("  %s" % summary) if summary else ""
            print("  [%2d] residual=%#010x handler=%#010x%s" % (i, k, h, extra))
        print()


def probe_modules():
    """Print the decoded role and handler xrefs for each chain module."""
    print("Decoded chain modules (file offset = address - %#x):" % BASE)
    for addr in sorted(MODULE_SEMANTICS):
        role, xrefs = MODULE_SEMANTICS[addr]
        print("  %#010x / %#08x  %-52s xrefs: %s" %
              (addr, off(addr), role, xrefs))


def probe(main):
    print("Art filters in %s (runtime BASE %#x)" % ("main block", BASE))
    print("key         filter                  curve        colour A/B          matrix")
    for k in all_keys():
        c = curve_table(k)
        a1, a2 = a_tables(k)
        mx = matrix_table(k)
        note = ""
        if afd.A.get(k) == "zero":
            note = " (cleared in code)"
        elif afd.A.get(k) is None:
            note = " (default table)"
        print("%-11s %-23s %-12s %-8s/%-8s %-12s%s" %
              (key_str(k), title(k), ("%#x" % c) if c else "cond/none",
               "%#x" % a1, "%#x" % a2, ("%#x" % mx) if mx else "-", note))
    print("\nShared tables (editing one changes every listed filter):")
    for label, fn, fmt in (("curve", curve_table, lambda a: "%#x" % a),
                           ("colour A", lambda k: a_tables(k)[0], lambda a: "%#x" % a),
                           ("colour B", lambda k: a_tables(k)[1], lambda a: "%#x" % a),
                           ("matrix", matrix_table, lambda a: "%#x" % a)):
        for addr, ks in sorted(groups(fn).items()):
            if len(ks) > 1:
                print("  %-8s %s : %s" % (label, fmt(addr), ", ".join(title(k) for k in ks)))
    print("\nCoefficient records (read-only; only the 6-byte windows per group are proven-consumed):")
    for k in all_keys():
        rec = coeff_record(k)
        blk = coeff_block(main, rec)
        triples = coeff_windows(main, blk)
        compact = []
        for t in triples:
            if compact and compact[-1][1] == t and compact[-1][0] < 11:
                compact[-1] = (compact[-1][0] + 1, t)
            else:
                compact.append((1, t))
        desc = " ".join(("%dx" % n if n > 1 else "") + "(%d,%d,%d)" % t for n, t in compact)
        print("  %-22s rec=%#x block=%#x  %s" % (title(k), rec, blk, desc))
    print("\nRegister records (100 B = two identical 50 B rows, 16 x 24-bit words):")
    for k in all_keys():
        rec = register_record(k)
        if rec is None:
            continue
        words = register_words(main, rec)
        compact = []
        for w in words:
            if compact and compact[-1][1] == w:
                compact[-1] = (compact[-1][0] + 1, w)
            else:
                compact.append((1, w))
        desc = " ".join(("%dx" % n if n > 1 else "") + "%06x" % w for n, w in compact)
        print("  %-22s rec=%#x  %s" % (title(k), rec, desc))

    print()
    probe_chain(main)


def parse_curve(value):
    if isinstance(value, str):
        return modcore.curve_from_points(modcore.parse_curve_points(value))
    check(isinstance(value, list) and len(value) == 256,
          "curve must be a point string or 256 values")
    out = []
    for v in value:
        check(isinstance(v, int) and 0 <= v <= 1023, "curve values must be 0..1023")
        out.append(v)
    return out


def parse_ints(value, n, name):
    check(isinstance(value, list) and len(value) == n,
          "%s must be a list of %d integers" % (name, n))
    out = []
    for v in value:
        check(isinstance(v, int) and -32768 <= v <= 32767,
              "%s values must be signed 16-bit" % name)
        out.append(v)
    return out


def parse_words(value):
    check(isinstance(value, list) and len(value) == 16,
          "register_words must be a list of 16 integers")
    for v in value:
        check(isinstance(v, int) and 0 <= v <= 0xffffff,
              "register_words values must be 24-bit (0..0xffffff)")
    return list(value)


def normalise_config(cfg):
    out = {}
    for name, spec in cfg.items():
        norm = str(name).strip().lower().replace("&", "and")
        norm = norm.replace(" ", "_").replace("-", "_")
        key = NAMES.get(norm)
        check(key is not None, "unknown filter '%s' (run --probe for filter names)" % name)
        check(key not in out, "filter '%s' appears twice" % name)
        check(isinstance(spec, dict), "filter '%s': expected an object" % name)
        item = {}
        if "curve" in spec:
            item["curve"] = parse_curve(spec["curve"])
        if "colour_a" in spec:
            item["colour_a"] = parse_ints(spec["colour_a"], 6, "colour_a")
        if "colour_b" in spec:
            item["colour_b"] = parse_ints(spec["colour_b"], 6, "colour_b")
        if "matrix" in spec:
            item["matrix"] = parse_ints(spec["matrix"], 9, "matrix")
        if "register_words" in spec:
            item["register_words"] = parse_words(spec["register_words"])
        check(item, "filter '%s': no editable fields" % name)
        out[key] = item
    return out


def check_shared(cfg):
    """Reject different values for one physical table."""
    checks = [
        ("curve", curve_table, "curve"),
        ("colour A", lambda k: a_tables(k)[0], "colour_a"),
        ("colour B", lambda k: a_tables(k)[1], "colour_b"),
        ("matrix", matrix_table, "matrix"),
        ("register record", register_record, "register_words"),
    ]
    for label, fn, field in checks:
        by_addr = collections.defaultdict(list)
        for k, spec in cfg.items():
            if field in spec:
                addr = fn(k)
                check(addr is not None, "%s: %s has no %s table" % (title(k), key_str(k), label))
                by_addr[addr].append((k, spec[field]))
        for addr, uses in by_addr.items():
            first = uses[0][1]
            for k, value in uses[1:]:
                check(value == first,
                      "%s %#x is shared by %s and %s; give them the same %s "
                      "(per-filter differences need a code patch)" %
                      (label, addr, title(uses[0][0]), title(k), field))


def warn_shared(cfg):
    for label, fn, field in (("curve", curve_table, "curve"),
                             ("colour A", lambda k: a_tables(k)[0], "colour_a"),
                             ("colour B", lambda k: a_tables(k)[1], "colour_b"),
                             ("matrix", matrix_table, "matrix"),
                             ("register record", register_record, "register_words")):
        group = groups(fn)
        seen = set()
        for k, spec in sorted(cfg.items()):
            if field not in spec:
                continue
            addr = fn(k)
            users = group.get(addr, [])
            if len(users) < 2 or addr in seen:
                continue
            seen.add(addr)
            others = [title(u) for u in users if u != k]
            print("  warning: %s %#x is also used by %s" %
                  (label, addr, ", ".join(others)))


def patch_main(main, cfg):
    m = bytearray(main)
    check_shared(cfg)
    warn_shared(cfg)
    for k, spec in sorted(cfg.items()):
        log = []
        if "curve" in spec:
            addr = curve_table(k)
            m[off(addr):off(addr) + 512] = struct.pack("<256H", *spec["curve"])
            log.append("curve@%#x" % addr)
        if "colour_a" in spec or "colour_b" in spec:
            a1, a2 = a_tables(k)
            if "colour_a" in spec:
                m[off(a1):off(a1) + 12] = struct.pack("<6h", *spec["colour_a"])
                log.append("A@%#x" % a1)
            if "colour_b" in spec:
                m[off(a2):off(a2) + 12] = struct.pack("<6h", *spec["colour_b"])
                log.append("B@%#x" % a2)
        if "matrix" in spec:
            addr = matrix_table(k)
            check(addr is not None, "%s has no own colour matrix" % title(k))
            m[off(addr):off(addr) + 18] = struct.pack("<9h", *spec["matrix"])
            log.append("matrix@%#x" % addr)
        if "register_words" in spec:
            addr = register_record(k)
            check(addr is not None, "%s has no register record" % title(k))
            scalar = m[off(addr) + 32]
            m[off(addr):off(addr) + 100] = pack_register_words(spec["register_words"], scalar)
            log.append("registers@%#x" % addr)
        print("  %-22s %s" % (title(k), " ".join(log)))
    return bytes(m)


def main(argv):
    if "--modules" in argv:
        print(__doc__.splitlines()[1])
        probe_modules()
        return 0
    if "--probe" in argv:
        check(len(argv) >= 1, "usage: patch_art_styles.py FIRMWARE.BIN --probe")
        fw = olyfw.read(argv[0])
        blocks = olyfw.unpack_blocks(fw)
        probe(blocks[0]["plain"])
        return 0
    if len(argv) < 3:
        print(__doc__)
        return 2
    src, dst, cfgpath = argv[:3]
    fw = olyfw.read(src)
    blocks = olyfw.unpack_blocks(fw)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    cfg = normalise_config(json.load(open(cfgpath)))
    plains = [b["plain"] for b in blocks]
    plains[0] = patch_main(plains[0], cfg)
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
    print("wrote %s  sha256 %s  version %#06x" %
          (dst, hashlib.sha256(out).hexdigest(),
           struct.unpack_from("<H", again[0]["head"], 16)[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
