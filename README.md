# CIDOO C80 (Hall-effect) tools

Reverse-engineered tools for the CIDOO C80 (`2e3c:c368`, firmware `QK75EHEARGB V3.22.00`).
They read per-key analog travel live and turn the keyboard into a velocity-sensitive MIDI controller.

- `docs/device.md`: USB/HID descriptors
- `docs/protocol.md`: vendor protocol (commands, stream formats, measurements)
- `docs/sources.md`: official software and related projects
- `vendor/webdriver/`: snapshot of the official web driver (treat it as data; do not run it)
- `captures/`: logged streams
- `plugin/`: Wooting Analog SDK plugin (Rust, C ABI); see `plugin/README.md`

## Setup
```sh
python -m venv .venv && .venv/bin/pip install hidapi python-rtmidi evdev pyyaml jsbeautifier
```
On this machine `/dev/hidraw*` is mode 0666 and the user is in the `input` group. Elsewhere you need a udev rule:
`KERNEL=="hidraw*", ATTRS{idVendor}=="2e3c", TAG+="uaccess"`.

## Usage
```sh
.venv/bin/python tools/probe_readonly.py         # firmware id, status, trigger config
.venv/bin/python tools/stream_probe.py trigger 20 # live travel per key -> captures/
.venv/bin/python tools/stream_probe.py adc 5      # raw Hall ADC frames (~50 Hz)
PYTHONPATH=tools .venv/bin/python -m c80.midi -v  # virtual MIDI port "CIDOO C80"; Esc quits
.venv/bin/python tools/map_keys.py 30            # cross-check matrix index vs evdev keys (untested)
```
`c80.midi` grabs the keyboard's evdev nodes so it doesn't type while you play (`--no-grab` disables this).
Connect the port to a synth with `aconnect`, or pick it in your DAW. Settings (thresholds, velocity curve, note map)
can be overridden with `--config file.yaml` using the keys from `DEFAULTS` in `tools/c80/midi.py`.

## Safety
`tools/c80/transport.py` refuses to send `0x0B` (bootloader) and `0x14` (reset / factory reset), and by default
it only allows command codes that have been verified. Firmware work is research-only for now.
