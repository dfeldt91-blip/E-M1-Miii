#!/usr/bin/env python3
"""E-M1 Mark III mod builder.

Downloads the official E-M1 Mark III firmware 1.6 from OM Digital Solutions' update server, lets you
pick mods and writes E1399999.BIN for the camera's card updater. Nothing of OM's firmware is stored
in this program: the mods are edit lists (builder/mods.json) applied to your own download.

  python3 builder/em1iii_builder.py                    window
  python3 builder/em1iii_builder.py --list             list the mods
  python3 builder/em1iii_builder.py --cli --mods panorama,hhrs_flash [--out DIR] [--version 1.601]
                                    [--stock FILE] [--frame-width 3] [--underwater-tint 0..4]
                                    [--custom-looks ID,ID,ID,ID,ID,ID]   (see --looks) [--custom-looks-sd] [--owner-text "NAME PHONE"]
                                    [--card-file CARD_DIR]   also write EM1MOD/LOOKS.BIN with those looks
                                                       no window ('--mods all' / '--mods none')

Needs Python 3.8+ and the lz4 package (pip install lz4). The window needs tkinter.
UNOFFICIAL. Flashing modified firmware is at your own risk.
"""
import json
import os
import queue
import sys
import threading
import traceback

# packaged app (PyInstaller): data files and the tools modules sit in sys._MEIPASS
HERE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

APP = "E-M1 Mark III mod builder"
CADUCEUS_URL = "https://github.com/cakelesscoder/caduceus-ep7"
PACK = os.path.join(HERE, "mods.json")
DATA_DIR = os.path.join(os.path.expanduser("~"), ".em1iii-mod-builder")
SETTINGS = os.path.join(DATA_DIR, "settings.json")

INSTALL = """How to install
1. Charge the battery fully.
2. Copy E1399999.BIN to the SD card as DCOLYMP/E1399999.BIN (a folder named DCOLYMP at the top level of the card, next to DCIM). It must be the only E139....BIN file on the card.
3. With the camera off, hold OK and switch it on to start the card update. Wait until the light stops (it may blink or simply go out), then switch the camera off and on.
4. Delete DCOLYMP/E1399999.BIN from the card afterwards.
To go back to stock, build with no mods ticked and install that file the same way."""


def missing_dependency():
    try:
        import lz4.block  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return "lz4 or Pillow is missing. Install them with:  %s -m pip install lz4 pillow" % os.path.basename(sys.executable)
    return None


def reveal(path):
    """Show the built file in Finder (macOS) or the folder in the file manager."""
    import subprocess
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except OSError:
        pass


def load_settings():
    try:
        with open(SETTINGS) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(s):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS, "w") as fh:
        json.dump(s, fh, indent=1)


VERSION = "1.601"   # fixed firmware version written to every build


def stock_path(s):
    return s.get("stock") or os.path.join(DATA_DIR, "OLY_E_139_1600_0000_0000.BIN")


def read_stock(path):
    import modcore
    with open(path, "rb") as fh:
        data = fh.read()
    modcore.verify_stock(data)
    return data


def do_build(stock, pack, selected, version_text, out_dir, log, options=None):
    import modcore
    ver = modcore.bcd_version(version_text)
    log("Building version %s with %d mod(s)..." % (version_text, len(selected)))
    data = modcore.build(stock, pack, selected, ver, log=log, options=options)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, modcore.CARD_NAME)
    with open(dst + ".part", "wb") as fh:
        fh.write(data)
    os.replace(dst + ".part", dst)
    with open(os.path.join(out_dir, "E1399999_mods.txt"), "w") as fh:
        fh.write("Built by %s\nBase: official %s\nVersion: %s\nMods:\n" % (APP, modcore.STOCK_NAME, version_text))
        for m in pack["mods"]:
            if m["id"] in selected:
                opts = (options or {}).get(m["id"], {})
                extra = "".join(", %s %s" % (m["options"][k]["label"],
                                             dict(m["options"][k].get("choices", [])).get(v, v)) for k, v in opts.items())
                fh.write("  - %s%s  (%s)\n" % (m["title"], extra, m["camera"]))
        if not selected:
            fh.write("  (none: stock 1.6)\n")
        import hashlib
        fh.write("sha256: %s\n\n%s\n" % (hashlib.sha256(data).hexdigest(), INSTALL))
    log("Wrote %s" % dst)
    return dst


def write_card_file(root, keys, log):
    """EM1MOD/LOOKS.BIN under ROOT (the card) with six looks (Film looks in Custom, SD option)."""
    import patch_looks
    d = os.path.join(root, "EM1MOD")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "LOOKS.BIN"), "wb") as fh:
        fh.write(patch_looks.make_looks_bin(keys))
    log("Wrote %s: %s" % (os.path.join(d, "LOOKS.BIN"),
                          ", ".join("Look %d = %s" % (i + 1, patch_looks.LOOKS[k]["name"]) for i, k in enumerate(keys))))


# ---------------------------------------------------------------- command line

def cli(argv):
    import modcore
    err = missing_dependency()
    if err:
        print(err)
        return 1
    pack = modcore.load_pack(PACK)
    ids = [m["id"] for m in pack["mods"]]
    if "--looks" in argv:
        for m in pack["mods"]:
            if m["id"] == "custom_looks":
                for k, name in m["options"]["look1"]["choices"]:
                    print("%-12s %s" % (k, name))
        return 0
    if "--list" in argv:
        for m in pack["mods"]:
            req = ("  needs: " + ", ".join(m["requires"])) if m["requires"] else ""
            print("%-15s %s\n%17s%s\n%17s%s%s" % (m["id"], m["title"], "", m["description"], "", m["camera"], req))
        return 0
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d   # noqa: E731
    s = load_settings()
    sel = arg("--mods", "")
    selected = set(ids) if sel == "all" else set() if sel in ("", "none") else set(sel.split(","))
    unknown = selected - set(ids)
    if unknown:
        print("unknown mod(s): %s  (see --list)" % ", ".join(sorted(unknown)))
        return 1
    path = arg("--stock") or stock_path(s)
    try:
        if not os.path.exists(path):
            print("Downloading the official firmware from OM Digital Solutions...")
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            last = [-1]

            def prog(done, total):
                p = done * 100 // max(total, 1)
                if p // 10 != last[0]:
                    last[0] = p // 10
                    print("  %d%%" % p)
            modcore.download_stock(path, prog)
        stock = read_stock(path)
        version = arg("--version") or VERSION
        options = {}
        if arg("--frame-width"):
            options["white_frame"] = {"width_pct": float(arg("--frame-width"))}
        if arg("--underwater-tint"):
            options["underwater_mono"] = {"tint": int(arg("--underwater-tint"))}
        if arg("--custom-looks"):
            ks = arg("--custom-looks").split(",")
            if len(ks) != 6:
                print("--custom-looks needs six look ids (see --looks)")
                return 1
            options["custom_looks"] = {"look%d" % (i + 1): k for i, k in enumerate(ks)}
        if arg("--owner-text"):
            options["owner_title"] = {"text": arg("--owner-text")}
        if "--custom-looks-sd" in argv:
            options.setdefault("custom_looks", {})["sd"] = "on"
        if arg("--card-file"):
            import patch_looks
            ks = arg("--custom-looks", ",".join(patch_looks.DEFAULT6)).split(",")
            write_card_file(arg("--card-file"), ks, print)
        do_build(stock, pack, selected, version, arg("--out", os.getcwd()), print, options)
    except (modcore.BuildError, OSError) as e:
        print("error:", e)
        return 1
    if not arg("--stock"):
        s["stock"] = path
    save_settings(s)
    print("\n" + INSTALL)
    return 0


# ---------------------------------------------------------------- window

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import modcore

    root = tk.Tk()
    root.title(APP)
    root.minsize(760, 560)
    s = load_settings()
    pack = modcore.load_pack(PACK)
    events = queue.Queue()
    state = {"stock": None, "busy": False}

    outer = ttk.Frame(root, padding=10)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text=APP, font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
    ttk.Label(outer, foreground="#a33", wraplength=720, text=(
        "Unofficial. Builds a modified firmware from OM's official 1.6 file. Flashing it is at your own "
        "risk; mods marked 'not tested' have never run on a camera.")).pack(anchor="w", pady=(2, 0))
    credit = ttk.Frame(outer)
    credit.pack(anchor="w", pady=(0, 8))
    ttk.Label(credit, text="Film looks and colour-engine research: Caduceus by cakelesscoder (Apache-2.0)  ").pack(side="left")
    link = ttk.Label(credit, text=CADUCEUS_URL, foreground="#0645ad", cursor="hand2")
    link.pack(side="left")
    link.bind("<Button-1>", lambda e: __import__("webbrowser").open(CADUCEUS_URL))

    # 1. firmware
    f1 = ttk.LabelFrame(outer, text="1. Official firmware 1.6", padding=8)
    f1.pack(fill="x")
    fw_status = ttk.Label(f1, text="", wraplength=720)
    fw_status.pack(anchor="w")
    r1 = ttk.Frame(f1)
    r1.pack(fill="x", pady=(4, 0))
    b_dl = ttk.Button(r1, text="Download from OM")
    b_dl.pack(side="left")
    b_pick = ttk.Button(r1, text="Use a file I already have...")
    b_pick.pack(side="left", padx=6)
    bar = ttk.Progressbar(r1, length=260, mode="determinate")
    bar.pack(side="left", padx=6)

    # 2. mods
    f2 = ttk.LabelFrame(outer, text="2. Choose mods", padding=8)
    f2.pack(fill="both", expand=True, pady=8)
    canvas = tk.Canvas(f2, highlightthickness=0, height=260)
    sb = ttk.Scrollbar(f2, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def wheel(e):
        step = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
        canvas.yview_scroll(step * (1 if abs(getattr(e, "delta", 0)) < 120 else abs(e.delta) // 120), "units")
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind_all(seq, wheel)
    chosen = set(s.get("mods", []))
    vars_ = {}
    by_id = {m["id"]: m for m in pack["mods"]}

    def toggled(mid):
        if vars_[mid].get():
            for r in by_id[mid]["requires"]:
                vars_[r].set(True)
        else:
            for m in pack["mods"]:
                if mid in m["requires"]:
                    vars_[m["id"]].set(False)

    opt_vars = {}
    for i, m in enumerate(pack["mods"]):
        v = tk.BooleanVar(value=m["id"] in chosen)
        vars_[m["id"]] = v
        ttk.Checkbutton(inner, text=m["title"], variable=v, command=lambda k=m["id"]: toggled(k)).grid(
            row=2 * i, column=0, sticky="w", pady=(6, 0))
        note = m["description"] + "\n" + m["camera"]
        if m["requires"]:
            note += "  Needs: " + ", ".join(by_id[r]["title"] for r in m["requires"]) + "."
        ttk.Label(inner, text=note, foreground="#555", wraplength=640, justify="left").grid(
            row=2 * i + 1, column=0, sticky="w", padx=(24, 0))
        if m["options"]:
            of = ttk.Frame(inner)
            of.grid(row=2 * i, column=0, sticky="e", padx=(0, 8))
            for name, o in m["options"].items():
                saved = s.get("options", {}).get(m["id"], {}).get(name, o["default"])
                if "choices" in o:
                    keys = [c[0] for c in o["choices"]]
                    labels = [c[1] for c in o["choices"]]
                    var = tk.StringVar(value=labels[keys.index(saved)] if saved in keys else labels[keys.index(o["default"])])
                    opt_vars[(m["id"], name)] = (var, dict(zip(labels, keys)))
                    ttk.Label(of, text=o["label"] + ":").pack(side="top", anchor="e")
                    ttk.Combobox(of, textvariable=var, values=labels, state="readonly", width=16).pack(side="top", anchor="e", padx=4)
                    continue
                if o.get("text"):
                    var = tk.StringVar(value=str(saved))
                    opt_vars[(m["id"], name)] = (var, "text")
                    ttk.Label(of, text=o["label"] + ":").pack(side="top", anchor="e")
                    ttk.Entry(of, textvariable=var, width=30).pack(side="top", anchor="e", padx=4)
                    continue
                var = tk.StringVar(value=str(saved))
                opt_vars[(m["id"], name)] = (var, None)
                ttk.Label(of, text=o["label"] + ":").pack(side="left")
                ttk.Spinbox(of, textvariable=var, from_=o["min"], to=o["max"], increment=o.get("step", 0.5), width=5).pack(side="left", padx=4)

    def set_all(val):
        for v in vars_.values():
            v.set(val)
    ttk.Button(inner, text="Select all", command=lambda: set_all(True)).grid(row=2 * len(pack["mods"]), column=0, sticky="w", pady=8)
    ttk.Button(inner, text="Select none (stock 1.6)", command=lambda: set_all(False)).grid(
        row=2 * len(pack["mods"]), column=0, sticky="w", padx=(100, 0), pady=8)

    # 3. output
    f3 = ttk.LabelFrame(outer, text="3. Build", padding=8)
    f3.pack(fill="x")
    ttk.Label(f3, text="Save to:").grid(row=1, column=0, sticky="w", pady=4)
    out = tk.StringVar(value=s.get("out") or os.path.join(os.path.expanduser("~"), "E-M1III-firmware"))
    ttk.Entry(f3, textvariable=out, width=60).grid(row=1, column=1, columnspan=2, sticky="we")
    ttk.Button(f3, text="Browse...", command=lambda: out.set(filedialog.askdirectory() or out.get())).grid(row=1, column=3, padx=6)
    b_build = ttk.Button(f3, text="Build E1399999.BIN")
    b_build.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
    b_card = ttk.Button(f3, text="Write card file (looks)...")
    b_card.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
    log = tk.Text(outer, height=7, wrap="word")
    log.pack(fill="both", pady=(8, 0))

    def say(msg):
        events.put(("log", msg))

    def refresh_fw():
        p = stock_path(s)
        if state["stock"] is not None:
            fw_status.config(text="Ready: %s (checksum verified)" % p, foreground="#262")
        elif os.path.exists(p):
            fw_status.config(text="Found %s, checking..." % p, foreground="#555")
        else:
            fw_status.config(text="Not downloaded yet.", foreground="#555")
        busy = state["busy"]
        b_build.state(["disabled"] if busy or state["stock"] is None else ["!disabled"])
        b_dl.state(["disabled"] if busy or state["stock"] is not None else ["!disabled"])
        b_pick.state(["disabled"] if busy else ["!disabled"])

    def work(fn, *a):
        state["busy"] = True
        refresh_fw()

        def run():
            try:
                events.put(("done", fn(*a)))
            except modcore.BuildError as e:
                events.put(("error", str(e)))
            except Exception as e:      # network errors, disk full, ...
                events.put(("error", "%s: %s" % (type(e).__name__, e)))
                traceback.print_exc()
        threading.Thread(target=run, daemon=True).start()

    def load(path):
        data = read_stock(path)
        state["stock"] = data
        s["stock"] = path
        save_settings(s)
        say("Firmware ready: %s" % path)
        return None

    def download():
        p = os.path.join(DATA_DIR, modcore.STOCK_NAME)
        os.makedirs(DATA_DIR, exist_ok=True)
        say("Asking OM's update server for the E-M1 Mark III firmware...")
        modcore.download_stock(p, lambda d, t: events.put(("progress", d * 100.0 / max(t, 1))))
        say("Downloaded and verified.")
        return load(p)

    def pick():
        p = filedialog.askopenfilename(title="Official E-M1 Mark III 1.6 firmware",
                                       filetypes=[("Firmware", "*.BIN *.bin"), ("All files", "*")])
        if p:
            work(load, p)

    def build():
        sel = {k for k, v in vars_.items() if v.get()}
        if not sel and not messagebox.askyesno(APP, "No mods selected. Build plain stock 1.6?"):
            return
        options = {}
        try:
            for (mid, name), (var, keymap) in opt_vars.items():
                options.setdefault(mid, {})[name] = (var.get().strip() if keymap == "text" else
                                                     keymap[var.get()] if keymap else float(var.get()))
        except ValueError:
            messagebox.showerror(APP, "Please enter a number for the options.")
            return
        s["mods"] = sorted(sel)
        s["out"] = out.get()
        s["options"] = options
        save_settings(s)
        work(lambda: ("built", do_build(state["stock"], pack, sel, VERSION, out.get(), say, options)))

    def card_file():
        keys = []
        for i in range(1, 7):
            var, keymap = opt_vars[("custom_looks", "look%d" % i)]
            keys.append(keymap[var.get()])
        root_dir = filedialog.askdirectory(title="SD card (top folder, next to DCIM)")
        if not root_dir:
            return
        try:
            write_card_file(root_dir, keys, say)
            messagebox.showinfo(APP, "Wrote EM1MOD/LOOKS.BIN with the six looks chosen under 'Film looks in Custom'.\n\n"
                                "The camera reads it at the first half-press after switching on (firmware built "
                                "with 'Load looks from SD card'), card in slot 1. Custom's list shows Look 1-6 in "
                                "the order of the six slots.")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP, str(e))

    b_card.config(command=card_file)
    b_dl.config(command=lambda: work(download))
    b_pick.config(command=pick)
    b_build.config(command=build)

    def poll():
        try:
            while True:
                kind, val = events.get_nowait()
                if kind == "log":
                    log.insert("end", val + "\n")
                    log.see("end")
                elif kind == "progress":
                    bar["value"] = val
                elif kind in ("done", "error"):
                    state["busy"] = False
                    if kind == "error":
                        log.insert("end", "Error: " + val + "\n")
                        log.see("end")
                        messagebox.showerror(APP, val)
                    elif isinstance(val, tuple) and val[0] == "built":
                        messagebox.showinfo(APP, "Saved %s\n\n%s" % (val[1], INSTALL))
                        reveal(val[1])
                    refresh_fw()
        except queue.Empty:
            pass
        root.after(100, poll)

    err = missing_dependency()
    if err:
        messagebox.showerror(APP, err)
        root.destroy()
        return 1
    refresh_fw()
    if os.path.exists(stock_path(s)):
        work(load, stock_path(s))
    poll()
    root.mainloop()
    return 0


def main(argv):
    # the windowed Windows .exe has no console: print() would fail on a None stream
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--cli" in argv or "--list" in argv or "--looks" in argv:
        return cli(argv)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter is not available; use --cli (see --help)")
        return 1
    return gui()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
