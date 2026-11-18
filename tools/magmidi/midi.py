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
import signal
import sys

from . import devices, layouts
from .bridge import Bridge, grab_keyboard, note_name, open_output, ungrab
from .velocity import DEFAULTS as VEL_DEFAULTS

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


PEDALS = ("inverted", "normal", "off")
PEDAL_HELP = ("Space as sustain pedal: inverted (default; sustain while Space is up), normal (sustain while held), "
              "off (Space does nothing; use for bowed/looped sounds such as a violin, which would ring forever)")


def load_config(device: str, path: str | None = None, **overrides) -> dict:
    """Merged config; for in-key layouts `notes` is generated and `hands` / `degrees` are added."""
    spec = devices.load(device)
    cfg = {**VEL_DEFAULTS, **COMMON, **spec.DEFAULTS}
    if path:
        import yaml

        cfg.update(yaml.safe_load(open(path)) or {})
    pedal = overrides.pop("pedal", None)
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    if pedal == "off":
        cfg["sustain_key"] = None
    elif pedal in ("normal", "inverted"):
        cfg["sustain_inverted"] = pedal == "inverted"
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
    ap.add_argument("--pedal", choices=PEDALS, help=PEDAL_HELP)
    ap.add_argument("--port-name", help="virtual MIDI port name (default: device name)")
    ap.add_argument("--to", metavar="NAME", help="connect straight to the MIDI input port containing NAME "
                    "(e.g. FLUID) instead of opening a virtual port")
    ap.add_argument("--light", action="store_true", help="colour the note keys while running")
    ap.add_argument("--brightness", type=int, help="lighting brightness 0-4 with --light")
    ap.add_argument("--tui", action="store_true", help="curses view: keyboard + piano with sounding notes")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # run the cleanup in `finally` on kill
    dev = devices.get(a.device)
    cfg = load_config(dev.NAME, a.config, layout=a.layout, scale=a.scale, pedal=a.pedal)
    out, port = open_output(a.port_name or dev.PORT_NAME, a.to)
    br = Bridge(dev, cfg, out)
    grabbed = [] if a.no_grab else grab_keyboard(dev)

    print(f"{dev.TITLE}: MIDI port '{port}' open; layout {cfg['layout']}"
          + (f" ({cfg['scale']})" if cfg["layout"] != "piano" else "")
          + f", {len(br.notes)} keys mapped; grabbed {len(grabbed)} evdev nodes. Press {cfg['quit_key']} to quit."
          + (f" {cfg['sustain_key']} = sustain pedal{' (inverted)' if br.inverted else ''}."
             if br.sus_idx is not None else "")
          + (" Arrows: transpose ±1, Shift+arrows: ±12." if br.xpose_keys else "")
          + (" LAlt/RAlt: +1 semitone for that hand." if br.sharp_of and br.hand_of else ""), flush=True)
    ui = None

    def report(evs):  # -> True to quit
        for ev in evs:
            kind = ev[0]
            if kind == "quit":
                return True
            if ui is not None:
                if kind == "on":
                    ui.log(f"{br.key_names[ev[1]]:>3} → {note_name(ev[2]):<4} v{ev[3]:<3} {ev[4]:5.1f}ms")
                elif kind == "transpose":
                    ui.log(f"transpose {ev[1]:+d}")
                elif kind == "sustain":
                    ui.log(f"sustain {'on' if ev[1] else 'off'}")
                elif kind == "full":
                    ui.log(f"full_travel -> {ev[1]}")
            elif kind == "on":
                if a.verbose:
                    print(f"on  {ev[2]:3d} vel {ev[3]:3d} dt {ev[4]:6.1f}ms", flush=True)
            elif kind == "off":
                if a.verbose:
                    print(f"off {ev[2]:3d}", flush=True)
            elif kind == "transpose":
                print(f"transpose {ev[1]:+d}", flush=True)
            elif a.verbose:
                print(f"{kind} {'on' if ev[1] is True else 'off' if ev[1] is False else ev[1]}", flush=True)
        return False

    def play(st):
        for t, idx, v in (st.events(timeout=0.02) if ui else st.events()):
            if ui:
                ui.tick(t, br)
            if idx is not None and report(br.handle(t, idx, v)):
                return

    try:
        report(br.start())
        with dev.stream(br.indices(), cfg, a.light, a.brightness) as st:
            if a.tui:
                import curses

                from .tui import BridgeTUI, roles_for

                def run_tui(scr):
                    nonlocal ui
                    ui = BridgeTUI(scr, dev, cfg, roles_for(br), br.th)
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
        br.all_off()
        ungrab(grabbed)
        out.close_port()
        print("bye")


if __name__ == "__main__":
    main()
