"""Live per-key depth stream (SET_MAGNETISM_REPORT 0x1B).

Enable with [1B 01], disable with [1B 00] on the config interface. While enabled, the keyboard sends
input reports `05 1B lo hi idx` on the vendor event interface; depth = hi<<8 | lo (raw units),
idx = matrix index (col*6 + row, see layout.py).
"""
from __future__ import annotations

import time

from .transport import FUN68, Events, packet


class DepthStream:
    def __init__(self, kb: FUN68, ev: Events | None = None):
        self.kb = kb
        self.ev = ev or Events()
        self.n_other = 0

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
        """Yield (t, index, depth). Yields (t, None, None) on idle timeout so callers can tick."""
        while True:
            p = self.ev.recv(timeout)
            t = time.monotonic()
            if p is None:
                yield t, None, None
                continue
            if len(p) >= 5 and p[0] == 0x05 and p[1] == 0x1B:
                yield t, p[4], p[3] << 8 | p[2]
            elif len(p) >= 4 and p[0] == 0x1B:  # report-ID-less form, seen by other drivers
                yield t, p[3], p[2] << 8 | p[1]
            else:
                self.n_other += 1
