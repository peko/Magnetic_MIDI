"""CIDOO C80 backend: live travel via the trigger-test stream (cmd 0x21), 0.01 mm units, 0..340."""
from __future__ import annotations

import contextlib
import json

from ...paths import C80_LAYOUT_JSON
from .stream import TravelStream
from .transport import C80, find_hidraw

NAME = "c80"
TITLE = "CIDOO C80"
PORT_NAME = "CIDOO C80"
EVDEV_GLOB = "usb-2e3c_CIDOO_C80*event*"
UNIT_MM = 0.01
FULL = 340
DEFAULTS = {
    "full_travel": FULL,
    "vel_lo": 40 / FULL,  # 0.40 mm
    "vel_hi": 200 / FULL,  # 2.00 mm -> note on
    "release": 120 / FULL,  # 1.20 mm -> note off
    "quit_key": "Esc",
    "notes": {
        "Z": 0, "S": 1, "X": 2, "D": 3, "C": 4, "V": 5, "G": 6, "B": 7, "H": 8, "N": 9, "J": 10, "M": 11,
        ",<": 12, "L": 13, ".>": 14, ";:": 15, "/?": 16,
        "Q": 12, "2@": 13, "W": 14, "3#": 15, "E": 16, "R": 17, "5%": 18, "T": 19, "6^": 20, "Y": 21,
        "7&": 22, "U": 23, "I": 24, "9(": 25, "O": 26, "0)": 27, "P": 28, "[{": 29, "=+": 30, "]}": 31,
    },
}

_PX, _ORIGIN = 37.5, 15.0  # web-driver layout: 35 px keys on a 37.5 px pitch, starting at 15 px


def present() -> bool:
    try:
        find_hidraw()
        return True
    except FileNotFoundError:
        return False


def keys() -> list[dict]:
    out = []
    for k in json.load(open(C80_LAYOUT_JSON))["keys"]:
        out.append({"index": int(k["index"]), "name": k["name"] or f"slot{k['index']}",
                    "x": (float(k["x"]) - _ORIGIN) / _PX, "y": (float(k["y"]) - _ORIGIN) / _PX,
                    "width": (float(k["width"]) + 2.5) / _PX})
    return out


@contextlib.contextmanager
def stream(indices, cfg=None, light=False, brightness=None):
    with contextlib.ExitStack() as stack:
        kb = stack.enter_context(C80())
        if light:
            from .light import NoteLighting, note_colours

            names = {k["name"]: k["index"] for k in keys()}
            stack.enter_context(NoteLighting(kb, note_colours(cfg, names), brightness))
        yield stack.enter_context(TravelStream(kb, list(indices)))
