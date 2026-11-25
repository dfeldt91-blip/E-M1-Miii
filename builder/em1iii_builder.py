#!/usr/bin/env python3
"""E-M1 Mark III mod builder.

Downloads the official E-M1 Mark III firmware 1.6 from OM Digital Solutions' update server, lets you
pick mods and writes E1399999.BIN for the camera's card updater. Nothing of OM's firmware is stored
in this program: the mods are edit lists (builder/mods.json) applied to your own download.

  python3 builder/em1iii_builder.py                    window
  python3 builder/em1iii_builder.py --list             list the mods
  python3 builder/em1iii_builder.py --cli --mods panorama,hhrs_flash [--out DIR] [--version 1.601]
                                    [--stock FILE] [--frame-width 3] [--underwater-tint 0..4]
                                    [--owner-text "NAME PHONE"]
                                    [--curve1 "0:30 128:128 255:235"] [--curve2 ...]   Gradation Custom1/2 curves (in:out, 0-255)
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


# ---------------------------------------------------------------- command line

def cli(argv):
    import modcore
    err = missing_dependency()
    if err:
        print(err)
        return 1
    pack = modcore.load_pack(PACK)
    ids = [m["id"] for m in pack["mods"]]
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
        if arg("--owner-text"):
            options["owner_title"] = {"text": arg("--owner-text")}
        for i in (1, 2):
            if arg("--curve%d" % i):
                options.setdefault("art_gradation", {})["curve%d" % i] = arg("--curve%d" % i)
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


def curve_editor(root, var, title):
    """Tone curve editor: drag points, double-click to add, right-click to remove. Writes 'in:out' points
    (0-255) into VAR; the camera gets the smooth curve through them (tools/modcore.py)."""
    import tkinter as tk
    from tkinter import ttk
    import modcore
    S, P = 512, 24                       # canvas size, margin
    win = tk.Toplevel(root)
    win.title(title)
    try:
        pts = modcore.parse_curve_points(var.get())
    except Exception:
        pts = [(0, 0), (255, 255)]
    pts = [list(p) for p in pts]
    cv = tk.Canvas(win, width=S + 2 * P, height=S + 2 * P, bg=PALETTE.get("field", "white"))
    cv.pack(padx=8, pady=8)
    info = ttk.Label(win, text="")
    info.pack()
    sx = lambda x: P + x * S / 255.0                 # noqa: E731
    sy = lambda y: P + S - y * S / 255.0             # noqa: E731
    vx = lambda X: max(0, min(255, round((X - P) * 255.0 / S)))      # noqa: E731
    vy = lambda Y: max(0, min(255, round((P + S - Y) * 255.0 / S)))  # noqa: E731
    drag = {"i": None}

    def draw():
        cv.delete("all")
        for k in range(5):
            g = k * 255 / 4
            cv.create_line(sx(g), sy(0), sx(g), sy(255), fill="#ddd")
            cv.create_line(sx(0), sy(g), sx(255), sy(g), fill="#ddd")
        cv.create_line(sx(0), sy(0), sx(255), sy(255), fill="#bbb", dash=(3, 3))
        pts.sort()
        curve = modcore.curve_from_points([tuple(p) for p in pts])
        cv.create_line(*[c for x in range(256) for c in (sx(x), sy(curve[x] * 255 / 1023.0))], fill="#0a5", width=2)
        for x, y in pts:
            cv.create_oval(sx(x) - 5, sy(y) - 5, sx(x) + 5, sy(y) + 5, fill="#06c", outline="")
        info.config(text="  ".join("%d:%d" % tuple(p) for p in pts) +
                    "     drag points, double-click adds, right-click removes")

    def nearest(e):
        best = None
        for i, (x, y) in enumerate(pts):
            d = (sx(x) - e.x) ** 2 + (sy(y) - e.y) ** 2
            if d < 100 and (best is None or d < best[0]):
                best = (d, i)
        return None if best is None else best[1]

    def press(e):
        drag["i"] = nearest(e)

    def move(e):
        i = drag["i"]
        if i is None:
            return
        x, y = vx(e.x), vy(e.y)
        if pts[i][0] in (0, 255):          # end points move up and down only
            x = pts[i][0]
        elif any(j != i and p[0] == x for j, p in enumerate(pts)):
            return
        pts[i][:] = [x, y]
        draw()

    def add(e):
        x, y = vx(e.x), vy(e.y)
        if all(p[0] != x for p in pts):
            pts.append([x, y])
            draw()

    def remove(e):
        i = nearest(e)
        if i is not None and pts[i][0] not in (0, 255):
            del pts[i]
            draw()

    cv.bind("<ButtonPress-1>", press)
    cv.bind("<B1-Motion>", move)
    cv.bind("<ButtonRelease-1>", lambda e: drag.update(i=None))
    cv.bind("<Double-Button-1>", add)
    cv.bind("<Button-3>", remove)
    cv.bind("<Button-2>", remove)
    presets = {"Straight (no change)": [(0, 0), (255, 255)],
               "Soft contrast": [(0, 0), (64, 56), (192, 200), (255, 255)],
               "Strong contrast": [(0, 0), (64, 40), (192, 215), (255, 255)],
               "Faded (lifted blacks)": [(0, 32), (128, 128), (255, 240)],
               "Washed out, flat": [(0, 40), (64, 82), (192, 186), (255, 225)]}
    bar = ttk.Frame(win)
    bar.pack(fill="x", padx=8, pady=(0, 8))
    pv = tk.StringVar(value="Presets...")

    def preset(*_):
        if pv.get() in presets:
            pts[:] = [list(p) for p in presets[pv.get()]]
            draw()
    ttk.Combobox(bar, textvariable=pv, values=list(presets), state="readonly", width=22).pack(side="left")
    pv.trace_add("write", preset)

    def ok():
        pts.sort()
        var.set("" if pts == [[0, 0], [255, 255]] else " ".join("%d:%d" % tuple(p) for p in pts))
        win.destroy()
    ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(bar, text="OK", command=ok).pack(side="right", padx=6)
    draw()
    win.transient(root)
    win.grab_set()


def system_dark():
    """Best-effort OS light/dark detection (macOS, Windows, common Linux desktops)."""
    try:
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                 capture_output=True, text=True, timeout=2).stdout.strip().lower()
            return out == "dark"
        if sys.platform.startswith("win"):
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(val) == 0
        import subprocess
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=2).stdout.strip().lower()
        return "dark" in out
    except Exception:
        return False


PALETTE = {}


def palette_for(dark):
    if dark:
        return dict(bg="#141824", card="#1c2230", border="#2b3446", text="#e8ecf5",
                    muted="#9aa6bf", accent="#7c83ff", accent_active="#6873f0",
                    accent_text="#0b1020", success="#5bd68b", warn="#ffcc66",
                    error="#ff8080", log="#151b28", field="#232b3a", field_border="#3a465d")
    return dict(bg="#f4f6fb", card="#ffffff", border="#dfe4ee", text="#1c2333",
                muted="#64708a", accent="#4f46e5", accent_active="#4338ca",
                accent_text="#ffffff", success="#0f9d58", warn="#b26a00",
                error="#c62828", log="#fbfcfe", field="#ffffff", field_border="#cbd3e1")


def apply_theme(root):
    """One consistent, themeable look on macOS and Windows (ttk 'clam')."""
    import tkinter as tk
    from tkinter import ttk
    p = palette_for(system_dark())
    PALETTE.update(p)
    root.configure(bg=p["bg"])
    try:
        root.tk_setPalette(background=p["bg"], foreground=p["text"],
                           activeBackground=p["border"], activeForeground=p["text"],
                           selectBackground=p["accent"], selectForeground=p["accent_text"])
    except Exception:
        pass
    st = ttk.Style()
    names = st.theme_names()
    st.theme_use("clam" if "clam" in names else st.theme_use())
    font = ("Segoe UI", 10) if sys.platform.startswith("win") else ("Helvetica", 11)
    heading = (("Segoe UI Semibold", 20) if sys.platform.startswith("win")
               else ("Helvetica", 19, "bold"))
    title = (("Segoe UI Semibold", 12) if sys.platform.startswith("win")
             else ("Helvetica", 12, "bold"))
    small = (("Segoe UI Semibold", 10) if sys.platform.startswith("win")
             else ("Helvetica", 10, "bold"))
    st.configure(".", font=font, background=p["bg"], foreground=p["text"],
                 fieldbackground=p["field"], bordercolor=p["border"],
                 lightcolor=p["border"], darkcolor=p["border"], troughcolor=p["border"])
    st.configure("Root.TFrame", background=p["bg"])
    st.configure("Card.TFrame", background=p["card"])
    st.configure("H1.TLabel", background=p["bg"], foreground=p["text"], font=heading)
    st.configure("Sub.TLabel", background=p["bg"], foreground=p["muted"], font=font)
    st.configure("Warn.TLabel", background=p["bg"], foreground=p["warn"], font=font)
    st.configure("Badge.TLabel", background=p["accent"], foreground=p["accent_text"],
                 font=font, padding=(8, 3))
    st.configure("Card.TLabel", background=p["card"], foreground=p["text"], font=font)
    st.configure("CardTitle.TLabel", background=p["card"], foreground=p["text"], font=title)
    st.configure("CardMuted.TLabel", background=p["card"], foreground=p["muted"], font=font)
    st.configure("Count.TLabel", background=p["card"], foreground=p["accent"], font=small)
    st.configure("Card.TCheckbutton", background=p["card"], foreground=p["text"],
                 indicatorcolor=p["field"], bordercolor=p["field_border"],
                 lightcolor=p["card"], darkcolor=p["card"], focuscolor=p["card"])
    st.map("Card.TCheckbutton",
           indicatorcolor=[("selected", p["accent"]), ("pressed", p["accent_active"])],
           background=[("active", p["card"])], lightcolor=[("active", p["card"])])
    st.configure("TButton", background=p["card"], foreground=p["text"],
                 bordercolor=p["field_border"], lightcolor=p["card"], darkcolor=p["card"],
                 padding=(10, 6), font=font)
    st.map("TButton", background=[("active", p["border"]), ("disabled", p["card"])])
    st.configure("Accent.TButton", background=p["accent"], foreground=p["accent_text"],
                 borderwidth=0, focusthickness=0, focuscolor=p["accent"],
                 padding=(12, 7), font=small)
    st.map("Accent.TButton", background=[("active", p["accent_active"]), ("disabled", p["border"])],
           foreground=[("disabled", p["muted"])])
    st.configure("TEntry", fieldbackground=p["field"], foreground=p["text"],
                 insertcolor=p["text"], bordercolor=p["field_border"],
                 lightcolor=p["field_border"], darkcolor=p["field_border"])
    st.configure("TCombobox", fieldbackground=p["field"], foreground=p["text"],
                 selectbackground=p["accent"], selectforeground=p["accent_text"],
                 bordercolor=p["field_border"], lightcolor=p["field_border"],
                 darkcolor=p["field_border"])
    st.configure("TSpinbox", fieldbackground=p["field"], foreground=p["text"],
                 bordercolor=p["field_border"], lightcolor=p["field_border"],
                 darkcolor=p["field_border"])
    st.configure("Accent.Horizontal.TProgressbar", background=p["accent"],
                 troughcolor=p["border"], bordercolor=p["border"],
                 lightcolor=p["accent"], darkcolor=p["accent"])
    st.configure("Card.Vertical.TScrollbar", background=p["border"], troughcolor=p["card"],
                 bordercolor=p["card"], arrowcolor=p["muted"],
                 lightcolor=p["card"], darkcolor=p["card"])
    return p


def card(parent, title, subtitle=None):
    """A subtle 1 px bordered panel that follows the active theme."""
    import tkinter as tk
    from tkinter import ttk
    p = PALETTE
    outer = tk.Frame(parent, bg=p["border"], bd=0)
    inner = ttk.Frame(outer, style="Card.TFrame", padding=12)
    inner.pack(fill="both", expand=True)
    head = ttk.Frame(inner, style="Card.TFrame")
    head.pack(fill="x")
    ttk.Label(head, text=title, style="CardTitle.TLabel").pack(side="left")
    if subtitle:
        ttk.Label(head, text=subtitle, style="CardMuted.TLabel").pack(side="right")
    return outer, inner


def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import modcore

    root = tk.Tk()
    root.title(APP)
    root.minsize(900, 640)
    p = apply_theme(root)
    s = load_settings()
    pack = modcore.load_pack(PACK)
    events = queue.Queue()
    state = {"stock": None, "busy": False}

    outer = ttk.Frame(root, style="Root.TFrame", padding=16)
    outer.pack(fill="both", expand=True)

    header = ttk.Frame(outer, style="Root.TFrame")
    header.pack(fill="x")
    ttk.Label(header, text="E-M1 III Mod Builder", style="H1.TLabel").pack(side="left")
    ttk.Label(header, text="Build a modified E-M1 Mark III firmware 1.6", style="Sub.TLabel").pack(
        side="left", padx=(12, 0), pady=(8, 0))
    ttk.Label(header, text=("Dark theme" if system_dark() else "Light theme"),
              style="Badge.TLabel").pack(side="right")
    ttk.Label(outer, text=(
        "Unofficial. Flashing modified firmware is at your own risk; mods marked 'not tested' "
        "have never run on a camera."), style="Warn.TLabel", wraplength=860,
        justify="left").pack(anchor="w", pady=(6, 12))

    main = ttk.Frame(outer, style="Root.TFrame")
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=3)
    main.columnconfigure(1, weight=2)
    main.rowconfigure(0, weight=1)
    left = ttk.Frame(main, style="Root.TFrame")
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    right = ttk.Frame(main, style="Root.TFrame")
    right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    # --- left column: mods -------------------------------------------------
    mods_outer, mods = card(left, "Mods", subtitle="Choose what to change")
    mods_outer.pack(fill="both", expand=True)
    count = ttk.Label(mods, text="", style="Count.TLabel")
    count.pack(anchor="w", pady=(4, 6))
    canvas = tk.Canvas(mods, bg=p["card"], highlightthickness=0, height=360)
    sb = ttk.Scrollbar(mods, orient="vertical", command=canvas.yview,
                       style="Card.Vertical.TScrollbar")
    inner = ttk.Frame(canvas, style="Card.TFrame")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def wheel(e):
        if e.widget.winfo_class() in ("Entry", "TEntry", "TSpinbox", "Spinbox", "TCombobox", "Text"):
            return
        step = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
        canvas.yview_scroll(step * (1 if abs(getattr(e, "delta", 0)) < 120 else abs(e.delta) // 120), "units")
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind_all(seq, wheel)

    chosen = set(s.get("mods", []))
    vars_ = {}
    by_id = {m["id"]: m for m in pack["mods"]}

    def update_count():
        count.config(text="%d of %d selected" % (sum(v.get() for v in vars_.values()), len(pack["mods"])))

    def toggled(mid):
        if vars_[mid].get():
            for r in by_id[mid]["requires"]:
                vars_[r].set(True)
        else:
            for m in pack["mods"]:
                if mid in m["requires"]:
                    vars_[m["id"]].set(False)
        update_count()

    opt_vars = {}
    for i, m in enumerate(pack["mods"]):
        v = tk.BooleanVar(value=m["id"] in chosen)
        vars_[m["id"]] = v
        ttk.Checkbutton(inner, text=m["title"], variable=v, style="Card.TCheckbutton",
                        command=lambda k=m["id"]: toggled(k)).grid(
            row=2 * i, column=0, sticky="w", pady=(6, 0))
        note = m["description"] + "\n" + m["camera"]
        if m["requires"]:
            note += "  Needs: " + ", ".join(by_id[r]["title"] for r in m["requires"]) + "."
        ttk.Label(inner, text=note, style="CardMuted.TLabel", wraplength=520,
                  justify="left").grid(row=2 * i + 1, column=0, sticky="w", padx=(24, 0))
        if m["options"]:
            of = ttk.Frame(inner, style="Card.TFrame")
            of.grid(row=2 * i, column=0, sticky="e", padx=(0, 8))
            for name, o in m["options"].items():
                saved = s.get("options", {}).get(m["id"], {}).get(name, o["default"])
                if "choices" in o:
                    keys = [c[0] for c in o["choices"]]
                    labels = [c[1] for c in o["choices"]]
                    var = tk.StringVar(value=labels[keys.index(saved)] if saved in keys else labels[keys.index(o["default"])])
                    opt_vars[(m["id"], name)] = (var, dict(zip(labels, keys)))
                    ttk.Label(of, text=o["label"] + ":", style="CardMuted.TLabel").pack(side="top", anchor="e")
                    ttk.Combobox(of, textvariable=var, values=labels, state="readonly",
                                 width=16).pack(side="top", anchor="e", padx=4)
                    continue
                if o.get("text"):
                    var = tk.StringVar(value=str(saved))
                    opt_vars[(m["id"], name)] = (var, "text")
                    ttk.Label(of, text=o["label"] + ":", style="CardMuted.TLabel").pack(side="top", anchor="e")
                    ttk.Entry(of, textvariable=var, width=30).pack(side="top", anchor="e", padx=4)
                    if o.get("curve"):
                        ttk.Button(of, text="Edit curve...", style="TButton",
                                   command=lambda v=var, t=o["label"]: curve_editor(root, v, t)).pack(
                            side="top", anchor="e", padx=4)
                    continue
                var = tk.StringVar(value=str(saved))
                opt_vars[(m["id"], name)] = (var, None)
                ttk.Label(of, text=o["label"] + ":", style="CardMuted.TLabel").pack(side="left")
                ttk.Spinbox(of, textvariable=var, from_=o["min"], to=o["max"],
                            increment=o.get("step", 0.5), width=5).pack(side="left", padx=4)

    actions = ttk.Frame(inner, style="Card.TFrame")
    actions.grid(row=2 * len(pack["mods"]), column=0, sticky="w", pady=8)
    ttk.Button(actions, text="Select all", style="TButton",
               command=lambda: set_all(True)).pack(side="left")
    ttk.Button(actions, text="Select none", style="TButton",
               command=lambda: set_all(False)).pack(side="left", padx=8)

    def set_all(val):
        for v in vars_.values():
            v.set(val)
        update_count()

    update_count()

    # --- right column: firmware, build, activity ---------------------------
    fw_outer, fw = card(right, "Firmware", subtitle="Official 1.6")
    fw_outer.pack(fill="x", pady=(0, 8))
    fw_status = ttk.Label(fw, text="", style="CardMuted.TLabel", wraplength=300, justify="left")
    fw_status.pack(anchor="w")
    r1 = ttk.Frame(fw, style="Card.TFrame")
    r1.pack(fill="x", pady=(8, 0))
    b_dl = ttk.Button(r1, text="Download from OM", style="Accent.TButton")
    b_dl.pack(side="left")
    b_pick = ttk.Button(r1, text="Use my file", style="TButton")
    b_pick.pack(side="left", padx=6)
    bar = ttk.Progressbar(fw, length=100, mode="determinate",
                          style="Accent.Horizontal.TProgressbar")
    bar.pack(fill="x", pady=(8, 0))

    build_outer, bf = card(right, "Build")
    build_outer.pack(fill="x", pady=8)
    ttk.Label(bf, text="Save to", style="CardMuted.TLabel").pack(anchor="w")
    r2 = ttk.Frame(bf, style="Card.TFrame")
    r2.pack(fill="x", pady=(2, 0))
    out = tk.StringVar(value=s.get("out") or os.path.join(os.path.expanduser("~"), "E-M1III-firmware"))
    ttk.Entry(r2, textvariable=out, width=28).pack(side="left", fill="x", expand=True)
    ttk.Button(r2, text="Browse...", style="TButton",
               command=lambda: out.set(filedialog.askdirectory() or out.get())).pack(side="left", padx=(6, 0))
    b_build = ttk.Button(bf, text="Build E1399999.BIN", style="Accent.TButton")
    b_build.pack(fill="x", pady=(10, 0))
    ttk.Label(bf, text="Version 1.601", style="CardMuted.TLabel").pack(anchor="w", pady=(6, 0))

    log_outer, lf = card(right, "Activity")
    log_outer.pack(fill="both", expand=True)
    log = tk.Text(lf, height=8, wrap="word", bg=p["log"], fg=p["text"],
                  insertbackground=p["text"], relief="flat", borderwidth=1,
                  highlightbackground=p["border"], highlightcolor=p["border"],
                  font=("Menlo", 10) if sys.platform == "darwin" else ("Consolas", 9))
    lsb = tk.Scrollbar(lf, command=log.yview, bg=p["border"], troughcolor=p["card"],
                       activebackground=p["accent"], relief="flat", width=10)
    log.configure(yscrollcommand=lsb.set)
    log.pack(side="left", fill="both", expand=True)
    lsb.pack(side="right", fill="y")

    def say(msg):
        events.put(("log", msg))

    def refresh_fw():
        path = stock_path(s)
        if state["stock"] is not None:
            fw_status.config(text="Ready: %s (checksum verified)" % path, foreground=p["success"])
        elif os.path.exists(path):
            fw_status.config(text="Found %s, checking..." % path, foreground=p["muted"])
        else:
            fw_status.config(text="Not downloaded yet.", foreground=p["muted"])
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
        path = os.path.join(DATA_DIR, modcore.STOCK_NAME)
        os.makedirs(DATA_DIR, exist_ok=True)
        say("Asking OM's update server for the E-M1 Mark III firmware...")
        modcore.download_stock(path, lambda d, t: events.put(("progress", d * 100.0 / max(t, 1))))
        say("Downloaded and verified.")
        return load(path)

    def pick():
        path = filedialog.askopenfilename(title="Official E-M1 Mark III 1.6 firmware",
                                          filetypes=[("Firmware", "*.BIN *.bin"), ("All files", "*")])
        if path:
            work(load, path)

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
    if "--cli" in argv or "--list" in argv:
        return cli(argv)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter is not available; use --cli (see --help)")
        return 1
    return gui()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
