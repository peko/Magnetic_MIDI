"""Raw hidraw transport for the CIDOO C80 vendor interface (usage page 0xFF1B, report ID 1).

Packets are 63 bytes of payload; on the wire (hidraw) they are prefixed by report ID 0x01.
Layout reverse-engineered from the official web driver (cidoo.illumipc.com, v2 app.js):
    [0] cmd  [1] flag/sub  [2..3] page (BE)  [4] len  [5..] data
"""
from __future__ import annotations

import glob
import os
import select
import time

VID, PID_RANGE = 0x2E3C, range(0xC365, 0xC369)
USAGE_PAGE = 0xFF1B
REPORT_ID = 1
PAYLOAD = 63

# Commands that are known-safe to send. Anything else is refused unless allow_unsafe=True.
# Explicitly dangerous (never in this list): 0x0B enter bootloader, 0x14 reset / factory reset.
SAFE_CMDS = {
    0x01,  # heartbeat / device status
    0x0D,  # identify product (CSV string)
    0x15,  # serial number
    0x21,  # trigger: sub 0x02 open test / 0x03 close test / 0x04 get config / 0x05 read key
    0x23,  # ADC stream: data[0] (byte 5) = 1 open, 0 close
}
DANGEROUS_CMDS = {0x0B: "enter bootloader", 0x14: "reset / factory reset"}
# Commands that also write (to flash), allowed only with the listed flag bytes (the read variants).
READ_ONLY_FLAGS = {
    0x18: {0x80, 0x82},  # keymap: 0x80 read default layer, 0x82 read Fn layer (0/1 would write)
    0x07: {0x01},  # lighting config read (flag 0 = write)
    0x09: {0x20, 0x80, 0x81},  # custom light: 0x20 current layer, 0x80/0x81 read colours (0/1 = write)
    0x0A: {0x00},  # lighting mode list
    0x0E: {0x00},  # Fn-locked key mask
}


def find_hidraw() -> str:
    """Return /dev/hidrawN of the C80 vendor interface."""
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = open(f"{node}/device/uevent").read()
            desc = open(f"{node}/device/report_descriptor", "rb").read()
        except OSError:
            continue
        if f"HID_ID=0003:{VID:08X}:" not in uevent:
            continue
        pid = int(uevent.split(f"HID_ID=0003:{VID:08X}:")[1][:8], 16)
        # Usage Page (Vendor) item: 06 1B FF
        if pid in PID_RANGE and desc.startswith(b"\x06\x1b\xff"):
            return "/dev/" + os.path.basename(node)
    raise FileNotFoundError("CIDOO C80 vendor hidraw interface not found")


def packet(cmd: int, *, flag: int = 0, page: int = 0, length: int = 0, data: bytes | list[int] = b"") -> bytes:
    p = bytearray(PAYLOAD)
    p[0], p[1], p[2], p[3], p[4] = cmd, flag, page >> 8, page & 0xFF, length
    p[5 : 5 + len(data)] = bytes(data)
    return bytes(p)


class C80:
    def __init__(self, path: str | None = None, allow_unsafe: bool = False):
        self.path = path or find_hidraw()
        self.allow_unsafe = allow_unsafe
        self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def send(self, pkt: bytes):
        assert len(pkt) == PAYLOAD
        cmd = pkt[0]
        if cmd in DANGEROUS_CMDS:
            raise PermissionError(f"refusing dangerous command 0x{cmd:02X} ({DANGEROUS_CMDS[cmd]})")
        if cmd in READ_ONLY_FLAGS and pkt[1] in READ_ONLY_FLAGS[cmd]:
            pass
        elif cmd not in SAFE_CMDS and not self.allow_unsafe:
            raise PermissionError(f"command 0x{cmd:02X} not in SAFE_CMDS; pass allow_unsafe=True")
        os.write(self.fd, bytes([REPORT_ID]) + pkt)

    def recv(self, timeout: float = 0.5) -> bytes | None:
        """Return one 63-byte payload (report ID stripped) or None on timeout."""
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        buf = os.read(self.fd, 128)
        if buf and buf[0] == REPORT_ID and len(buf) >= PAYLOAD + 1:
            return buf[1 : PAYLOAD + 1]
        return buf  # unexpected shape; return raw for inspection

    def drain(self, timeout: float = 0.05):
        while self.recv(timeout) is not None:
            pass

    def request(self, pkt: bytes, match=None, timeout: float = 1.0, collect: bool = False, idle: float = 0.3):
        """Send pkt and wait for reply(ies). match(p)->bool filters replies (default: same cmd)."""
        match = match or (lambda p: p[0] == pkt[0])
        self.send(pkt)
        out, deadline = [], time.monotonic() + timeout
        while time.monotonic() < deadline:
            p = self.recv(idle if (collect and out) else max(0.0, deadline - time.monotonic()))
            if p is None:
                break
            if match(p):
                if not collect:
                    return p
                out.append(p)
        return out if collect else None


def hexdump(p: bytes) -> str:
    return " ".join(f"{b:02x}" for b in p)
