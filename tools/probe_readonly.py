"""Read-only probe: identify, serial, status, trigger config. Sends no write/config commands."""
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from c80 import C80, hexdump, packet  # noqa: E402

with C80() as kb:
    print("device:", kb.path)
    kb.drain()

    for name, pkt, kw in [
        ("identify 0x0D", packet(0x0D), dict(collect=True)),
        ("serial 0x15", packet(0x15), {}),
        ("status 0x01", packet(0x01), {}),
        ("trigger cfg 0x21/04", packet(0x21, length=24, data=[0x04]), dict(match=lambda p: p[0] == 0x21 and p[5] == 4)),
    ]:
        r = kb.request(pkt, **kw)
        print(f"\n== {name}")
        for p in (r if isinstance(r, list) else [r]):
            if p is None:
                print("  (no reply)")
                continue
            print("  ", hexdump(p))
            if name.startswith(("identify", "serial")):
                n = p[4]
                print("   text:", p[5 : 5 + n].decode(errors="replace"))
        time.sleep(0.05)
