"""CIDOO C80 → velocity-sensitive MIDI.

    python -m c80.midi [--config layout.yaml] [--no-grab] [--port-name "CIDOO C80"] [--light]

Velocity = time to travel from `vel_lo` to `vel_hi` (0.01 mm units), mapped logarithmically
between `fast_ms` (→127) and `slow_ms` (→1). Note-on fires at `vel_hi`; note-off when
travel drops below `release`. Travel beyond `vel_hi` is sent as polyphonic aftertouch.
Press Esc on the C80 to quit (the keyboard is grabbed so it doesn't type while playing).
--light colours the note keys (C red, white keys white, sharps blue, quit key red) for the session and
restores the previous lighting on exit (two flash writes per session; see c80.light).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import pathlib
import sys

import rtmidi

from .stream import TravelStream
from .transport import C80

ROOT = pathlib.Path(__file__).resolve().parents[2]
LAYOUT_JSON = ROOT / "vendor/webdriver/config/keys/QK75EHEARGB.json"

DEFAULTS = {
    "channel": 0,
    "base_note": 48,  # C3
    "vel_lo": 40,  # 0.40 mm
    "vel_hi": 200,  # 2.00 mm  -> note on
    "release": 120,  # 1.20 mm  -> note off
    "max_travel": 340,
    "fast_ms": 4.0,
    "slow_ms": 200.0,
    "aftertouch": True,
    "quit_key": "Esc",
    # Two-row "tracker" layout: semitone offsets from base_note, keyed by web-driver key name.
    "notes": {
        "Z": 0, "S": 1, "X": 2, "D": 3, "C": 4, "V": 5, "G": 6, "B": 7, "H": 8, "N": 9, "J": 10, "M": 11,
        ",<": 12, "L": 13, ".>": 14, ";:": 15, "/?": 16,
        "Q": 12, "2@": 13, "W": 14, "3#": 15, "E": 16, "R": 17, "5%": 18, "T": 19, "6^": 20, "Y": 21,
        "7&": 22, "U": 23, "I": 24, "9(": 25, "O": 26, "0)": 27, "P": 28, "[{": 29, "=+": 30, "]}": 31,
    },
}


def load_config(path: str | None) -> dict:
    cfg = dict(DEFAULTS)
    if path:
        import yaml

        cfg.update(yaml.safe_load(open(path)) or {})
    return cfg


def velocity(dt_ms: float, fast: float, slow: float) -> int:
    if dt_ms <= fast:
        return 127
    if dt_ms >= slow:
        return 1
    x = (math.log(slow) - math.log(dt_ms)) / (math.log(slow) - math.log(fast))
    return max(1, min(127, round(1 + 126 * x)))


class Voice:
    __slots__ = ("note", "t_lo", "on", "prev", "last_at")
    t_lo: float | None
    prev: int

    def __init__(self, note: int):
        self.note, self.t_lo, self.on, self.prev, self.last_at = note, None, False, 0, -1


def _lighting(kb, cfg, names, a):
    if not a.light:
        return contextlib.nullcontext()
    from .light import NoteLighting, note_colours
    return NoteLighting(kb, note_colours(cfg, names), a.brightness)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--no-grab", action="store_true", help="don't grab evdev (keys will also type)")
    ap.add_argument("--port-name", default="CIDOO C80")
    ap.add_argument("--light", action="store_true", help="colour the note keys while running")
    ap.add_argument("--brightness", type=int, help="lighting brightness 0-4 with --light")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)

    names = {k["name"]: int(k["index"]) for k in json.load(open(LAYOUT_JSON))["keys"]}
    unknown = [n for n in cfg["notes"] if n not in names]
    if unknown:
        sys.exit(f"unknown key names in notes map: {unknown}; valid: {sorted(names)}")
    voices = {names[n]: Voice(cfg["base_note"] + off) for n, off in cfg["notes"].items()}
    quit_idx = names.get(cfg["quit_key"])

    out = rtmidi.MidiOut()
    out.open_virtual_port(a.port_name)
    ch = cfg["channel"] & 0x0F
    lo, hi, rel, mx = cfg["vel_lo"], cfg["vel_hi"], cfg["release"], cfg["max_travel"]

    grabbed = []
    if not a.no_grab:
        import evdev

        for p in sorted(pathlib.Path("/dev/input/by-id").glob("usb-2e3c_CIDOO_C80*event*")):
            d = evdev.InputDevice(str(p))
            d.grab()
            grabbed.append(d)

    print(f"MIDI port '{a.port_name}' open; {len(voices)} keys mapped; grabbed {len(grabbed)} evdev nodes. "
          f"Press {cfg['quit_key']} on the C80 to quit.", flush=True)
    try:
        with C80() as kb, _lighting(kb, cfg, names, a), \
                TravelStream(kb, list(voices) + ([quit_idx] if quit_idx is not None else [])) as st:
            for t, idx, v in st.events():
                if idx is None:
                    continue
                if idx == quit_idx:
                    if v >= hi:
                        break
                    continue
                vc = voices.get(idx)
                if vc is None:
                    continue
                if not vc.on:
                    if vc.prev < lo <= v or (vc.t_lo is None and lo <= v < hi and vc.prev == 0):
                        vc.t_lo = t
                    if v < lo:
                        vc.t_lo = None
                    if v >= hi:
                        dt = (t - vc.t_lo) * 1000 if vc.t_lo is not None else 0.0
                        vel = velocity(dt, cfg["fast_ms"], cfg["slow_ms"])
                        out.send_message([0x90 | ch, vc.note, vel])
                        vc.on, vc.t_lo, vc.last_at = True, None, -1
                        if a.verbose:
                            print(f"on  {vc.note:3d} vel {vel:3d} dt {dt:6.1f}ms", flush=True)
                if vc.on:
                    if v < rel:
                        out.send_message([0x80 | ch, vc.note, 64])
                        vc.on = False
                        if a.verbose:
                            print(f"off {vc.note:3d}", flush=True)
                    elif cfg["aftertouch"]:
                        at = max(0, min(127, round(127 * (v - hi) / max(1, mx - hi))))
                        if at != vc.last_at:
                            out.send_message([0xA0 | ch, vc.note, at])
                            vc.last_at = at
                vc.prev = v
    except KeyboardInterrupt:
        pass
    finally:
        for vc in voices.values():
            if vc.on:
                out.send_message([0x80 | ch, vc.note, 0])
        out.send_message([0xB0 | ch, 123, 0])  # all notes off
        for d in grabbed:
            try:
                d.ungrab()
            except OSError:
                pass
        out.close_port()
        print("bye")


if __name__ == "__main__":
    main()
