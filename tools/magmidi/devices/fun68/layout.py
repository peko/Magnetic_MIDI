"""FUN68 physical layout: matrix index (col*6 + row) -> key name and position in key units.

Matrix from monsgeek-akko-linux data/device_matrices.json, entry 12625:20528:2811
(ry5088_akko_fun68_8k_8k_3m, layout Common68_K80X68); snapshot in
vendor/fun68/monsgeek-akko-linux/data/device_matrices_fun68.json. Row 0 is unused. Fn (65) is not in that
matrix (stock entry `0A 01 00 00` = Fn) but has its own slot; whether it reports depth is unverified.
"""
from __future__ import annotations

# (index, name, width) left to right; x is accumulated, `None` name = gap of `width` units.
ROWS = [
    [(1, "Esc", 1), (7, "1", 1), (13, "2", 1), (19, "3", 1), (25, "4", 1), (31, "5", 1), (37, "6", 1),
     (43, "7", 1), (49, "8", 1), (55, "9", 1), (61, "0", 1), (67, "-", 1), (73, "=", 1),
     (79, "Backspace", 2), (85, "Home", 1)],
    [(2, "Tab", 1.5), (8, "Q", 1), (14, "W", 1), (20, "E", 1), (26, "R", 1), (32, "T", 1), (38, "Y", 1),
     (44, "U", 1), (50, "I", 1), (56, "O", 1), (62, "P", 1), (68, "[", 1), (74, "]", 1), (80, "\\", 1.5),
     (86, "Delete", 1)],
    [(3, "CapsLock", 1.75), (9, "A", 1), (15, "S", 1), (21, "D", 1), (27, "F", 1), (33, "G", 1), (39, "H", 1),
     (45, "J", 1), (51, "K", 1), (57, "L", 1), (63, ";", 1), (69, "'", 1), (81, "Enter", 2.25),
     (87, "PageUp", 1)],
    [(4, "LShift", 2.25), (16, "Z", 1), (22, "X", 1), (28, "C", 1), (34, "V", 1), (40, "B", 1), (46, "N", 1),
     (52, "M", 1), (58, ",", 1), (64, ".", 1), (70, "/", 1), (76, "RShift", 1.75), (82, "Up", 1),
     (88, "PageDown", 1)],
    [(5, "LCtrl", 1.25), (11, "LMeta", 1.25), (17, "LAlt", 1.25), (41, "Space", 6.25), (59, "RAlt", 1),
     (65, "Fn", 1), (71, "RCtrl", 1), (77, "Left", 1), (83, "Down", 1), (89, "Right", 1)],
]

KEYS: list[dict] = []
for y, row in enumerate(ROWS):
    x = 0.0
    for idx, name, w in row:
        if idx is not None:
            KEYS.append({"index": idx, "name": name, "x": x, "y": float(y), "width": float(w)})
        x += w

# Stock HID usage per matrix index (same source); 0 = no analog key.
STOCK_HID = [0, 41, 43, 57, 225, 224, 0, 30, 20, 4, 0, 227, 0, 31, 26, 22, 29, 226, 0, 32, 8, 7, 27, 0, 0, 33, 21, 9, 6, 0, 0, 34, 23, 10, 25, 0, 0, 35, 28, 11, 5, 44, 0, 36, 24, 13, 17, 0, 0, 37, 12, 14, 16, 0, 0, 38, 18, 15, 54, 230, 0, 39, 19, 51, 55, 0, 0, 45, 47, 52, 56, 228, 0, 46, 48, 0, 229, 80, 0, 42, 49, 40, 82, 81, 0, 74, 76, 75, 78, 79]

BY_NAME = {k["name"]: k["index"] for k in KEYS}
BY_INDEX = {k["index"]: k["name"] for k in KEYS}
