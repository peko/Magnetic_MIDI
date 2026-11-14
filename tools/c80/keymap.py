"""Read / change the C80 keymap (default + Fn layer) over the vendor protocol.

    PYTHONPATH=tools .venv/bin/python -m c80.keymap dump [-o keymap.yaml] [--changed] [--raw]
    PYTHONPATH=tools .venv/bin/python -m c80.keymap set fn J F13      # one key; "stock" reverts it
    PYTHONPATH=tools .venv/bin/python -m c80.keymap restore captures/keymap_backup_<ts>.json

Protocol (from the official web driver, `getLayoutKey` / `_fetchAllKeyData`):
    request  [18 80] (default layer) or [18 82] (Fn layer)
    reply    pages 0..9: [18 80|82 page_hi page_lo len  4 bytes per key ...], key index = 14*page + i
    entry    [code1, hidCode, code3, code4]; code1 selects the action type (see ACTION_TYPES)
             00000000 = not remapped (stock function / Fn-layer firmware default). The driver writes
             zeros for every key the user did not change.
Write (`_sendKeyData`): the whole 528-byte layer (132 x 4) in 10 pages
    [18 layer page_hi page_lo len data<=56], layer 0 = default, 2 = Fn (read flag = 0x80 | layer),
    each page acked by [18 00|layer ...]; then poll [01] until bit 1 of reply[22] ("storing") clears.
`set` always reads the layer first, saves a backup, changes one entry, writes, and reads back to verify.
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
WRITE_FLAG = {"default": 0x00, "fn": 0x02}
N_SLOTS = 132
WRITE_CHUNK = 56
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


def encode(action: str) -> tuple:
    """Action name (driver `code`, e.g. KeyA, F13, AudioVolumeUp, MouseLeft), 'stock', 'Fn' or 8 hex digits."""
    if action.lower() == "stock":
        return (0, 0, 0, 0)
    if action == "Fn":
        return (0, 0xFA, 0, 0)
    if len(action) == 8 and all(c in "0123456789abcdefABCDEF" for c in action):
        return tuple(bytes.fromhex(action))
    for group in json.load(open(FIXED))["keysConfig"]:
        for k in group["keys"]:
            if k["code"].lower() == action.lower():
                c1, hid, c3, c4 = (int(k[f], 16) for f in ("code1", "hidCode", "code3", "code4"))
                if c1 == 0x10:
                    raise SystemExit("macros need a macro slot; use raw hex")
                return (c1, c3, hid, c4) if c1 == 0x12 else (c1, hid, c3, c4)
    raise SystemExit(f"unknown action {action!r} (see 'code' fields in {FIXED.relative_to(ROOT)})")


def find_key(key: str, layout) -> int:
    if key.isdigit():
        idx = int(key)
        if idx not in layout:
            raise SystemExit(f"index {idx} is not a key on this layout")
        return idx
    hits = [i for i, k in layout.items() if (k["name"] or "").lower() == key.lower()
            or (k.get("code") or "").lower() in (key.lower(), "key" + key.lower())]
    if len(hits) != 1:
        raise SystemExit(f"key {key!r} matches {len(hits)} layout keys; use the index from 'dump'")
    return hits[0]


def wait_storing(kb: C80, timeout=5.0, interval=0.06, settle=0.25):
    """Poll 0x01 until the 'storing to flash' bit (reply[22] & 2) has been seen and cleared."""
    t0, seen = time.monotonic(), False
    while time.monotonic() - t0 < timeout:
        r = kb.request(packet(0x01), timeout=0.3)
        if r is None:
            return seen, time.monotonic() - t0, "no status reply"
        busy = bool(r[22] & 2)
        seen |= busy
        if not busy and (seen or time.monotonic() - t0 >= settle):
            return seen, time.monotonic() - t0, "ok"
        time.sleep(interval)
    return seen, time.monotonic() - t0, "timeout"


def write_layer(kb: C80, layer: str, entries: dict) -> int:
    """Send the full layer. Returns the number of acked pages."""
    flag = WRITE_FLAG[layer]
    buf = bytearray(N_SLOTS * 4)
    for i, e in entries.items():
        buf[4 * i: 4 * i + 4] = bytes(e)
    acked = 0
    kb.drain()
    for page in range((len(buf) + WRITE_CHUNK - 1) // WRITE_CHUNK):
        chunk = buf[page * WRITE_CHUNK:(page + 1) * WRITE_CHUNK]
        r = kb.request(packet(0x18, flag=flag, page=page, length=len(chunk), data=chunk),
                       match=lambda p: p[0] == 0x18 and p[1] in (0, flag), timeout=0.3)
        acked += r is not None
    return acked


def _check_layout(entries, layer):
    if len(entries) != N_SLOTS:
        raise SystemExit(f"read of {layer} layer returned {len(entries)} slots, expected {N_SLOTS}; aborting")


def apply(layer: str, changes: dict[int, tuple], backup_note: str):
    fixed = load_fixed()
    with C80(allow_unsafe=True) as kb:  # 0x0B/0x14 stay blocked; this code only sends 0x18 and 0x01
        before, _ = read_layer(kb, layer)
        _check_layout(before, layer)
        ts = time.strftime("%Y%m%d_%H%M%S")
        bak = ROOT / f"captures/keymap_backup_{ts}.json"
        bak.write_text(json.dumps({"layer": layer, "note": backup_note,
                                   "entries": {i: bytes(e).hex() for i, e in sorted(before.items())}}, indent=0))
        print(f"backup: {bak.relative_to(ROOT)}")
        after = dict(before)
        for idx, e in changes.items():
            print(f"  {layer} idx {idx}: {describe(before[idx], fixed)} ({bytes(before[idx]).hex()})"
                  f" -> {describe(e, fixed)} ({bytes(e).hex()})")
            after[idx] = e
        if after == before:
            print("nothing to change")
            return
        acked = write_layer(kb, layer, after)
        seen, waited, status = wait_storing(kb)
        print(f"wrote 10 pages ({acked} acked); storing flag seen={seen}, {waited * 1000:.0f} ms, {status}")
        check, _ = read_layer(kb, layer)
        bad = {i for i in range(N_SLOTS) if check.get(i) != after[i]}
        if bad:
            print(f"VERIFY FAILED at {sorted(bad)}: " + ", ".join(
                f"{i}={bytes(check.get(i, ())).hex()}" for i in sorted(bad)))
            print(f"restore with: python -m c80.keymap restore {bak.relative_to(ROOT)}")
            raise SystemExit(1)
        print("verified: read-back matches")


def cmd_set(args):
    layout = load_layout()
    idx = find_key(args.key, layout)
    apply(args.layer, {idx: encode(args.action)}, f"before set {args.layer} {args.key} {args.action}")


def cmd_restore(args):
    d = json.load(open(args.backup))
    entries = {int(i): tuple(bytes.fromhex(h)) for i, h in d["entries"].items()}
    apply(d["layer"], entries, f"before restore of {args.backup}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="read both layers")
    d.add_argument("-o", "--output", help="write YAML here")
    d.add_argument("--changed", action="store_true", help="only print keys that differ from stock")
    d.add_argument("--raw", action="store_true", help="also print raw 4-byte entries")
    st = sub.add_parser("set", help="remap one key (reads, backs up, writes, verifies)")
    st.add_argument("layer", choices=list(LAYERS))
    st.add_argument("key", help="layout key name (as in dump) or index")
    st.add_argument("action", help="driver key code (KeyA, F13, AudioVolumeUp...), 'stock' or 8 hex digits")
    rs = sub.add_parser("restore", help="write a backup JSON back")
    rs.add_argument("backup")
    args = ap.parse_args()
    {"dump": dump, "set": cmd_set, "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    main()
