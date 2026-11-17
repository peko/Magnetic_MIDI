"""Magnetic keyboard → velocity-sensitive MIDI (CIDOO C80, MonsGeek FUN68).

    PYTHONPATH=tools .venv/bin/python -m magmidi.midi [--device auto|c80|fun68] [--config layout.yaml]
                                                     [--layout thirds|piano] [--scale major|minor|...]
                                                     [--no-grab] [--port-name NAME | --to FLUID] [--light] [--tui] [-v]

--tui draws the keyboard and a piano with the sounding notes (magmidi/tui.py); run it in a real terminal.

Layout "thirds" (default, see layouts.py): in-key, tonic under the resting fingers (left S, right J), adjacent
home-row keys a third apart (3 adjacent = triad), bottom row fills the steps, upper row = home row +1 octave; the
left hand plays an octave below the right. LAlt / RAlt held raise the left / right hand's notes by a semitone.
Layout "piano" uses the device's piano-style `notes` map.

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

from . import devices, layouts
from .velocity import DEFAULTS as VEL_DEFAULTS
from .velocity import KeyTracker, Thresholds

_NOTE_NAMES = "C C# D D# E F F# G G# A A# B".split()


def tui_note(n: int) -> str:
    return f"{_NOTE_NAMES[n % 12]}{n // 12 - 1}"

COMMON = {
    "channel": 0, "base_note": 48, "aftertouch": True,  # base_note 48 = C3
    "sustain_key": "Space",  # sustain pedal (CC64); null disables
    "sustain_inverted": True,  # sustain is on while the key is up; pressing it lifts the pedal (dampers)
    "transpose_keys": {"Up": 1, "Right": 1, "Down": -1, "Left": -1},  # semitones per press
    "shift_keys": ["LShift", "RShift", "L-Shift", "R-Shift"],  # held: transpose keys move by an octave
    "transpose_range": 48,  # max |transpose| in semitones
    "layout": "thirds",  # thirds (in-key, home row) | piano (device `notes` map)
    "scale": "major",  # for in-key layouts: see layouts.SCALES
    "sharp_keys": {"LAlt": "left", "RAlt": "right", "L-Alt": "left", "R-Alt": "right"},  # held: that hand +1 semitone
}


def load_config(device: str, path: str | None = None, **overrides) -> dict:
    """Merged config; for in-key layouts `notes` is generated and `hands` / `degrees` are added."""
    spec = devices.load(device)
    cfg = {**VEL_DEFAULTS, **COMMON, **spec.DEFAULTS}
    if path:
        import yaml

        cfg.update(yaml.safe_load(open(path)) or {})
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    if cfg["layout"] != "piano":
        try:
            cfg["notes"], cfg["hands"], cfg["degrees"] = layouts.build(
                cfg["layout"], cfg["scale"], [k["name"] for k in spec.keys()])
        except ValueError as e:
            sys.exit(str(e))
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(prog="magmidi.midi")
    ap.add_argument("--device", default="auto", help="auto (default), " + ", ".join(devices.NAMES))
    ap.add_argument("--config")
    ap.add_argument("--layout", choices=layouts.LAYOUTS, help="note layout (default: thirds)")
    ap.add_argument("--scale", choices=list(layouts.SCALES), help="scale for in-key layouts (default: major)")
    ap.add_argument("--no-grab", action="store_true", help="don't grab evdev (keys will also type)")
    ap.add_argument("--port-name", help="virtual MIDI port name (default: device name)")
    ap.add_argument("--light", action="store_true", help="colour the note keys while running")
    ap.add_argument("--brightness", type=int, help="lighting brightness 0-4 with --light")
    ap.add_argument("--tui", action="store_true", help="curses view: keyboard + piano with sounding notes")
    ap.add_argument("--to", metavar="NAME", help="connect straight to the MIDI input port containing NAME "
                    "(e.g. FLUID) instead of opening a virtual port")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # run the cleanup in `finally` on kill
    dev = devices.get(a.device)
    cfg = load_config(dev.NAME, a.config, layout=a.layout, scale=a.scale)

    import rtmidi

    names = {k["name"]: k["index"] for k in dev.keys()}
    unknown = [n for n in cfg["notes"] if n not in names]
    if unknown:
        sys.exit(f"unknown key names in notes map: {unknown}; valid: {sorted(names)}")
    notes = {names[n]: cfg["base_note"] + off for n, off in cfg["notes"].items()}
    keys = {idx: KeyTracker() for idx in notes}
    last_at = {idx: -1 for idx in notes}
    quit_idx = names.get(cfg["quit_key"])
    key_names = {i: n for n, i in names.items()}
    sus_idx = names.get(cfg.get("sustain_key") or "")
    if cfg.get("sustain_key") and sus_idx is None:
        sys.exit(f"unknown sustain_key {cfg['sustain_key']!r}")
    if sus_idx in notes:
        sys.exit(f"sustain_key {cfg['sustain_key']!r} is also mapped to a note")
    xpose_keys = {names[n]: int(d) for n, d in (cfg.get("transpose_keys") or {}).items() if n in names}
    shift_idx = {names[n] for n in cfg.get("shift_keys") or [] if n in names}
    sharp_of = {names[n]: h for n, h in (cfg.get("sharp_keys") or {}).items() if n in names}  # key idx -> hand
    hand_of = {names[n]: h for n, h in (cfg.get("hands") or {}).items()}  # note key idx -> hand
    clash = (set(xpose_keys) | shift_idx | set(sharp_of)) & (set(notes) | {quit_idx, sus_idx})
    if clash:
        sys.exit(f"transpose/shift/sharp keys overlap notes/quit/sustain: {sorted(clash)}")
    inverted = bool(cfg.get("sustain_inverted")) and sus_idx is not None
    pressed: dict[int, bool] = {}  # control keys with hysteresis (press >= release, let go < vel_lo)
    sustain = None
    transpose = 0
    playing: dict[int, int] = {}  # key index -> note actually sounding (survives transposition)
    depth: dict[int, int] = {}  # key index -> last raw travel (for --tui)
    vel: dict[int, int] = {}  # key index -> last strike velocity (for --tui)
    ringing: dict[int, float] = {}  # note -> release time, while held by the sustain pedal (for --tui)
    ui = None
    xrange = int(cfg.get("transpose_range", 48))
    port = a.port_name or dev.PORT_NAME

    out = rtmidi.MidiOut()
    if a.to:
        match = [i for i, p in enumerate(out.get_ports()) if a.to.lower() in p.lower()]
        if not match:
            sys.exit(f"no MIDI input port matching {a.to!r}; ports: {out.get_ports()}")
        port = out.get_ports()[match[0]]
        out.open_port(match[0])
    else:
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

    print(f"{dev.TITLE}: MIDI port '{port}' open; layout {cfg['layout']}"
          + (f" ({cfg['scale']})" if cfg["layout"] != "piano" else "")
          + f", {len(notes)} keys mapped; grabbed {len(grabbed)} evdev nodes. "
          f"Press {cfg['quit_key']} to quit."
          + (f" {cfg['sustain_key']} = sustain pedal{' (inverted)' if inverted else ''}." if sus_idx is not None else "")
          + (" Arrows: transpose ±1, Shift+arrows: ±12." if xpose_keys else "")
          + (" LAlt/RAlt: +1 semitone for that hand." if sharp_of and hand_of else ""), flush=True)

    def say(msg, always=False):
        if ui is not None:
            ui.log(msg)
        elif always or a.verbose:
            print(msg, flush=True)

    def note_for(idx):  # the note this key plays now (transposition + held sharp modifier of its hand)
        n = notes[idx] + transpose
        if any(pressed.get(i) for i, h in sharp_of.items() if h == hand_of.get(idx)):
            n += 1
        return n

    def set_sustain(on):
        nonlocal sustain
        if on != sustain:
            sustain = on
            out.send_message([0xB0 | ch, 64, 127 if on else 0])
            if not on:
                ringing.clear()
            say(f"sustain {'on' if on else 'off'}")

    def control(idx, v):  # -> True on the press edge
        was = pressed.get(idx, False)
        now = v >= th.lo if was else v >= th.rel
        pressed[idx] = now
        return now and not was

    def play(st):
        nonlocal transpose
        for t, idx, v in (st.events(timeout=0.02) if ui else st.events()):
            if ui:
                ui.tick(t, depth=depth, playing=playing, vel=vel, ringing=ringing, note_for=note_for,
                        base_notes=notes, transpose=transpose, sustain=sustain)
            if idx is None:
                continue
            depth[idx] = v
            if th.grow(v):
                say(f"full_travel -> {th.full}")
            if idx == quit_idx:
                if v >= th.hi:
                    return
                continue
            if idx == sus_idx:
                control(idx, v)
                set_sustain(pressed[idx] != inverted)
                continue
            if idx in shift_idx or idx in sharp_of:
                control(idx, v)
                continue
            if idx in xpose_keys:
                if control(idx, v):
                    step = xpose_keys[idx] * (12 if any(pressed.get(i) for i in shift_idx) else 1)
                    transpose = max(-xrange, min(xrange, transpose + step))
                    say(f"transpose {transpose:+d}", always=True)
                continue
            k = keys.get(idx)
            if k is None:
                continue
            ev = k.update(t, v, th, fast, slow)
            if ev and ev[0] == "on":
                note = note_for(idx)
                if not 0 <= note <= 127:
                    continue
                playing[idx] = note
                vel[idx] = ev[1]
                ringing.pop(note, None)
                out.send_message([0x90 | ch, note, ev[1]])
                last_at[idx] = -1
                if ui:
                    ui.log(f"{key_names[idx]:>3} → {tui_note(note):<4} v{ev[1]:<3} {ev[2]:5.1f}ms")
                elif a.verbose:
                    print(f"on  {note:3d} vel {ev[1]:3d} dt {ev[2]:6.1f}ms", flush=True)
            elif ev:
                note = playing.pop(idx, None)
                if note is None:
                    continue
                out.send_message([0x80 | ch, note, 64])
                if sustain:
                    ringing[note] = t
                if a.verbose and not ui:
                    print(f"off {note:3d}", flush=True)
            note = playing.get(idx)
            if note is not None and k.on and cfg["aftertouch"]:
                at = max(0, min(127, round(127 * (v - th.hi) / max(1, th.full - th.hi))))
                if at != last_at[idx]:
                    out.send_message([0xA0 | ch, note, at])
                    last_at[idx] = at

    try:
        indices = list(notes) + [i for i in (quit_idx, sus_idx) if i is not None] + list(xpose_keys) + list(shift_idx) + list(sharp_of)
        if sus_idx is not None:
            set_sustain(inverted)
        with dev.stream(indices, cfg, a.light, a.brightness) as st:
            if a.tui:
                import curses

                from .tui import BridgeTUI

                roles = {i: "note" for i in notes}
                roles.update({i: ("+1" if d > 0 else "-1") for i, d in xpose_keys.items()})
                roles.update({i: "×12" for i in shift_idx})
                roles.update({i: f"♯ {h[0].upper()}" for i, h in sharp_of.items()})
                if sus_idx is not None:
                    roles[sus_idx] = "pedal (inverted)" if inverted else "pedal"
                if quit_idx is not None:
                    roles[quit_idx] = "quit"

                def run_tui(scr):
                    nonlocal ui
                    ui = BridgeTUI(scr, dev, cfg, roles, th)
                    try:
                        play(st)
                    finally:
                        ui = None

                curses.wrapper(run_tui)
            else:
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
