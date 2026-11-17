"""Play-along trainer: a MIDI score falls onto the piano, you play it on the magnetic keyboard.

    PYTHONPATH=tools .venv/bin/python -m magmidi.trainer [SCORE] [--mode practice|game|demo] [--hands both|right|left]
                                                         [--speed 1.0] [--zoom 3] [--to FLUID] [--device fun68]

SCORE is a .mid path or the name/number of an exercise in scores/ ("05", "ode"); without it the exercises are
listed. The score is moved to the layout: its key (key signature, else detected) becomes the layout's tonic and
mode, notes out of reach are folded by octaves, and every falling note is labelled with the computer key that
plays it ("♯" = hold that hand's Alt).

Modes (Tab cycles them while playing):
  practice  the score waits at each chord until you play all of its notes; wrong notes are counted.
  game      the score runs in tempo; each note is judged by timing (perfect ≤45 ms, good ≤90, ok ≤150 ms,
            else miss), and keys that match nothing are counted as wrong.
  demo      the trainer plays everything itself (as the layout would sound it) and lights the keys: watch, listen.
Parts you don't practise (--hands) play by themselves on MIDI channel 2.

Keys: ←/→ previous/next bar, Shift+← start, ↑/↓ speed ±10%, Enter pause, Tab mode, Backspace restart
(clears the score), Space sustain pedal (inverted, as in magmidi.midi), Esc quit.
"""
from __future__ import annotations

import argparse
import curses
import pathlib
import signal
import sys
import time

from . import devices, fit
from . import score as scoremod
from .bridge import NOTE_NAMES, Bridge, grab_keyboard, open_output, ungrab
from .midi import load_config
from .paths import ROOT
from .tui import (P_ACCOMP, P_GRID, P_HIT, P_LEFT, P_RIGHT, P_WANT, P_WRONG, PianoGeom, base_attr, draw_piano,
                  key_labels, put, setup_piano_colors)
from .viz import level, setup_colors

SCORES = ROOT / "scores"
CONTROL_KEYS = ["Left", "Right", "Up", "Down", "Enter", "Tab", "Backspace"]
JUDGE = [(0.045, "perfect"), (0.090, "good"), (0.150, "ok")]  # real-time windows
EARLY = 0.35  # practice: a note struck up to this many real seconds before its chord arrives still counts
ACC_CH = 1


def find_score(arg: str) -> pathlib.Path:
    p = pathlib.Path(arg)
    if p.exists():
        return p
    hits = [f for f in sorted(SCORES.glob("*.mid")) if f.stem.startswith(arg) or arg.lower() in f.stem.lower()]
    if not hits:
        sys.exit(f"no score {arg!r}; exercises: {', '.join(f.stem for f in sorted(SCORES.glob('*.mid')))}")
    return hits[0]


class Session:
    """Score clock, practice waiting, game judging and the accompaniment. Times are score seconds unless noted."""

    def __init__(self, sc, targets, br, out, mode, hands, speed):
        self.sc, self.tg, self.br, self.out = sc, targets, br, out
        self.mode, self.speed = mode, speed
        self.hands = {"both": {"left", "right"}, "right": {"right"}, "left": {"left"}}[hands]
        self.practised = [i for i, n in enumerate(sc.notes) if n.hand in self.hands and targets[i].key]
        self.is_practised = set(self.practised)
        # chords: practised notes starting together
        self.groups: list[tuple[float, list[int]]] = []
        for i in self.practised:
            n = sc.notes[i]
            if self.groups and n.start - self.groups[-1][0] < 0.03:
                self.groups[-1][1].append(i)
            else:
                self.groups.append((n.start, [i]))
        self._build_acc()
        self.lead_in = 2 * sc.beat
        self.restart(clear=True)

    def _build_acc(self):
        """Auto-played notes: the parts not practised, or everything in demo mode (at the pitch the layout plays)."""
        acc = []
        for i, n in enumerate(self.sc.notes):
            if self.mode == "demo" or i not in self.is_practised:
                p = self.tg[i].pitch if i in self.is_practised else n.pitch
                acc.append((n.start, 1, p, n.vel))
                acc.append((n.end, 0, p, 0))
        self.acc = sorted(acc, key=lambda e: (e[0], e[1]))

    # ---------------------------------------------------------------- clock
    def restart(self, clear=False):
        if clear:
            self.judged: dict[int, tuple[str, float]] = {}  # note -> (judgement, offset real s)
            self.wrong = 0
            self.errors = 0
            self.combo = self.best_combo = 0
        self.seek(-self.lead_in)
        self.paused = False
        self.finished = False

    def seek(self, pos):
        self.out.send_message([0xB0 | ACC_CH, 123, 0])
        self.acc_sounding = set()
        self.pos = pos
        self.last = time.monotonic()
        self.acc_i = next((k for k, e in enumerate(self.acc) if e[0] >= pos), len(self.acc))
        self.gi = next((k for k, g in enumerate(self.groups) if g[0] >= pos - 1e-6), len(self.groups))
        self.struck: dict[int, float] = {}  # pitch -> real time of the strike
        self.wrong_flash: dict[int, float] = {}
        self.arrived = None  # practice: real time the clock reached the current chord
        window = JUDGE[-1][0] * self.speed
        self.miss_i = next((k for k, i in enumerate(self.practised)
                            if self.sc.notes[i].start >= pos - window), len(self.practised))
        for i in list(self.judged):
            if self.sc.notes[i].start >= pos:
                del self.judged[i]
        self.finished = False

    def bar_index(self):
        bars = self.sc.bars
        return max(0, max((k for k, b in enumerate(bars) if b <= self.pos + 1e-3), default=0))

    def jump_bar(self, step):
        bars = self.sc.bars
        k = self.bar_index()
        if step < 0 and self.pos - bars[k] > 0.6 * self.speed:
            step += 1  # first press goes to the start of the current bar
        k = max(0, min(len(bars) - 1, k + step))
        self.seek(bars[k] - (self.sc.beat if k == 0 else 0.0))

    def waiting(self) -> bool:
        return self.mode == "practice" and self.gi < len(self.groups) and self.pos >= self.groups[self.gi][0] - 1e-9

    def update(self, now):
        dt, self.last = now - self.last, now
        if self.paused or self.finished:
            return
        if self.mode == "practice" and self.gi < len(self.groups):
            g_start, g = self.groups[self.gi]
            if self.pos + dt * self.speed >= g_start:
                self.pos = max(self.pos, g_start)
                if self.arrived is None:
                    self.arrived = now
                if all(self.struck.get(self.tg[i].pitch, -1e9) >= self.arrived - EARLY for i in g):
                    for i in g:
                        self.struck.pop(self.tg[i].pitch, None)  # a repeated note must be struck again
                        self.judged[i] = ("hit", 0.0)
                    self.gi += 1
                    self.arrived = None
                self._accompany()
                return
        self.pos += dt * self.speed
        if self.mode == "game":
            window = JUDGE[-1][0] * self.speed
            while self.miss_i < len(self.practised) and self.sc.notes[self.practised[self.miss_i]].start < self.pos - window:
                i = self.practised[self.miss_i]
                if i not in self.judged:
                    self.judged[i] = ("miss", 0.0)
                    self.combo = 0
                self.miss_i += 1
        self._accompany()
        if self.pos > self.sc.duration + 0.5:
            self.finished = True
            self.out.send_message([0xB0 | ACC_CH, 123, 0])

    def _accompany(self):
        while self.acc_i < len(self.acc) and self.acc[self.acc_i][0] <= self.pos:
            _, on, p, v = self.acc[self.acc_i]
            if on:
                self.out.send_message([0x90 | ACC_CH, p, max(1, int(v * 0.8))])
                self.acc_sounding.add(p)
            elif p in self.acc_sounding:
                self.out.send_message([0x80 | ACC_CH, p, 0])
                self.acc_sounding.discard(p)
            self.acc_i += 1

    # ---------------------------------------------------------------- input
    def strike(self, pitch, now):
        self.struck[pitch] = now
        if self.mode == "demo":
            return
        if self.mode == "practice":
            if self.waiting() and pitch not in {self.tg[i].pitch for i in self.groups[self.gi][1]}:
                self.errors += 1
                self.wrong_flash[pitch] = now
            return
        window = JUDGE[-1][0] * self.speed
        best = None
        for i in self.practised:
            n = self.sc.notes[i]
            if n.start > self.pos + window:
                break
            if i in self.judged or self.tg[i].pitch != pitch or abs(n.start - self.pos) > window:
                continue
            if best is None or abs(n.start - self.pos) < abs(self.sc.notes[best].start - self.pos):
                best = i
        if best is None:
            self.wrong += 1
            self.combo = 0
            self.wrong_flash[pitch] = now
            return
        off = (self.pos - self.sc.notes[best].start) / self.speed
        verdict = next(name for lim, name in JUDGE if abs(off) <= lim)
        self.judged[best] = (verdict, off)
        self.combo += 1
        self.best_combo = max(self.best_combo, self.combo)

    def control(self, name):
        if name == "Left":
            if self.br.shift_held():
                self.seek(-self.lead_in)
            else:
                self.jump_bar(-1)
        elif name == "Right":
            self.jump_bar(1)
        elif name == "Up":
            self.speed = min(2.0, round(self.speed + 0.1, 2))
        elif name == "Down":
            self.speed = max(0.2, round(self.speed - 0.1, 2))
        elif name == "Enter":
            if self.finished:
                self.restart()
            else:
                self.paused = not self.paused
                self.last = time.monotonic()
                if self.paused:
                    self.out.send_message([0xB0 | ACC_CH, 123, 0])
                    self.acc_sounding = set()
        elif name == "Tab":
            self.mode = {"practice": "game", "game": "demo", "demo": "practice"}[self.mode]
            self._build_acc()
            self.seek(self.pos)
        elif name == "Backspace":
            self.restart(clear=True)

    # ---------------------------------------------------------------- stats
    def stats(self) -> dict:
        counts = {"perfect": 0, "good": 0, "ok": 0, "miss": 0, "hit": 0}
        offs = []
        for verdict, off in self.judged.values():
            counts[verdict] += 1
            if verdict in ("perfect", "good", "ok"):
                offs.append(off)
        hits = counts["perfect"] + counts["good"] + counts["ok"]
        total = hits + counts["miss"] + self.wrong
        return dict(counts, hits=hits, acc=(100 * hits / total if total else 100.0),
                    offset=(1000 * sum(offs) / len(offs) if offs else 0.0))


# -------------------------------------------------------------------- drawing
def draw(scr, s: Session, br, title_key, zoom, g: PianoGeom, labels, now):
    h, w = scr.getmaxyx()
    scr.erase()
    sc = s.sc
    bar = s.bar_index() + 1
    clock = f"{max(0, s.pos) // 60:.0f}:{max(0, s.pos) % 60:02.0f}/{sc.duration // 60:.0f}:{sc.duration % 60:02.0f}"
    hands = "+".join(sorted(s.hands)) if len(s.hands) == 1 else "both hands"
    put(scr, 0, 0, f" {sc.name} | {s.mode.upper()} | {hands} | key {title_key} | speed {s.speed:.0%} | "
                   f"bar {bar}/{len(sc.bars)} | {clock}" + (" | PAUSED" if s.paused else ""), curses.A_BOLD)
    if s.mode == "demo":
        line = " demo: the trainer plays both hands; watch the labels — Tab: practice, then game"
    elif s.mode == "practice":
        want = ""
        if s.gi < len(s.groups):
            want = " ".join(_label(s, i) for i in s.groups[s.gi][1])
        line = (f" errors {s.errors} | chords {s.gi}/{len(s.groups)} | "
                + (f"play: {want}" if s.waiting() else f"next: {want}" if want else "done"))
    else:
        st = s.stats()
        line = (f" hits {st['hits']} (perfect {st['perfect']} / good {st['good']} / ok {st['ok']}) | miss {st['miss']}"
                f" | wrong {s.wrong} | accuracy {st['acc']:.0f}% | combo {s.combo} (best {s.best_combo})"
                f" | avg {abs(st['offset']):.0f} ms {'late' if st['offset'] > 0 else 'early'}")
    if s.finished:
        line += " | FINISHED — Enter: again"
    put(scr, 1, 0, line)
    put(scr, 2, 0, " ←/→ bar  Shift+← start  ↑/↓ speed  Enter pause  Tab mode  Backspace restart  Esc quit",
        curses.A_DIM)
    x = put_legend(scr, 3, 1, [("right hand", P_RIGHT), ("left hand", P_LEFT), ("plays itself", P_ACCOMP),
                               ("play now", P_WANT), ("done", P_HIT), ("miss / wrong", P_WRONG)])
    put(scr, 3, x, " label = computer key, ♯ = hold Alt of that hand", curses.A_DIM)

    piano_y = h - 6
    now_y = piano_y - 1
    top = 5
    rows = now_y - top
    if rows < 3:
        put(scr, 4, 0, " terminal too small")
        scr.refresh()
        return
    row_s = sc.beat / zoom  # score seconds per row
    horizon = s.pos + rows * row_s

    def row_of(t):
        return now_y - 1 - int((t - s.pos) / row_s)

    for b in sc.bars:
        if s.pos <= b <= horizon:
            put(scr, row_of(b), 1, "┈" * (w - 3), curses.color_pair(P_GRID))
    want_now = set()
    if s.mode == "practice" and s.gi < len(s.groups):
        want_now = set(s.groups[s.gi][1])
    for i, n in enumerate(sc.notes):
        if n.start > horizon:
            break
        if n.end < s.pos:
            continue
        t = s.tg[i]
        span = g.span(t.pitch if i in s.is_practised else n.pitch)
        if not span:
            continue
        x, wd = span
        y0 = row_of(max(n.start, s.pos))
        y1 = max(top, row_of(n.end - 1e-6) + 1)
        if i in want_now:
            a = curses.color_pair(P_WANT) | curses.A_BOLD
        elif i not in s.is_practised:
            a = curses.color_pair(P_ACCOMP)
        elif i in s.judged and s.mode != "demo":
            a = curses.color_pair(P_WRONG if s.judged[i][0] == "miss" else P_HIT)
        else:
            a = curses.color_pair(P_LEFT if n.hand == "left" else P_RIGHT) | curses.A_BOLD
        for y in range(y1, y0 + 1):
            put(scr, y, x, " " * wd, a)
        if i in s.is_practised:
            put(scr, y0, x, _label(s, i)[:wd].ljust(wd), a)
    put(scr, now_y, 1, "━" * (w - 3), curses.A_BOLD)

    held = {}
    for idx, p in br.playing.items():
        held[p] = max(held.get(p, 0), br.vel.get(idx, 64))
    want_p = {s.tg[i].pitch for i in want_now}
    if s.mode == "game":
        win = JUDGE[-1][0] * s.speed
        want_p = {s.tg[i].pitch for i in s.practised
                  if i not in s.judged and abs(sc.notes[i].start - s.pos) <= win}
    flash = {p for p, t in s.wrong_flash.items() if now - t < 0.4}
    auto = {}  # demo: notes sounding now -> colour of their part
    if s.mode == "demo":
        for i, n in enumerate(sc.notes):
            if n.start > s.pos:
                break
            if n.end > s.pos:
                practised = i in s.is_practised
                auto[s.tg[i].pitch if practised else n.pitch] = (
                    (P_LEFT if n.hand == "left" else P_RIGHT) if practised else P_ACCOMP)

    def attr_for(p, black):
        if p in flash:
            return curses.color_pair(P_WRONG) | curses.A_BOLD
        if p in held:
            return curses.color_pair(1 + level(held[p], 127)) | curses.A_BOLD
        if p in auto:
            return curses.color_pair(auto[p]) | curses.A_BOLD
        if p in want_p:
            return curses.color_pair(P_WANT) | curses.A_BOLD
        return base_attr(p, black, labels)

    draw_piano(scr, piano_y, g, labels, attr_for)
    scr.refresh()


def put_legend(scr, y, x, items) -> int:
    for text, pair in items:
        put(scr, y, x, f" {text} ", curses.color_pair(pair))
        x += len(text) + 3
    return x


def _label(s: Session, i: int) -> str:
    t = s.tg[i]
    return (t.key or "?") + ("♯" if t.sharp else "")


# -------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(prog="magmidi.trainer", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("score", nargs="?", help=".mid file or exercise name/number in scores/")
    ap.add_argument("--mode", choices=("practice", "game", "demo"), default="practice")
    ap.add_argument("--hands", choices=("both", "right", "left"), default="both")
    ap.add_argument("--speed", type=float, default=1.0, help="tempo factor (default 1.0)")
    ap.add_argument("--zoom", type=float, default=3, help="screen rows per beat (default 3)")
    ap.add_argument("--device", default="auto", help="auto (default), " + ", ".join(devices.NAMES))
    ap.add_argument("--config")
    ap.add_argument("--to", metavar="NAME", help="MIDI input port to play into, e.g. FLUID (default: virtual port)")
    ap.add_argument("--port-name", help="virtual MIDI port name (default: device name)")
    ap.add_argument("--no-grab", action="store_true")
    a = ap.parse_args(argv)
    if not a.score:
        print("exercises (scores/):")
        for f in sorted(SCORES.glob("*.mid")):
            print("  ", f.stem)
        print("usage: python -m magmidi.trainer 05 --to FLUID   (any .mid path works too)")
        return

    sc = scoremod.load(find_score(a.score))
    if not sc.notes:
        sys.exit("the score has no notes")
    scoremod.split_hands(sc)
    tonic, mode = sc.detect_key()
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    dev = devices.get(a.device)
    cfg = load_config(dev.NAME, a.config, scale=mode)
    if cfg["layout"] == "piano":
        sys.exit("the trainer needs an in-key layout (layout: thirds)")
    cfg["transpose_keys"] = {}  # the trainer owns the arrows
    transpose = fit.choose_transpose(sc, cfg)
    targets = fit.assign(sc, cfg, transpose)
    out, port = open_output(a.port_name or dev.PORT_NAME, a.to)
    br = Bridge(dev, cfg, out, extra_keys=CONTROL_KEYS, transpose=transpose)
    s = Session(sc, targets, br, out, a.mode, a.hands, a.speed)
    title_key = f"{NOTE_NAMES[tonic]} {mode}"
    print(f"{sc.name}: {len(sc.notes)} notes, key {title_key}, transpose {transpose:+d}; "
          f"{sum(t.sharp for t in targets)} need Alt, {sum(1 for t in targets if t.folded)} octave-folded, "
          f"{sum(1 for t in targets if not t.key)} unreachable; MIDI -> {port}", flush=True)
    grabbed = [] if a.no_grab else grab_keyboard(dev)
    pitches = [t.pitch for t in targets] + [n.pitch for n in sc.notes]  # piano spans the music, whole octaves

    def run(scr):
        curses.curs_set(0)
        scr.nodelay(True)
        setup_colors()
        setup_piano_colors()
        labels = key_labels(br)
        last_draw = 0.0
        with dev.stream(br.indices(), cfg) as st:
            br.start()
            for t, idx, v in st.events(timeout=0.005):
                while scr.getch() != -1:
                    pass
                s.update(t)
                if idx is not None:
                    for ev in br.handle(t, idx, v):
                        if ev[0] == "quit":
                            return
                        if ev[0] == "on":
                            s.strike(ev[2], t)
                        elif ev[0] == "press":
                            s.control(ev[1])
                if t - last_draw >= 1 / 30:
                    last_draw = t
                    g = PianoGeom(min(pitches), max(pitches), scr.getmaxyx()[1])
                    draw(scr, s, br, title_key, a.zoom, g, labels, t)

    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    finally:
        br.all_off()
        out.send_message([0xB0 | ACC_CH, 123, 0])
        ungrab(grabbed)
        out.close_port()
    st = s.stats()
    if s.mode == "practice":
        print(f"{sc.name}: practice, {s.gi}/{len(s.groups)} chords, {s.errors} wrong notes")
    elif s.mode == "demo":
        print(f"{sc.name}: demo")
    else:
        print(f"{sc.name}: game, hits {st['hits']} (perfect {st['perfect']}, good {st['good']}, ok {st['ok']}), "
              f"miss {st['miss']}, wrong {s.wrong}, accuracy {st['acc']:.0f}%, best combo {s.best_combo}")


if __name__ == "__main__":
    main()
