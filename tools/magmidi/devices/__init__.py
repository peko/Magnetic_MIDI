"""Device registry. Each backend exposes a `spec` module with the same interface:

    NAME, TITLE, PORT_NAME, EVDEV_GLOB, UNIT_MM (mm per raw depth unit, or None if unknown), DEFAULTS (dict)
    present() -> bool                      device is connected
    keys() -> list[{index, name, x, y, width}]   physical layout in key units (1u = one standard key)
    stream(indices, cfg=None, light=False, brightness=None)
        context manager yielding a stream whose events(timeout) yields (t, index, depth) or (t, None, None)
"""
from __future__ import annotations

import importlib

NAMES = ("c80", "fun68", "mars68")


def load(name: str):
    if name not in NAMES:
        raise SystemExit(f"unknown device {name!r}; known: {', '.join(NAMES)}")
    return importlib.import_module(f"{__name__}.{name}.spec")


def detect():
    """Return the spec of the first connected device."""
    found = [n for n in NAMES if load(n).present()]
    if not found:
        raise SystemExit(f"no supported keyboard found ({', '.join(NAMES)})")
    if len(found) > 1:
        print(f"several keyboards connected ({', '.join(found)}); using {found[0]} (pick with --device)")
    return load(found[0])


def get(name: str | None):
    if name in (None, "auto"):
        return detect()
    spec = load(name)
    if not spec.present():
        raise SystemExit(f"{spec.TITLE} is not connected")
    return spec
