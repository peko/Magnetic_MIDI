"""Open a live stream (trigger test or ADC), log packets with timestamps, print stats.

usage: stream_probe.py trigger|adc [seconds]
Both modes are the same non-persistent test modes the official web driver uses; the
stream is always closed in `finally`.
"""
import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from magmidi.devices.c80 import C80, hexdump, packet  # noqa: E402

from magmidi.paths import C80_LAYOUT_JSON, ROOT, captures  # noqa: E402
mode = sys.argv[1]
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 10
layout = json.load(open(C80_LAYOUT_JSON))["keys"]
names = {int(k["index"]): k["name"] for k in layout}

if mode == "trigger":
    mask = bytearray(22)
    for i in names:
        mask[i % 22] |= 1 << (i // 22)
    open_pkt = packet(0x21, length=24, data=[0x02, *mask])
    close_pkt = packet(0x21, length=24, data=[0x03])
else:
    open_pkt = packet(0x23, data=[0x01])
    close_pkt = packet(0x23, data=[0x00])

log = open(captures("c80") / f"{mode}_{time.strftime('%Y%m%d_%H%M%S')}.txt", "w")
stats = collections.Counter()
travel = collections.defaultdict(list)
with C80() as kb:
    kb.drain()
    t0 = time.monotonic()
    kb.send(open_pkt)
    try:
        while time.monotonic() - t0 < secs:
            p = kb.recv(0.2)
            if p is None:
                continue
            t = time.monotonic() - t0
            log.write(f"{t:.6f} {hexdump(p)}\n")
            stats[p[0], p[5] if p[0] == 0x21 else p[3]] += 1
            if p[0] == 0x21 and p[5] == 0x01:
                idx = p[6] * 22 + p[7]
                travel[idx].append((t, p[9] << 8 | p[8]))
            elif p[0] == 0x23:
                row = p[3] - 1  # rows are 1-based on the wire
                vals = [p[5 + 2 * i] << 8 | p[6 + 2 * i] for i in range(22)]
                for c, v in enumerate(vals):
                    if row * 22 + c in names:
                        travel[row * 22 + c].append((t, v))
    finally:
        kb.send(close_pkt)
        time.sleep(0.1)
        kb.drain()
log.close()

print("packets by (cmd, sub/row):", dict(stats))
for idx, seq in sorted(travel.items()):
    vs = [v for _, v in seq]
    if mode == "adc" and max(vs) - min(vs) < 30:
        continue  # skip idle keys
    dts = [b[0] - a[0] for a, b in zip(seq, seq[1:])]
    rate = (len(seq) - 1) / (seq[-1][0] - seq[0][0]) if len(seq) > 1 and seq[-1][0] > seq[0][0] else 0
    print(f"{names.get(idx, idx):>8} n={len(seq):5d} min={min(vs):5d} max={max(vs):5d} "
          f"rate~{rate:7.1f}/s min_dt={min(dts) * 1000 if dts else 0:.2f}ms")
