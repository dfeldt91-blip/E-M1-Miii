"""Designed Gradation curve set (tools/patch_art_gradation.py): washed out -> contrasty.

Each entry: (camera label, in:out points 0..255, string id). The labels replace, in English only and
in place, camera strings of features this body does not have (Color Profile, Monochrome Profile,
Film Grain Effect, Mono Profile); a label must not be longer than the string it replaces.
Curves are the smooth monotone curve through the points (tools/modcore.py curve_from_points).
"""
SET = [
    ("Faded Matte",    "0:56 64:92 128:132 192:180 255:215",  0xabd),
    ("Washed Out",     "0:44 64:84 128:130 192:182 255:225",  0xabe),
    ("Soft Matte",     "0:36 64:76 128:128 192:186 255:232",  0xabf),
    ("Airy Pastel",    "0:30 64:90 128:150 192:205 255:240",  0xac0),
    ("Low Con Film",   "0:24 64:70 128:128 192:190 255:240",  0xac1),
    ("Faded Blacks",   "0:32 64:66 128:126 192:192 255:252",  0xac2),
    ("Cine Rolloff",   "0:12 64:62 128:130 192:194 255:238",  0xac5),
    ("Matte S Curve",        "0:20 64:58 128:128 192:200 255:248",  0xac6),
    ("Neutral Soft",   "0:6 64:60 128:128 192:198 255:252",   0xac7),
    ("Bright Open",    "0:8 48:56 128:142 192:204 255:255",   0xac8),
    ("Soft S Curve",         "0:4 64:56 128:130 192:206 255:255",   0xac9),
    ("Film S Curve",         "0:0 64:50 128:128 192:208 255:255",   0xaca),
    ("Crisp",          "0:0 64:44 128:128 192:214 255:255",   0xad4),
    ("Dark Moody",     "0:0 64:36 128:108 192:184 255:240",   0xad5),
    ("Punchy S Curve",       "0:0 64:38 128:128 192:220 255:255",   0xad6),
    ("Slide Film",     "0:0 48:20 128:122 192:218 255:255",   0xad7),
    ("Hard S Curve",         "0:0 64:30 128:128 192:228 255:255",   0xad8),
    ("Crushed Silver", "0:0 40:8 128:132 192:222 255:246",    0xb2e),
    ("Graphic",        "0:0 64:18 128:128 192:240 255:255",   0xb2f),
]
# stock text of those strings (checked before replacing)
STOCK_TEXT = {
    0xabd: "Color Profile 1", 0xabe: "Color Profile 2", 0xabf: "Color Profile 3",
    0xac0: "@A0B2@Color Profile 1", 0xac1: "@A0B3@Color Profile 2", 0xac2: "@A0B4@Color Profile 3",
    0xac5: "Monochrome Profile 1", 0xac6: "Monochrome Profile 2", 0xac7: "Monochrome Profile 3",
    0xac8: "@A0B5@Monochrome Profile 1", 0xac9: "@A0B6@Monochrome Profile 2", 0xaca: "@A0B7@Monochrome Profile 3",
    0xad4: "Film Grain Effect", 0xad5: "Film Grain Effect Off", 0xad6: "Film Grain Effect Low",
    0xad7: "Film Grain Effect Medium", 0xad8: "Film Grain Effect High",
    0xb2e: "Mono Profile 1", 0xb2f: "Mono Profile 2",
}
