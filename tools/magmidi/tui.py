"""Curses view for the MIDI bridge (magmidi.midi --tui): the computer keyboard and a piano keyboard.

Top: every key at its physical position, filled by current travel, with the note it plays now (transposition and
held sharp modifiers included) or its control role. Bottom: a piano spanning the mapped range. Held notes are lit
by velocity, notes still ringing on the sustain pedal are shaded, and each piano key carries the computer key(s)
that play it at the current transposition. "C3" etc. below mark the octaves.
"""
from __future__ import annotations

import collections
import curses
import time

from .viz import BLOCKS, level, setup_colors

NAMES = "C C# D D# E F F# G G# A A# B".split()
BLACK = {1, 3, 6, 8, 10}
RING_S = 5.0  # show a pedal-sustained note this long after its key was released (the piano tone has decayed)
P_WHITE, P_WHITE_DIM, P_BLACK, P_BLACK_DIM, P_RING, P_RING_BLACK, P_DIM = range(20, 27)


def note_name(n: int) -> str:
    return f"{NAMES[n % 12]}{n // 12 - 1}"


def setup_piano_colors():
    c256 = curses.COLORS >= 256
    pairs = {
        P_WHITE: (curses.COLOR_BLACK, 231 if c256 else curses.COLOR_WHITE),
        P_WHITE_DIM: (240 if c256 else curses.COLOR_BLACK, 250 if c256 else curses.COLOR_WHITE),
        P_BLACK: (curses.COLOR_WHITE, 238 if c256 else curses.COLOR_BLACK),
        P_BLACK_DIM: (244 if c256 else curses.COLOR_WHITE, 233 if c256 else curses.COLOR_BLACK),
        P_RING: (curses.COLOR_BLACK, 116 if c256 else curses.COLOR_CYAN),
        P_RING_BLACK: (curses.COLOR_WHITE, 30 if c256 else curses.COLOR_CYAN),
        P_DIM: (244 if c256 else curses.COLOR_WHITE, -1),
    }
    for p, (fg, bg) in pairs.items():
        curses.init_pair(p, fg, bg)


class BridgeTUI:
    """Owned by magmidi.midi; it calls log() for messages and tick() on every stream event or idle timeout."""

    def __init__(self, scr, dev, cfg, roles: dict[int, str], th):
        self.scr, self.dev, self.cfg, self.roles, self.th = scr, dev, cfg, roles, th
        self.keys = dev.keys()
        self.msgs = collections.deque(maxlen=8)
        self.last_draw = 0.0
        curses.curs_set(0)
        scr.nodelay(True)
        setup_colors()
        setup_piano_colors()

    def log(self, msg: str):
        self.msgs.appendleft(f"{time.strftime('%H:%M:%S')} {msg}")

    def tick(self, now, *, depth, playing, vel, ringing, note_for, base_notes, transpose, sustain):
        """depth: idx->raw; playing: idx->sounding note; vel: idx->last velocity; ringing: note->release time;
        note_for(idx): note the key would play now; base_notes: idx->untransposed note."""
        while self.scr.getch() != -1:  # swallow typed input (with --no-grab)
            pass
        if now - self.last_draw < 1 / 30:
            return
        self.last_draw = now
        scr = self.scr
        h, w = scr.getmaxyx()
        scr.erase()
        tonic = (self.cfg["base_note"] + transpose) % 12
        scale = self.cfg["scale"].replace("_", " ") if self.cfg["layout"] != "piano" else ""
        title = (f" {self.dev.TITLE} → MIDI | layout {self.cfg['layout']} | key {NAMES[tonic]} {scale} "
                 f"(transpose {transpose:+d}) | sustain {'ON' if sustain else 'off'} | {self.cfg['quit_key']} quits ")
        self._put(0, 0, title, curses.A_BOLD)
        bottom = self._keyboard(2, w, depth, playing, vel, note_for)
        ring = {n for n, t in ringing.items() if now - t < RING_S}
        held = {}
        for idx, n in playing.items():
            held[n] = max(held.get(n, 0), vel.get(idx, 64))
        y = self._piano(bottom + 1, w, base_notes, held, ring, note_for)
        self._put(y + 1, 0, " recent:", curses.A_BOLD)
        for i, m in enumerate(self.msgs):
            if y + 2 + i >= h:
                break
            self._put(y + 2 + i, 1, m)
        scr.refresh()

    # ---------------------------------------------------------------- drawing helpers
    def _put(self, y, x, s, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and 0 <= x < w - 1:
            try:
                self.scr.addnstr(y, x, s, w - 1 - x, attr)
            except curses.error:
                pass

    def _keyboard(self, top, w, depth, playing, vel, note_for) -> int:
        mx = self.th.full
        max_x = max(k["x"] + k["width"] for k in self.keys)
        sx = (w - 2) / max_x
        bottom = top
        for k in self.keys:
            idx = k["index"]
            x0 = 1 + int(k["x"] * sx)
            y0 = top + int(round(k["y"] * 3))
            kw = max(3, int(k["width"] * sx) - 1)
            d = depth.get(idx, 0)
            role = self.roles.get(idx)
            if role == "note":
                n = playing.get(idx)
                sub = note_name(n if n is not None else note_for(idx))
                if n is not None and idx in vel:
                    sub = f"{sub} {vel[idx]}"
            else:
                sub = role or ""
            if not role and not d:
                attr = curses.color_pair(P_DIM)  # unused key
            else:
                attr = curses.color_pair(1 + level(d, mx)) | (curses.A_BOLD if idx in playing else 0)
            if not sub and d:  # unused key pressed: show travel as a bar
                cells = kw * min(d, mx) / mx
                full = int(cells)
                sub = "█" * full + (BLOCKS[int((cells - full) * 8)] if full < kw else "")
            self._put(y0, x0, k["name"][:kw].ljust(kw), attr)
            self._put(y0 + 1, x0, sub[:kw].ljust(kw), attr)
            bottom = max(bottom, y0 + 2)
        return bottom

    def _piano(self, y, w, base_notes, held, ring, note_for) -> int:
        cur = {idx: note_for(idx) for idx in base_notes}
        span = list(cur.values()) + list(held) + list(ring)
        if not span:
            return y
        lo, hi = max(0, min(span)), min(127, max(span))
        lo -= lo % 12
        hi = min(127, hi + 11 - hi % 12)
        whites = [n for n in range(lo, hi + 1) if n % 12 not in BLACK]
        W = max(2, min(5, (w - 3) // max(1, len(whites))))
        x0 = 1
        pos = {n: x0 + i * W for i, n in enumerate(whites)}
        names = {}
        for idx, n in cur.items():
            names.setdefault(n, []).append(self.dev_name(idx))
        mapped = set(names)

        def attr_for(n, black):
            if n in held:
                return curses.color_pair(1 + level(held[n], 127)) | curses.A_BOLD
            if n in ring:
                return curses.color_pair(P_RING_BLACK if black else P_RING)
            if black:
                return curses.color_pair(P_BLACK if n in mapped else P_BLACK_DIM)
            return curses.color_pair(P_WHITE if n in mapped else P_WHITE_DIM)

        for n in whites:
            a = attr_for(n, False)
            lab = "".join(names.get(n, []))[:W - 1]
            for r in range(4):
                text = "│" + (lab.ljust(W - 1) if r == 3 else " " * (W - 1))
                self._put(y + r, pos[n], text, a)
            if n % 12 == 0:
                self._put(y + 4, pos[n], note_name(n), curses.A_BOLD)
        bw = W - 1 if W >= 3 else 1
        for n in range(lo, hi + 1):
            if n % 12 not in BLACK or n + 1 not in pos:
                continue
            a = attr_for(n, True)
            xb = pos[n + 1] - bw // 2
            lab = "".join(names.get(n, []))[:bw]
            self._put(y, xb, " " * bw, a)
            self._put(y + 1, xb, lab.center(bw), a)
        legend = " lit = held (colour = velocity), cyan = ringing on the pedal, labels = computer keys "
        self._put(y + 5, 0, legend, curses.A_DIM)
        return y + 5

    def dev_name(self, idx) -> str:
        if not hasattr(self, "_names"):
            self._names = {k["index"]: k["name"] for k in self.keys}
        return self._names.get(idx, "?")
