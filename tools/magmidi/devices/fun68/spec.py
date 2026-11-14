"""MonsGeek FUN68 HE backend: depth reports (cmd 0x1B) on the vendor event interface, raw units."""
from __future__ import annotations

import contextlib

from .layout import KEYS
from .stream import DepthStream
from .transport import FUN68, find_hidraw

NAME = "fun68"
TITLE = "MonsGeek FUN68"
PORT_NAME = "MonsGeek FUN68"
EVDEV_GLOB = "usb-*Monsgeek*event*"
UNIT_MM = None  # raw unit unconfirmed; probably 0.005 mm (driver DB travel step), i.e. 720 = 3.6 mm
DEFAULTS = {
    "full_travel": 720,  # bottom-out, measured 2026-11-14 (hard ceiling: 14 of 27 keys hit exactly 720)
    "vel_lo": 0.12,
    "vel_hi": 0.60,
    "release": 0.35,
    "quit_key": "Esc",
    "notes": {
        "Z": 0, "S": 1, "X": 2, "D": 3, "C": 4, "V": 5, "G": 6, "B": 7, "H": 8, "N": 9, "J": 10, "M": 11,
        ",": 12, "L": 13, ".": 14, ";": 15, "/": 16,
        "Q": 12, "2": 13, "W": 14, "3": 15, "E": 16, "R": 17, "5": 18, "T": 19, "6": 20, "Y": 21,
        "7": 22, "U": 23, "I": 24, "9": 25, "O": 26, "0": 27, "P": 28, "[": 29, "=": 30, "]": 31,
    },
}


def present() -> bool:
    try:
        find_hidraw(2)
        return True
    except FileNotFoundError:
        return False


def keys() -> list[dict]:
    return [dict(k) for k in KEYS]


@contextlib.contextmanager
def stream(indices, cfg=None, light=False, brightness=None):
    with contextlib.ExitStack() as stack:
        kb = stack.enter_context(FUN68())
        if light:
            from .light import NoteLighting, note_colours

            stack.enter_context(NoteLighting(kb, note_colours(cfg), brightness))
        yield stack.enter_context(DepthStream(kb))
