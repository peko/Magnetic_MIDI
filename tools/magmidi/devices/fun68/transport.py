"""hidraw transport for the MonsGeek FUN68 HE vendor interfaces (RongYuan RY5088 platform).

Config interface (USB interface 2, usage page 0xFFFF / usage 0x02): 64-byte Feature reports, report ID 0.
    SET_FEATURE: [cmd, a1..a6, chk, payload...]  chk makes sum(bytes[0..7]) == 0xFF (Bit7);
                 LED SET commands 0x07/0x08 use Bit8 instead: sum(bytes[0..8]) == 0xFF. Their GETs 0x87/0x88 use Bit7
                 (with Bit8 the keyboard rejects the request and GET returns the request buffer).
    GET_FEATURE: reply, byte 0 echoes cmd (GET_MULTI_MAGNETISM 0xE5 replies without an echo).
Event interface (USB interface 1, usage page 0xFFFF / usage 0x01): input report ID 5, 31 bytes.
    05 1B lo hi idx   key depth (only while SET_MAGNETISM_REPORT 0x1B is on)

Protocol source: github.com/echtzeit-solutions/monsgeek-akko-linux docs/PROTOCOL.md and
github.com/dot-agi/ry5088-flasher docs/. See docs/protocol.md.
"""
from __future__ import annotations

import fcntl
import glob
import os
import select
import time

VID, PID = 0x3151, 0x5030  # shared by many RY5088 models; the model is the dev_id from GET_USB_VERSION 0x8F
REPORT_LEN = 64
DEV_FUN68 = 2811  # MonsGeek FUN68 HE (ry5088_akko_fun68_8k_8k_3m)
DEV_MARS68 = 2431  # CAROTMAS Mars68 PRO (not in the monsgeek-akko-linux device DB)

# Opcodes that are known-safe. Anything else is refused unless allow_unsafe=True.
# Explicitly dangerous: 0x01 SET_RESET (factory reset), 0x7F ENTER_BOOTLOADER (erases config),
# 0xC5 ISP_PREPARE, 0x1C/0x1E calibration (overwrites stored calibration), 0x30/0x31 OLED bootloader.
SAFE_CMDS = {
    0x1B,  # SET_MAGNETISM_REPORT: runtime on/off of key-depth reports (no flash)
    0x80, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x8C, 0x8F, 0x90, 0x91, 0x97,
    0xD0, 0xE5, 0xE6, 0xFE,  # GET_* reads
}
DANGEROUS_CMDS = {
    0x01: "factory reset",
    0x7F: "enter bootloader (wipes config)",
    0xC5: "ISP prepare",
    0x1C: "min calibration",
    0x1E: "max calibration",
    0x30: "OLED bootloader",
    0x31: "OLED boot start",
}
# Writes allowed without allow_unsafe, each only with arguments inside these bounds (the firmware does not
# bounds-check chunked writes). Both persist to flash.
#   0x07 SET_LEDPARAM [mode speed brightness option R G B]   mode 0-25, speed 0-4, brightness 0-4
#   0x0C SET_USERPIC  [slot FF page len last 0] + rgb         slot 0-4, page 0-6, len <= 56, last 0/1
CHECKED_WRITES = {
    0x07: lambda p: p[1] <= 25 and p[2] <= 4 and p[3] <= 4,
    0x0C: lambda p: p[1] <= 4 and p[2] == 0xFF and p[3] <= 6 and p[4] <= 56 and p[5] in (0, 1),
}
BIT8_CMDS = {0x07, 0x08}  # SET_LEDPARAM / SET_SLEDPARAM only; their GETs (0x87/0x88) use Bit7


def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


def HIDIOCSFEATURE(n: int) -> int:
    return _ioc(3, 0x06, n)


def HIDIOCGFEATURE(n: int) -> int:
    return _ioc(3, 0x07, n)


def find_hidraw(usage: int) -> str:
    """Return /dev/hidrawN of the vendor collection 0xFFFF/`usage` (2 = config, 1 = events)."""
    want = bytes([0x06, 0xFF, 0xFF, 0x09, usage])
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = open(f"{node}/device/uevent").read()
            desc = open(f"{node}/device/report_descriptor", "rb").read()
        except OSError:
            continue
        if f"HID_ID=0003:{VID:08X}:{PID:08X}" in uevent and want in desc:
            return "/dev/" + os.path.basename(node)
    raise FileNotFoundError(f"MonsGeek {VID:04x}:{PID:04x} vendor hidraw (usage {usage}) not found")


def packet(cmd: int, *args: int, payload: bytes | list[int] = b"") -> bytes:
    p = bytearray(REPORT_LEN)
    p[0] = cmd
    p[1 : 1 + len(args)] = bytes(args)
    if payload:
        p[8 : 8 + len(payload)] = bytes(payload)
    if cmd in BIT8_CMDS:
        p[8] = 0xFF - (sum(p[0:8]) & 0xFF)
    else:
        p[7] = 0xFF - (sum(p[0:7]) & 0xFF)
    return bytes(p)


def boards() -> list[dict]:
    """Connected RY5088 keyboards: [{"usb", "config", "events", "dev_id", "fw"}], grouped by USB device."""
    found: dict[str, dict] = {}
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = open(f"{node}/device/uevent").read()
            desc = open(f"{node}/device/report_descriptor", "rb").read()
        except OSError:
            continue
        if f"HID_ID=0003:{VID:08X}:{PID:08X}" not in uevent:
            continue
        usb = os.path.dirname(os.path.dirname(os.path.realpath(f"{node}/device")))  # .../X-Y (USB device)
        b = found.setdefault(usb, {"usb": usb, "config": None, "events": None, "dev_id": None, "fw": None})
        dev = "/dev/" + os.path.basename(node)
        if bytes([0x06, 0xFF, 0xFF, 0x09, 0x02]) in desc:
            b["config"] = dev
        elif bytes([0x06, 0xFF, 0xFF, 0x09, 0x01]) in desc:
            b["events"] = dev
    out = []
    for b in found.values():
        if not (b["config"] and b["events"]):
            continue
        try:
            with FUN68(b["config"]) as kb:
                r = kb.query(packet(0x8F))  # GET_USB_VERSION (read-only)
            if r:
                b["dev_id"], b["fw"] = r[1] | r[2] << 8, r[7] | r[8] << 8
        except OSError:
            pass
        out.append(b)
    return out


def find_board(dev_id: int | None = None) -> dict:
    bs = [b for b in boards() if dev_id is None or b["dev_id"] == dev_id]
    if not bs:
        what = f"dev_id {dev_id}" if dev_id is not None else "any model"
        raise FileNotFoundError(f"RY5088 keyboard {VID:04x}:{PID:04x} ({what}) not found")
    return bs[0]


class FUN68:
    """Config-interface client for RY5088 keyboards (FUN68, Mars68, ...). Pass dev_id to pick the model."""

    def __init__(self, path: str | None = None, allow_unsafe: bool = False, dev_id: int | None = None):
        self.events_path = None
        if path is None:
            b = find_board(dev_id)
            path, self.events_path = b["config"], b["events"]
        self.path = path
        self.allow_unsafe = allow_unsafe
        self.fd = os.open(self.path, os.O_RDWR)

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def send(self, pkt: bytes):
        assert len(pkt) == REPORT_LEN
        cmd = pkt[0]
        if cmd in DANGEROUS_CMDS:
            raise PermissionError(f"refusing dangerous command 0x{cmd:02X} ({DANGEROUS_CMDS[cmd]})")
        if cmd in CHECKED_WRITES:
            if not CHECKED_WRITES[cmd](pkt):
                raise PermissionError(f"command 0x{cmd:02X} arguments out of range: {hexdump(pkt[:8])}")
        elif cmd not in SAFE_CMDS and not self.allow_unsafe:
            raise PermissionError(f"command 0x{cmd:02X} not in SAFE_CMDS; pass allow_unsafe=True")
        buf = bytearray([0]) + pkt
        fcntl.ioctl(self.fd, HIDIOCSFEATURE(len(buf)), buf)

    def get(self) -> bytes:
        buf = bytearray(REPORT_LEN + 1)
        fcntl.ioctl(self.fd, HIDIOCGFEATURE(len(buf)), buf, True)
        return bytes(buf[1:])

    def query(self, pkt: bytes, echo: bool = True, tries: int = 4, delay: float = 0.01) -> bytes | None:
        """SET then GET; retry the GET until byte 0 echoes the command (hidraw may return a stale reply)."""
        self.send(pkt)
        for _ in range(tries):
            time.sleep(delay)
            r = self.get()
            if not echo or r[0] == pkt[0]:
                return r
            delay *= 2
        return None


class Events:
    """Reader for the vendor input interface (report ID 5)."""

    def __init__(self, path: str | None = None):
        self.path = path or find_hidraw(1)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def recv(self, timeout: float = 0.5) -> bytes | None:
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        return os.read(self.fd, 64)

    def drain(self):
        while self.recv(0) is not None:
            pass


def hexdump(p: bytes) -> str:
    return " ".join(f"{b:02x}" for b in p)
