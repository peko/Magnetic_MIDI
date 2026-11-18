"""CAROTMAS Mars68 PRO backend: the FUN68 (RY5088) depth stream with this model's travel range.

Shares VID:PID 3151:5030 with the FUN68; told apart by dev_id 2431 from GET_USB_VERSION 0x8F (fw 0x0306 seen).
Checked 2026-11-18: the letter rows and Esc report the same matrix indices as the FUN68 layout; full travel is
0..350 raw; the arrows and Space still need a mapping check. Lighting writes are not enabled for this model.
"""
from __future__ import annotations

import contextlib

from ..fun68.layout import KEYS
from ..fun68.spec import DEFAULTS as FUN68_DEFAULTS
from ..fun68.stream import DepthStream
from ..fun68.transport import DEV_MARS68, FUN68, find_board

NAME = "mars68"
DEV_ID = DEV_MARS68
TITLE = "CAROTMAS Mars68 PRO"
PORT_NAME = "Mars68 PRO"
EVDEV_GLOB = "usb-*Mars68*event*"
UNIT_MM = None  # unconfirmed; 350 raw at bottom-out looks like 0.01 mm (3.5 mm travel)
DEFAULTS = {
    **FUN68_DEFAULTS,
    "full_travel": 350,  # bottom-out, measured 2026-11-18: 33 of 35 keys hit exactly 350
}


def present() -> bool:
    try:
        find_board(DEV_ID)
        return True
    except FileNotFoundError:
        return False


def keys() -> list[dict]:
    return [dict(k) for k in KEYS]


@contextlib.contextmanager
def stream(indices, cfg=None, light=False, brightness=None):
    if light:
        raise SystemExit("--light is not verified on the Mars68 PRO (LED writes go to flash); run without it")
    with contextlib.ExitStack() as stack:
        kb = stack.enter_context(FUN68(dev_id=DEV_ID))
        yield stack.enter_context(DepthStream(kb))
