"""FUN68 lighting: LED params and per-key colours (userpic slots).

    PYTHONPATH=tools python3 -m magmidi.devices.fun68.light show [-v]        # params + userpic slots (read-only)
    PYTHONPATH=tools python3 -m magmidi.devices.fun68.light notes [--config midi.yaml] [--brightness N]
    PYTHONPATH=tools python3 -m magmidi.devices.fun68.light restore captures/fun68/light_backup_<ts>.json

Protocol (vendor/fun68/monsgeek-akko-linux, verified on this unit 2026-11-14):
    [87]                       -> 87 mode speed(inverted) brightness option R G B   (Bit7 checksum)
    [07 mode speed bri opt R G B]  set LED params (Bit8 checksum, no reply); persists
    [8C slot FF block]         -> 64 bytes of userpic `slot` (0-4); 6 blocks = 126 keys x RGB, index = col*6 + row
    [0C slot FF page len last 0] + rgb   write userpic, 7 pages of 56 B (last 42 B, last=1); persists
    Mode 13 = User Picture; option = slot << 4, colour bytes fixed to 00 C8 C8 (as the vendor app sends them).
Note lighting uses slot 4 (empty from the factory; slots 0-3 hold red presets) and is written only if it differs.
"""
from __future__ import annotations

import argparse
import json
import time

from ...paths import ROOT, captures
from .layout import BY_INDEX, BY_NAME
from .transport import FUN68, packet

N_KEYS = 126
USERPIC_BYTES = N_KEYS * 3
PAGE = 56
SLOTS = 5
NOTE_SLOT = 4
USER_PICTURE = 13
MODES = {0: "Off", 1: "Constant", 2: "Breathing", 3: "Neon", 4: "Wave", 5: "Ripple", 6: "Raindrop", 7: "Snake",
         8: "Reactive", 9: "Converge", 10: "Sine Wave", 11: "Kaleidoscope", 12: "Line Wave", 13: "User Picture",
         14: "Laser", 15: "Circle Wave", 16: "Rainbow", 17: "Rain Down", 18: "Meteor", 19: "Reactive Off",
         20: "Music Patterns", 21: "Screen Sync", 22: "Music Bars", 23: "Train", 24: "Fireworks", 25: "Per-Key Color"}


def get_params(kb: FUN68) -> list[int]:
    r = kb.query(packet(0x87))
    if r is None:
        raise RuntimeError("no reply to GET_LEDPARAM (0x87)")
    return list(r[1:8])


def set_params(kb: FUN68, raw: list[int]):
    kb.send(packet(0x07, *raw))
    time.sleep(0.05)


def describe(raw) -> str:
    mode, speed, bri, opt, r, g, b = raw
    extra = f"slot {opt >> 4}" if mode == USER_PICTURE else f"#{r:02x}{g:02x}{b:02x}" + (" dazzle" if opt & 0x0F == 8 else "")
    return f"{MODES.get(mode, mode)} (mode {mode}), brightness {bri}/4, speed {4 - min(speed, 4)}/4, {extra}"


def read_userpic(kb: FUN68, slot: int) -> bytes:
    for settle in (0.02, 0.05, 0.1):
        passes = []
        for _ in range(2):
            data = b""
            for block in range(-(-USERPIC_BYTES // 64)):
                kb.send(packet(0x8C, slot, 0xFF, block))
                time.sleep(settle)
                data += kb.get()
            passes.append(data[:USERPIC_BYTES])
        if passes[0] == passes[1]:
            return passes[0]
    raise RuntimeError("userpic read unstable (two passes differ)")


def write_userpic(kb: FUN68, slot: int, data: bytes):
    data = bytes(data[:USERPIC_BYTES]).ljust(USERPIC_BYTES, b"\0")
    pages = -(-USERPIC_BYTES // PAGE)
    for page in range(pages):
        chunk = data[page * PAGE:(page + 1) * PAGE]
        kb.send(packet(0x0C, slot, 0xFF, page, len(chunk), int(page == pages - 1), 0, payload=chunk))
        time.sleep(0.01)
    time.sleep(0.05)


# ---------------------------------------------------------------- note colouring
WHITE, BLACK, ROOT_C, QUIT = (150, 150, 150), (0, 40, 255), (255, 40, 0), (255, 0, 0)
BLACK_PCS = {1, 3, 6, 8, 10}


PEDAL = (0, 255, 40)  # sustain key: green
CONTROL = (255, 160, 0)  # transpose arrows + shift: amber


def note_colours(midi_cfg: dict) -> bytes:
    buf = bytearray(USERPIC_BYTES)
    for name, off in midi_cfg["notes"].items():
        idx = BY_NAME[name]
        pc = (midi_cfg["base_note"] + off) % 12
        buf[3 * idx:3 * idx + 3] = bytes(ROOT_C if pc == 0 else BLACK if pc in BLACK_PCS else WHITE)
    sp = BY_NAME.get(midi_cfg.get("sustain_key") or "")
    if sp is not None:
        buf[3 * sp:3 * sp + 3] = bytes(PEDAL)
    for name in list(midi_cfg.get("transpose_keys") or {}) + list(midi_cfg.get("shift_keys") or []):
        i = BY_NAME.get(name)
        if i is not None:
            buf[3 * i:3 * i + 3] = bytes(CONTROL)
    q = BY_NAME.get(midi_cfg.get("quit_key", ""))
    if q is not None:
        buf[3 * q:3 * q + 3] = bytes(QUIT)
    return bytes(buf)


class NoteLighting:
    """Context manager: back up LED params, show note colours from userpic slot 4, restore params on exit."""

    def __init__(self, kb: FUN68, colours: bytes, brightness: int | None = None, verbose=True):
        self.kb, self.colours, self.brightness, self.verbose = kb, colours, brightness, verbose
        self.backup: dict | None = None

    def __enter__(self):
        kb = self.kb
        params = get_params(kb)
        self.backup = {"params": params}
        bak = captures("fun68") / f"light_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
        bak.write_text(json.dumps(self.backup, indent=1))
        wrote = False
        if read_userpic(kb, NOTE_SLOT) != self.colours:
            write_userpic(kb, NOTE_SLOT, self.colours)
            wrote = True
            if read_userpic(kb, NOTE_SLOT) != self.colours:
                print("lighting: warning: userpic slot 4 read-back differs")
        bri = self.brightness if self.brightness is not None else (params[2] or 3)
        set_params(kb, [USER_PICTURE, params[1], bri, NOTE_SLOT << 4, 0, 200, 200])
        now = get_params(kb)
        if self.verbose:
            print(f"lighting: notes on userpic slot {NOTE_SLOT} ({'written' if wrote else 'unchanged, not rewritten'}); "
                  f"now {describe(now)}; was {describe(params)}; backup {bak.relative_to(ROOT)}")
        return self

    def __exit__(self, *_exc):
        restore(self.kb, self.backup, self.verbose)


def restore(kb: FUN68, backup, verbose=True):
    if not backup:
        return
    set_params(kb, backup["params"])
    now = get_params(kb)
    if verbose:
        ok = "ok" if now == backup["params"] else f"MISMATCH (now {now})"
        print(f"lighting restored: {describe(backup['params'])} — {ok}")


def cmd_show(args):
    with FUN68() as kb:
        print("LED:", describe(get_params(kb)))
        r = kb.query(packet(0x88))
        if r:
            print("side LED:", describe(list(r[1:8])))
        for slot in range(SLOTS):
            buf = read_userpic(kb, slot)
            lit = {BY_INDEX.get(i, i): buf[3 * i:3 * i + 3].hex() for i in range(N_KEYS) if any(buf[3 * i:3 * i + 3])}
            print(f"userpic slot {slot}: {len(lit)} keys lit", lit if args.verbose else "")


def cmd_notes(args):
    from ...midi import load_config

    with FUN68() as kb:
        NoteLighting(kb, note_colours(load_config("fun68", args.config)), args.brightness).__enter__()
        print("note lighting stays on; undo with: python -m magmidi.devices.fun68.light restore <backup file above>")


def cmd_restore(args):
    with FUN68() as kb:
        restore(kb, json.load(open(args.backup)))


def main():
    ap = argparse.ArgumentParser(prog="magmidi.devices.fun68.light", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("-v", "--verbose", action="store_true")
    n = sub.add_parser("notes")
    n.add_argument("--config")
    n.add_argument("--brightness", type=int, choices=range(5), help="0-4 (default: current, or 3 if 0)")
    r = sub.add_parser("restore")
    r.add_argument("backup")
    args = ap.parse_args()
    {"show": cmd_show, "notes": cmd_notes, "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    main()
