"""Magnetic keyboard → velocity-sensitive MIDI (CIDOO C80, MonsGeek FUN68).

    PYTHONPATH=tools .venv/bin/python -m magmidi.midi [--device auto|c80|fun68] [--config layout.yaml]
                                                     [--no-grab] [--port-name NAME] [--light] [-v]

Velocity = time to travel from `vel_lo` to `vel_hi` (fractions of `full_travel`), mapped logarithmically
between `fast_ms` (→127) and `slow_ms` (→1). Note-on fires at `vel_hi`; note-off when travel drops below
`release`. Travel beyond `vel_hi` is sent as polyphonic aftertouch. If a deeper value than `full_travel` is
seen, it grows to it (-v prints the new value). Press the quit key (Esc) on the keyboard to quit; its evdev
nodes are grabbed so it doesn't type while you play.
--light (C80 only) colours the note keys for the session and restores the lighting on exit.
Config keys: see velocity.DEFAULTS, COMMON below and the device's spec.DEFAULTS (notes map by layout key name).
"""
from __future__ import annotations

import argparse
import pathlib
import signal
import sys

from . import devices
from .velocity import DEFAULTS as VEL_DEFAULTS
from .velocity import KeyTracker, Thresholds

COMMON = {"channel": 0, "base_note": 48, "aftertouch": True}  # base_note 48 = C3


def load_config(device: str, path: str | None = None) -> dict:
    cfg = {**VEL_DEFAULTS, **COMMON, **devices.load(device).DEFAULTS}
    if path:
        import yaml

        cfg.update(yaml.safe_load(open(path)) or {})
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(prog="magmidi.midi")
    ap.add_argument("--device", default="auto", help="auto (default), " + ", ".join(devices.NAMES))
    ap.add_argument("--config")
    ap.add_argument("--no-grab", action="store_true", help="don't grab evdev (keys will also type)")
    ap.add_argument("--port-name", help="virtual MIDI port name (default: device name)")
    ap.add_argument("--light", action="store_true", help="colour the note keys while running (C80)")
    ap.add_argument("--brightness", type=int, help="lighting brightness 0-4 with --light")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # run the cleanup in `finally` on kill
    dev = devices.get(a.device)
    cfg = load_config(dev.NAME, a.config)

    import rtmidi

    names = {k["name"]: k["index"] for k in dev.keys()}
    unknown = [n for n in cfg["notes"] if n not in names]
    if unknown:
        sys.exit(f"unknown key names in notes map: {unknown}; valid: {sorted(names)}")
    notes = {names[n]: cfg["base_note"] + off for n, off in cfg["notes"].items()}
    keys = {idx: KeyTracker() for idx in notes}
    last_at = {idx: -1 for idx in notes}
    quit_idx = names.get(cfg["quit_key"])
    port = a.port_name or dev.PORT_NAME

    out = rtmidi.MidiOut()
    out.open_virtual_port(port)
    ch = cfg["channel"] & 0x0F
    th = Thresholds(cfg)
    fast, slow = cfg["fast_ms"], cfg["slow_ms"]

    grabbed = []
    if not a.no_grab:
        import evdev

        for p in sorted(pathlib.Path("/dev/input/by-id").glob(dev.EVDEV_GLOB)):
            d = evdev.InputDevice(str(p))
            d.grab()
            grabbed.append(d)

    print(f"{dev.TITLE}: MIDI port '{port}' open; {len(notes)} keys mapped; grabbed {len(grabbed)} evdev nodes. "
          f"Press {cfg['quit_key']} to quit.", flush=True)
    try:
        indices = list(notes) + ([quit_idx] if quit_idx is not None else [])
        with dev.stream(indices, cfg, a.light, a.brightness) as st:
            for t, idx, v in st.events():
                if idx is None:
                    continue
                if th.grow(v) and a.verbose:
                    print(f"full_travel -> {th.full}", flush=True)
                if idx == quit_idx:
                    if v >= th.hi:
                        break
                    continue
                k = keys.get(idx)
                if k is None:
                    continue
                note = notes[idx]
                ev = k.update(t, v, th, fast, slow)
                if ev and ev[0] == "on":
                    out.send_message([0x90 | ch, note, ev[1]])
                    last_at[idx] = -1
                    if a.verbose:
                        print(f"on  {note:3d} vel {ev[1]:3d} dt {ev[2]:6.1f}ms", flush=True)
                elif ev:
                    out.send_message([0x80 | ch, note, 64])
                    if a.verbose:
                        print(f"off {note:3d}", flush=True)
                if k.on and cfg["aftertouch"]:
                    at = max(0, min(127, round(127 * (v - th.hi) / max(1, th.full - th.hi))))
                    if at != last_at[idx]:
                        out.send_message([0xA0 | ch, note, at])
                        last_at[idx] = at
    except KeyboardInterrupt:
        pass
    finally:
        for idx, k in keys.items():
            if k.on:
                out.send_message([0x80 | ch, notes[idx], 0])
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
