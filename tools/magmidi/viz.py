"""Live terminal visualisation of key travel and strike velocity (CIDOO C80, MonsGeek FUN68).

    python3 tools/viz.py [--device auto|c80|fun68|mars68]   (Esc or Ctrl+C to quit)

Each key is drawn at its physical position. Its fill colour and the bar under its name show the current
travel relative to full travel. The number shows the velocity (1–127) of that key's last strike, using the
same model as magmidi.midi. The bottom panel lists recent strikes. The title shows the event rate, the
deepest raw value seen ("max raw"), the smallest gap between reports and the current full travel.
The keyboard is not grabbed, so keys still type; the program ignores that input.
"""
from __future__ import annotations

import argparse
import collections
import curses
import os
import time

from . import devices
from .midi import load_config
from .velocity import KeyTracker, Thresholds

BLOCKS = " ▁▂▃▄▅▆▇█"
LEVELS = 8


def setup_colors():
    curses.start_color()
    curses.use_default_colors()
    ramp256 = [236, 24, 30, 36, 70, 142, 178, 208, 196]
    ramp8 = [curses.COLOR_BLACK, curses.COLOR_BLUE, curses.COLOR_CYAN, curses.COLOR_CYAN, curses.COLOR_GREEN,
             curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_YELLOW, curses.COLOR_RED]
    ramp = ramp256 if curses.COLORS >= 256 else ramp8
    for i, bg in enumerate(ramp):
        curses.init_pair(1 + i, curses.COLOR_WHITE, bg)


def level(depth, mx):
    return 0 if depth <= 0 else 1 + min(LEVELS - 1, int((LEVELS - 1) * depth / mx))


def run(scr, dev):
    curses.curs_set(0)
    scr.nodelay(True)
    setup_colors()
    cfg = load_config(dev.NAME)
    keys = dev.keys()
    names = {k["index"]: k["name"] for k in keys}
    states = {k["index"]: KeyTracker() for k in keys}
    vel = {}
    log = collections.deque(maxlen=8)
    th = Thresholds(cfg)
    fast, slow = cfg["fast_ms"], cfg["slow_ms"]
    stats = {"events": 0, "unknown": 0, "max_raw": 0, "min_gap": None, "t_start": time.monotonic(), "last_t": None}

    with dev.stream(list(states)) as st:
        last_draw = 0.0
        quit_idx = {k["name"]: k["index"] for k in keys}.get(cfg["quit_key"])
        for t, idx, v in st.events(timeout=0.01):
            while (ch := scr.getch()) != -1:  # typed input (the keyboard is not grabbed): Esc / q quit
                if ch in (27, ord("q")):
                    return
            if idx is not None and idx == quit_idx and v >= th.hi:  # Esc pressed on the magnetic keyboard
                return
            if idx is not None:
                stats["events"] += 1
                if stats["last_t"] is not None and v:
                    gap = (t - stats["last_t"]) * 1000
                    stats["min_gap"] = gap if stats["min_gap"] is None else min(stats["min_gap"], gap)
                stats["last_t"] = t
                stats["max_raw"] = max(stats["max_raw"], v)
                th.grow(v)
                s = states.get(idx)
                if s is None:
                    stats["unknown"] += 1
                else:
                    ev = s.update(t, v, th, fast, slow)
                    if ev and ev[0] == "on":
                        vel[idx] = ev[1]
                        log.appendleft((time.strftime("%H:%M:%S"), names[idx], ev[1], ev[2]))
            if t - last_draw < 1 / 60:
                continue
            last_draw = t
            draw(scr, dev, keys, states, vel, log, th, cfg, stats, getattr(st, "n_other", 0), t)


def fmt_depth(dev, v):
    if not v:
        return ""
    return f"{v * dev.UNIT_MM:.1f}" if dev.UNIT_MM else str(v)


def draw(scr, dev, keys, states, vel, log, th, cfg, stats, n_other, now):
    h, w = scr.getmaxyx()
    mx = th.full
    max_x = max(k["x"] + k["width"] for k in keys)
    sx = (w - 2) / max_x
    key_h = 3
    scr.erase()
    elapsed = max(now - stats["t_start"], 1e-3)
    gap = "-" if stats["min_gap"] is None else f"{stats['min_gap']:.1f}ms"
    title = (f" {dev.TITLE} live travel | events {stats['events']} ({stats['events'] / elapsed:.0f}/s) "
             f"| max raw {stats['max_raw']} | min gap {gap} | full={mx} | Esc quits ")
    scr.addnstr(0, 0, title, w - 1, curses.A_BOLD)
    if stats["events"] == 0:
        scr.addnstr(1, 0, " waiting for travel reports — press a key", w - 1, curses.A_DIM)
    elif stats["unknown"] or n_other:
        scr.addnstr(1, 0, f" unknown key index: {stats['unknown']}  other reports: {n_other}", w - 1, curses.A_DIM)
    top = 2
    for k in keys:
        s = states[k["index"]]
        x0 = 1 + int(k["x"] * sx)
        y0 = top + int(round(k["y"] * (key_h + 1)))
        kw = max(3, int(k["width"] * sx) - 1)
        if y0 + key_h > h - 10 or x0 + kw >= w:
            continue
        attr = curses.color_pair(1 + level(s.depth, mx))
        if s.on:
            attr |= curses.A_BOLD
        cells = kw * min(s.depth, mx) / mx
        full = int(cells)
        bar = "█" * full + (BLOCKS[int((cells - full) * 8)] if full < kw and s.depth else "")
        vs = "" if k["index"] not in vel else f"{vel[k['index']]:>4}"
        try:
            scr.addnstr(y0, x0, k["name"][:kw].ljust(kw), kw, attr)
            scr.addnstr(y0 + 1, x0, bar.ljust(kw), kw, attr)
            scr.addnstr(y0 + 2, x0, fmt_depth(dev, s.depth).ljust(kw - len(vs)) + vs, kw, attr)
        except curses.error:
            pass
    y = h - 9
    try:
        scr.addnstr(y, 0, f" last strikes (velocity 1–127, time {cfg['vel_lo']:.0%}→{cfg['vel_hi']:.0%} of travel):",
                    w - 1, curses.A_BOLD)
        for i, (ts, name, v, dt) in enumerate(log):
            bar_w = max(1, (w - 40) * v // 127)
            scr.addnstr(y + 1 + i, 1, f"{ts} {name:>9} v{v:>4} {dt:6.1f}ms ", w - 2)
            scr.addnstr(y + 1 + i, 38, " " * bar_w, w - 39, curses.color_pair(1 + level(v * mx // 127, mx)))
    except curses.error:
        pass
    scr.refresh()


def main(argv=None):
    import signal

    ap = argparse.ArgumentParser(prog="magmidi.viz")
    ap.add_argument("--device", default="auto", help="auto (default), " + ", ".join(devices.NAMES))
    a = ap.parse_args(argv)
    dev = devices.get(a.device)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    os.environ.setdefault("ESCDELAY", "25")  # curses waits 1 s after Esc by default
    try:
        curses.wrapper(run, dev)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
