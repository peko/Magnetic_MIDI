"""Record the live travel stream of any supported keyboard and summarise it (for calibrating full_travel).

    python3 tools/scripts/depth_probe.py [--device auto|c80|fun68] [seconds]

Press keys all the way down a few times while it runs. Writes captures/<device>/depth_<ts>.txt
(`t_ms index depth` per event) and prints per-key maximum depth, bottom-out statistics and the
report cadence during movement.
"""
import argparse
import pathlib
import signal
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from magmidi import devices  # noqa: E402
from magmidi.paths import ROOT, captures  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seconds", nargs="?", type=float, default=30)
    ap.add_argument("--device", default="auto")
    a = ap.parse_args()
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    dev = devices.get(a.device)
    names = {k["index"]: k["name"] for k in dev.keys()}
    events = []
    t0 = time.monotonic()
    print(f"{dev.TITLE}: recording {a.seconds:.0f} s — press keys fully down several times", flush=True)
    try:
        with dev.stream(list(names)) as st:
            for t, idx, v in st.events(timeout=0.05):
                if t - t0 > a.seconds:
                    break
                if idx is not None:
                    events.append((t - t0, idx, v))
    except KeyboardInterrupt:
        pass
    out = captures(dev.NAME) / f"depth_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    out.write_text("".join(f"{t * 1000:.3f} {i} {v}\n" for t, i, v in events))
    print(f"{len(events)} events -> {out.relative_to(ROOT)}")
    if not events:
        return
    peak, last = {}, {}
    gaps, strokes = [], {}
    for t, i, v in events:
        peak[i] = max(peak.get(i, 0), v)
        if i in last and v and last[i][1] != v:
            gaps.append((t - last[i][0]) * 1000)
        last[i] = (t, v)
    # per-stroke maxima: a stroke ends when depth returns to 0
    cur = {}
    for t, i, v in events:
        if v:
            cur[i] = max(cur.get(i, 0), v)
        elif i in cur:
            strokes.setdefault(i, []).append(cur.pop(i))
    print("\nper key: max depth (stroke maxima)")
    for i in sorted(peak, key=lambda i: -peak[i]):
        print(f"  {names.get(i, i):>9} {peak[i]:5d}   {strokes.get(i, [])}")
    deep = sorted(peak.values())
    print(f"\nkey maxima: min {deep[0]}  median {statistics.median(deep)}  max {deep[-1]}  ({len(deep)} keys)")
    if gaps:
        g = sorted(gaps)
        q = lambda p: g[min(len(g) - 1, int(p * len(g)))]  # noqa: E731
        print(f"report gaps while moving (ms): min {g[0]:.2f}  p25 {q(.25):.2f}  median {q(.5):.2f}  p75 {q(.75):.2f}")
    values = sorted({v for _, _, v in events})
    small = [b - a for a, b in zip(values, values[1:])]
    print(f"distinct depth values: {len(values)}; smallest step {min(small) if small else '-'}")


if __name__ == "__main__":
    main()
