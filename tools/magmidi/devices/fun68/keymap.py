"""Read the FUN68 keymap: keymatrix layers 0–3 and the Fn tables (Win / Mac) of one profile. Read-only.

    PYTHONPATH=tools python3 -m magmidi.devices.fun68.keymap dump [--profile N] [--changed] [--raw] [-o keymap.yaml]

Protocol (monsgeek-akko-linux docs/PROTOCOL.md, monsgeek-transport/src/command.rs):
    GET_KEYMATRIX [8A profile FF page layer]   8 pages x 64 B = 128 entries x 4 B, index = col*6 + row
    GET_FN        [90 sys profile FF page]     sys 0 = Win, 1 = Mac; same paging
    Replies carry no command echo, so every layer is read twice and compared (hidraw can return a stale buffer).
    Layers: 0 = base, 1 = alternate (Fn+Alt), 2/3 = extra DKS outputs only. Layer ids > 3 are not bounds-checked
    by the firmware (layer 4 reads back a copy of layer 0), so they are never requested here.
Entry [type, b1, b2, b3]:
    00 key/chord (b1..b3 = up to three HID usages)   01 mouse (b2)   03 consumer (b2 | b3<<8)
    08 profile switch   09 macro (b1 kind, b2 index)   0A special fn (b1 sub; 01 = Fn)   0D LED control
    0E connection mode   12 knob/extended   15 gamepad
    00000000 = disabled in layer 0, transparent in layer 1..3 and Fn.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

from .layout import BY_INDEX, STOCK_HID
from .transport import DEV_FUN68, FUN68, hexdump, packet

from ...paths import ROOT, captures
PAGES = 8
FN_INDEX = 65
ENTRIES = PAGES * 64 // 4

HID = {0x28: "Enter", 0x29: "Esc", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Space", 0x2D: "-", 0x2E: "=", 0x2F: "[",
       0x30: "]", 0x31: "\\", 0x32: "#", 0x33: ";", 0x34: "'", 0x35: "`", 0x36: ",", 0x37: ".", 0x38: "/",
       0x39: "CapsLock", 0x46: "PrintScreen", 0x47: "ScrollLock", 0x48: "Pause", 0x49: "Insert", 0x4A: "Home",
       0x4B: "PageUp", 0x4C: "Delete", 0x4D: "End", 0x4E: "PageDown", 0x4F: "Right", 0x50: "Left", 0x51: "Down",
       0x52: "Up", 0x53: "NumLock", 0x65: "Menu", 0x64: "NonUS\\",
       0xE0: "LCtrl", 0xE1: "LShift", 0xE2: "LAlt", 0xE3: "LMeta", 0xE4: "RCtrl", 0xE5: "RShift", 0xE6: "RAlt",
       0xE7: "RMeta"}
HID.update({0x04 + i: chr(ord("A") + i) for i in range(26)})
HID.update({0x1E + i: str((i + 1) % 10) for i in range(10)})
HID.update({0x3A + i: f"F{i + 1}" for i in range(12)})
HID.update({0x68 + i: f"F{i + 13}" for i in range(12)})

CONSUMER = {0xB5: "Next Track", 0xB6: "Previous Track", 0xB7: "Stop", 0xCD: "Play/Pause", 0xE2: "Mute",
            0xE9: "Volume Up", 0xEA: "Volume Down", 0x6F: "Brightness Up", 0x70: "Brightness Down",
            0x183: "Media Player", 0x18A: "Mail", 0x192: "Calculator", 0x194: "My Computer", 0x221: "Search",
            0x223: "Browser Home"}
SPECIAL_FN = {1: "Fn", 2: "Game Mode", 3: "Win Lock", 8: "BT Pairing", 9: "Fn Toggle", 0x0A: "WASD Swap",
              0x0B: "NKRO Toggle", 0x0C: "Fn Lock", 0x0D: "Report Mode", 0x0E: "Knob Mode Toggle",
              0x17: "RCtrl Modifier"}
LED = {(2, 1, 0): "LED Brightness Up", (2, 2, 0): "LED Brightness Down", (3, 1, 0): "LED Speed Up",
       (3, 2, 0): "LED Speed Down"}
LED_WIDE = {1: "LED Mode Cycle", 5: "LED Direction", 6: "LED Layer Select"}


def hid_name(u: int) -> str:
    return HID.get(u, f"0x{u:02X}")


def describe(e: bytes) -> str:
    t, b1, b2, b3 = e
    if t == 0:
        keys = [hid_name(u) for u in (b1, b2, b3) if u]
        return "+".join(keys) if keys else "(none)"
    if t == 1:
        return f"Mouse{b2}"
    if t == 3:
        c = b2 | b3 << 8
        return CONSUMER.get(c, f"Consumer(0x{c:04X})")
    if t == 8:
        return {1: "Profile Next", 2: "Profile Prev", 3: "Profile Cycle"}.get(b2, f"Profile {b3 + 1}" if b2 == 4 else
                                                                             f"ProfileSwitch({b2},{b3})")
    if t == 9:
        return f"Macro({b2}{['', ',toggle', ',hold'][b1] if b1 < 3 else f',type{b1}'})"
    if t == 0x0A:
        if b1 == 5:
            return {0: "OS: Windows", 1: "OS: Mac", 2: "OS: iOS", 3: "OS: Cycle"}.get(b2, f"OS Mode({b2})")
        return SPECIAL_FN.get(b1, f"SpecialFn({b1},{b2},{b3})")
    if t == 0x0D:
        name = LED.get((b1, b2, b3)) or LED_WIDE.get(b1)
        if name and (b1, b2, b3) not in LED and (b2 or b3):
            name += f" ({b2},{b3})"
        return name or f"LedControl({b1},{b2},{b3})"
    if t == 0x0E:
        if b1 == 1:
            return {0: "Pair 2.4G", 1: "Pair BT"}.get(b2, f"Pair({b2})")
        return {0: "BT1", 1: "BT2", 2: "BT3", 5: "2.4GHz", 6: "USB"}.get(b2, f"Connection({b2})")
    if t == 0x15:
        return f"Gamepad({b2})"
    if t == 0x12:
        keys = "+".join(hid_name(u) for u in (b2, b3) if u)  # seen: 12 00 E3 2C on Mac Fn+4 (Cmd+Space)
        return f"type12({b1:02X}): {keys}"
    return f"type{t:02X}({b1:02X},{b2:02X},{b3:02X})"


def _read(kb: FUN68, make, settle: float = 0.02) -> bytes:
    data = b""
    for page in range(PAGES):
        kb.send(make(page))
        time.sleep(settle)
        data += kb.get()
    return data


def read_table(kb: FUN68, make) -> tuple[list[bytes], bytes]:
    """Read a paged table twice (no echo to validate against); retry with a longer settle on mismatch."""
    for settle in (0.02, 0.05, 0.1):
        a, b = _read(kb, make, settle), _read(kb, make, settle)
        if a == b:
            return [a[i * 4: i * 4 + 4] for i in range(ENTRIES)], a
    raise RuntimeError("keymap read unstable (two passes differ)")


def tables(profile: int):
    for layer in range(4):
        yield f"layer{layer}", lambda pg, layer=layer: packet(0x8A, profile, 0xFF, pg, layer)
    for sys_, name in ((0, "fn_win"), (1, "fn_mac")):
        yield name, lambda pg, sys_=sys_: packet(0x90, sys_, profile, 0xFF, pg)


def changed(table: str, idx: int, e: bytes) -> bool:
    if table == "layer0":
        if idx == FN_INDEX:
            return e != bytes([0x0A, 1, 0, 0])
        stock = STOCK_HID[idx] if idx < len(STOCK_HID) else 0
        return e != bytes([0, 0, stock, 0])
    return any(e)


def dump(args):
    result, raw = {}, []
    with FUN68(dev_id=DEV_FUN68) as kb:
        cur = kb.query(packet(0x84))
        profile = args.profile if args.profile is not None else (cur[1] if cur else 0)
        for name, make in tables(profile):
            entries, blob = read_table(kb, make)
            raw += [f"# profile {profile} {name}"] + [hexdump(blob[i:i + 64]) for i in range(0, len(blob), 64)]
            rows = []
            for idx, e in enumerate(entries):
                if idx not in BY_INDEX and not any(e):
                    continue
                rows.append({"idx": idx, "key": BY_INDEX.get(idx, f"slot{idx}"), "action": describe(e),
                             "raw": e.hex(), "changed": changed(name, idx, e)})
            result[name] = rows

    ts = time.strftime("%Y%m%d_%H%M%S")
    cap = captures("fun68") / f"keymap_{ts}.txt"
    cap.write_text("\n".join(raw) + "\n")

    print(f"profile {profile}" + (" (active)" if cur and cur[1] == profile else ""))
    for name, rows in result.items():
        n = sum(r["changed"] for r in rows)
        what = "differ from stock" if name == "layer0" else "non-empty"
        print(f"== {name}: {n} {what}")
        for r in rows:
            if args.changed and not r["changed"]:
                continue
            if name != "layer0" and not r["changed"] and not args.all:
                continue
            mark = "*" if r["changed"] else " "
            rawcol = f"  {r['raw']}" if args.raw else ""
            print(f" {mark} {r['idx']:3d} c{r['idx'] // 6:<2d}r{r['idx'] % 6} {r['key']:>9} -> {r['action']}{rawcol}")
    print(f"raw pages: {cap.relative_to(ROOT)}")

    if args.output:
        with open(args.output, "w") as f:
            f.write(f"# MonsGeek FUN68 keymap dump {ts}, profile {profile}; raw = type b1 b2 b3 (hex)\n")
            for name, rows in result.items():
                f.write(f"{name}:\n")
                for r in rows:
                    if name != "layer0" and not r["changed"]:
                        continue
                    key = r["key"].replace('"', '\\"')
                    act = r["action"].replace('"', '\\"')
                    f.write(f'  - {{idx: {r["idx"]}, key: "{key}", action: "{act}", raw: "{r["raw"]}"'
                            f', changed: {str(r["changed"]).lower()}}}\n')
        print(f"wrote {args.output}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="magmidi.devices.fun68.keymap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="read layers 0-3 and Fn tables (read-only)")
    d.add_argument("--profile", type=int, choices=range(4), help="default: active profile")
    d.add_argument("--changed", action="store_true", help="only entries that differ from stock / are non-empty")
    d.add_argument("--all", action="store_true", help="also list empty (transparent) entries of layers 1-3 / Fn")
    d.add_argument("--raw", action="store_true", help="show raw entry bytes")
    d.add_argument("-o", "--output", help="write YAML")
    a = ap.parse_args(argv)
    if a.cmd == "dump":
        dump(a)


if __name__ == "__main__":
    sys.exit(main())
