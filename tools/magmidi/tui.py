"""Curses views: the bridge view (magmidi.midi --tui) and the piano drawing shared with magmidi.trainer.

Bridge view, top: every key at its physical position, tinted by current travel, with the note it plays now
(transposition and held sharp modifiers included) or its control role. Bottom: a piano over the mapped range. Held
notes are lit by velocity, notes ringing on the sustain pedal are shaded, and each piano key carries the computer
key(s) that play it at the current transposition. "C3" etc. mark the octaves.
"""
from __future__ import annotations

import collections
import curses
import time

from .bridge import NOTE_NAMES, note_name
from .viz import BLOCKS, level, setup_colors

BLACK = {1, 3, 6, 8, 10}
RING_S = 5.0  # show a pedal-sustained note this long after its key was released (the piano tone has decayed)
(P_WHITE, P_WHITE_DIM, P_BLACK, P_BLACK_DIM, P_RING, P_RING_BLACK, P_DIM,
 P_RIGHT, P_LEFT, P_ACCOMP, P_WANT, P_WRONG, P_HIT, P_GRID) = range(20, 34)


def setup_piano_colors():
    c256 = curses.COLORS >= 256
    pick = (lambda a, b: a) if c256 else (lambda a, b: b)
    pairs = {
        P_WHITE: (curses.COLOR_BLACK, pick(231, curses.COLOR_WHITE)),
        P_WHITE_DIM: (pick(240, curses.COLOR_BLACK), pick(250, curses.COLOR_WHITE)),
        P_BLACK: (curses.COLOR_WHITE, pick(238, curses.COLOR_BLACK)),
        P_BLACK_DIM: (pick(244, curses.COLOR_WHITE), pick(233, curses.COLOR_BLACK)),
        P_RING: (curses.COLOR_BLACK, pick(116, curses.COLOR_CYAN)),
        P_RING_BLACK: (curses.COLOR_WHITE, pick(30, curses.COLOR_CYAN)),
        P_DIM: (pick(244, curses.COLOR_WHITE), -1),
        # trainer
        P_RIGHT: (curses.COLOR_BLACK, pick(77, curses.COLOR_GREEN)),  # right-hand notes: green
        P_LEFT: (curses.COLOR_WHITE, pick(33, curses.COLOR_BLUE)),  # left-hand notes: blue
        P_ACCOMP: (pick(250, curses.COLOR_WHITE), pick(237, curses.COLOR_BLACK)),  # auto-played parts: grey
        P_WANT: (curses.COLOR_BLACK, pick(220, curses.COLOR_YELLOW)),  # expected now: yellow
        P_WRONG: (curses.COLOR_WHITE, pick(160, curses.COLOR_RED)),  # wrong key: red
        P_HIT: (pick(22, curses.COLOR_GREEN), pick(151, curses.COLOR_WHITE)),  # already hit: pale
        P_GRID: (pick(238, curses.COLOR_WHITE), -1),
    }
    for p, (fg, bg) in pairs.items():
        curses.init_pair(p, fg, bg)


def put(scr, y, x, s, attr=0):
    h, w = scr.getmaxyx()
    if 0 <= y < h and 0 <= x < w - 1 and s:
        if x < 0:
            s, x = s[-x:], 0
        try:
            scr.addnstr(y, x, s, w - 1 - x, attr)
        except curses.error:
            pass


class PianoGeom:
    """Column layout of a piano over [lo, hi] (widened to whole octaves) for a screen `width` columns wide."""

    def __init__(self, lo: int, hi: int, width: int, x0: int = 1):
        lo, hi = max(0, lo), min(127, hi)
        self.lo = lo - lo % 12
        self.hi = min(127, hi + 11 - hi % 12)
        self.whites = [n for n in range(self.lo, self.hi + 1) if n % 12 not in BLACK]
        self.W = max(2, min(5, (width - x0 - 2) // max(1, len(self.whites))))
        self.bw = self.W - 1 if self.W >= 3 else 1
        x0 = max(x0, (width - len(self.whites) * self.W) // 2)  # centre the keyboard
        self.pos = {n: x0 + i * self.W for i, n in enumerate(self.whites)}

    def span(self, n: int) -> tuple[int, int] | None:
        """(x, width) of the note's column above the keyboard (for falling notes)."""
        if n in self.pos:
            return self.pos[n] + 1, self.W - 1
        if n + 1 in self.pos and n % 12 in BLACK:
            return self.pos[n + 1] - self.bw // 2, self.bw
        return None


def draw_piano(scr, y, g: PianoGeom, labels: dict[int, str], attr_for) -> int:
    """Draw the piano at row y; attr_for(note, is_black) -> curses attr. Returns the last row used."""
    for n in g.whites:
        a = attr_for(n, False)
        lab = labels.get(n, "")[:g.W - 1]
        for r in range(4):
            put(scr, y + r, g.pos[n], "│" + (lab.ljust(g.W - 1) if r == 3 else " " * (g.W - 1)), a)
        if n % 12 == 0:
            put(scr, y + 4, g.pos[n], note_name(n), curses.A_BOLD)
    if g.whites:
        for r in range(4):
            put(scr, y + r, g.pos[g.whites[-1]] + g.W, "│", attr_for(g.whites[-1], False))
    for n in range(g.lo, g.hi + 1):
        if n % 12 not in BLACK or n + 1 not in g.pos:
            continue
        xb = g.pos[n + 1] - g.bw // 2
        lab = labels.get(n, "")[:g.bw]
        a = attr_for(n, True)
        put(scr, y, xb, " " * g.bw, a)
        put(scr, y + 1, xb, lab.center(g.bw), a)
    return y + 4


def base_attr(n, black, mapped):
    if black:
        return curses.color_pair(P_BLACK if n in mapped else P_BLACK_DIM)
    return curses.color_pair(P_WHITE if n in mapped else P_WHITE_DIM)


def key_labels(br) -> dict[int, str]:
    """note -> computer key names that play it now (no sharp modifier)."""
    labels: dict[int, str] = {}
    for idx, base in br.notes.items():
        n = base + br.transpose
        labels[n] = labels.get(n, "") + br.key_names[idx]
    return labels


def roles_for(br) -> dict[int, str]:
    roles = {i: "note" for i in br.notes}
    roles.update({i: ("+1" if d > 0 else "-1") for i, d in br.xpose_keys.items()})
    roles.update({i: "×12" for i in br.shift_idx})
    roles.update({i: f"♯ {h[0].upper()}" for i, h in br.sharp_of.items()})
    roles.update({i: n.lower() for i, n in br.extra.items()})
    if br.sus_idx is not None:
        roles[br.sus_idx] = "pedal (inverted)" if br.inverted else "pedal"
    if br.quit_idx is not None:
        roles[br.quit_idx] = "quit"
    return roles


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

    def tick(self, now, br):
        while self.scr.getch() != -1:  # swallow typed input (with --no-grab)
            pass
        if now - self.last_draw < 1 / 30:
            return
        self.last_draw = now
        scr = self.scr
        h, w = scr.getmaxyx()
        scr.erase()
        tonic = (self.cfg["base_note"] + br.transpose) % 12
        scale = self.cfg["scale"].replace("_", " ") if self.cfg["layout"] != "piano" else ""
        put(scr, 0, 0, f" {self.dev.TITLE} → MIDI | layout {self.cfg['layout']} | key {NOTE_NAMES[tonic]} {scale} "
                       f"(transpose {br.transpose:+d}) | sustain {'ON' if br.sustain else 'off'} | "
                       f"{self.cfg['quit_key']} quits ", curses.A_BOLD)
        bottom = self._keyboard(2, w, br)
        ring = {n for n, t in br.ringing.items() if now - t < RING_S}
        held = {}
        for idx, n in br.playing.items():
            held[n] = max(held.get(n, 0), br.vel.get(idx, 64))
        cur = {br.note_for(i) for i in br.notes}
        g = PianoGeom(min(cur | set(held) | ring), max(cur | set(held) | ring), w)
        labels = key_labels(br)

        def attr_for(n, black):
            if n in held:
                return curses.color_pair(1 + level(held[n], 127)) | curses.A_BOLD
            if n in ring:
                return curses.color_pair(P_RING_BLACK if black else P_RING)
            return base_attr(n, black, labels)

        y = draw_piano(scr, bottom + 1, g, labels, attr_for) + 1
        put(scr, y, 0, " lit = held (colour = velocity), cyan = ringing on the pedal, labels = computer keys ",
            curses.A_DIM)
        put(scr, y + 1, 0, " recent:", curses.A_BOLD)
        for i, m in enumerate(self.msgs):
            if y + 2 + i >= h:
                break
            put(scr, y + 2 + i, 1, m)
        scr.refresh()

    def _keyboard(self, top, w, br) -> int:
        mx = self.th.full
        max_x = max(k["x"] + k["width"] for k in self.keys)
        sx = (w - 2) / max_x
        bottom = top
        for k in self.keys:
            idx = k["index"]
            x0 = 1 + int(k["x"] * sx)
            y0 = top + int(round(k["y"] * 3))
            kw = max(3, int(k["width"] * sx) - 1)
            d = br.depth.get(idx, 0)
            role = self.roles.get(idx)
            if role == "note":
                n = br.playing.get(idx)
                sub = note_name(n if n is not None else br.note_for(idx))
                if n is not None and idx in br.vel:
                    sub = f"{sub} {br.vel[idx]}"
            else:
                sub = role or ""
            if not role and not d:
                attr = curses.color_pair(P_DIM)  # unused key
            else:
                attr = curses.color_pair(1 + level(d, mx)) | (curses.A_BOLD if idx in br.playing else 0)
            if not sub and d:  # unused key pressed: show travel as a bar
                cells = kw * min(d, mx) / mx
                full = int(cells)
                sub = "█" * full + (BLOCKS[int((cells - full) * 8)] if full < kw else "")
            put(self.scr, y0, x0, k["name"][:kw].ljust(kw), attr)
            put(self.scr, y0 + 1, x0, sub[:kw].ljust(kw), attr)
            bottom = max(bottom, y0 + 2)
        return bottom
