# Magnetic MIDI

Reverse-engineered tools for Hall-effect (magnetic) keyboards: read per-key analog travel live and turn the
keyboard into a velocity-sensitive MIDI controller.

| device | id | protocol | travel stream | docs |
|---|---|---|---|---|
| CIDOO C80 | `2e3c:c368`, fw `QK75EHEARGB V3.22.00` | illumipc white-label (usage page 0xFF1B) | cmd `0x21` trigger test, 0.01 mm, ~1 ms | [docs/c80](docs/c80/) |
| MonsGeek FUN68 HE | `3151:5030`, dev_id 2811, fw 0x0504 | RongYuan RY5088 (usage page 0xFFFF, feature reports) | cmd `0x1B` depth report, 0–720 raw, ~1.4 ms | [docs/fun68](docs/fun68/) |

## Layout
- `tools/magmidi/` — shared core: `midi.py` (MIDI bridge), `viz.py` (live TUI), `velocity.py` (strike model),
  `paths.py`; device backends in `devices/<name>/` (`spec.py` = common interface, plus transport, stream,
  layout, keymap, and `light.py` for the C80).
- `tools/scripts/c80/` — C80 research scripts (probe, raw stream logger, evdev cross-check, plugin keymap generator,
  SDK harness).
- `plugin/c80/` — Wooting Analog SDK plugin for the C80 (Rust, C ABI); see `plugin/c80/README.md`.
- `docs/<device>/` — USB/HID descriptors, vendor protocol, sources. `captures/<device>/` — logged streams and backups.
- `vendor/<device>/` — third-party snapshots, treat as data: `c80/webdriver/` (official C80 web driver, do not run it),
  `fun68/` (monsgeek-akko-linux protocol doc + FUN68 DB extracts, GPL-3.0; ry5088-flasher docs, MIT; see its README).

## Setup
```sh
python -m venv .venv && .venv/bin/pip install hidapi python-rtmidi evdev pyyaml jsbeautifier
```
`viz.py` and the keymap tools need only the standard library. `/dev/hidraw*` must be readable and writable
(udev: `KERNEL=="hidraw*", ATTRS{idVendor}=="2e3c|3151", TAG+="uaccess"`, or one rule per vendor), and grabbing
the keyboard needs the `input` group.

## Usage
`--device` defaults to `auto` (the first connected keyboard); pass `c80` or `fun68` to choose.
```sh
python3 tools/viz.py [--device fun68]                              # live TUI: travel per key + strike velocity
PYTHONPATH=tools .venv/bin/python -m magmidi.midi -v               # virtual MIDI port named after the device
PYTHONPATH=tools .venv/bin/python -m magmidi.midi --light         # note keys lit for the session, restored on exit
PYTHONPATH=tools python3 -m magmidi.devices.c80.keymap dump [--changed] [-o km.yaml]   # read-only
PYTHONPATH=tools python3 -m magmidi.devices.c80.keymap set fn J F13   # remap one key (backup + verify)
PYTHONPATH=tools python3 -m magmidi.devices.c80.light show -v      # C80 lighting (read-only)
PYTHONPATH=tools python3 -m magmidi.devices.fun68.keymap dump [--changed] [--raw] [--profile N]  # read-only
PYTHONPATH=tools python3 -m magmidi.devices.fun68.light show [-v]  # FUN68 LED params + userpic slots (read-only)
.venv/bin/python tools/scripts/c80/probe_readonly.py              # C80 firmware id, status, trigger config
.venv/bin/python tools/scripts/c80/stream_probe.py trigger 20     # C80 raw travel log -> captures/c80/
python3 tools/scripts/depth_probe.py [--device fun68] 40          # record travel, per-key maxima + cadence (calibration)
```
`magmidi.midi` grabs the keyboard's evdev nodes so it doesn't type while you play (`--no-grab` disables this);
Esc on the keyboard quits. Connect the port with `aconnect` or pick it in your DAW. `--config file.yaml` overrides
`velocity.DEFAULTS`, `midi.COMMON` and the device's `spec.DEFAULTS` (note map by layout key name; thresholds
`vel_lo` / `vel_hi` / `release` as fractions of `full_travel`).

## Safety
Each transport refuses commands that reset or brick the keyboard and, by default, allows only verified ones:
- C80 (`devices/c80/transport.py`): blocks `0x0B` (bootloader) and `0x14` (reset / factory reset).
- FUN68 (`devices/fun68/transport.py`): blocks `0x01` (factory reset), `0x7F` (bootloader, wipes config), `0xC5`,
  `0x1C`/`0x1E` (calibration), `0x30`/`0x31`. The only writes allowed are `0x07` (LED params) and `0x0C` (userpic),
  each with range-checked arguments; `--light` uses userpic slot 4 and restores the LED params on exit. Never request FUN68 keymatrix layers > 3 (no bounds check in firmware).

Firmware work is research-only for now.
