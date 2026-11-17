"""Key travel -> MIDI: the playing core shared by magmidi.midi and magmidi.trainer.

`Bridge.handle(t, idx, depth)` turns one travel report into MIDI (note on/off with strike velocity, aftertouch,
sustain) and returns what happened as small tuples, so front ends (plain log, --tui, trainer) only react to them:
    ("on", idx, note, velocity, dt_ms)   ("off", idx, note)   ("sustain", on)   ("transpose", n)
    ("full", full_travel)   ("press", key_name)   ("quit",)
"press" is the press edge of a key listed in `extra_keys` (the trainer's transport controls).
"""
from __future__ import annotations

import sys

from .velocity import KeyTracker, Thresholds

NOTE_NAMES = "C C# D D# E F F# G G# A A# B".split()


def note_name(n: int) -> str:
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


class Bridge:
    def __init__(self, dev, cfg: dict, out, *, extra_keys=(), transpose: int = 0):
        self.dev, self.cfg, self.out = dev, cfg, out
        names = {k["name"]: k["index"] for k in dev.keys()}
        self.names = names
        self.key_names = {i: n for n, i in names.items()}
        unknown = [n for n in cfg["notes"] if n not in names]
        if unknown:
            sys.exit(f"unknown key names in notes map: {unknown}; valid: {sorted(names)}")
        self.notes = {names[n]: cfg["base_note"] + off for n, off in cfg["notes"].items()}  # idx -> untransposed note
        self.trackers = {idx: KeyTracker() for idx in self.notes}
        self.quit_idx = names.get(cfg["quit_key"])
        self.sus_idx = names.get(cfg.get("sustain_key") or "")
        if cfg.get("sustain_key") and self.sus_idx is None:
            sys.exit(f"unknown sustain_key {cfg['sustain_key']!r}")
        if self.sus_idx in self.notes:
            sys.exit(f"sustain_key {cfg['sustain_key']!r} is also mapped to a note")
        self.xpose_keys = {names[n]: int(d) for n, d in (cfg.get("transpose_keys") or {}).items() if n in names}
        self.shift_idx = {names[n] for n in cfg.get("shift_keys") or [] if n in names}
        self.sharp_of = {names[n]: h for n, h in (cfg.get("sharp_keys") or {}).items() if n in names}  # idx -> hand
        self.hand_of = {names[n]: h for n, h in (cfg.get("hands") or {}).items()}  # note idx -> hand
        self.extra = {names[n]: n for n in extra_keys if n in names}  # idx -> name
        controls = set(self.xpose_keys) | self.shift_idx | set(self.sharp_of) | set(self.extra)
        clash = controls & (set(self.notes) | {self.quit_idx, self.sus_idx})
        if clash:
            sys.exit(f"control keys overlap notes/quit/sustain: {sorted(self.key_names[i] for i in clash)}")
        self.inverted = bool(cfg.get("sustain_inverted")) and self.sus_idx is not None
        self.th = Thresholds(cfg)
        self.ch = cfg["channel"] & 0x0F
        self.xrange = int(cfg.get("transpose_range", 48))
        self.transpose = transpose
        self.sustain = None
        self.pressed: dict[int, bool] = {}  # control keys, with hysteresis
        self.playing: dict[int, int] = {}  # idx -> note actually sounding (survives transposition)
        self.depth: dict[int, int] = {}  # idx -> last raw travel
        self.vel: dict[int, int] = {}  # idx -> last strike velocity
        self.ringing: dict[int, float] = {}  # note -> release time while the sustain pedal holds it
        self._last_at: dict[int, int] = {}

    # ---------------------------------------------------------------- queries
    def indices(self) -> list[int]:
        ctl = [i for i in (self.quit_idx, self.sus_idx) if i is not None]
        return list(self.notes) + ctl + list(self.xpose_keys) + list(self.shift_idx) + list(self.sharp_of) + list(self.extra)

    def shift_held(self) -> bool:
        return any(self.pressed.get(i) for i in self.shift_idx)

    def sharp_held(self, hand: str | None) -> bool:
        return any(self.pressed.get(i) for i, h in self.sharp_of.items() if h == hand)

    def note_for(self, idx: int) -> int:
        """The note this key plays now (transposition + held sharp modifier of its hand)."""
        return self.notes[idx] + self.transpose + (1 if self.sharp_held(self.hand_of.get(idx)) else 0)

    # ---------------------------------------------------------------- actions
    def start(self) -> list:
        return self._set_sustain(self.inverted) if self.sus_idx is not None else []

    def set_transpose(self, n: int):
        self.transpose = max(-self.xrange, min(self.xrange, n))

    def all_off(self):
        for note in self.playing.values():
            self.out.send_message([0x80 | self.ch, note, 0])
        self.playing.clear()
        self.out.send_message([0xB0 | self.ch, 64, 0])  # sustain up
        self.out.send_message([0xB0 | self.ch, 123, 0])  # all notes off

    def _set_sustain(self, on) -> list:
        if on == self.sustain:
            return []
        self.sustain = on
        self.out.send_message([0xB0 | self.ch, 64, 127 if on else 0])
        if not on:
            self.ringing.clear()
        return [("sustain", on)]

    def _control(self, idx, v) -> bool:  # -> True on the press edge
        was = self.pressed.get(idx, False)
        now = v >= self.th.lo if was else v >= self.th.rel
        self.pressed[idx] = now
        return now and not was

    def handle(self, t: float, idx: int, v: int) -> list:
        evs = []
        self.depth[idx] = v
        if self.th.grow(v):
            evs.append(("full", self.th.full))
        if idx == self.quit_idx:
            return evs + ([("quit",)] if v >= self.th.hi else [])
        if idx == self.sus_idx:
            self._control(idx, v)
            return evs + self._set_sustain(self.pressed[idx] != self.inverted)
        if idx in self.shift_idx or idx in self.sharp_of:
            self._control(idx, v)
            return evs
        if idx in self.extra:
            return evs + ([("press", self.extra[idx])] if self._control(idx, v) else [])
        if idx in self.xpose_keys:
            if self._control(idx, v):
                self.set_transpose(self.transpose + self.xpose_keys[idx] * (12 if self.shift_held() else 1))
                evs.append(("transpose", self.transpose))
            return evs
        k = self.trackers.get(idx)
        if k is None:
            return evs
        ev = k.update(t, v, self.th, self.cfg["fast_ms"], self.cfg["slow_ms"])
        if ev and ev[0] == "on":
            note = self.note_for(idx)
            if 0 <= note <= 127:
                self.playing[idx] = note
                self.vel[idx] = ev[1]
                self.ringing.pop(note, None)
                self.out.send_message([0x90 | self.ch, note, ev[1]])
                self._last_at[idx] = -1
                evs.append(("on", idx, note, ev[1], ev[2]))
        elif ev:
            note = self.playing.pop(idx, None)
            if note is not None:
                self.out.send_message([0x80 | self.ch, note, 64])
                if self.sustain:
                    self.ringing[note] = t
                evs.append(("off", idx, note))
        note = self.playing.get(idx)
        if note is not None and k.on and self.cfg["aftertouch"]:
            th = self.th
            at = max(0, min(127, round(127 * (v - th.hi) / max(1, th.full - th.hi))))
            if at != self._last_at.get(idx):
                self.out.send_message([0xA0 | self.ch, note, at])
                self._last_at[idx] = at
        return evs


def open_output(port_name: str, to: str | None):
    """-> (rtmidi.MidiOut, port label). `to`: connect straight to the input port containing that text."""
    import rtmidi

    out = rtmidi.MidiOut()
    if to:
        ports = out.get_ports()
        match = [i for i, p in enumerate(ports) if to.lower() in p.lower()]
        if not match:
            sys.exit(f"no MIDI input port matching {to!r}; ports: {ports}")
        out.open_port(match[0])
        return out, ports[match[0]]
    out.open_virtual_port(port_name)
    return out, port_name


def _wait_released(devs, timeout: float) -> bool:
    import time

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if not any(d.active_keys() for d in devs):
                return True
        except OSError:
            return True
        time.sleep(0.01)
    return False


def grab_keyboard(dev) -> list:
    """Grab the keyboard's evdev nodes so keys don't type while playing.

    Waits until no key is held first: if the Enter that launched us is still down when we grab, the desktop never
    sees its release and auto-repeats it into the terminal (a flood of newlines after exit)."""
    import pathlib

    import evdev

    devs = [evdev.InputDevice(str(p)) for p in sorted(pathlib.Path("/dev/input/by-id").glob(dev.EVDEV_GLOB))]
    _wait_released(devs, 3.0)
    for d in devs:
        d.grab()
    return devs


def ungrab(grabbed):
    """Release the grab once all keys are up (else the desktop sees a stray key-down, e.g. the quit key)."""
    _wait_released(grabbed, 3.0)
    for d in grabbed:
        try:
            d.ungrab()
        except OSError:
            pass
    flush_tty()


def flush_tty():
    """Drop anything typed into the terminal while we ran."""
    import sys
    import termios

    try:
        if sys.stdin.isatty():
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except (OSError, termios.error):
        pass
