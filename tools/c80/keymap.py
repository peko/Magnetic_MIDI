"""Read the C80 keymap (default + Fn layer) over the vendor protocol. Read-only.

    PYTHONPATH=tools .venv/bin/python -m c80.keymap dump [-o keymap.yaml] [--changed] [--raw]

Protocol (from the official web driver, `getLayoutKey` / `_fetchAllKeyData`):
    request  [18 80] (default layer) or [18 82] (Fn layer)
    reply    pages 0..9: [18 80|82 page_hi page_lo len  4 bytes per key ...], key index = 14*page + i
    entry    [code1, hidCode, code3, code4]; code1 selects the action type (see ACTION_TYPES)
             00000000 = not remapped (stock function / Fn-layer firmware default). The driver writes
             zeros for every key the user did not change.
Writing uses flag 0/1 instead of 0x80/0x82. Writes are blocked by transport.READ_ONLY_FLAGS.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from .transport import C80, hexdump, packet

ROOT = pathlib.Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "vendor/webdriver/config/keys/QK75EHEARGB.json"
FIXED = ROOT / "vendor/webdriver/config/keys.json"
LAYERS = {"default": 0x80, "fn": 0x82}
KEYS_PER_PAGE = 14
LAST_PAGE = 9

# code1 values (hex in keys.json) and their meaning
ACTION_TYPES = {
    0x00: "key", 0x02: "light-mode", 0x03: "brightness", 0x04: "light-speed", 0x05: "light-dir",
    0x06: "light-color", 0x07: "media", 0x10: "macro", 0x11: "lock", 0x12: "mouse", 0x13: "combo",
    0x18: "gamepad", 0x19: "xinput",
}
MODS = {0xE0: "Ctrl", 0xE1: "Shift", 0xE2: "Alt", 0xE3: "Win", 0xE4: "RCtrl", 0xE5: "RShift", 0xE6: "RAlt", 0xE7: "RWin"}


def load_layout():
    return {int(k["index"]): k for k in json.load(open(LAYOUT))["keys"]}


def load_fixed():
    """(code1, hid, code3) -> name, from the driver's config/keys.json (all fields hex)."""
    table = {}
    for group in json.load(open(FIXED))["keysConfig"]:
        for k in group["keys"]:
            c1, hid, c3 = (int(k[f], 16) for f in ("code1", "hidCode", "code3"))
            table.setdefault((c1, hid, c3), k["code"])
    return table


def read_layer(kb: C80, layer: str, timeout: float = 1.5):
    """Return ({index: (code1, hid, code3, code4)}, raw packets)."""
    flag = LAYERS[layer]
    kb.drain()
    pkts: list[bytes] = kb.request(  # type: ignore[assignment]
        packet(0x18, flag=flag), match=lambda p: p[0] == 0x18 and p[1] == flag,
        timeout=timeout, collect=True, idle=0.3)
    entries = {}
    pages = set()
    for p in pkts:
        page, n = p[2] << 8 | p[3], p[4]
        pages.add(page)
        for i in range(n // 4):
            entries[KEYS_PER_PAGE * page + i] = tuple(p[5 + 4 * i: 9 + 4 * i])
    missing = set(range(LAST_PAGE + 1)) - pages
    if missing:
        print(f"warning: {layer} layer missing pages {sorted(missing)}", file=sys.stderr)
    return entries, pkts


def describe(entry, fixed) -> str:
    c1, hid, c3, c4 = entry
    if entry == (0, 0, 0, 0):
        return "(stock)"
    if c1 == 0 and hid == 0xFA:
        return "Fn"
    if c1 == 0x12:  # mouse entries are stored as code1, code3, hid, code4
        hid, c3 = c3, hid
    name = fixed.get((c1, hid, c3)) or (fixed.get((c1, hid, 0)) if c1 not in (0x12, 0x13) else None)
    if name:
        return name
    if c1 == 0x13 and hid in MODS:
        k = fixed.get((0, c3, 0), f"0x{c3:02X}")
        return f"{MODS[hid]}+{k.removeprefix('Key').removeprefix('Digit')}"
    if c1 == 0x10:
        return f"macro#{c3}"
    return f"{ACTION_TYPES.get(c1, f'type{c1:02X}')}:{hid:02X}:{c3:02X}:{c4:02X}"


def dump(args):
    layout, fixed = load_layout(), load_fixed()
    result, raw = {}, []
    with C80() as kb:
        for layer in LAYERS:
            entries, pkts = read_layer(kb, layer)
            raw += [f"# {layer}"] + [hexdump(p) for p in pkts]
            rows = []
            for idx in sorted(layout):
                k = layout[idx]
                e = entries.get(idx)
                if e is None:
                    continue
                act = describe(e, fixed)
                changed = e != (0, 0, 0, 0)
                rows.append({"idx": idx, "key": k["name"] or f"slot{idx}", "action": act,
                             "raw": bytes(e).hex(), "changed": changed})
            extra = {i: e for i, e in entries.items() if i not in layout and e != (0, 0, 0, 0)}
            for i, e in sorted(extra.items()):
                rows.append({"idx": i, "key": f"(unused slot {i})", "action": describe(e, fixed),
                             "raw": bytes(e).hex(), "changed": True})
            result[layer] = rows

    ts = time.strftime("%Y%m%d_%H%M%S")
    cap = ROOT / f"captures/keymap_{ts}.txt"
    cap.write_text("\n".join(raw) + "\n")

    for layer, rows in result.items():
        shown = [r for r in rows if r["changed"]] if args.changed else rows
        n_changed = sum(r["changed"] for r in rows)
        print(f"== {layer} layer: {len(rows)} keys, {n_changed} remapped")
        for r in shown:
            mark = "*" if r["changed"] else " "
            rawcol = f"  {r['raw']}" if args.raw else ""
            print(f" {mark} {r['idx']:3d} r{r['idx'] // 22}c{r['idx'] % 22:<2d} {r['key']:>10} -> {r['action']}{rawcol}")
    print(f"raw packets: {cap.relative_to(ROOT)}")

    if args.output:
        with open(args.output, "w") as f:
            f.write(f"# CIDOO C80 keymap dump {ts}; raw = code1 hid code3 code4 (hex)\n")
            for layer, rows in result.items():
                f.write(f"{layer}:\n")
                for r in rows:
                    f.write("  - {" + ", ".join(f"{k}: {json.dumps(v)}" for k, v in r.items()) + "}\n")
        print(f"yaml: {args.output}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="read both layers")
    d.add_argument("-o", "--output", help="write YAML here")
    d.add_argument("--changed", action="store_true", help="only print keys that differ from stock")
    d.add_argument("--raw", action="store_true", help="also print raw 4-byte entries")
    args = ap.parse_args()
    {"dump": dump}[args.cmd](args)


if __name__ == "__main__":
    main()
