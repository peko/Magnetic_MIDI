"""Strike velocity model shared by all devices.

Velocity = time to travel from `vel_lo` to `vel_hi`, mapped logarithmically between `fast_ms` (→127) and
`slow_ms` (→1). Thresholds are fractions of `full_travel` (raw depth at bottom-out); devices set their own
values in their spec DEFAULTS.
"""
from __future__ import annotations

import math

DEFAULTS = {
    "full_travel": 340,
    "vel_lo": 0.12,
    "vel_hi": 0.60,
    "release": 0.35,
    "fast_ms": 4.0,
    "slow_ms": 200.0,
}


def velocity(dt_ms: float, fast: float, slow: float) -> int:
    if dt_ms <= fast:
        return 127
    if dt_ms >= slow:
        return 1
    x = (math.log(slow) - math.log(dt_ms)) / (math.log(slow) - math.log(fast))
    return max(1, min(127, round(1 + 126 * x)))


class Thresholds:
    """Absolute thresholds from cfg fractions; `grow(v)` raises full travel when a deeper value is seen."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.full = cfg["full_travel"]
        self._set()

    def _set(self):
        c = self.cfg
        self.lo, self.hi, self.rel = c["vel_lo"] * self.full, c["vel_hi"] * self.full, c["release"] * self.full

    def grow(self, v: int) -> bool:
        if v > self.full:
            self.full = v
            self._set()
            return True
        return False


class KeyTracker:
    """Per-key strike state machine (timing starts crossing lo, note-on at hi, note-off below release)."""

    __slots__ = ("t_lo", "on", "prev", "depth")

    def __init__(self):
        self.t_lo: float | None = None
        self.on = False
        self.prev = self.depth = 0

    def update(self, t: float, v: int, th: Thresholds, fast: float, slow: float):
        """Return ("on", velocity, dt_ms), ("off",) or None."""
        ev = None
        self.depth = v
        if not self.on:
            if self.prev < th.lo <= v or (self.t_lo is None and th.lo <= v < th.hi and self.prev == 0):
                self.t_lo = t
            if v < th.lo:
                self.t_lo = None
            if v >= th.hi:
                dt = (t - self.t_lo) * 1000 if self.t_lo is not None else 0.0
                self.on, self.t_lo = True, None
                ev = ("on", velocity(dt, fast, slow), dt)
        elif v < th.rel:
            self.on = False
            ev = ("off",)
        self.prev = v
        return ev
