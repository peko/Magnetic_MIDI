"""Live per-key depth stream (SET_MAGNETISM_REPORT 0x1B).

Enable with [1B 01], disable with [1B 00] on the config interface. While enabled, the keyboard sends
input reports `05 1B lo hi idx` on the vendor event interface; depth = hi<<8 | lo (raw units),
idx = matrix index (col*6 + row, see layout.py).
"""
from __future__ import annotations

import time

from .transport import FUN68, Events, packet


REENABLE_S = 1.0


class DepthStream:
    def __init__(self, kb: FUN68, ev: Events | None = None):
        self.kb = kb
        self.ev = ev or Events(getattr(kb, "events_path", None))
        self.n_other = 0
        self.last_report = self.last_enable = time.monotonic()

    def __enter__(self):
        self.ev.drain()
        self.kb.send(packet(0x1B, 1))
        return self

    def __exit__(self, *_):
        try:
            self.kb.send(packet(0x1B, 0))
        except OSError:
            pass
        self.ev.close()

    def events(self, timeout: float = 0.05):
        """Yield (t, index, depth). Yields (t, None, None) on idle timeout so callers can tick.

        The report switch is one flag for the whole keyboard: another client (viz.py, a second bridge) turns it off
        for everyone when it exits. So after REENABLE_S without reports it is switched on again (a runtime flag,
        not written to flash)."""
        while True:
            p = self.ev.recv(min(timeout, REENABLE_S))
            t = time.monotonic()
            if p is None:
                if t - self.last_report > REENABLE_S and t - self.last_enable > REENABLE_S:
                    try:
                        self.kb.send(packet(0x1B, 1))
                    except OSError:
                        pass
                    self.last_enable = t
                yield t, None, None
                continue
            self.last_report = t
            if len(p) >= 5 and p[0] == 0x05 and p[1] == 0x1B:
                yield t, p[4], p[3] << 8 | p[2]
            elif len(p) >= 4 and p[0] == 0x1B:  # report-ID-less form, seen by other drivers
                yield t, p[3], p[2] << 8 | p[1]
            else:
                self.n_other += 1
