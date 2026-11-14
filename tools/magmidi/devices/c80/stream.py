"""Live per-key travel stream via the 'trigger test' mode (cmd 0x21, sub 0x02/0x03).

Events: (row, col, travel) where travel is in 0.01 mm (0..~340 on the C80).
Packets are emitted by the keyboard only when a key's travel changes (~1 ms granularity).
"""
from __future__ import annotations

import time

from .transport import C80, packet

N_COLS = 22
N_ROWS = 6


def key_mask(indices) -> bytes:
    """22-byte mask; bit `row` of byte `col` enables key index row*22+col."""
    mask = bytearray(N_COLS)
    for i in indices:
        mask[i % N_COLS] |= 1 << (i // N_COLS)
    return bytes(mask)


class TravelStream:
    HEARTBEAT_S = 2.0

    def __init__(self, kb: C80, indices=None):
        self.kb = kb
        self.indices = list(indices) if indices is not None else range(N_ROWS * N_COLS)
        self._last_hb = 0.0

    def __enter__(self):
        self.kb.drain()
        self.kb.send(packet(0x21, length=24, data=[0x02, *key_mask(self.indices)]))
        self._last_hb = time.monotonic()
        return self

    def __exit__(self, *_):
        try:
            self.kb.send(packet(0x21, length=24, data=[0x03]))
            time.sleep(0.05)
            self.kb.drain()
        except OSError:
            pass

    def events(self, timeout: float = 0.05):
        """Yield (t, index, travel). Yields (t, None, None) on idle timeout so callers can tick."""
        while True:
            now = time.monotonic()
            if now - self._last_hb > self.HEARTBEAT_S:
                self.kb.send(packet(0x01))  # same keepalive the web driver sends
                self._last_hb = now
            p = self.kb.recv(timeout)
            t = time.monotonic()
            if p is None:
                yield t, None, None
                continue
            if p[0] == 0x21 and p[5] == 0x01 and len(p) >= 10:
                yield t, p[6] * N_COLS + p[7], p[9] << 8 | p[8]
