"""Verify the matrix-index -> key mapping by correlating the travel stream with evdev key-downs.

usage: map_keys.py [seconds]   — type anything on the C80 while it runs (no grab).
For every evdev key-down, the matrix index whose travel most recently rose from 0 is taken as
its source. Prints the learned mapping and disagreements with the web-driver layout JSON.
"""
import collections
import json
import pathlib
import sys
import threading
import time

import evdev
from evdev import ecodes

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from magmidi.devices.c80 import C80  # noqa: E402
from magmidi.devices.c80.stream import TravelStream  # noqa: E402

from magmidi.paths import C80_LAYOUT_JSON, ROOT, captures  # noqa: E402
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30
layout = {int(k["index"]): k for k in json.load(open(C80_LAYOUT_JSON))["keys"]}

downs = []  # (t, evdev keyname)
stop = threading.Event()


def ev_reader():
    devs = [evdev.InputDevice(str(p)) for p in pathlib.Path("/dev/input/by-id").glob("usb-2e3c_CIDOO_C80*event*")]
    import select
    while not stop.is_set():
        r, _, _ = select.select(devs, [], [], 0.1)
        for d in r:
            for e in d.read():
                if e.type == ecodes.EV_KEY and e.value == 1:
                    name = ecodes.KEY.get(e.code, e.code)
                    downs.append((time.monotonic(), name if isinstance(name, str) else name[0]))


th = threading.Thread(target=ev_reader, daemon=True)
th.start()
rises = []  # (t, idx)
prev = collections.defaultdict(int)
print(f"type on the C80 for {secs:.0f}s ...", flush=True)
with C80() as kb, TravelStream(kb) as st:
    t0 = time.monotonic()
    for t, idx, v in st.events():
        if t - t0 > secs:
            break
        if idx is None:
            continue
        if prev[idx] == 0 and v > 0:
            rises.append((t, idx))
        prev[idx] = v
stop.set()
th.join()

votes = collections.defaultdict(collections.Counter)
for t, name in downs:
    cands = [(t - rt, idx) for rt, idx in rises if 0 <= t - rt < 0.25]
    if cands:
        votes[name][min(cands)[1]] += 1
print(f"{len(downs)} key-downs, {len(rises)} travel onsets")
for name, c in sorted(votes.items(), key=lambda kv: kv[1].most_common(1)[0][0]):
    idx, n = c.most_common(1)[0]
    js = layout.get(idx, {})
    hid_name = js.get("name", "?")
    print(f"  idx {idx:3d} (r{idx // 22} c{idx % 22:2d})  evdev {name:<16} json '{hid_name}' x{n}")
json.dump({n: c.most_common(1)[0][0] for n, c in votes.items()},
          open(captures("c80") / f"keymap_learned_{time.strftime('%Y%m%d_%H%M%S')}.json", "w"), indent=1)
