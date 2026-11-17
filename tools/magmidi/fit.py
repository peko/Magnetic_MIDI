"""Fit a score onto the note layout: choose the transposition and the computer key for every note."""
from __future__ import annotations

import dataclasses

from .score import Score

ROW_PRIO = {}  # canonical key -> preference among duplicates (home < bottom < upper)
for _row, _p in (("ASDFGHJKL;'", 0), ("ZXCVBNM,./", 1), ("QWERTYUIOP[]", 2)):
    for _c in _row:
        ROW_PRIO[_c] = _p


@dataclasses.dataclass
class Target:
    pitch: int  # what the player must sound (score pitch, octave-folded into reach if needed)
    key: str | None  # device key name, None if unreachable
    sharp: bool  # needs the hand's sharp modifier (LAlt / RAlt)
    folded: int  # octaves moved to bring it into reach (0 = as written)


def reach(cfg: dict, transpose: int) -> dict[int, list[tuple]]:
    """pitch -> [(prio, hand, key, sharp)] for the layout at this transposition."""
    from .layouts import canonical

    sharp_hands = set((cfg.get("sharp_keys") or {}).values())
    out: dict[int, list[tuple]] = {}
    for name, off in cfg["notes"].items():
        hand = (cfg.get("hands") or {}).get(name, "right")
        p = cfg["base_note"] + off + transpose
        prio = ROW_PRIO.get(canonical(name) or "", 3)
        out.setdefault(p, []).append((prio, hand, name, False))
        if hand in sharp_hands:
            out.setdefault(p + 1, []).append((prio + 10, hand, name, True))
    return out


def pick(cands, hand):
    """Best candidate: the note's own hand first, then plain over sharp, then home/bottom/upper row."""
    return min(cands, key=lambda c: (c[1] != hand, c[0])) if cands else None


def choose_transpose(score: Score, cfg: dict) -> int:
    """Tonic of the score onto the layout's tonic, then the octave that reaches most notes in the right hand."""
    tonic, _mode = score.detect_key()
    t0 = (tonic - cfg["base_note"]) % 12
    t0 -= 12 if t0 > 6 else 0
    best = None
    for k in range(-3, 4):
        t = t0 + 12 * k
        r = reach(cfg, t)
        val = 0
        for n in score.notes:
            c = pick(r.get(n.pitch, []), n.hand)
            if c:
                val += 3 if (c[1] == n.hand and not c[3]) else 2 if c[1] == n.hand else 1
        cand = (val, -abs(k), t)
        best = max(best, cand) if best else cand
    return best[2]


# Search order for an unreachable pitch: exact in its own hand, an octave away in its own hand, exact in the
# other hand, then further folds.
SEARCH = [(True, 0), (True, 12), (True, -12), (False, 0), (True, 24), (True, -24), (False, 12), (False, -12),
          (False, 24), (False, -24), (False, 36), (False, -36)]


def assign(score: Score, cfg: dict, transpose: int) -> list[Target]:
    r = reach(cfg, transpose)
    out = []
    for n in score.notes:
        for own, fold in SEARCH:
            cands = [c for c in r.get(n.pitch + fold, []) if c[1] == n.hand or not own]
            c = pick(cands, n.hand)
            if c:
                out.append(Target(n.pitch + fold, c[2], c[3], fold // 12))
                break
        else:
            out.append(Target(n.pitch, None, False, 0))
    return out
