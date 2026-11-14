"""Live terminal visualisation of C80 key travel and strike velocity.

    .venv/bin/python tools/viz.py          (Ctrl+C to quit)

Each key is drawn at its physical position. Its fill colour and the bar under its name show the
current travel (0–3.40 mm). The number shows the velocity (1–127) of that key's last strike,
using the same formula as c80.midi. The bottom panel lists recent strikes.
The keyboard is not grabbed, so keys still type; the program ignores that input.
"""
import collections
import curses
import json
import pathlib
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from c80 import C80  # noqa: E402
from c80.midi import DEFAULTS, velocity  # noqa: E402
from c80.stream import TravelStream  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEYS = json.load(open(ROOT / "vendor/webdriver/config/keys/QK75EHEARGB.json"))["keys"]
LO, HI, REL = DEFAULTS["vel_lo"], DEFAULTS["vel_hi"], DEFAULTS["release"]
FAST, SLOW = DEFAULTS["fast_ms"], DEFAULTS["slow_ms"]
BLOCKS = " ▁▂▃▄▅▆▇█"
LEVELS = 8


class KeyState:
    __slots__ = ("travel", "peak", "t_lo", "on", "vel", "dt", "prev")

    def __init__(self):
        self.travel = self.peak = self.prev = 0
        self.t_lo: float | None = None
        self.on = False
        self.vel = None
        self.dt: float | None = None


def setup_colors():
    curses.start_color()
    curses.use_default_colors()
    # gradient dark-blue -> green -> yellow -> red (256-colour if available)
    ramp256 = [236, 24, 30, 36, 70, 142, 178, 208, 196]
    ramp8 = [curses.COLOR_BLACK, curses.COLOR_BLUE, curses.COLOR_CYAN, curses.COLOR_CYAN, curses.COLOR_GREEN,
             curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_YELLOW, curses.COLOR_RED]
    ramp = ramp256 if curses.COLORS >= 256 else ramp8
    for i, bg in enumerate(ramp):
        curses.init_pair(1 + i, curses.COLOR_WHITE, bg)
    curses.init_pair(20, curses.COLOR_BLACK, curses.COLOR_WHITE)  # bar in log


def level(travel, mx):
    return 0 if travel <= 0 else 1 + min(LEVELS - 1, int((LEVELS - 1) * travel / mx))


def main(scr):
    curses.curs_set(0)
    scr.nodelay(True)
    setup_colors()
    max_x = max(float(k["x"]) + float(k["width"]) for k in KEYS)
    max_y = max(float(k["y"]) + float(k["height"]) for k in KEYS)
    states = {int(k["index"]): KeyState() for k in KEYS}
    log = collections.deque(maxlen=8)
    mx = 340
    last_draw, n_events, t_start = 0.0, 0, time.monotonic()

    with C80() as kb, TravelStream(kb, list(states)) as st:
        for t, idx, v in st.events(timeout=0.01):
            while scr.getch() != -1:  # swallow typed input
                pass
            if idx is not None and idx in states:
                n_events += 1
                s = states[idx]
                s.travel = v
                s.peak = max(s.peak, v) if v > 0 else 0
                if not s.on:
                    if s.prev < LO <= v:
                        s.t_lo = t
                    if v < LO:
                        s.t_lo = None
                    if v >= HI:
                        s.dt = (t - s.t_lo) * 1000 if s.t_lo is not None else 0.0
                        s.vel = velocity(s.dt, FAST, SLOW)
                        s.on, s.t_lo = True, None
                        name = next(k["name"] for k in KEYS if int(k["index"]) == idx)
                        log.appendleft((time.strftime("%H:%M:%S"), name, s.vel, s.dt))
                elif v < REL:
                    s.on = False
                s.prev = v
            if t - last_draw < 1 / 60:
                continue
            last_draw = t
            draw(scr, states, log, mx, max_x, max_y, n_events, t - t_start)


def draw(scr, states, log, mx, max_x, max_y, n_events, elapsed):
    h, w = scr.getmaxyx()
    sx = (w - 2) / max_x
    key_h = 3
    sy = key_h / 38.0  # ~38px per row in the layout
    scr.erase()
    title = f" CIDOO C80 live travel  |  events {n_events}  ({n_events / max(elapsed, 1e-3):.0f}/s)  |  Ctrl+C quits "
    scr.addnstr(0, 0, title, w - 1, curses.A_BOLD)
    top = 2
    for k in KEYS:
        s = states[int(k["index"])]
        x0 = 1 + int(float(k["x"]) * sx)
        y0 = top + int(float(k["y"]) * sy)
        kw = max(3, int(float(k["width"]) * sx) - 1)
        if y0 + key_h > h - 10 or x0 + kw >= w:
            continue
        attr = curses.color_pair(1 + level(s.travel, mx))
        if s.on:
            attr |= curses.A_BOLD
        name = (k["name"] or "·")[:kw]
        bar_len = round(kw * s.travel / mx)
        frac = (kw * s.travel / mx) - int(kw * s.travel / mx)
        bar = "█" * int(kw * s.travel / mx) + (BLOCKS[int(frac * 8)] if bar_len < kw and s.travel else "")
        vel = "" if s.vel is None else f"{s.vel:>4}"
        try:
            scr.addnstr(y0, x0, name.ljust(kw), kw, attr)
            scr.addnstr(y0 + 1, x0, bar.ljust(kw), kw, attr)
            scr.addnstr(y0 + 2, x0, (f"{s.travel / 100:.1f}" if s.travel else "").ljust(kw - len(vel)) + vel, kw, attr)
        except curses.error:
            pass
    y = h - 9
    try:
        scr.addnstr(y, 0, " last strikes (velocity 1–127, time 0.4→2.0 mm):", w - 1, curses.A_BOLD)
        for i, (ts, name, vel, dt) in enumerate(log):
            bar_w = max(1, (w - 40) * vel // 127)
            scr.addnstr(y + 1 + i, 1, f"{ts} {name:>8} v{vel:>4} {dt:6.1f}ms ", w - 2)
            scr.addnstr(y + 1 + i, 38, " " * bar_w, w - 39, curses.color_pair(1 + level(vel * mx // 127, mx)))
    except curses.error:
        pass
    scr.refresh()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
