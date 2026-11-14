"""Exercise the plugin through the real Wooting Analog SDK (libwooting_analog_sdk.so) via ctypes.

usage: sdk_harness.py /path/to/libwooting_analog_sdk.so [seconds]
The SDK loads plugins from /usr/local/share/WootingAnalogPlugins/<subdir>/*.so.
"""
import ctypes as C
import sys
import time

lib = C.CDLL(sys.argv[1])
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 15


class DeviceInfo(C.Structure):
    _fields_ = [("vendor_id", C.c_uint16), ("product_id", C.c_uint16),
                ("manufacturer_name", C.c_char_p), ("device_name", C.c_char_p),
                ("device_id", C.c_uint64), ("device_type", C.c_int)]


lib.wooting_analog_initialise.restype = C.c_int
lib.wooting_analog_version.restype = C.c_int
lib.wooting_analog_get_connected_devices_info.argtypes = [C.POINTER(C.POINTER(DeviceInfo)), C.c_uint]
lib.wooting_analog_read_full_buffer.argtypes = [C.POINTER(C.c_uint16), C.POINTER(C.c_float), C.c_uint]
lib.wooting_analog_read_analog.argtypes = [C.c_uint16]
lib.wooting_analog_read_analog.restype = C.c_float

print("SDK version:", lib.wooting_analog_version())
n = lib.wooting_analog_initialise()
print("initialise ->", n, "(>=0 = number of devices)")
infos = (C.POINTER(DeviceInfo) * 8)()
cnt = lib.wooting_analog_get_connected_devices_info(infos, 8)
print("devices:", cnt)
for i in range(max(0, cnt)):
    d = infos[i].contents
    print(f"  {d.manufacturer_name.decode()} / {d.device_name.decode()} vid={d.vendor_id:04x} "
          f"pid={d.product_id:04x} id={d.device_id:#x} type={d.device_type}")

codes = (C.c_uint16 * 64)()
vals = (C.c_float * 64)()
t0, polls, seen, peak = time.monotonic(), 0, {}, {}
while time.monotonic() - t0 < secs:
    k = lib.wooting_analog_read_full_buffer(codes, vals, 64)
    polls += 1
    if k < 0:
        print("read_full_buffer error", k)
        time.sleep(0.5)
        continue
    for i in range(k):
        seen[codes[i]] = seen.get(codes[i], 0) + 1
        peak[codes[i]] = max(peak.get(codes[i], 0.0), vals[i])
    time.sleep(0.001)
print(f"polls={polls}; keys seen (HID usage: samples, peak value):")
for c in sorted(seen):
    print(f"  0x{c:02X}: {seen[c]:5d}  peak {peak[c]:.3f}")
print("read_analog(Esc 0x29) =", lib.wooting_analog_read_analog(0x29))
print("uninitialise ->", lib.wooting_analog_uninitialise())
