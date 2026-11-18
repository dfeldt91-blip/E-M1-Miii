"""Core of the E-M1 Mark III mod builder: fetch the official firmware, apply mod edit lists, write
the camera file. Used by builder/em1iii_builder.py (GUI) and tools/make_modpack.py.

Edits are in runtime addresses with both olycompress blobs expanded in place:
  0x60021020..        main block as stored
  0x60803000..        blob A (header at main offset 0x7e1fe0), GUI/OSD code
  0x60c6c000..        blob B (header at main offset 0xc4afe0), GUI code
  ..0x612f1000        end of blob B's unpack area
"""
import hashlib
import json
import struct
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import olyfw
import olycompress

BASE = 0x60021020
BLOBS = ((0x7e1fe0, 0x60803000), (0xc4afe0, 0x60c6c000))   # (header offset in main, runtime address)
BLOB_END = 0x612f1000
MODEL_ID = 0x1390
STOCK_NAME = "OLY_E_139_1600_0000_0000.BIN"
STOCK_SHA256 = "4f9ea315a2f2280dd5746abc39b5e4b038f183836eadfbe9d96b266e49a09aac"
STOCK_SIZE = 109838336
CARD_NAME = "E1399999.BIN"
CATALOG = "https://fw01.om-digitalsolutions.net/ww_inform/fcache.do"

# Same request OM's updater makes, with placeholder MAC address and serial number.
REQUEST = ("<?xml version='1.0' encoding='utf-8'?><firmware_demand><revision>0001</revision>"
           "<mac_address>00-00-00-00-00-00</mac_address><time>%s</time><language>ENU</language>"
           "<application>FWUT</application><type>0000</type><version>00005000</version><os>WIN</os>"
           "<country_code>0001</country_code><hardwares><firmup_mode>0</firmup_mode><hardware_info>"
           "<hard_code>OLYE139000000000</hard_code><firmware_version>00001000</firmware_version>"
           "<serial_no>000000000</serial_no></hardware_info></hardwares></firmware_demand>")


def _ssl_context():
    """A packaged app (PyInstaller, macOS especially) may not see the system certificates: use
    certifi's there. Plain Python keeps its normal certificate store."""
    import ssl
    import sys
    if not getattr(sys, "frozen", False):
        return None
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


class BuildError(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise BuildError(msg)


# ---------------------------------------------------------------- download

def catalog_entry(timeout=30):
    """Ask OM's update catalog for the E-M1 Mark III firmware. Returns (file name, url, size)."""
    req = urllib.request.Request(
        CATALOG, data=(REQUEST % datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")).encode(),
        headers={"Content-Type": "text/xml; Charset=UTF-8", "User-Agent": "Olympus"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        root = ET.fromstring(r.read())
    for info in root.iter("firmware_info"):
        if info.findtext("model_id") == "1390":
            return info.findtext("file_name"), info.findtext("url"), int(info.findtext("file_size") or 0)
    raise BuildError("OM's catalog has no E-M1 Mark III firmware entry")


def download_stock(path, progress=None, timeout=60):
    """Download the official 1.6 file to PATH (via PATH.part) and verify its SHA-256."""
    name, url, size = catalog_entry(timeout)
    check(name == STOCK_NAME, "OM's catalog now offers %s, not %s; the mods are made for 1.6" % (name, STOCK_NAME))
    h = hashlib.sha256()
    done = 0
    req = urllib.request.Request(url, headers={"User-Agent": "Olympus"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r, \
            open(path + ".part", "wb") as fh:
        total = int(r.headers.get("Content-Length") or size or STOCK_SIZE)
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    check(h.hexdigest() == STOCK_SHA256, "downloaded file has the wrong checksum (%s)" % h.hexdigest())
    import os
    os.replace(path + ".part", path)
    return path


def verify_stock(data):
    check(len(data) == STOCK_SIZE and hashlib.sha256(data).hexdigest() == STOCK_SHA256,
          "this is not the official E-M1 Mark III 1.6 firmware (%s)" % STOCK_NAME)


# ---------------------------------------------------------------- images and edits

def runtime_image(main):
    """Main block with both blobs expanded at their runtime addresses."""
    m = bytearray(main)
    for hdr, rt in BLOBS:
        g = olycompress.unpack(main, hdr)
        m[rt - BASE:rt - BASE + len(g)] = g
    return bytes(m)


def diff(a, b, gap=8):
    """[(runtime address, new bytes)] where B differs from A; runs closer than GAP are joined."""
    out = []
    n = min(len(a), len(b))
    page = 4096
    done = 0                       # everything below this offset is already handled
    for k in range(0, n, page):
        if k + page <= done or a[k:k + page] == b[k:k + page]:
            continue
        i, end = max(k, done), min(k + page, n)
        while i < end:
            if a[i] == b[i]:
                i += 1
                continue
            j = i
            while j < n and a[j:j + gap] != b[j:j + gap]:
                j += 1
            while a[j - 1] == b[j - 1]:
                j -= 1
            if out and out[-1][0] + len(out[-1][1]) == i + BASE:
                out[-1] = (out[-1][0], out[-1][1] + b[i:j])
            else:
                out.append((i + BASE, b[i:j]))
            i = done = j
    return out


def stock_digest(img, edits, blocks=None):
    """SHA-256 of the stock bytes under EDITS (block 0: runtime image IMG; others: BLOCKS[i] plain)."""
    h = hashlib.sha256()
    for blk, a, new in edits:
        if blk == 0:
            h.update(img[a - BASE:a - BASE + len(new)])
        else:
            h.update(blocks[blk][a:a + len(new)])
    return h.hexdigest()


def block_diffs(stock_blocks, new_blocks):
    """All edits between two unpacked files: (0, runtime address, bytes) for the main block (blobs
    expanded), (i, plain offset, bytes) for the other blocks."""
    out = [(0, a, n) for a, n in diff(runtime_image(stock_blocks[0]["plain"]),
                                      runtime_image(new_blocks[0]["plain"]))]
    for i in range(1, len(stock_blocks)):
        out += [(i, a - BASE, n) for a, n in diff(stock_blocks[i]["plain"], new_blocks[i]["plain"])]
    return out


def load_pack(path):
    with open(path) as fh:
        pack = json.load(fh)
    check(pack.get("format") == 1, "unknown mods.json format")
    for mod in pack["mods"]:
        mod["edits"] = [(int(b), int(a, 16), bytes.fromhex(n)) for b, a, n in mod.get("edits", [])]
        mod.setdefault("generator", None)
        mod.setdefault("options", {})
    return pack


# ---------------------------------------------------------------- generated mods
# Mods whose bytes are made at build time (images drawn to a chosen size). Each gets the expanded main
# image, the plain blocks and the option values, and edits them in place.

def _frame(img, plains, opts, log, panorama):
    import patch_frame_white as fw
    fw.LOG = log
    pct = float(opts.get("width_pct", 3))
    check(0.5 <= pct <= 20, "frame width must be between 0.5 and 20 %")
    try:
        if not panorama:
            plains[2][:] = fw.patch_images(bytes(plains[2]), pct, "l0")
        else:
            plains[2][:], ids = fw.panorama_images(bytes(plains[2]), pct, "l0")
            m = bytearray(img[:fw.ROWS + 12 * 11 - BASE])
            m = fw.panorama_row(bytes(m), ids)
            o = fw.ROWS + 12 * fw.PAN_ROW - BASE
            img[o:o + 12] = m[o:o + 12]
    except SystemExit as e:                       # the tool's own refusal
        raise BuildError(str(e))


def _xpan(img, plains, opts, log):
    import patch_xpan_icon as xi
    xi.LOG = log
    try:
        xi.apply(img, plains)
    except SystemExit as e:
        raise BuildError(str(e))


def _uw_mono(img, plains, opts, log):
    import patch_underwater_mono as um
    tint = int(round(float(opts.get("tint", 0))))
    try:
        um.patch_at(img, BASE, tint)
    except SystemExit as e:
        raise BuildError(str(e))
    log("    Underwater tint: %s" % um.TINT_NAMES[tint])


def _custom_looks(img, plains, opts, log):
    import patch_looks as pl
    keys = [str(opts.get("look%d" % i, pl.DEFAULT6[i - 1])) for i in range(1, 7)]
    try:
        sd = str(opts.get("sd", "off")) == "on"
        names = pl.apply6(img, BASE, keys, sd=sd)
    except SystemExit as e:
        raise BuildError(str(e))
    if sd:
        log("    Custom shows Look 1..6; built-in: " + ", ".join(names) + "; the card file EM1MOD/LOOKS.BIN replaces them")
    else:
        log("    Custom looks: " + ", ".join("%s = %s" % (s, n) for s, n in zip(pl.MENU_NAMES, names)))


def _owner_title(img, plains, opts, log):
    import patch_owner_title as ot
    text = str(opts.get("text", "")).strip()
    check(text, "type the owner text (name and phone) for the Owner title mod")
    check(len(text) <= ot.MAX_CHARS, "owner text is %d characters; at most %d fit" % (len(text), ot.MAX_CHARS))
    check(all(32 <= ord(c) < 127 for c in text), "owner text: use plain letters, digits and punctuation only")
    check("@" not in text, "owner text: '@' does not display on the camera (it starts icon codes), leave the email out")
    try:
        plains[1][:] = ot.patch_block1(bytes(plains[1]), {ot.TITLE1: text})
    except SystemExit as e:
        raise BuildError(str(e))
    log("    Shooting Menu 1 title: %s" % text)


# ---------------------------------------------------------------- user tone curves (Gradation)
# The art_gradation mod reserves USER_SLOTS curves (256 x u16, output 0..1023) at USER_CURVES; they
# hold the identity curve until the app writes the user's curve. Points are "in:out" pairs, 0..255.
USER_CURVES, USER_SLOTS, IDENTITY_CURVE = 0x600dec00, 2, 0x60508f06


def parse_curve_points(text):
    """'0:10 128:120 255:240' -> sorted [(x, y)] with both ends present (0..255)."""
    pts = {}
    for tok in str(text).replace(",", " ").replace(";", " ").split():
        check(":" in tok, "curve point '%s': write in:out, e.g. 128:120" % tok)
        x, y = tok.split(":", 1)
        try:
            x, y = int(round(float(x))), int(round(float(y)))
        except ValueError:
            raise BuildError("curve point '%s' is not a number pair" % tok)
        check(0 <= x <= 255 and 0 <= y <= 255, "curve point '%s': values are 0..255" % tok)
        pts[x] = y
    pts.setdefault(0, 0)
    pts.setdefault(255, 255)
    return sorted(pts.items())


def curve_from_points(points):
    """256 output values (0..1023) through POINTS [(x, y)] 0..255: monotone cubic (Fritsch-Carlson)
    where the points rise, so the curve has no overshoot."""
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    n = len(xs)
    if n == 2:
        ms = [(ys[1] - ys[0]) / (xs[1] - xs[0])] * 2
    else:
        d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
        ms = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
        for i in range(n - 1):
            if d[i] == 0:
                ms[i] = ms[i + 1] = 0.0
                continue
            a, b = ms[i] / d[i], ms[i + 1] / d[i]
            h = a * a + b * b
            if h > 9:
                t = 3 / h ** 0.5
                ms[i], ms[i + 1] = t * a * d[i], t * b * d[i]
    out = []
    k = 0
    for x in range(256):
        while k < n - 2 and x > xs[k + 1]:
            k += 1
        h = xs[k + 1] - xs[k]
        t = (x - xs[k]) / h
        h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        y = h00 * ys[k] + h10 * h * ms[k] + h01 * ys[k + 1] + h11 * h * ms[k + 1]
        out.append(max(0, min(1023, int(round(y * 1023 / 255)))))
    return out


def _user_curves(img, plains, opts, log):
    ident = bytes(img[IDENTITY_CURVE - BASE:IDENTITY_CURVE - BASE + 512])
    for i in range(USER_SLOTS):
        o = USER_CURVES + 512 * i - BASE
        check(bytes(img[o:o + 512]) == ident, "Gradation curve slot %d not found (art_gradation mod)" % (i + 1))
        text = str(opts.get("curve%d" % (i + 1), "")).strip()
        if not text:
            log("    Custom%d curve: none (identity)" % (i + 1))
            continue
        pts = parse_curve_points(text)
        img[o:o + 512] = struct.pack("<256H", *curve_from_points(pts))
        log("    Custom%d curve: %s" % (i + 1, " ".join("%d:%d" % p for p in pts)))


GENERATORS = {
    "art_gradation": _user_curves,
    "owner_title": _owner_title,
    "custom_looks": _custom_looks,
    "underwater_mono": _uw_mono,
    "xpan_icon": _xpan,
    "white_frame": lambda img, plains, opts, log: _frame(img, plains, opts, log, False),
    "white_frame_panorama": lambda img, plains, opts, log: _frame(img, plains, opts, log, True),
}


def bcd_version(text):
    """'1.601' -> 0x1601."""
    t = text.strip().replace(".", "")
    check(len(t) == 4 and t.isdigit(), "version must look like 1.601")
    return int(t, 16)


def rebuild_main(main, img):
    """Main block bytes for the edited runtime image IMG (blobs recompressed only if changed)."""
    out_main = bytearray(main)
    blob_lo = BLOBS[0][1]
    out_main[:blob_lo - BASE] = img[:blob_lo - BASE]                   # main part before the blobs
    tail = BLOB_END - BASE
    out_main[tail:] = img[tail:len(out_main)]                         # main part after the blobs
    for k, (hdr, rt) in enumerate(BLOBS):
        csz, usz = struct.unpack_from("<II", main, hdr + 16)
        raw = bytes(img[rt - BASE:rt - BASE + usz])
        if raw == olycompress.unpack(main, hdr):
            continue
        limit = (BLOBS[k + 1][0] if k + 1 < len(BLOBS) else tail) - (hdr + 32)
        c = olycompress.pack(raw)
        check(len(c) <= limit, "compressed blob %d does not fit" % k)
        out_main[hdr + 32:hdr + 32 + limit] = c + b"\xff" * (limit - len(c))
        struct.pack_into("<I", out_main, hdr + 16, len(c))
        check(olycompress.unpack(bytes(out_main), hdr) == raw, "blob %d does not decode back" % k)
    check(runtime_image(bytes(out_main)) == bytes(img), "rebuilt image differs from the edited image")
    return bytes(out_main)


def build(stock, pack, selected, version, log=print, options=None):
    """Return the camera file bytes: official 1.6 + the mods in SELECTED (ids), main version VERSION.
    OPTIONS: {mod id: {option: value}} for generated mods (defaults from mods.json)."""
    options = options or {}
    verify_stock(stock)
    mods = {m["id"]: m for m in pack["mods"]}
    chosen = [m for m in pack["mods"] if m["id"] in selected]
    for m in chosen:
        for r in m["requires"]:
            check(r in selected, "'%s' needs '%s'" % (m["title"], mods[r]["title"]))
    blocks = olyfw.unpack_blocks(stock)
    check(all(b["stored"] == b["calc"] for b in blocks), "input has a bad block checksum")
    main = blocks[0]["plain"]
    img = bytearray(runtime_image(main))
    plains = [bytearray(b["plain"]) for b in blocks]
    owner = {}
    for m in chosen:
        if m["edits"]:
            check(stock_digest(img, m["edits"], plains) == m["stock_sha256"],
                  "'%s' does not match this firmware" % m["title"])
    for m in chosen:
        for blk, a, new in m["edits"]:
            if blk == 0:
                check(BASE <= a and a + len(new) <= BASE + len(img), "edit outside the image")
                buf, o = img, a - BASE
            else:
                check(0 < blk < len(plains) and 0 <= a and a + len(new) <= len(plains[blk]), "edit outside block")
                buf, o = plains[blk], a
            for x in (o, o + len(new) - 1):
                check(owner.get((blk, x), m["id"]) == m["id"], "'%s' and '%s' overlap" % (owner.get((blk, x)), m["title"]))
            for x in range(o, o + len(new)):
                owner[(blk, x)] = m["id"]
            buf[o:o + len(new)] = new
        if m["edits"]:
            log("  + %s (%d edits)" % (m["title"], len(m["edits"])))
    for m in chosen:                       # generated mods last; they check their own targets
        if m["generator"]:
            check(m["generator"] in GENERATORS, "unknown generator %s" % m["generator"])
            opts = {k: v["default"] for k, v in m["options"].items()}
            opts.update(options.get(m["id"], {}))
            log("  + %s %s" % (m["title"], " ".join("%s=%s" % kv for kv in sorted(opts.items()))))
            GENERATORS[m["generator"]](img, plains, opts, log)
    out_main = rebuild_main(main, img)
    out = bytearray()
    for i, b in enumerate(blocks):
        head, tl = bytearray(b["head"]), bytearray(b["tail"])
        plain = bytes(out_main) if i == 0 else bytes(plains[i])
        if i == 0:
            struct.pack_into("<H", head, 16, version)
            struct.pack_into("<H", tl, 16, version)
        out += olyfw.build_block(bytes(head), plain, bytes(tl))
    check(len(out) == len(stock), "size changed")
    again = olyfw.unpack_blocks(bytes(out))
    check(all(b["stored"] == b["calc"] for b in again), "output checksum check failed")
    check(again[0]["info"]["model"] == MODEL_ID, "model id changed")
    return bytes(out)
