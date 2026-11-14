"""Magnetic keyboard → velocity-sensitive MIDI (CIDOO C80, MonsGeek FUN68).

    PYTHONPATH=tools .venv/bin/python -m magmidi.midi [--device auto|c80|fun68] [--config layout.yaml]
                                                     [--no-grab] [--port-name NAME] [--light] [-v]

Velocity = time to travel from `vel_lo` to `vel_hi` (fractions of `full_travel`), mapped logarithmically
between `fast_ms` (→127) and `slow_ms` (→1). Note-on fires at `vel_hi`; note-off when travel drops below
`release`. Travel beyond `vel_hi` is sent as polyphonic aftertouch. If a deeper value than `full_travel` is
seen, it grows to it (-v prints the new value). The sustain key (Space) works as a sustain pedal (CC64), pressed
once past `release`, released once back above `vel_lo`; with `sustain_inverted` (default) the pedal is down while
Space is up, and pressing Space lifts it. Arrows transpose by a semitone (Up/Right +1, Down/Left -1), Shift+arrow by
an octave; a held note keeps its pitch until released. Press the quit key (Esc) on the keyboard to quit; its evdev
nodes are grabbed so it doesn't type while you play.
--light colours the note keys for the session and restores the lighting on exit (C80: custom layer; FUN68: userpic
slot 4 + User Picture mode).
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

COMMON = {
    "channel": 0, "base_note": 48, "aftertouch": True,  # base_note 48 = C3
    "sustain_key": "Space",  # sustain pedal (CC64); null disables
    "sustain_inverted": True,  # sustain is on while the key is up; pressing it lifts the pedal (dampers)
    "transpose_keys": {"Up": 1, "Right": 1, "Down": -1, "Left": -1},  # semitones per press
    "shift_keys": ["LShift", "RShift", "L-Shift", "R-Shift"],  # held: transpose keys move by an octave
    "transpose_range": 48,  # max |transpose| in semitones
}


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
    ap.add_argument("--light", action="store_true", help="colour the note keys while running")
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
    sus_idx = names.get(cfg.get("sustain_key") or "")
    if cfg.get("sustain_key") and sus_idx is None:
        sys.exit(f"unknown sustain_key {cfg['sustain_key']!r}")
    if sus_idx in notes:
        sys.exit(f"sustain_key {cfg['sustain_key']!r} is also mapped to a note")
    xpose_keys = {names[n]: int(d) for n, d in (cfg.get("transpose_keys") or {}).items() if n in names}
    shift_idx = {names[n] for n in cfg.get("shift_keys") or [] if n in names}
    clash = (set(xpose_keys) | shift_idx) & (set(notes) | {quit_idx, sus_idx})
    if clash:
        sys.exit(f"transpose/shift keys overlap notes/quit/sustain: {sorted(clash)}")
    inverted = bool(cfg.get("sustain_inverted")) and sus_idx is not None
    pressed: dict[int, bool] = {}  # control keys with hysteresis (press >= release, let go < vel_lo)
    sustain = None
    transpose = 0
    playing: dict[int, int] = {}  # key index -> note actually sounding (survives transposition)
    xrange = int(cfg.get("transpose_range", 48))
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
          f"Press {cfg['quit_key']} to quit."
          + (f" {cfg['sustain_key']} = sustain pedal{' (inverted)' if inverted else ''}." if sus_idx is not None else "")
          + (" Arrows: transpose ±1, Shift+arrows: ±12." if xpose_keys else ""), flush=True)

    def set_sustain(on):
        nonlocal sustain
        if on != sustain:
            sustain = on
            out.send_message([0xB0 | ch, 64, 127 if on else 0])
            if a.verbose:
                print(f"sustain {'on' if on else 'off'}", flush=True)

    def control(idx, v):  # -> True on the press edge
        was = pressed.get(idx, False)
        now = v >= th.lo if was else v >= th.rel
        pressed[idx] = now
        return now and not was

    def play(st):
        nonlocal transpose
        for t, idx, v in st.events():
            if idx is None:
                continue
            if th.grow(v) and a.verbose:
                print(f"full_travel -> {th.full}", flush=True)
            if idx == quit_idx:
                if v >= th.hi:
                    return
                continue
            if idx == sus_idx:
                control(idx, v)
                set_sustain(pressed[idx] != inverted)
                continue
            if idx in shift_idx:
                control(idx, v)
                continue
            if idx in xpose_keys:
                if control(idx, v):
                    step = xpose_keys[idx] * (12 if any(pressed.get(i) for i in shift_idx) else 1)
                    transpose = max(-xrange, min(xrange, transpose + step))
                    print(f"transpose {transpose:+d}", flush=True)
                continue
            k = keys.get(idx)
            if k is None:
                continue
            ev = k.update(t, v, th, fast, slow)
            if ev and ev[0] == "on":
                note = notes[idx] + transpose
                if not 0 <= note <= 127:
                    continue
                playing[idx] = note
                out.send_message([0x90 | ch, note, ev[1]])
                last_at[idx] = -1
                if a.verbose:
                    print(f"on  {note:3d} vel {ev[1]:3d} dt {ev[2]:6.1f}ms", flush=True)
            elif ev:
                note = playing.pop(idx, None)
                if note is None:
                    continue
                out.send_message([0x80 | ch, note, 64])
                if a.verbose:
                    print(f"off {note:3d}", flush=True)
            note = playing.get(idx)
            if note is not None and k.on and cfg["aftertouch"]:
                at = max(0, min(127, round(127 * (v - th.hi) / max(1, th.full - th.hi))))
                if at != last_at[idx]:
                    out.send_message([0xA0 | ch, note, at])
                    last_at[idx] = at

    try:
        indices = list(notes) + [i for i in (quit_idx, sus_idx) if i is not None] + list(xpose_keys) + list(shift_idx)
        if sus_idx is not None:
            set_sustain(inverted)
        with dev.stream(indices, cfg, a.light, a.brightness) as st:
            play(st)
    except KeyboardInterrupt:
        pass
    finally:
        for note in playing.values():
            out.send_message([0x80 | ch, note, 0])
        out.send_message([0xB0 | ch, 64, 0])  # sustain up
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
