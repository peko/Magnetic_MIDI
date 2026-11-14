"""Repository paths shared by all devices."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
VENDOR_C80 = ROOT / "vendor/c80/webdriver"
C80_LAYOUT_JSON = VENDOR_C80 / "config/keys/QK75EHEARGB.json"


def captures(device: str) -> pathlib.Path:
    d = ROOT / "captures" / device
    d.mkdir(parents=True, exist_ok=True)
    return d
