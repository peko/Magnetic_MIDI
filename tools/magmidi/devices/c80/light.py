"""C80 lighting: global config and per-key custom colours (protocol from the web driver's light controller).

    PYTHONPATH=tools .venv/bin/python -m magmidi.devices.c80.light show               # config, mode list, custom colours (read-only)
    PYTHONPATH=tools .venv/bin/python -m magmidi.devices.c80.light notes [--config midi.yaml]   # colour the MIDI note keys
    PYTHONPATH=tools .venv/bin/python -m magmidi.devices.c80.light restore captures/c80/light_backup_<ts>.json

Protocol:
    [0A 00]                  -> mode list: data = modes..., speed_max, brightness_max (+2 more); custom = mode 10 if
                                 status data[12] bit 1 (isCustomLight)
    [07 01]                  -> config: mode bri speed fgR fgG fgB bgR bgG bgB dir fullColor power timer
    [07 00 00 00 0E cfg...]  set config (no reply); power 0 = ON, 1 = OFF (openLighting/closedLighting)
    [09 20]                  -> current custom layer in reply[1]
    [09 80|81]               -> custom colours of layer 0|1: pages 0..7, 18 keys x RGB per page (key = 18*page + i)
    [09 layer page len rgb]  write custom colours, 8 pages of <=54 bytes, each acked by [09 layer ...]

Custom colours are most likely stored in flash, so this is written once per session (not per note).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

from .transport import C80, packet

from ...paths import C80_LAYOUT_JSON, ROOT, VENDOR_C80, captures
N_KEYS = 132
PAGE_KEYS = 18
N_PAGES = 8
CUSTOM_MODE = 10
CFG_FIELDS = ("mode", "brightness", "speed", "fg_r", "fg_g", "fg_b", "bg_r", "bg_g", "bg_b",
              "direction", "full_color", "power", "timer")


def get_modes(kb: C80):
    r = kb.request(packet(0x0A), timeout=1.0)
    if r is None:
        return None
    n = r[4]
    d = list(r[5:5 + n])
    return {"modes": d[:n - 4], "tail": d[n - 4:], "max_speed": d[n - 2], "max_brightness": d[n - 1]}


def get_config(kb: C80) -> dict:
    r = kb.request(packet(0x07, flag=1), match=lambda p: p[0] == 0x07, timeout=1.0)
    if r is None:
        raise RuntimeError("no lighting config reply")
    return dict(zip(CFG_FIELDS, r[5:5 + len(CFG_FIELDS)]))


def set_config(kb: C80, cfg: dict):
    kb.send(packet(0x07, flag=0, length=14, data=[cfg[f] for f in CFG_FIELDS]))
    time.sleep(0.05)


def get_custom_layer(kb: C80) -> int | None:
    r = kb.request(packet(0x09, flag=0x20), match=lambda p: p[0] == 0x09 and p[1] not in (0x80, 0x81), timeout=1.0)
    return None if r is None else r[1]


def read_custom(kb: C80, layer: int) -> bytearray:
    flag = 0x80 | layer
    kb.drain()
    pkts: list[bytes] = kb.request(packet(0x09, flag=flag), match=lambda p: p[0] == 0x09 and p[1] == flag,  # type: ignore[assignment]
                                   timeout=1.5, collect=True, idle=0.3)
    buf = bytearray(N_KEYS * 3)
    pages = set()
    for p in pkts:
        page, n = p[2] << 8 | p[3], p[4]
        pages.add(page)
        for i in range(n // 3):
            k = PAGE_KEYS * page + i
            if k < N_KEYS:
                buf[3 * k:3 * k + 3] = p[5 + 3 * i:8 + 3 * i]
    if pages != set(range(N_PAGES)):
        raise RuntimeError(f"custom colour read incomplete: pages {sorted(pages)}")
    return buf


def write_custom(kb: C80, layer: int, buf: bytes) -> int:
    acked = 0
    kb.drain()
    for page in range(N_PAGES):
        chunk = buf[page * PAGE_KEYS * 3:(page + 1) * PAGE_KEYS * 3]
        r = kb.request(packet(0x09, flag=layer, page=page, length=len(chunk), data=chunk),
                       match=lambda p: p[0] == 0x09 and p[1] == layer, timeout=0.3)
        acked += r is not None
    return acked


# ---------------------------------------------------------------- note colouring
WHITE, BLACK, ROOT_C, OFF = (150, 150, 150), (0, 40, 255), (255, 40, 0), (0, 0, 0)
BLACK_PCS = {1, 3, 6, 8, 10}


PEDAL = (0, 255, 40)  # sustain key: green
CONTROL = (255, 160, 0)  # transpose arrows + shift: amber


def note_colours(midi_cfg: dict, layout: dict) -> bytearray:
    buf = bytearray(N_KEYS * 3)  # everything else off
    for name, off in midi_cfg["notes"].items():
        idx = layout[name]
        pc = (midi_cfg["base_note"] + off) % 12
        col = ROOT_C if pc == 0 else BLACK if pc in BLACK_PCS else WHITE
        buf[3 * idx:3 * idx + 3] = bytes(col)
    sp = layout.get(midi_cfg.get("sustain_key") or "")
    if sp is not None:
        buf[3 * sp:3 * sp + 3] = bytes(PEDAL)
    for name in list(midi_cfg.get("transpose_keys") or {}) + list(midi_cfg.get("shift_keys") or []):
        i = layout.get(name)
        if i is not None:
            buf[3 * i:3 * i + 3] = bytes(CONTROL)
    q = layout.get(midi_cfg.get("quit_key", ""))
    if q is not None:
        buf[3 * q:3 * q + 3] = bytes((255, 0, 0))
    return buf


class NoteLighting:
    """Context manager: back up lighting, show note colours, restore on exit."""

    def __init__(self, kb: C80, colours: bytes | bytearray, brightness: int | None = None, verbose=True):
        self.kb, self.colours, self.verbose = kb, bytes(colours), verbose
        self.brightness = brightness
        self.backup: dict | None = None

    def __enter__(self):
        kb = self.kb
        cfg = get_config(kb)
        layer = get_custom_layer(kb) or 0
        old = read_custom(kb, layer)
        self.backup = {"config": cfg, "layer": layer, "colours": old.hex()}
        bak = captures("c80") / f"light_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
        bak.write_text(json.dumps(self.backup, indent=1))
        kb.allow_unsafe = True
        acked = write_custom(kb, layer, self.colours)
        bri = self.brightness if self.brightness is not None else (cfg["brightness"] or 3)
        set_config(kb, dict(cfg, mode=CUSTOM_MODE, power=0, brightness=bri))
        if self.verbose:
            print(f"lighting: note colours on custom layer {layer} ({acked}/8 acked); backup {bak.relative_to(ROOT)}")
        return self

    def __exit__(self, *_exc):
        restore(self.kb, self.backup, self.verbose)


def restore(kb: C80, backup, verbose=True):
    if not backup:
        return
    kb.allow_unsafe = True
    acked = write_custom(kb, backup["layer"], bytes.fromhex(backup["colours"]))
    set_config(kb, backup["config"])
    if verbose:
        print(f"lighting restored (mode {backup['config']['mode']}, {acked}/8 colour pages acked)")


def _layout():
    return {k["name"]: int(k["index"]) for k in
            json.load(open(C80_LAYOUT_JSON))["keys"]}


def cmd_show(args):
    with C80(allow_unsafe=True) as kb:  # read-only requests below
        print("modes:", get_modes(kb))
        print("config:", get_config(kb))
        layer = get_custom_layer(kb)
        print("custom layer:", layer)
        names = {v: k for k, v in _layout().items()}
        for ly in (0, 1):
            buf = read_custom(kb, ly)
            lit = {names.get(i, i): buf[3 * i:3 * i + 3].hex() for i in range(N_KEYS) if any(buf[3 * i:3 * i + 3])}
            print(f"custom layer {ly}: {len(lit)} keys lit", lit if args.verbose else "")


def cmd_notes(args):
    from ...midi import load_config
    colours = note_colours(load_config("c80", args.config), _layout())
    with C80() as kb:
        nl = NoteLighting(kb, colours, args.brightness)
        nl.__enter__()
        print("note lighting stays on; undo with: python -m magmidi.devices.c80.light restore <backup file above>")


def cmd_restore(args):
    with C80() as kb:
        restore(kb, json.load(open(args.backup)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("-v", "--verbose", action="store_true")
    n = sub.add_parser("notes")
    n.add_argument("--config")
    n.add_argument("--brightness", type=int, help="0-4 while notes are shown (default: current, or 3 if 0)")
    r = sub.add_parser("restore")
    r.add_argument("backup")
    args = ap.parse_args()
    {"show": cmd_show, "notes": cmd_notes, "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    main()
